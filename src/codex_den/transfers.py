"""Selected, sanitized configuration snapshots and transactional transfers."""

import base64
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import time
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

import tomli_w

from .config import validate
from .errors import DenError
from .jsonc import loads as load_jsonc
from .storage import atomic_bytes, overlaps, protect_path

MAX_FILES = 2000
MAX_TOTAL = 32 * 1024 * 1024
MAX_FILE = 4 * 1024 * 1024
SENSITIVE = re.compile(
    r"(?i)(api[_-]?key|token|password|secret|credential|authorization|private[_-]?key)"
)
BLOCKED = {
    "auth.json",
    ".env",
    ".ssh",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "sessions",
    "logs",
    "cache",
    "caches",
    "history.jsonl",
    ".git",
    "node_modules",
}


def safe_relative(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in ("..", ".") for part in name.split("/"))
        or "\x00" in name
    ):
        raise DenError("Unsafe relative path in selection or bundle.")
    if any(
        part.lower() in BLOCKED
        or part.lower().startswith((".env", "id_rsa", "id_ed25519"))
        or part.lower().endswith((".pem", ".key", ".p12", ".pfx"))
        or SENSITIVE.search(part)
        or ".sqlite" in part.lower()
        for part in path.parts
    ):
        raise DenError(
            "Credentials, history and runtime state are excluded from configuration transfers."
        )
    return str(path)


def scrub(value):
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items() if not SENSITIVE.search(key)}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def sanitize(name: str, content: bytes) -> bytes:
    try:
        if name.endswith(".toml"):
            return tomli_w.dumps(scrub(tomllib.loads(content.decode()))).encode()
        if name.endswith(".json"):
            parser = (
                load_jsonc
                if name.endswith(("/User/settings.json", "/User/keybindings.json"))
                else json.loads
            )
            return (json.dumps(scrub(parser(content)), indent=2) + "\n").encode()
    except (ValueError, UnicodeDecodeError, TypeError) as error:
        raise DenError(
            f"Configuration cannot be safely parsed: {name}. Fix it before copying."
        ) from error
    return content


def selected_files(source: Path, selected: list[str]) -> dict[str, bytes]:
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise DenError("Import source must be an existing directory.")
    result, total = {}, 0

    def collect(relative):
        nonlocal total
        relative = safe_relative(relative)
        path = source / relative
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise DenError("Cannot copy symlinks or paths outside the selected source.")
        for parent in path.parents:
            if parent == source:
                break
            if parent.is_symlink():
                raise DenError("Cannot copy through a source symlink.")
        if path.is_dir():
            for child in sorted(path.iterdir()):
                try:
                    safe_relative(str(child.relative_to(source)))
                except DenError:
                    continue
                collect(str(child.relative_to(source)))
            return
        if not path.is_file() or path.stat().st_size > MAX_FILE:
            raise DenError(
                "Selected item is missing, unsupported, or exceeds the 4 MiB file limit."
            )
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise DenError("Only regular configuration files can be copied.")
            content = stream.read(MAX_FILE + 1)
        if len(content) > MAX_FILE:
            raise DenError("Selected file exceeds the 4 MiB limit.")
        content = sanitize(relative, content)
        if len(content) > MAX_FILE:
            raise DenError("Normalized configuration exceeds the 4 MiB file limit.")
        result[relative] = content
        total += len(content)
        if len(result) > MAX_FILES or total > MAX_TOTAL:
            raise DenError("Configuration selection exceeds the transfer size limit.")

    for relative in selected:
        collect(relative)
    return result


def encode_files(files):
    return {name: base64.b64encode(content).decode() for name, content in files.items()}


def decode_files(files):
    result = {}
    for name, content in files.items():
        safe_relative(name)
        editor_settings = {
            f"editors/{editor}/user-data/User/{filename}"
            for editor in ("vscode", "cursor")
            for filename in ("settings.json", "keybindings.json")
        }
        if (
            name != "extensions.json"
            and not name.startswith("codex-home/")
            and name not in editor_settings
        ):
            raise DenError("Unsupported bundle destination.")
        result[name] = sanitize(name, base64.b64decode(content, validate=True))
    return result


