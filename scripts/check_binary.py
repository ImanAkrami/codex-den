"""Validate a real native executable with disposable data and terminal input."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pexpect


def check(executable):
    executable = executable.resolve()
    architecture = executable.name.rsplit("-", 1)[-1]
    notices = (executable.parent / f"THIRD_PARTY_NOTICES-linux-{architecture}.txt").read_text()
    assert "PYTHON SOFTWARE FOUNDATION LICENSE" in notices
    assert "System library: libexpat1" in notices
    assert "OpenSSL" in notices
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in notices
    with tempfile.TemporaryDirectory(prefix="codex-den-native-check-") as directory:
        root = Path(directory)
        tools = root / "bin"
        tools.mkdir()
        capture = root / "capture.txt"
        editor = tools / "cursor"
        editor.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$PWD" "$CODEX_HOME" "$LD_LIBRARY_PATH" '
            '"${VSCODE_IPC_HOOK_CLI-unset}" "${ELECTRON_RUN_AS_NODE-unset}" "$@" > "$CAPTURE"\n'
        )
        editor.chmod(0o700)
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("PYTHONPATH", "PYTHONHOME")
        }
        env.update(
            HOME=str(root / "home"),
            XDG_DATA_HOME=str(root / "data"),
            XDG_CONFIG_HOME=str(root / "config"),
            PATH=str(tools),
            CAPTURE=str(capture),
            CODEX_HOME=str(root / "unmanaged"),
            TERM="xterm-256color",
            NO_COLOR="1",
            LD_LIBRARY_PATH="/synthetic/system-libraries",
            VSCODE_IPC_HOOK_CLI="synthetic-routing",
            ELECTRON_RUN_AS_NODE="synthetic-routing",
        )

        def run(*arguments):
            result = subprocess.run(
                [str(executable), *arguments],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            return result.stdout

        run("--version")
        run("--help")
        json.loads(run("config", "show", "--json"))
        for action in ("update", "uninstall"):
            guidance = json.loads(run(action, "--json"))
            assert not guidance["automatic"]
            assert "uv tool" not in guidance["command"]
            assert "python" not in guidance["command"].lower()
        assert not (root / "home").exists()
        assert not (root / "data").exists()
        child = pexpect.spawn(
            str(executable),
            env=env,
            cwd=str(root),
            encoding="utf-8",
            dimensions=(40, 120),
            timeout=30,
        )
        try:
            child.expect("No workspaces here yet")
            child.send("s")
            child.expect("Useful defaults first")
            child.send("\r")
            child.expect("User defaults")
            child.send("\x1b")
            child.send("\t")
            child.send("\x1b")
            child.expect("No workspaces here yet")
            child.send("n")
            child.expect("Workspace name")
            child.send("\t")
            child.send("binary-check")
            child.send("\t\t\t\t\r")
            child.expect("Review the target")
            child.send("\x1b")
            child.expect("Workspace name")
            child.send("\x1b")
            child.expect("No workspaces here yet")
            child.send("\x0e")
            child.expect("Make yourself at home")
            child.send("\x1b")
            child.expect("No workspaces here yet")
            child.send("q")
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            if child.isalive():
                child.terminate(force=True)
        assert not (root / "data").exists()
        assert not capture.exists()
        repo = root / "repo with spaces"
        repo.mkdir()
        run("config", "set", "frontend", "cursor")
        run("config", "set", "executables.cursor", str(editor))
        run("workspace", "add", "repo", "--path", str(repo), "--json")
        extra = ["--new-window", "literal $(touch unintended)"]
        plan = json.loads(run("open", "repo", "--dry-run", "--json", "--", *extra))
        run("open", "repo", "--", *extra)
        lines = capture.read_text().splitlines()
        assert lines[:5] == [
            str(repo),
            plan["codex_home"],
            "/synthetic/system-libraries",
            "unset",
            "unset",
        ]
        assert lines[5:] == plan["argv"]
        assert not (repo / "unintended").exists()
        print(
            "Native CLI, PTY dashboard/settings/review/wizard, cancellation and fake-editor boundaries passed without Python/uv on PATH."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    check(parser.parse_args().executable)
