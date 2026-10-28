import json
import os
import sys
from pathlib import Path

import pytest

from codex_den.errors import DenError


@pytest.mark.parametrize("original", [None, "", "/opt/editor-libraries"])
def test_frozen_editor_children_restore_system_library_routing(tmp_path, monkeypatch, original):
    from codex_den.launch import child_environment

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/bundle/lib")
    if original is None:
        monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    else:
        monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", original)
    before = dict(os.environ)
    child = child_environment(tmp_path / "codex-home")
    assert child.get("LD_LIBRARY_PATH") == original
    assert child["CODEX_HOME"] == str(tmp_path / "codex-home")
    assert dict(os.environ) == before


def test_source_launch_preserves_user_library_routing(tmp_path, monkeypatch):
    from codex_den.launch import child_environment

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/custom-libraries")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/opt/older-libraries")
    assert child_environment(tmp_path / "codex-home")["LD_LIBRARY_PATH"] == "/opt/custom-libraries"


def prepared(service, tmp_path, editor):
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    service.add_workspace("repo", repo)
    service.config.save("executables.cursor", str(editor))
    return repo


def test_exact_launch_argv_env_cwd_and_legacy_coexistence(service, tmp_path, editor, monkeypatch):
    repo = prepared(service, tmp_path, editor)
    legacy = Path.home() / ".local/share/vscode-codex/old/codex-home"
    legacy.mkdir(parents=True)
    (legacy / "auth.json").write_text("do not touch")
    launcher = Path.home() / ".local/bin/existing-editor"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("original launcher")
    capture = tmp_path / "capture.json"
    monkeypatch.setenv("CAPTURE", str(capture))
    monkeypatch.setenv("CODEX_HOME", str(legacy))
    plan = service.plan_open(
        "repo", frontend="cursor", extra=["--new-window", "literal $(touch nope)"]
    )
    assert plan.cwd == repo
    assert plan.argv[-3:] == [str(repo), "--new-window", "literal $(touch nope)"]
    assert plan.environment["CODEX_HOME"] != str(legacy)
    service.open("repo", frontend="cursor", extra=["--new-window", "literal $(touch nope)"])
    result = json.loads(capture.read_text())
    assert result["cwd"] == str(repo)
    assert result["codex_home"] == str(Path(plan.environment["CODEX_HOME"]))
    assert result["argv"] == plan.argv
    assert result["home"] == str(Path.home())
    assert os.environ["CODEX_HOME"] == str(legacy)
    assert launcher.read_text() == "original launcher"
    assert (legacy / "auth.json").read_text() == "do not touch"
    assert not (repo / "nope").exists()


@pytest.mark.parametrize(
    "extra",
    [
        ["--user-data-dir", "/tmp/other"],
        ["--user-data-dir=/tmp/other"],
        ["--extensions-dir=/tmp/other"],
        ["--profile=other"],
        ["--profile", "other"],
        ["--user-d", "/tmp/other"],
        ["--extensions-d=/tmp/other"],
    ],
)
def test_rejects_profile_overrides_before_launch(service, tmp_path, editor, extra):
    prepared(service, tmp_path, editor)
    with pytest.raises(DenError, match="managed"):
        service.plan_open("repo", frontend="cursor", extra=extra)
    assert service.recent() == []


def test_failed_launch_preserves_recency(service, tmp_path, editor, monkeypatch):
    prepared(service, tmp_path, editor)
    monkeypatch.setenv("CAPTURE", str(tmp_path / "capture"))
    monkeypatch.setenv("EDITOR_STATUS", "7")
    with pytest.raises(DenError, match="7"):
        service.open("repo", frontend="cursor")
    assert service.recent() == []


def test_temporary_environment_does_not_reassign_saved_membership(service, tmp_path, editor):
    prepared(service, tmp_path, editor)
    private = service.create_environment("private")
    original = service.inspect("repo")["environment"]["id"]
    plan = service.plan_open("repo", frontend="cursor", environment="private")
    assert private["id"] in plan.environment["CODEX_HOME"]
    assert service.inspect("repo")["environment"]["id"] == original


def test_launch_clears_inherited_editor_ipc_without_changing_parent(
    service, tmp_path, editor, monkeypatch
):
    prepared(service, tmp_path, editor)
    for key in ("VSCODE_IPC_HOOK_CLI", "CURSOR_IPC_HOOK_CLI", "ELECTRON_RUN_AS_NODE"):
        monkeypatch.setenv(key, "legacy-editor-state")
    plan = service.plan_open("repo", frontend="cursor")
    for key in ("VSCODE_IPC_HOOK_CLI", "CURSOR_IPC_HOOK_CLI", "ELECTRON_RUN_AS_NODE"):
        assert key not in plan.environment
        assert os.environ[key] == "legacy-editor-state"


def test_install_codex_extension_uses_managed_profile_and_does_not_record_open(
    service, tmp_path, editor, monkeypatch
):
    prepared(service, tmp_path, editor)
    capture = tmp_path / "extension-capture"
    monkeypatch.setenv("CAPTURE", str(capture))
    name = service.inspect("repo")["environment"]["name"]
    service.install_codex_extension(name, "cursor")
    result = json.loads(capture.read_text())
    assert result["argv"][-2:] == ["--install-extension", "openai.chatgpt"]
    assert result["codex_home"] == service.inspect("repo")["codex_home"]
    assert service.recent() == []


def test_detects_missing_appimage_target_without_running_wrapper(service, tmp_path, monkeypatch):
    from codex_den.launch import resolve_executable

    wrapper = tmp_path / "cursor-wrapper"
    wrapper.write_text(
        '#!/bin/sh\nAPPIMAGE="$HOME/.AppImage/Missing-Cursor.AppImage"\nexec "$APPIMAGE" "$@"\n'
    )
    wrapper.chmod(0o700)
    with pytest.raises(DenError, match="AppImage"):
        resolve_executable(str(wrapper))


@pytest.mark.parametrize(
    "relative", ["codex-home", "editors/cursor/user-data", "editors/cursor/extensions"]
)
def test_extension_install_rejects_symlinked_managed_children(
    service, tmp_path, editor, monkeypatch, relative
):
    prepared(service, tmp_path, editor)
    environment = service.inspect("repo")["environment"]
    child = service.environment_path(environment) / relative
    child.rmdir()
    legacy = Path.home() / ".vscode/extensions"
    legacy.mkdir(parents=True)
    (legacy / "sentinel").write_text("preserve")
    child.symlink_to(legacy, target_is_directory=True)
    capture = tmp_path / "capture"
    monkeypatch.setenv("CAPTURE", str(capture))
    with pytest.raises(DenError, match="symlink|escapes"):
        service.install_codex_extension(environment["name"], "cursor")
    assert not capture.exists()
    assert (legacy / "sentinel").read_text() == "preserve"
