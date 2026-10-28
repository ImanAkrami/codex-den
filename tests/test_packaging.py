import configparser
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def run(*args, env=None):
    result = subprocess.run(
        args, cwd=PROJECT, env=env, text=True, capture_output=True, timeout=90, check=False
    )
    assert result.returncode == 0, result.stderr
    return result


def test_built_wheel_installs_only_codex_den_in_clean_environment(tmp_path):
    build_env = {**os.environ, "UV_CACHE_DIR": str(tmp_path / "cache"), "UV_OFFLINE": "false"}
    distribution = tmp_path / "dist"
    run("uv", "build", "--wheel", "--out-dir", str(distribution), env=build_env)
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
    run("uv", "venv", "--python", sys.executable, str(virtualenv), env=build_env)
    python = virtualenv / "bin/python"
    run("uv", "pip", "install", "--python", str(python), str(wheel), env=build_env)
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


def test_source_archive_excludes_local_artifacts_without_vcs_metadata(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE", "install.sh"):
        shutil.copy2(PROJECT / name, checkout / name)
    for name in ("src", "scripts"):
        shutil.copytree(
            PROJECT / name, checkout / name, ignore=shutil.ignore_patterns("__pycache__")
        )
    for name in (
        ".cache/binary-build/private.pkg",
        ".dev/session.md",
        ".hypothesis/cache",
        ".coverage.local",
        ".env",
        "private.key",
        "unrelated.txt",
    ):
        path = checkout / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private-build-sentinel")
    env = {**os.environ, "UV_CACHE_DIR": str(tmp_path / "cache"), "UV_OFFLINE": "false"}
    result = subprocess.run(
        ["uv", "build", "--sdist"],
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    with tarfile.open(next((checkout / "dist").glob("*.tar.gz"))) as archive:
        paths = [Path(member.name).relative_to("codex_den-0.1.0a1") for member in archive]
        assert Path("src/codex_den/ui.tcss") in paths
        assert Path("scripts/install-source.sh") in paths
        for member in archive.getmembers():
            if member.isfile():
                assert b"private-build-sentinel" not in archive.extractfile(member).read(), (
                    member.name
                )
        assert all("__pycache__" not in path.parts for path in paths)