def remap_files(files, mappings, require_mappings):
    from pathlib import PureWindowsPath

    paths, unresolved, result = {}, set(), {}
    for source, target in mappings.items():
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or not Path(target).is_absolute()
            or not Path(target).exists()
        ):
            raise DenError(
                "Path mappings need a source and an existing absolute local destination."
            )
    for name, content in files.items():
        if not name.endswith((".toml", ".json")):
            result[name] = content
            continue
        value = tomllib.loads(content.decode()) if name.endswith(".toml") else json.loads(content)
        found = set()

        def replace(item):
            if isinstance(item, dict):
                mapped = {}
                for key, value in item.items():
                    new_key = replace(key)
                    if new_key in mapped:
                        raise DenError(
                            "Path mapping would produce duplicate configuration keys; choose distinct destinations."
                        )
                    mapped[new_key] = replace(value)
                return mapped
            if isinstance(item, list):
                return [replace(value) for value in item]
            if isinstance(item, str) and (
                Path(item).is_absolute() or PureWindowsPath(item).is_absolute()
            ):
                found.add(item)
                if item not in mappings:
                    unresolved.add(item)
                    return item
                return mappings[item]
            return item

        mapped = replace(value)
        if found:
            paths[name] = sorted(found)
        result[name] = (
            tomli_w.dumps(mapped).encode()
            if name.endswith(".toml")
            else (json.dumps(mapped, indent=2) + "\n").encode()
        )
    if require_mappings and unresolved:
        raise DenError(
            "Bundle contains machine-specific paths. Preview it and provide --map SOURCE=DEST for each path before import."
        )
    return result, paths, sorted(unresolved)


