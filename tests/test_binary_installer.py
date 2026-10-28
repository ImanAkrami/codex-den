"""Native installation never requires Python/uv or touches application state."""

import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "install.sh"


@pytest.fixture
def native_installer(tmp_path):
    home, tools = tmp_path / "home", tmp_path / "tools"
    tools.mkdir()
    state = home / ".local/share/codex-den/preserved"
    state.parent.mkdir(parents=True)
    state.write_text("keep my environments")
    payload, checksums, log = tmp_path / "payload", tmp_path / "checksums", tmp_path / "downloads"
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{tools}:/usr/bin:/bin",
        "PAYLOAD": str(payload),
        "CHECKSUMS": str(checksums),
        "DOWNLOAD_LOG": str(log),
        "FAKE_ARCH": "x86_64",
        "FAKE_LIBC": "glibc 2.35",
    }
    tools.joinpath("curl").write_text(f"""#!{sys.executable}
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
url=next(arg for arg in args if arg.startswith('https://'))
with open(os.environ['DOWNLOAD_LOG'],'a') as stream: stream.write(json.dumps(args)+'\\n')
kind='checksum' if url.endswith('/SHA256SUMS') else 'binary'
if os.environ.get('FAIL_DOWNLOAD')==kind: sys.exit(22)
Path(args[args.index('-o')+1]).write_bytes(Path(os.environ['CHECKSUMS' if kind=='checksum' else 'PAYLOAD']).read_bytes())
""")
    tools.joinpath("uname").write_text(
        '#!/bin/sh\nif [ "$1" = "-m" ]; then echo "$FAKE_ARCH"; else echo "${FAKE_OS-Linux}"; fi\n'
    )
    tools.joinpath("getconf").write_text('#!/bin/sh\necho "$FAKE_LIBC"\n')
    for command in ("uv", "python", "python3"):
        tools.joinpath(command).write_text(
            '#!/bin/sh\necho "Unexpected runtime prerequisite" >&2\nexit 79\n'
        )
    tools.joinpath("mv").write_text(f"""#!{sys.executable}
import os,sys
if os.environ.get('FAIL_MARKER_MOVE') and sys.argv[-1].endswith('/.codex-den-install'): sys.exit(74)
os.execv('/usr/bin/mv',['mv',*sys.argv[1:]])
""")
    for path in tools.iterdir():
        path.chmod(0o700)
    destination = home / ".local/bin/codex-den"

    def set_asset(
        content=b"synthetic executable, never invoked", version="v0.1.0a1", arch="x86_64"
    ):
        payload.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        checksums.write_text(f"{digest}  codex-den-{version}-linux-{arch}\n")
        return digest

    def run(*args):
        result = subprocess.run(
            ["sh", str(SCRIPT), *args],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert state.read_text() == "keep my environments"
        return result

    set_asset()
    return run, set_asset, destination, checksums, env, log


def test_binary_installs_with_no_runtime_prerequisites(native_installer):
    run, _, target, _, _, log = native_installer
    result = run()
    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == b"synthetic executable, never invoked"
    assert os.access(target, os.X_OK)
    assert (target.parent / ".codex-den-install").is_file()
    assert "codex-den setup" in result.stdout
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 2
    assert all(
        any(
            "github.com/ImanAkrami/codex-den/releases/download/v0.1.0a1/" in value for value in call
        )
        for call in calls
    )


@pytest.mark.parametrize("arch", ["aarch64", "arm64"])
def test_binary_installer_maps_native_arm_and_pins_versions(native_installer, arch):
    run, set_asset, target, _, env, log = native_installer
    env["FAKE_ARCH"] = arch
    set_asset(version="v1.2.3", arch="aarch64")
    result = run("--version", "v1.2.3")
    assert result.returncode == 0, result.stderr
    assert "codex-den-v1.2.3-linux-aarch64" in log.read_text()
    assert target.is_file()


def test_binary_update_and_uninstall_retain_state(native_installer):
    run, set_asset, target, _, _, _ = native_installer
    assert run().returncode == 0
    set_asset(b"updated executable")
    result = run("--update")
    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == b"updated executable"
    assert run("--uninstall").returncode == 0
    assert not target.exists()
    assert not (target.parent / ".codex-den-install").exists()


@pytest.mark.parametrize("mode", ["digest", "missing", "duplicate"])
def test_bad_checksum_preserves_existing_install(native_installer, mode):
    run, set_asset, target, sums, _, _ = native_installer
    assert run().returncode == 0
    before = target.read_bytes()
    set_asset(b"new binary")
    if mode == "digest":
        sums.write_text("0" * 64 + "  codex-den-v0.1.0a1-linux-x86_64\n")
    elif mode == "missing":
        sums.write_text("")
    else:
        sums.write_text(sums.read_text() * 2)
    assert run("--update").returncode != 0
    assert target.read_bytes() == before


@pytest.mark.parametrize("kind", ["binary", "checksum"])
def test_failed_download_keeps_previous_binary(native_installer, kind):
    run, _, target, _, env, _ = native_installer
    assert run().returncode == 0
    before = target.read_bytes()
    env["FAIL_DOWNLOAD"] = kind
    assert run("--update").returncode != 0
    assert target.read_bytes() == before


@pytest.mark.parametrize("symlink", [False, True])
def test_unowned_target_or_symlink_is_never_replaced(native_installer, tmp_path, symlink):
    run, _, target, _, _, log = native_installer
    target.parent.mkdir(parents=True)
    valuable = tmp_path / "valuable"
    valuable.write_text("original")
    if symlink:
        target.symlink_to(valuable)
    else:
        target.write_text("original")
    assert run().returncode != 0
    assert target.read_text() == "original"
    assert valuable.read_text() == "original"
    assert not log.exists()


def test_modified_owned_binary_is_not_removed(native_installer):
    run, _, target, _, _, _ = native_installer
    assert run().returncode == 0
    target.write_text("replaced by another tool")
    assert run("--uninstall").returncode != 0
    assert target.read_text() == "replaced by another tool"


def test_busy_lock_is_not_removed_or_bypassed(native_installer):
    run, _, target, _, _, _ = native_installer
    assert run().returncode == 0
    before = target.read_bytes()
    lock = target.parent / ".codex-den-install.lock"
    lock.mkdir()
    assert run("--update").returncode != 0
    assert target.read_bytes() == before
    assert lock.is_dir()


def test_failed_marker_publication_restores_owned_binary(native_installer):
    run, set_asset, target, _, env, _ = native_installer
    assert run().returncode == 0
    before = target.read_bytes()
    marker = (target.parent / ".codex-den-install").read_bytes()
    set_asset(b"new binary")
    env["FAIL_MARKER_MOVE"] = "1"
    assert run("--update").returncode != 0
    assert target.read_bytes() == before
    assert (target.parent / ".codex-den-install").read_bytes() == marker


@pytest.mark.parametrize("name", ["bin with spaces $(touch unintended)", "quote' bin"])
def test_binary_destination_with_spaces_and_metacharacters_is_literal(
    native_installer, tmp_path, name
):
    run, _, _, _, _, _ = native_installer
    folder = tmp_path / name
    result = run("--bin-dir", str(folder))
    assert result.returncode == 0, result.stderr
    assert (folder / "codex-den").is_file()
    assert not (tmp_path / "unintended").exists()
    command = next(
        line.removeprefix("Run directly: ")
        for line in result.stdout.splitlines()
        if line.startswith("Run directly: ")
    )
    assert shlex.split(command) == [str(folder / "codex-den"), "setup"]


@pytest.mark.parametrize("args", [("--help",), ("--dry-run",), ("--uninstall", "--dry-run")])
def test_help_and_preview_are_write_free(native_installer, args):
    run, _, target, _, _, log = native_installer
    assert run(*args).returncode == 0
    assert not target.parent.exists()
    assert not log.exists()


@pytest.mark.parametrize(
    "args", [("--unknown",), ("--bin-dir",), ("--version", "../bad"), ("--uninstall", "--update")]
)
def test_invalid_binary_installer_args_fail_before_mutation(native_installer, args):
    run, _, target, _, _, log = native_installer
    assert run(*args).returncode != 0
    assert not target.parent.exists()
    assert not log.exists()


@pytest.mark.parametrize(
    "key,value",
    [
        ("FAKE_OS", "Darwin"),
        ("FAKE_ARCH", "riscv64"),
        ("FAKE_LIBC", "glibc 2.31"),
        ("FAKE_LIBC", "musl"),
    ],
)
def test_unsupported_platform_has_no_download_or_writes(native_installer, key, value):
    run, _, target, _, env, log = native_installer
    env[key] = value
    assert run().returncode != 0
    assert not target.parent.exists()
    assert not log.exists()


def test_failed_first_marker_write_leaves_no_half_install(native_installer):
    run, _, target, _, env, _ = native_installer
    env["FAIL_MARKER_MOVE"] = "1"
    assert run().returncode != 0
    assert not target.exists()
    assert not (target.parent / ".codex-den-install").exists()
    assert not list(target.parent.glob(".codex-den-*"))


def test_checksum_record_with_extra_fields_is_rejected(native_installer):
    run, _, target, sums, _, _ = native_installer
    sums.write_text(sums.read_text().rstrip() + " unexpected\n")
    assert run().returncode != 0
    assert not target.exists()


@pytest.mark.parametrize("marker_kind", ["symlink", "extra-line", "malformed"])
def test_invalid_ownership_marker_never_authorizes_mutation(
    native_installer, tmp_path, marker_kind
):
    run, _, target, _, _, _ = native_installer
    assert run().returncode == 0
    before = target.read_bytes()
    marker = target.parent / ".codex-den-install"
    content = marker.read_text()
    if marker_kind == "symlink":
        other = tmp_path / "foreign-record"
        other.write_text(content)
        marker.unlink()
        marker.symlink_to(other)
    elif marker_kind == "extra-line":
        marker.write_text(content + "extra\n")
    else:
        marker.write_text("not an ownership record\n")
    assert run("--update").returncode != 0
    assert run("--uninstall").returncode != 0
    assert target.read_bytes() == before
