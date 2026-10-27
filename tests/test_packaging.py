import configparser
import os
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def run(*args, env=None):
    return subprocess.run(
        args, cwd=PROJECT, env=env, text=True, capture_output=True, timeout=90, check=True
    )


def test_built_wheel_installs_only_codex_den_in_clean_environment(tmp_path):
    distribution = tmp_path / "dist"
    run("uv", "build", "--wheel", "--out-dir", str(distribution))
    wheel = next(distribution.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        assert "codex_den/ui.tcss" in archive.namelist()
        entrypoint = next(
            name for name in archive.namelist() if name.endswith(".dist-info/entry_points.txt")
        )
        metadata = configparser.ConfigParser()
        metadata.read_string(archive.read(entrypoint).decode())
        assert dict(metadata["console_scripts"]) == {"codex-den": "codex_den.cli:main"}
    virtualenv = tmp_path / "install"
    run("uv", "venv", "--python", sys.executable, str(virtualenv))
    python = virtualenv / "bin/python"
    run("uv", "pip", "install", "--python", str(python), "--offline", str(wheel))
    fake_home = tmp_path / "home"
    env = {
        **os.environ,
        "HOME": str(fake_home),
        "XDG_CONFIG_HOME": str(fake_home / "config"),
        "XDG_DATA_HOME": str(fake_home / "data"),
    }
    env.pop("CODEX_HOME", None)
    # Run outside the source tree so an editable import cannot hide missing wheel files.
    for arguments in (["--version"], ["--help"], ["config", "show", "--json"]):
        result = subprocess.run(
            [str(virtualenv / "bin/codex-den"), *arguments],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
    assert not fake_home.exists()
    assert not (virtualenv / "bin/existing-editor").exists()