class TransferOperations:
    def snapshot(self, name, state=None):
        if state is None:
            with self.store.locked_read() as locked_state:
                return self.snapshot(name, locked_state)
        environment = self.environment(name, state)
        if self.is_active(environment["id"]):
            raise DenError(
                "Environment is active; close its editors before taking a configuration snapshot."
            )
        root = self.environment_path(environment)
        files = {}
        selections = [
            relative
            for relative in (
                "codex-home/config.toml",
                "codex-home/AGENTS.md",
                "codex-home/instructions.md",
                "codex-home/skills",
                "editors/vscode/user-data/User/settings.json",
                "editors/vscode/user-data/User/keybindings.json",
                "editors/cursor/user-data/User/settings.json",
                "editors/cursor/user-data/User/keybindings.json",
                "extensions.json",
            )
            if (root / relative).exists() or (root / relative).is_symlink()
        ]
        files = selected_files(root, selections)
        settings = {
            key: value
            for key, value in environment["settings"].items()
            if not key.startswith("executables.")
        }
        return {"settings": settings, "files": encode_files(files)}

    def _populate(self, environment, files):
        root = self.environment_path(environment)
        for name, content in decode_files(files).items():
            target = self.store.path(str((root / name).relative_to(self.store.root)))
            atomic_bytes(target, content)

    def _create_snapshot(self, name, snapshot, settings=None):
        created = None
        try:
            with self.store.transaction() as state:
                created = self._new_environment(
                    state, name, {**snapshot["settings"], **(settings or {})}
                )
                self._populate(created, snapshot["files"])
            return created
        except BaseException as error:
            if created and not getattr(error, "registry_committed", False):
                shutil.rmtree(self.environment_path(created), ignore_errors=True)
            raise

    def clone_environment(self, source, name):
        return self._create_snapshot(name, self.snapshot(source))

    def save_preset(self, name, environment):
        self.validate_name(name)
        snapshot = self.snapshot(environment)
        with self.store.transaction() as state:
            if name in state["presets"]:
                raise DenError("Preset already exists; delete it explicitly before replacing it.")
            state["presets"][name] = {**snapshot, "created": time.time()}
        return {"name": name, "settings": snapshot["settings"], "files": list(snapshot["files"])}

    def delete_preset(self, name):
        with self.store.transaction() as state:
            if name not in state["presets"]:
                raise DenError("Preset not found.")
            del state["presets"][name]

    def compare(self, source, destination, source_preset=False, destination_preset=False):
        with self.store.locked_read() as state:
            return self._compare_locked(
                source, destination, source_preset, destination_preset, state
            )

    def _compare_locked(self, source, destination, source_preset, destination_preset, state):

        def get(name, preset):
            if not preset:
                return self.snapshot(name, state)
            if name not in state["presets"]:
                raise DenError("Preset not found.")
            return state["presets"][name]

        left, right = get(source, source_preset), get(destination, destination_preset)
        changes = {"settings": {}, "files": {}}
        for key in sorted(left["settings"].keys() | right["settings"].keys()):
            if left["settings"].get(key) != right["settings"].get(key):
                changes["settings"][key] = {
                    "from": left["settings"].get(key),
                    "to": right["settings"].get(key),
                }
        old, new = decode_files(left["files"]), decode_files(right["files"])
        for name in sorted(old.keys() | new.keys()):
            if old.get(name) != new.get(name):
                changes["files"][name] = "".join(
                    difflib.unified_diff(
                        old.get(name, b"").decode(errors="replace").splitlines(True),
                        new.get(name, b"").decode(errors="replace").splitlines(True),
                        fromfile=f"{source}/{name}",
                        tofile=f"{destination}/{name}",
                    )
                )
        return changes

    def import_files(self, name, source, selected, dry_run=False, replace=False):
        environment = self.environment(name)
        root = self.environment_path(environment)
        source = Path(source).expanduser().resolve()
        if overlaps(source, root):
            raise DenError("Import source and destination overlap.")
        if not selected:
            raise DenError("Choose at least one file or folder with --include.")
        files = selected_files(source, selected)
        plan = [
            {"path": name, "bytes": len(content), "conflict": (root / "codex-home" / name).exists()}
            for name, content in files.items()
        ]
        for name in files:
            self.store.path(str((root / "codex-home" / name).relative_to(self.store.root)))
        if dry_run:
            return plan
        if self.is_active(environment["id"]):
            raise DenError("Environment is active; close its editors before importing settings.")
        staging = None
        preserve_staging = False
        changed, created_dirs = [], []

        def rollback():
            nonlocal preserve_staging
            try:
                for target, backup in reversed(changed):
                    # Keep the replacement until the original can atomically take its place.
                    if backup.exists():
                        os.replace(backup, target)
                    else:
                        target.unlink(missing_ok=True)
                for directory in reversed(created_dirs):
                    directory.rmdir()
            except OSError as error:
                preserve_staging = True
                raise DenError(
                    f"Import rollback could not finish. Original backups are preserved for recovery at {staging}.",
                    exit_code=1,
                ) from error

        try:
            with self.store.transaction(on_abort=rollback) as state:
                current = self.environment(environment["id"], state)
                if self.is_active(environment["id"]):
                    raise DenError(
                        "Environment is active; close its editors before importing settings."
                    )
                staging = Path(tempfile.mkdtemp(prefix=".import-", dir=self.store.root))
                for index, (relative, content) in enumerate(files.items()):
                    target = self.store.path(
                        str((root / "codex-home" / relative).relative_to(self.store.root))
                    )
                    if target.exists() and not replace:
                        continue
                    if target.exists() and not target.is_file():
                        raise DenError("Import destination is not a regular file.")
                    staged, backup = staging / f"new-{index}", staging / f"old-{index}"
                    atomic_bytes(staged, content)
                    missing, parent = [], target.parent
                    while not parent.exists():
                        missing.append(parent)
                        parent = parent.parent
                    for directory in reversed(missing):
                        directory.mkdir(mode=0o700)
                        created_dirs.append(directory)
                    if target.exists():
                        os.replace(target, backup)
                    changed.append((target, backup))
                    os.replace(staged, target)
                current.setdefault("imports", []).append(
                    {"at": time.time(), "files": [p["path"] for p in plan], "replaced": replace}
                )
        except BaseException as error:
            if getattr(error, "registry_committed", False):
                preserve_staging = True
            raise
        finally:
            if staging and not preserve_staging:
                shutil.rmtree(staging, ignore_errors=True)
        return plan

    def export_environment(self, name, output):
        snapshot = self.snapshot(name)
        files = decode_files(snapshot["files"])
        manifest = {
            "schema_version": 1,
            "settings": snapshot["settings"],
            "files": {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
        }
        manifest_bytes = json.dumps(manifest).encode()
        if len(manifest_bytes) > MAX_FILE:
            raise DenError(
                "Bundle manifest exceeds the file size limit; select a smaller snapshot."
            )
        output = protect_path(Path(output))
        if output.exists():
            raise DenError("Export destination already exists; choose a new file.")
        if overlaps(output, self.store.root):
            raise DenError("Export outside managed state to keep the bundle independent.")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", manifest_bytes)
            for path, content in files.items():
                archive.writestr(path, content)
        atomic_bytes(output, buffer.getvalue())
        return {
            "output": str(output),
            "files": list(files),
            "excluded": ["credentials", "history", "runtime state", "machine executable paths"],
        }

    def read_bundle(self, bundle, path_map=None, require_mappings=True):
        try:
            with zipfile.ZipFile(bundle) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                if (
                    len(entries) > MAX_FILES + 1
                    or len(names) != len(set(names))
                    or sum(
                        entry.file_size for entry in entries if entry.filename != "manifest.json"
                    )
                    > MAX_TOTAL
                ):
                    raise DenError("Bundle exceeds size limits or has duplicate entries.")
                for entry in entries:
                    if entry.file_size > MAX_FILE or stat.S_ISLNK(entry.external_attr >> 16):
                        raise DenError("Bundle contains an oversized file or symlink.")
                    if entry.filename != "manifest.json":
                        safe_relative(entry.filename)
                manifest = json.loads(archive.read("manifest.json"))
                if not isinstance(manifest, dict):
                    raise DenError("Invalid bundle manifest: expected an object.")
                if (
                    type(manifest.get("schema_version")) is not int
                    or manifest["schema_version"] != 1
                ):
                    raise DenError("Unsupported bundle schema.")
                if not isinstance(manifest.get("files"), dict) or not isinstance(
                    manifest.get("settings"), dict
                ):
                    raise DenError("Invalid bundle manifest: files and settings must be objects.")
                if set(names) != {"manifest.json", *manifest["files"]}:
                    raise DenError("Bundle integrity mismatch: unlisted or missing files.")
                for key, value in manifest["settings"].items():
                    validate(key, value)
                    if key.startswith("executables."):
                        raise DenError("Portable bundles cannot set local executable paths.")
                files = {}
                for relative, digest in manifest["files"].items():
                    content = archive.read(relative)
                    if hashlib.sha256(content).hexdigest() != digest:
                        raise DenError("Bundle integrity check failed; source was not imported.")
                    files[relative] = content
                mapped, paths, unresolved = remap_files(files, path_map or {}, require_mappings)
                snapshot = {
                    "settings": manifest["settings"],
                    "files": encode_files(mapped),
                    "machine_paths": paths,
                    "unresolved_paths": unresolved,
                }
                decode_files(snapshot["files"])
        except (
            zipfile.BadZipFile,
            KeyError,
            ValueError,
            TypeError,
            OSError,
            NotImplementedError,
            RuntimeError,
        ) as error:
            raise DenError("Invalid bundle. Check the file and its integrity manifest.") from error
        return snapshot

    def preview_bundle(self, bundle, path_map=None):
        snapshot = self.read_bundle(bundle, path_map, require_mappings=False)
        return {**snapshot, "files": list(snapshot["files"])}

    def import_environment(self, bundle, name, path_map=None):
        return self._create_snapshot(name, self.read_bundle(bundle, path_map))

    def detach_workspace(self, workspace, name, clone_settings=False):
        created = None
        try:
            with self.store.transaction() as state:
                original = self.workspace(workspace, state)
                if self.is_active(original["environment"]):
                    raise DenError("Environment is active; close its editors before detaching.")
                snapshot = (
                    self.snapshot(original["environment"], state)
                    if clone_settings
                    else {"settings": {}, "files": {}}
                )
                created = self._new_environment(state, name, snapshot["settings"])
                self._populate(created, snapshot["files"])
                original["environment"] = created["id"]
            return self.inspect(workspace)
        except BaseException as error:
            if created and not getattr(error, "registry_committed", False):
                shutil.rmtree(self.environment_path(created), ignore_errors=True)
            raise
