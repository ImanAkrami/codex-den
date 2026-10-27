"""Installer uses argv safely, preserves user state, and stays package scoped."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "install.sh"


@pytest.fixture
def installer(tmp_path):
    home = tmp_path / "home"
    tools = tmp_path / "bin"
    tools.mkdir()
    capture = tmp_path / "uv-call.json"
    uv = tools / "uv"
    uv.write_text(
        f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\nPath(os.environ['INSTALL_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\nsys.exit(int(os.environ.get('INSTALL_STATUS','0')))\n"
    )
    uv.chmod(0o700)
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{tools}:/usr/bin:/bin",
        "INSTALL_CAPTURE": str(capture),
    }

    def run(*args, input=None):
        return subprocess.run(
            ["sh", str(SCRIPT), *args],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
            input=input,
        )

    return run, capture, home, env


def test_installer_local_source_spaces_and_arguments_are_literal(installer):
    run, capture, home, _ = installer
    result = run("--source", str(PROJECT), "--python", "3.13")
    assert result.returncode == 0, result.stderr
    assert json.loads(capture.read_text()) == ["tool", "install", "--python", "3.13", str(PROJECT)]
    assert not home.exists()
    assert "codex-den setup" in result.stdout


def test_installer_ref_and_update_are_package_scoped(installer):
    run, capture, _, _ = installer
    result = run("--ref", "v0.1.0a1", "--update")
    assert result.returncode == 0, result.stderr
    assert json.loads(capture.read_text()) == [
        "tool",
        "install",
        "--python",
        "3.12",
        "--force",
        "git+https://github.com/ImanAkrami/codex-den.git@v0.1.0a1",
    ]


def test_installer_uninstall_preserves_data_and_never_starts_editor(installer):
    run, capture, home, _ = installer
    home.mkdir()
    retained = home / "keep-config"
    retained.write_text("unchanged")
    result = run("--uninstall")
    assert result.returncode == 0, result.stderr
    assert json.loads(capture.read_text()) == ["tool", "uninstall", "codex-den"]
    assert retained.read_text() == "unchanged"


@pytest.mark.parametrize("args", [("--help",), ("--dry-run",), ("--uninstall", "--dry-run")])
def test_installer_preview_and_help_are_write_free(installer, args):
    run, capture, home, _ = installer
    result = run(*args)
    assert result.returncode == 0, result.stderr
    assert not capture.exists()
    assert not home.exists()


@pytest.mark.parametrize(
    "args",
    [
        ("--unknown",),
        ("--source",),
        ("--ref", "--bogus"),
        ("--source", "/missing"),
        ("--ref", "x;touch sentinel"),
        ("--source", str(PROJECT), "--ref", "main"),
        ("--uninstall", "--update"),
    ],
)
def test_installer_invalid_options_fail_before_mutation(installer, args):
    run, capture, home, _ = installer
    result = run(*args)
    assert result.returncode != 0
    assert not capture.exists()
    assert not home.exists()


def test_installer_propagates_package_manager_failure(installer):
    run, capture, _, env = installer
    env["INSTALL_STATUS"] = "7"
    result = run("--source", str(PROJECT))
    assert result.returncode == 7
    assert "installed successfully" not in result.stdout.lower()
    assert capture.exists()


def test_installer_passes_shell_metacharacters_in_source_path_literally(installer, tmp_path):
    run, capture, _, _ = installer
    source = tmp_path / "source with spaces $(touch unexpected)"
    (source / "src/codex_den").mkdir(parents=True)
    (source / "pyproject.toml").write_text('[project]\nname="codex-den"\n')
    (source / "src/codex_den/__init__.py").write_text("")
    result = run("--source", str(source))
    assert result.returncode == 0, result.stderr
    assert json.loads(capture.read_text())[-1] == str(source)
    assert not (tmp_path / "unexpected").exists()


def test_actual_installer_update_and_uninstall_in_isolated_tool_home(tmp_path):
    import shutil

    checkout = tmp_path / "source checkout"
    checkout.mkdir()
    shutil.copytree(PROJECT / "src", checkout / "src", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "README.md", "LICENSE", "install.sh"):
        shutil.copy2(PROJECT / name, checkout / name)
    module = checkout / "src/codex_den/__init__.py"
    original = module.read_text()
    module.write_text(original + '\nINSTALLER_SMOKE = "before"\n')
    tool_bin = tmp_path / "tool-bin"
    tool_bin.mkdir()
    adjacent = tool_bin / "existing-editor"
    adjacent.write_text("existing installation")
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "home/.config"),
        "XDG_DATA_HOME": str(tmp_path / "home/.local/share"),
        "UV_TOOL_DIR": str(tmp_path / "tools"),
        "UV_TOOL_BIN_DIR": str(tool_bin),
        "UV_CACHE_DIR": str(PROJECT / ".cache/uv"),
        "UV_OFFLINE": "true",
        "UV_PYTHON_DOWNLOADS": "never",
    }
    env.pop("CODEX_HOME", None)

    def command(*args):
        result = subprocess.run(
            args, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=90
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    command("sh", str(checkout / "install.sh"), "--python", sys.executable)
    executable = tool_bin / "codex-den"
    assert "0.1.0a1" in command(str(executable), "--version")
    command(str(executable), "environment", "create", "retained", "--json")
    registry = tmp_path / "home/.local/share/codex-den/registry.json"
    retained = registry.read_bytes()
    module.write_text(original + '\nINSTALLER_SMOKE = "after"\n')
    command("sh", str(checkout / "install.sh"), "--update", "--python", sys.executable)
    python = tmp_path / "tools/codex-den/bin/python"
    assert (
        command(str(python), "-c", "import codex_den; print(codex_den.INSTALLER_SMOKE)").strip()
        == "after"
    )
    command("sh", str(checkout / "install.sh"), "--uninstall")
    assert not executable.exists()
    assert registry.read_bytes() == retained
    assert adjacent.read_text() == "existing installation"
