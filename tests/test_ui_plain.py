"""Linear menu exercises shared commands with disposable state and fake editors."""

import json

from codex_den.ui_plain import plain_menu


def feed(monkeypatch, answers):
    pending = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(pending))


def test_plain_cancel_help_errors_and_context_leave_no_state(service, monkeypatch, capsys):
    feed(
        monkeypatch,
        [
            "help",
            "unknown-command",
            "'broken",
            "--data-root /tmp/elsewhere list",
            "config set frontend invalid",
            "settings",
            "",
            "setup",
            "vscode",
            "fake",
            "/not-a-folder",
            "repo",
            "",
            "n",
            "q",
        ],
    )
    plain_menu(service)
    output = capsys.readouterr().out
    assert "Error:" in output
    assert "Cancelled; nothing was saved" in output
    assert "change the menu storage context" in output
    assert "\x1b[" not in output
    assert not service.store.root.exists()
    assert not service.config.path.exists()


def test_plain_setup_settings_direct_commands_overrides_and_fake_launch(
    service, tmp_path, editor, monkeypatch, capsys
):
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    capture = tmp_path / "capture"
    monkeypatch.setenv("CAPTURE", str(capture))
    feed(
        monkeypatch,
        [
            "cursor",
            str(editor),
            str(repo),
            "plain",
            "",
            "y",
            "settings",
            "ui.color",
            "never",
            "y",
            "config show",
            "--set frontend=cursor open plain -- --new-window 'two words'",
            "config reset ui.color",
            "list",
            "q",
        ],
    )
    plain_menu(service, initial="setup")
    result = json.loads(capture.read_text())
    assert result["cwd"] == str(repo)
    assert result["argv"][-3:] == [str(repo), "--new-window", "two words"]
    assert result["codex_home"] == service.inspect("plain")["codex_home"]
    assert service.config.saved()["frontend"] == "cursor"
    assert "ui.color" not in service.config.saved()
    assert service.config.overrides == {}
    assert "Setup complete" in capsys.readouterr().out


def test_plain_initial_settings_and_temporary_frontend_do_not_save_overrides(
    service, tmp_path, editor, monkeypatch
):
    service.create_environment("shared")
    repo = tmp_path / "repo"
    repo.mkdir()
    service.add_workspace("repo", repo, "shared")
    service.config.save("executables.cursor", str(editor))
    capture = tmp_path / "capture"
    monkeypatch.setenv("CAPTURE", str(capture))
    feed(monkeypatch, ["", "--frontend cursor inspect repo", "--frontend cursor open repo", "q"])
    plain_menu(service, initial="settings")
    assert json.loads(capture.read_text())["cwd"] == str(repo)
    assert "frontend" not in service.config.saved()
    assert service.config.overrides == {}
