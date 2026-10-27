"""CLI/UI parity and literal user-content regression tests."""

import sys

import pytest
from textual.widgets import Input, Select, Static

from codex_den.cli import main
from codex_den.errors import DenError
from codex_den.ui import DenApp
from codex_den.ui_plain import plain_menu


@pytest.mark.parametrize("entry", [[], ["menu"], ["setup"], ["config", "configure"]])
def test_interactive_dry_run_cannot_enter_mutating_ui(service, monkeypatch, entry):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(
        "codex_den.ui.launch_ui", lambda *a, **k: pytest.fail("dry run entered mutating UI")
    )
    assert main([*entry, "--dry-run"]) == 2
    assert not service.store.root.exists()
    assert not service.config.path.exists()


def test_setup_keeps_unrelated_invocation_overrides_temporary(service, tmp_path, editor):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert (
        main(
            [
                "setup",
                "--path",
                str(repo),
                "--name",
                "repo",
                "--frontend",
                "vscode",
                "--set",
                f"executables.vscode={editor}",
                "--set",
                "ui.theme=light",
                "--set",
                "discovery.max_depth=17",
                "--non-interactive",
                "--json",
            ]
        )
        == 0
    )
    assert service.config.saved() == {"frontend": "vscode", "executables.vscode": str(editor)}


def test_zero_discovery_depth_fails_instead_of_using_default(service, tmp_path):
    assert main(["workspace", "discover", str(tmp_path), "--max-depth", "0", "--json"]) == 2
    assert not service.store.root.exists()


def test_plain_invalid_editor_suffix_does_not_unregister(service, tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    service.add_workspace("repo", repo)
    answers = iter(["workspace remove repo --yes -- --bogus", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    plain_menu(service)
    assert service.workspace("repo")["path"] == str(repo)
    assert "only" in capsys.readouterr().out


async def test_wizard_honors_argument_frontend_precedence(service):
    service.config.save("frontend", "cursor")
    service.config.overrides["frontend"] = "vscode"
    app = DenApp(service, initial="setup")
    async with app.run_test(size=(100, 38)):
        assert app.screen.query_one("#setup-frontend", Select).value == "vscode"


async def test_wizard_path_and_errors_are_literal_text(service, tmp_path, editor):
    repo = tmp_path / "[" / "]"
    repo.mkdir(parents=True)
    service.config.save("frontend", "vscode")
    service.config.save("executables.vscode", str(editor))
    app = DenApp(service, initial="setup")
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.click("#next")
        app.screen.query_one("#setup-path", Input).value = str(repo)
        app.screen.query_one("#setup-name", Input).value = "literal"
        await pilot.click("#next")
        await pilot.pause()
        assert str(repo) in str(app.screen.query_one("#setup-summary", Static).render())
        assert app.screen.step == 2
    assert not service.store.root.exists()


async def test_favorite_failure_is_recoverable(service, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    service.add_workspace("repo", repo)
    original = service.favorite

    def fail(*args):
        raise DenError("Storage temporarily unavailable")

    monkeypatch.setattr(service, "favorite", fail)
    app = DenApp(service)
    async with app.run_test(size=(100, 38)) as pilot:
        await pilot.click("#favorite")
        assert app.is_running
        assert not service.workspace("repo")["favorite"]
        assert any("Storage temporarily" in str(n.message) for n in app._notifications)
        monkeypatch.setattr(service, "favorite", original)
        app.query_one("#favorite").focus()
        await pilot.press("enter")
        assert service.workspace("repo")["favorite"]


async def test_launch_error_toast_renders_literal_paths(service, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    service.add_workspace("repo", repo)
    missing = tmp_path / "[" / "]" / "missing"
    service.config.overrides["executables.vscode"] = str(missing)
    app = DenApp(service)
    async with app.run_test(size=(100, 38), notifications=True) as pilot:
        await pilot.press("o")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.is_running
        assert not app.opening
        assert any(str(missing) in str(n.message) for n in app._notifications)


@pytest.mark.parametrize("option", ["--frontend vscode", "--set frontend=vscode"])
def test_plain_command_overrides_inherited_frontend(service, monkeypatch, capsys, option):
    service.config.overrides["frontend"] = "cursor"
    answers = iter([f"config get frontend {option}", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    plain_menu(service)
    output = capsys.readouterr().out
    assert '"value": "vscode"' in output
    assert "Error:" not in output
    assert service.config.overrides["frontend"] == "cursor"


async def test_discovery_uses_full_configured_depth_and_literal_labels(service, tmp_path):
    repo = tmp_path / "[red]repo"
    (repo / ".git").mkdir(parents=True)
    service.config.overrides["discovery.max_depth"] = 20
    app = DenApp(service)
    async with app.run_test(size=(110, 40)) as pilot:
        app.choose_action("discover")
        await pilot.pause()
        assert app.screen.query_one("#discovery-depth", Select).value == 20
        app.screen.query_one("#discovery-root", Input).value = str(tmp_path)
        await pilot.click("#scan-repositories")
        await pilot.pause()
        assert "[red]repo" in "\n".join(s.text for s in app.screen._compositor.render_strips())
