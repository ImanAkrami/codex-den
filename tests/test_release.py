"""Release checks use disposable repositories and synthetic distribution files."""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_release.py"


@pytest.fixture
def release_checkout(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Release test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Release test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.invalid")
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nversion="0.1.0a1"\n')
    (root / "install.sh").write_text("#!/bin/sh\nDEFAULT_VERSION='v0.0.1'\n")
    for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "Initial"], ["tag", "v0.1.0a1"]):
        subprocess.run(["git", *args], cwd=root, check=True)
    return root


def run(root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=root, capture_output=True, text=True
    )


@pytest.mark.parametrize("tag", ["main", "v0.2.0", "v0.1.0a1;echo-bad"])
def test_release_rejects_invalid_or_mismatched_tags(release_checkout, tag):
    result = run(release_checkout, tag)
    assert result.returncode != 0
    assert not (release_checkout / "dist").exists()


def test_release_requires_tagged_commit(release_checkout):
    assert run(release_checkout, "v0.1.0a1").returncode == 0
    subprocess.run(
        ["git", "commit", "--allow-empty", "-qm", "Later"], cwd=release_checkout, check=True
    )
    result = run(release_checkout, "v0.1.0a1")
    assert result.returncode != 0
    assert "tagged commit" in result.stderr


def distribution_files(root):
    dist = root / "dist"
    dist.mkdir()
    for name in (
        "codex_den-0.1.0a1-py3-none-any.whl",
        "codex_den-0.1.0a1.tar.gz",
        "codex-den-v0.1.0a1-linux-x86_64",
        "codex-den-v0.1.0a1-linux-aarch64",
        "THIRD_PARTY_NOTICES-linux-x86_64.txt",
        "THIRD_PARTY_NOTICES-linux-aarch64.txt",
    ):
        (dist / name).write_bytes(name.encode())
    return dist


def test_release_assets_pin_installer_and_verify_from_download_directory(release_checkout):
    dist = distribution_files(release_checkout)
    result = run(release_checkout, "v0.1.0a1", "--artifacts", str(dist))
    assert result.returncode == 0, result.stderr
    assert "DEFAULT_VERSION='v0.1.0a1'" in (dist / "install.sh").read_text()
    assert "DEFAULT_VERSION='v0.0.1'" in (release_checkout / "install.sh").read_text()
    checksums = (dist / "SHA256SUMS").read_text().splitlines()
    assert len(checksums) == 7
    for line in checksums:
        digest, name = line.split("  ")
        assert "/" not in name
        assert hashlib.sha256((dist / name).read_bytes()).hexdigest() == digest
    assert (
        subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=dist, capture_output=True).returncode
        == 0
    )


def test_missing_release_artifact_leaves_no_partial_manifest(release_checkout):
    dist = release_checkout / "dist"
    dist.mkdir()
    result = run(release_checkout, "v0.1.0a1", "--artifacts", str(dist))
    assert result.returncode != 0
    assert not (dist / "SHA256SUMS").exists()


@pytest.mark.parametrize(
    "missing",
    [
        "codex-den-v0.1.0a1-linux-x86_64",
        "codex-den-v0.1.0a1-linux-aarch64",
        "THIRD_PARTY_NOTICES-linux-aarch64.txt",
    ],
)
def test_release_requires_every_native_artifact(release_checkout, missing):
    dist = distribution_files(release_checkout)
    (dist / missing).unlink()
    result = run(release_checkout, "v0.1.0a1", "--artifacts", str(dist))
    assert result.returncode != 0
    assert not (dist / "install.sh").exists()
    assert not (dist / "SHA256SUMS").exists()


@pytest.mark.parametrize("installer", ["no marker", "DEFAULT_VERSION='v0.0.1'\n" * 2])
def test_release_rejects_ambiguous_installer_before_writing(release_checkout, installer):
    dist = distribution_files(release_checkout)
    (release_checkout / "install.sh").write_text(installer)
    result = run(release_checkout, "v0.1.0a1", "--artifacts", str(dist))
    assert result.returncode != 0
    assert not (dist / "install.sh").exists()
    assert not (dist / "SHA256SUMS").exists()


def test_release_accepts_already_stamped_version(release_checkout):
    dist = distribution_files(release_checkout)
    (release_checkout / "install.sh").write_text("DEFAULT_VERSION='v0.1.0a1'\n")
    result = run(release_checkout, "v0.1.0a1", "--artifacts", str(dist))
    assert result.returncode == 0, result.stderr


def test_release_refuses_symlink_artifacts(release_checkout):
    dist = distribution_files(release_checkout)
    native = dist / "codex-den-v0.1.0a1-linux-aarch64"
    native.unlink()
    native.symlink_to(dist / "codex-den-v0.1.0a1-linux-x86_64")
    result = run(release_checkout, "v0.1.0a1", "--artifacts", str(dist))
    assert result.returncode != 0
    assert not (dist / "SHA256SUMS").exists()
