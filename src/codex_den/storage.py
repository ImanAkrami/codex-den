"""Private, atomic, process-locked state, separated from existing launchers."""

import copy
import fcntl
import json
import math
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .errors import DenError, PublicationError


def overlaps(left: Path, right: Path) -> bool:
    left, right = left.resolve(), right.resolve()
    return left == right or left in right.parents or right in left.parents


def _registered_home(root: Path, inherited: Path) -> bool:
    try:
        relative = inherited.relative_to(root)
        parts = relative.parts
        if len(parts) != 3 or parts[0] != "environments" or parts[2] != "codex-home":
            return False
        if str(uuid.UUID(parts[1])) != parts[1]:
            return False
        registry = root / "registry.json"
        if registry.is_symlink():
            return False
        value = json.loads(registry.read_text())
        return (
            type(value.get("schema_version")) is int
            and value["schema_version"] == 1
            and value["environments"][parts[1]]["id"] == parts[1]
        )
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        return False


def protect_path(path: Path, managed_root: Path | None = None) -> Path:
    path = path.expanduser().resolve()
    home = Path.home().resolve()
    protected = [home / p for p in (".codex", ".vscode", ".cursor", ".local/share/vscode-codex")]
    protected += [home / ".local/bin", home / ".vscode-insiders"]
    config_roots = {
        home / ".config",
        Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")).expanduser().resolve(),
    }
    for config_root in config_roots:
        protected.extend(config_root / name for name in ("Code", "Code - Insiders", "Cursor"))
    if os.environ.get("CODEX_HOME"):
        inherited = Path(os.environ["CODEX_HOME"]).expanduser().resolve()
        if managed_root is None or not _registered_home(managed_root.resolve(), inherited):
            protected.append(inherited)
    if any(overlaps(path, legacy) for legacy in protected):
        raise DenError(
            "Storage path overlaps an existing Codex/editor home or launcher; choose a separate path."
        )
    return path


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise DenError("Refusing to replace a symlinked state file.")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            directory = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as error:
            raise PublicationError(
                f"Change to {path} was applied, but storage could not confirm durability. Inspect the current state before retrying.",
                exit_code=1,
            ) from error
    finally:
        Path(temporary).unlink(missing_ok=True)


def atomic_json(path: Path, value: dict) -> None:
    atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


@contextmanager
def lock_file(path: Path, timeout: float = 5):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise DenError(
                        "State is busy. Wait for the other operation and retry."
                    ) from None
                time.sleep(0.01)
        yield
    finally:
        os.close(fd)


class Store:
    def __init__(self, root: Path):
        self.root = protect_path(root, managed_root=root.expanduser().resolve())
        self.registry = self.root / "registry.json"

    def path(self, relative: str) -> Path:
        candidate = self.root / relative
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(self.root):
            raise DenError("Managed path escapes storage or is a symlink.")
        for parent in candidate.parents:
            if parent == self.root:
                break
            if parent.is_symlink():
                raise DenError("Managed storage contains a symlink; repair it before continuing.")
        return candidate

    def read(self) -> dict:
        self.path("registry.json")
        if not self.registry.exists():
            return {"schema_version": 1, "environments": {}, "workspaces": {}, "presets": {}}
        try:
            value = json.loads(self.registry.read_text())
            if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
                raise ValueError("unsupported schema")
            for key in ("environments", "workspaces", "presets"):
                if not isinstance(value.get(key), dict):
                    raise ValueError("invalid registry structure")
            from .config import validate

            def settings(item):
                if not isinstance(item, dict) or not isinstance(item.get("settings"), dict):
                    raise ValueError("invalid settings structure")
                for key, setting in item["settings"].items():
                    validate(key, setting)

            for identifier, environment in value["environments"].items():
                settings(environment)
                if (
                    str(uuid.UUID(identifier)) != identifier
                    or environment.get("id") != identifier
                    or not isinstance(environment.get("name"), str)
                ):
                    raise ValueError("invalid environment")
            for name, workspace in value["workspaces"].items():
                settings(workspace)
                path = workspace.get("path")
                if (
                    workspace.get("name") != name
                    or not isinstance(path, str)
                    or "\x00" in path
                    or not Path(path).is_absolute()
                    or workspace.get("environment") not in value["environments"]
                    or type(workspace.get("favorite")) is not bool
                ):
                    raise ValueError("invalid workspace")
                at = workspace.get("last_opened")
                if at is not None and (type(at) not in (int, float) or not math.isfinite(at)):
                    raise ValueError("invalid recent timestamp")
            for preset in value["presets"].values():
                settings(preset)
                if not isinstance(preset.get("files"), dict) or not all(
                    isinstance(data, str) for data in preset["files"].values()
                ):
                    raise ValueError("invalid preset")
            return value
        except (DenError, ValueError, TypeError, AttributeError, KeyError) as error:
            raise DenError(
                f"Invalid registry at {self.registry}. Restore a valid backup; it was not reset."
            ) from error

    @contextmanager
    def locked_read(self):
        if not self.registry.exists():
            yield self.read()
            return
        self.path(".lock")
        with lock_file(self.root / ".lock"):
            yield self.read()

    @contextmanager
    def transaction(self, on_abort=None):
        protect_path(self.root, managed_root=self.root)
        self.path(".lock")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with lock_file(self.root / ".lock"):
            state = copy.deepcopy(self.read())
            try:
                yield state
                try:
                    atomic_json(self.registry, state)
                except PublicationError as error:
                    error.registry_committed = True
                    raise
            except BaseException as error:
                if on_abort is not None and not getattr(error, "registry_committed", False):
                    on_abort()
                raise
