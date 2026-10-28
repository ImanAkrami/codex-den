"""Editor launch contracts: no shell evaluation and no global environment mutation."""

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .errors import DenError


@dataclass
class LaunchPlan:
    executable: str
    argv: list[str]
    cwd: Path
    environment: dict[str, str]
    environment_id: str
    frontend: str

    def public(self):
        return {
            "executable": self.executable,
            "argv": self.argv,
            "cwd": str(self.cwd),
            "codex_home": self.environment["CODEX_HOME"],
            "frontend": self.frontend,
            "environment_id": self.environment_id,
        }


def resolve_executable(command: str) -> str:
    path = shutil.which(command)
    if not path:
        raise DenError(
            f"Editor executable not found: {command}. Set executables.vscode or executables.cursor in Settings."
        )
    if not os.access(path, os.X_OK):
        raise DenError("Selected editor is not executable. Choose a working editor in Settings.")
    # Recognize common AppImage wrappers without executing them or shell expansion.
    try:
        with Path(path).open("rb") as stream:
            script = stream.read(65536).decode(errors="replace")
        if script.startswith("#!"):
            targets = re.findall(r"(?:\$\{HOME\}|\$HOME|~)/[^\s\"\']+\.AppImage", script)
            for target in targets:
                expanded = target.replace("${HOME}", str(Path.home())).replace(
                    "$HOME", str(Path.home())
                )
                if not Path(expanded).expanduser().exists():
                    raise DenError(
                        "Selected editor wrapper references a missing AppImage. Choose a working installed editor executable in Settings."
                    )
    except OSError:
        pass
    return path


def validate_editor_args(arguments: list[str]):
    owned = ("--user-data-dir", "--extensions-dir", "--profile")
    for argument in arguments:
        flag = argument.partition("=")[0]
        if "\x00" in argument:
            raise DenError("Editor arguments cannot contain NUL characters.")
        if flag.startswith("--") and any(
            option.startswith(flag) or flag == option for option in owned
        ):
            raise DenError("Editor arguments cannot override managed profile or state paths.")


def execute(plan: LaunchPlan):
    try:
        result = subprocess.run(
            [plan.executable, *plan.argv],
            cwd=plan.cwd,
            env=plan.environment,
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise DenError(
            "Could not launch the editor. Check its executable path and permissions with doctor."
        ) from error
    if result.returncode:
        raise DenError(
            f"Editor launch exited with status {result.returncode}. Run doctor and verify the executable path.",
            exit_code=result.returncode if result.returncode > 0 else 128 - result.returncode,
        )


def child_environment(codex_home: Path) -> dict[str, str]:
    # Editor IPC inherited from an integrated terminal can route into its old instance.
    inherited = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("VSCODE_", "CURSOR_")) and key != "ELECTRON_RUN_AS_NODE"
    }
    if getattr(sys, "frozen", False):
        # The bundle's libraries belong to this process, not external editors.
        if "LD_LIBRARY_PATH_ORIG" in inherited:
            inherited["LD_LIBRARY_PATH"] = inherited["LD_LIBRARY_PATH_ORIG"]
        else:
            inherited.pop("LD_LIBRARY_PATH", None)
    return {**inherited, "CODEX_HOME": str(codex_home)}
