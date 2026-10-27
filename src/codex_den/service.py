"""Environment/workspace operations shared by CLI and terminal UI."""

import re
import shutil
import time
import uuid
from pathlib import Path

from .config import Configuration, validate
from .errors import DenError
from .launch import LaunchPlan, child_environment, execute, resolve_executable, validate_editor_args
from .storage import Store, overlaps
from .transfers import TransferOperations


class Service(TransferOperations):
    def __init__(self, store: Store, config: Configuration):
        self.store, self.config = store, config

    @staticmethod
    def validate_name(name):
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[\w][\w .-]{0,63}", name)
            or name.strip() != name
        ):
            raise DenError(
                "Names need 1–64 letters, numbers, spaces, dots, underscores or hyphens; start with a letter or number."
            )

    def inventory(self):
        return self.store.read()

    def environment(self, name, state=None):
        state = self.inventory() if state is None else state
        for identifier, environment in state["environments"].items():
            if identifier == name or environment.get("name") == name:
                try:
                    if str(uuid.UUID(identifier)) != identifier:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise DenError(
                        "Invalid environment identity in registry; restore a valid backup."
                    ) from None
                return environment
        raise DenError(
            f"Environment not found: {name}. Create one or choose an existing environment."
        )

    def workspace(self, name, state=None):
        state = self.inventory() if state is None else state
        try:
            return state["workspaces"][name]
        except KeyError:
            raise DenError(f"Workspace not found: {name}. Register its directory first.") from None

    def environment_path(self, environment):
        identifier = environment["id"]
        try:
            if str(uuid.UUID(identifier)) != identifier:
                raise ValueError()
        except (ValueError, TypeError):
            raise DenError("Invalid environment identity in registry.") from None
        return self.store.path(f"environments/{identifier}")

    def _new_environment(self, state, name, settings=None):
        self.validate_name(name)
        if any(item["name"] == name for item in state["environments"].values()):
            raise DenError("Environment name already exists; choose a different name.")
        for key, value in (settings or {}).items():
            validate(key, value)
        environment = {
            "id": str(uuid.uuid4()),
            "name": name,
            "settings": settings or {},
            "created": time.time(),
        }
        root = self.environment_path(environment)
        root.mkdir(parents=True, mode=0o700)
        try:
            for relative in (
                "codex-home",
                "editors/vscode/user-data",
                "editors/vscode/extensions",
                "editors/cursor/user-data",
                "editors/cursor/extensions",
            ):
                (root / relative).mkdir(parents=True, mode=0o700)
            state["environments"][environment["id"]] = environment
            return environment
        except BaseException:
            shutil.rmtree(root)
            raise

    def create_environment(self, name, settings=None, preset=None):
        created = None
        try:
            with self.store.transaction() as state:
                snapshot = state["presets"].get(preset) if preset else None
                if preset and snapshot is None:
                    raise DenError("Preset not found.")
                combined = {**(snapshot["settings"] if snapshot else {}), **(settings or {})}
                created = self._new_environment(state, name, combined)
                if snapshot:
                    self._populate(created, snapshot["files"])
            return created
        except BaseException as error:
            if created and not getattr(error, "registry_committed", False):
                shutil.rmtree(self.environment_path(created), ignore_errors=True)
            raise

    def add_workspace(self, name, path, environment=None):
        self.validate_name(name)
        path = Path(path).expanduser().resolve()
        if not path.is_dir():
            raise DenError("Workspace path must be an existing directory.")
        if overlaps(path, self.store.root):
            raise DenError(
                "Workspace and managed storage paths cannot overlap. Choose a separate repository directory."
            )
        created = None
        try:
            with self.store.transaction() as state:
                if name in state["workspaces"] or any(
                    item["path"] == str(path) for item in state["workspaces"].values()
                ):
                    raise DenError("Workspace name or canonical path is already registered.")
                if environment:
                    selected = self.environment(environment, state)
                else:
                    env_name = name
                    if any(item["name"] == name for item in state["environments"].values()):
                        env_name = f"{name[:50]}-{uuid.uuid4().hex[:6]}"
                    created = selected = self._new_environment(state, env_name)
                workspace = {
                    "name": name,
                    "path": str(path),
                    "environment": selected["id"],
                    "settings": {},
                    "favorite": False,
                    "last_opened": None,
                }
                state["workspaces"][name] = workspace
            return workspace
        except BaseException as error:
            if created and not getattr(error, "registry_committed", False):
                shutil.rmtree(self.environment_path(created), ignore_errors=True)
            raise

    def inspect(self, name):
        state = self.inventory()
        workspace = self.workspace(name, state)
        environment = self.environment(workspace["environment"], state)
        root = self.environment_path(environment)
        members = sorted(
            w["name"] for w in state["workspaces"].values() if w["environment"] == environment["id"]
        )
        return {
            "workspace": workspace,
            "environment": environment,
            "members": members,
            "codex_home": str(root / "codex-home"),
            "editors": {
                editor: {
                    "user_data": str(root / f"editors/{editor}/user-data"),
                    "extensions": str(root / f"editors/{editor}/extensions"),
                }
                for editor in ("vscode", "cursor")
            },
        }

    def settings(self, workspace=None, environment=None):
        state = self.inventory()
        item = self.workspace(workspace, state) if workspace else None
        selected = (
            self.environment(environment or item["environment"], state)
            if environment or item
            else None
        )
        return self.config.resolve(
            environment=selected.get("settings", {}) if selected else {},
            workspace=item.get("settings", {}) if item else {},
        )

    def set_setting(self, key, value=None, scope="user", target=None, reset=False):
        if scope == "user":
            return self.config.reset(key) if reset else self.config.save(key, value)
        if not target or scope not in ("workspace", "environment"):
            raise DenError(
                "Choose user scope, or an environment/workspace scope with an exact target."
            )
        if not reset:
            validate(key, value)
        else:
            validate(key, self.config.effective().get(key))
        with self.store.transaction() as state:
            item = (
                self.environment(target, state)
                if scope == "environment"
                else self.workspace(target, state)
            )
            identifier = item["id"] if scope == "environment" else item["environment"]
            if self.is_active(identifier):
                raise DenError(
                    "Environment is active; close its editor sessions before changing saved settings."
                )
            if reset:
                item["settings"].pop(key, None)
            else:
                item["settings"][key] = value

    def is_active(self, identifier):
        root = str(self.environment_path({"id": identifier}))
        for process in Path("/proc").glob("[0-9]*/cmdline"):
            try:
                arguments = process.read_bytes().split(b"\0")
                if any(root.encode() in argument for argument in arguments):
                    return True
            except (OSError, PermissionError):
                pass
        return False

    def switch_workspace(self, name, environment):
        with self.store.transaction() as state:
            workspace = self.workspace(name, state)
            selected = self.environment(environment, state)
            if self.is_active(workspace["environment"]) or self.is_active(selected["id"]):
                raise DenError(
                    "Environment is active; close its editor sessions before switching membership."
                )
            workspace["environment"] = selected["id"]
        return self.inspect(name)

    def favorite(self, name, enabled=True):
        with self.store.transaction() as state:
            self.workspace(name, state)["favorite"] = enabled

    def record_open(self, name, at=None):
        with self.store.transaction() as state:
            self.workspace(name, state)["last_opened"] = time.time() if at is None else at

    def recent(self):
        return sorted(
            (
                w
                for w in self.inventory()["workspaces"].values()
                if w.get("last_opened") is not None
            ),
            key=lambda w: (-w["last_opened"], w["name"]),
        )

    def clear_recent(self):
        with self.store.transaction() as state:
            for workspace in state["workspaces"].values():
                workspace["last_opened"] = None

    def discover(self, root, max_depth=3, exclude=None):
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            raise DenError("Discovery root must be an existing directory.")
        validate("discovery.max_depth", max_depth)
        excluded = {
            ".git",
            "node_modules",
            ".venv",
            ".cache",
            ".codex",
            ".vscode",
            ".cursor",
        } | set(exclude or [])
        registered = {w["path"] for w in self.inventory()["workspaces"].values()}
        result = []

        def scan(path, depth):
            if path == self.store.root or path.is_symlink():
                return
            if (path / ".git").exists():
                result.append(
                    {"name": path.name, "path": str(path), "registered": str(path) in registered}
                )
            if depth >= max_depth:
                return
            try:
                for child in sorted(path.iterdir()):
                    if child.name not in excluded and child.is_dir() and not child.is_symlink():
                        scan(child, depth + 1)
            except PermissionError:
                return

        scan(root, 0)
        return result

    def validated_editor_root(self, environment, frontend):
        root = self.environment_path(environment)
        for relative in (
            "codex-home",
            f"editors/{frontend}/user-data",
            f"editors/{frontend}/extensions",
        ):
            path = self.store.path(str((root / relative).relative_to(self.store.root)))
            if not path.is_dir():
                raise DenError("Environment state is missing. Restore it before using the editor.")
        return root

    def plan_open(self, name, frontend=None, environment=None, extra=None, state=None):
        state = self.inventory() if state is None else state
        workspace = self.workspace(name, state)
        selected = self.environment(environment or workspace["environment"], state)
        values = self.config.effective(
            environment=selected["settings"], workspace=workspace["settings"]
        )
        frontend = frontend or values["frontend"]
        validate("frontend", frontend)
        executable = resolve_executable(values[f"executables.{frontend}"])
        extra = extra or []
        validate_editor_args(extra)
        path = Path(workspace["path"])
        if not path.is_dir():
            raise DenError(
                "Workspace directory is missing. Relocate its registration before opening."
            )
        root = self.validated_editor_root(selected, frontend)
        argv = [
            "--user-data-dir",
            str(root / f"editors/{frontend}/user-data"),
            "--extensions-dir",
            str(root / f"editors/{frontend}/extensions"),
            str(path),
            *extra,
        ]
        environment_variables = child_environment(root / "codex-home")
        return LaunchPlan(executable, argv, path, environment_variables, selected["id"], frontend)

    def open(self, name, frontend=None, environment=None, extra=None):
        self.workspace(name)  # Reject unknown registrations without initializing storage.
        with self.store.transaction() as state:
            plan = self.plan_open(name, frontend, environment, extra, state=state)
            execute(plan)
            self.workspace(name, state)["last_opened"] = time.time()
        return plan.public()

    def remove_workspace(self, name):
        with self.store.transaction() as state:
            workspace = self.workspace(name, state)
            if self.is_active(workspace["environment"]):
                raise DenError("Environment is active; close its editor sessions first.")
            del state["workspaces"][name]

    def remove_environment(self, name):
        root = trash = None

        def restore():
            if trash and trash.exists() and root and not root.exists():
                try:
                    trash.rename(root)
                except OSError as error:
                    raise DenError(
                        f"Environment removal was not committed. Recovery data is preserved at {trash}.",
                        exit_code=1,
                    ) from error

        with self.store.transaction(on_abort=restore) as state:
            selected = self.environment(name, state)
            if any(w["environment"] == selected["id"] for w in state["workspaces"].values()):
                raise DenError(
                    "Environment still has registered workspaces; reassign or unregister them first."
                )
            if self.is_active(selected["id"]):
                raise DenError("Environment is active; close its editor sessions first.")
            root = self.environment_path(selected)
            if any(overlaps(root, Path(w["path"])) for w in state["workspaces"].values()):
                raise DenError(
                    "Environment storage overlaps a registered repository. Relocate the workspace before removal."
                )
            trash = self.store.path(f".removed-{selected['id']}")
            if root.exists():
                root.rename(trash)
            del state["environments"][selected["id"]]
        if trash and trash.exists():
            shutil.rmtree(trash)

    def doctor(self):
        values = self.config.effective()
        editors = []
        for name in ("vscode", "cursor"):
            executable = shutil.which(values[f"executables.{name}"])
            warnings = []
            if executable:
                try:
                    with Path(executable).open("rb") as stream:
                        content = stream.read(65536)
                    if b"AppImage" in content:
                        warnings.append(
                            "AppImage wrapper detected; verify its target exists. Use an explicit installed editor path if shadowed."
                        )
                except OSError:
                    pass
            editors.append(
                {
                    "frontend": name,
                    "executable": executable,
                    "available": bool(executable),
                    "warnings": warnings,
                }
            )
        return {
            "data_root": str(self.store.root),
            "config": str(self.config.path),
            "editors": editors,
            "state_policy": "Managed environments are separate from existing editor installations.",
            "runtime_validation": "Actual extension home, account isolation, and process reuse require real-editor checks.",
        }

    def setup_workspace(self, name, path, frontend, executable, environment=None, preset=None):
        validate("frontend", frontend)
        resolve_executable(executable)
        path = Path(path).expanduser().resolve()
        if not path.is_dir():
            raise DenError("Choose an existing workspace directory.")
        state = self.inventory()
        if name in state["workspaces"]:
            workspace = self.workspace(name, state)
            if workspace["path"] != str(path):
                raise DenError("Workspace name is already registered at another path.")
            if environment and self.environment(environment)["id"] != workspace["environment"]:
                raise DenError("Use workspace switch to change an existing association.")
        elif preset:
            if environment:
                raise DenError(
                    "Presets create new environments; they cannot overwrite a shared one."
                )
            created = self.create_environment(name, preset=preset)
            try:
                workspace = self.add_workspace(name, path, created["id"])
            except BaseException as error:
                if not getattr(error, "registry_committed", False):
                    self.remove_environment(created["id"])
                raise
        else:
            workspace = self.add_workspace(name, path, environment)
        self.config.save("frontend", frontend)
        self.config.save(f"executables.{frontend}", executable)
        return workspace

    def install_codex_extension(self, environment, frontend=None):
        from .storage import atomic_json

        with self.store.transaction() as state:
            selected = self.environment(environment, state)
            if self.is_active(selected["id"]):
                raise DenError(
                    "Environment is active; close its editors before installing the extension."
                )
            values = self.config.effective(environment=selected["settings"])
            frontend = frontend or values["frontend"]
            validate("frontend", frontend)
            root = self.validated_editor_root(selected, frontend)
            argv = [
                "--user-data-dir",
                str(root / f"editors/{frontend}/user-data"),
                "--extensions-dir",
                str(root / f"editors/{frontend}/extensions"),
                "--install-extension",
                "openai.chatgpt",
            ]
            plan = LaunchPlan(
                resolve_executable(values[f"executables.{frontend}"]),
                argv,
                root,
                child_environment(root / "codex-home"),
                selected["id"],
                frontend,
            )
            execute(plan)
            atomic_json(root / "extensions.json", ["openai.chatgpt"])
        return {
            "environment": selected["name"],
            "frontend": frontend,
            "extension": "openai.chatgpt",
            "editor_launched": False,
        }
