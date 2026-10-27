"""UI operation outcomes, shared settings, recovery, and launch boundaries."""

import asyncio
import json
import threading

import pytest
from textual.widgets import Button, Input, Select, Static, TextArea

from codex_den.errors import DenError
from codex_den.ui import DenApp


async def pick(pilot, widget, value):
    index = next(i for i, (_, candidate) in enumerate(widget._options) if candidate == value)
    # Finish focus-driven scrolling before positioning a mouse target. `immediate`
    # bypasses deferred scheduling, but does not disable Textual's animation.
    await pilot.wait_for_scheduled_animations()
    widget.scroll_visible(animate=False, immediate=True)
    await pilot.pause()
    assert widget.display
    hit, _ = pilot.app.screen.get_widget_at(*widget.region.center)
    assert hit is widget or widget in hit.ancestors
    await pilot.click(offset=tuple(widget.region.center))
    assert widget.expanded
    await pilot.press("home", *(["down"] * index), "enter")
    assert widget.value == value


async def confirm(app, pilot):
    await pilot.click("#preview")
    await pilot.pause()
    assert app.screen.query("#review-content")
    await pilot.click("#confirm")
    await app.workers.wait_for_complete()
    await pilot.pause()


@pytest.mark.parametrize(
    "action",
    [
        "switch",
        "export",
        "bundle",
        "unregister",
        "remove-environment",
        "remove-preset",
        "install-extension",
        "compare",
        "preset-inspect",
        "clear-recent",
    ],
)
async def test_remaining_menu_operations_apply_observable_results(
    service, tmp_path, editor, monkeypatch, action
):
    alpha = service.create_environment("alpha")
    service.create_environment("beta")
    repo = tmp_path / "repo"
    repo.mkdir()
    service.add_workspace("repo", repo, "alpha")
    service.save_preset("template", "alpha")
    service.record_open("repo")
    home = service.environment_path(alpha) / "codex-home"
    (home / "AGENTS.md").write_text("workspace rules")
    bundle = tmp_path / "config.den"
    if action == "bundle":
        service.export_environment("alpha", bundle)
    service.config.save("executables.cursor", str(editor))
    capture = tmp_path / "editor.json"
    monkeypatch.setenv("CAPTURE", str(capture))
    before = service.inventory()
    app = DenApp(service)
    async with app.run_test(size=(110, 40)) as pilot:
        app.choose_action(action)
        await pilot.pause()
        if action in ("switch", "remove-environment"):
            await pick(pilot, app.screen.query_one("#field-environment", Select), "beta")
        if action in ("export", "install-extension"):
            await pick(pilot, app.screen.query_one("#field-environment", Select), "alpha")
        if action in ("export", "bundle"):
            app.screen.query_one("#field-path", Input).value = str(bundle)
        if action == "bundle":
            app.screen.query_one("#field-name", Input).value = "imported"
        if action in ("compare", "preset-inspect"):
            await pilot.click("#preview")
            await pilot.pause()
            content = json.loads(app.screen.query_one("#review-content", TextArea).text)
            assert content is not None
            assert not app.screen.query("#confirm")
            await pilot.click("#cancel")
            await pilot.press("escape")
            assert service.inventory() == before
        elif action == "clear-recent":
            await pilot.click("#confirm")
            await app.workers.wait_for_complete()
            await pilot.pause()
        else:
            await confirm(app, pilot)
        assert len(app.screen_stack) == 1
    if action == "switch":
        assert service.inspect("repo")["environment"]["name"] == "beta"
        assert (home / "AGENTS.md").read_text() == "workspace rules"
    elif action == "export":
        assert bundle.is_file()
        assert "codex-home/AGENTS.md" in service.preview_bundle(bundle, {})["files"]
    elif action == "bundle":
        destination = service.environment_path(service.environment("imported")) / "codex-home"
        assert (destination / "AGENTS.md").read_text() == "workspace rules"
    elif action == "unregister":
        assert not service.inventory()["workspaces"]
        assert repo.is_dir() and home.is_dir()
    elif action == "remove-environment":
        assert [e["name"] for e in service.inventory()["environments"].values()] == ["alpha"]
    elif action == "remove-preset":
        assert not service.inventory()["presets"]
    elif action == "install-extension":
        result = json.loads(capture.read_text())
        root = service.environment_path(alpha)
        assert result["argv"] == [
            "--user-data-dir",
            str(root / "editors/cursor/user-data"),
            "--extensions-dir",
            str(root / "editors/cursor/extensions"),
            "--install-extension",
            "openai.chatgpt",
        ]
        assert result["codex_home"] == str(home)
    elif action == "clear-recent":
        assert service.recent() == []
        assert service.workspace("repo")["path"] == str(repo)
    if action != "install-extension":
        assert not capture.exists()


async def test_open_repeated_shortcut_is_serialized_and_recovers(service, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    service.add_workspace("repo", repo)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def blocked_open(name):
        calls.append(name)
        entered.set()
        if not release.wait(10):
            raise DenError("test operation was not released")
        raise DenError("simulated editor failure")

    monkeypatch.setattr(service, "open", blocked_open)
    app = DenApp(service)
    async with app.run_test(size=(110, 40)) as pilot:
        try:
            await pilot.press("o")
            assert await asyncio.to_thread(entered.wait, 5)
            app.refresh_dashboard()  # Refresh/filter must not bypass the pending launch guard.
            await pilot.press("o", "o")
            assert calls == ["repo"]
            assert app.query_one("#open-workspace", Button).disabled
        finally:
            release.set()
            await app.workers.wait_for_complete()
        await pilot.pause()
        assert not app.query_one("#open-workspace", Button).disabled
        assert service.recent() == []
        assert any("simulated editor failure" in str(n.message) for n in app._notifications)


async def test_settings_user_shared_workspace_validation_reset_and_cancel(service, tmp_path):
    service.create_environment("shared")
    for name in ("one", "two"):
        path = tmp_path / name
        path.mkdir()
        service.add_workspace(name, path, "shared")
    app = DenApp(service)
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_settings()
        await pilot.pause()
        settings = app.screen
        value = settings.query_one("#setting-value", Input)
        value.value = "invalid-editor"
        await pilot.click("#save-setting")
        assert "Invalid frontend" in str(settings.query_one("#settings-error", Static).render())
        assert not service.config.path.exists()
        value.scroll_visible(immediate=True)
        value.focus()
        await pilot.press("ctrl+shift+a", *"cursor")
        await pilot.click("#save-setting")
        assert service.settings()[0]["frontend"] == "cursor"
        assert not str(settings.query_one("#settings-error", Static).render())
        await pilot.click("#reset-setting")
        assert service.settings()[1]["frontend"] == "default"
        for scope in ("environment:shared", "workspace:one"):
            await pick(pilot, settings.query_one("#settings-scope", Select), scope)
            value.scroll_visible(immediate=True)
            value.value = "cursor"
            await pilot.click("#save-setting")
            await pilot.pause()
            assert service.settings("one")[0]["frontend"] == "vscode"
            await pilot.click("#cancel")
            assert service.settings("one")[0]["frontend"] == "vscode"
            value.value = "cursor"
            await pilot.click("#save-setting")
            await pilot.pause()
            await pilot.click("#confirm")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert value.value == "cursor"
            assert service.settings("one")[0]["frontend"] == "cursor"
            assert service.settings("two")[0]["frontend"] == (
                "cursor" if scope.startswith("environment:") else "vscode"
            )
            await pilot.click("#reset-setting")
            await pilot.pause()
            await pilot.click("#confirm")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert value.value == "vscode"
        await pilot.press("escape")


async def test_review_failure_retry_preserves_form_values(service, monkeypatch):
    original = service.create_environment
    attempts = []

    def fail_once(*args, **kwargs):
        attempts.append(args)
        if len(attempts) == 1:
            raise DenError("Simulated denied write; retry is safe.")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "create_environment", fail_once)
    app = DenApp(service)
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_form("environment")
        await pilot.pause()
        app.screen.query_one("#field-name", Input).value = "retry"
        await pilot.click("#preview")
        await pilot.pause()
        await pilot.click("#confirm")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "retry is safe" in str(app.screen.query_one("#operation-error", Static).render())
        assert not service.inventory()["environments"]
        assert not app.screen.query_one("#confirm", Button).disabled
        app.screen.query_one("#confirm", Button).focus()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert len(app.screen_stack) == 1
        assert service.environment("retry")["name"] == "retry"
        assert len(attempts) == 2


async def test_wizard_advanced_back_validation_and_cancel_preserve_values(
    service, tmp_path, editor
):
    repo = tmp_path / "repo"
    repo.mkdir()
    app = DenApp(service, initial="setup")
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pick(pilot, app.screen.query_one("#setup-frontend", Select), "cursor")
        advanced = app.screen.query_one("#setup-advanced")
        advanced.scroll_visible(immediate=True)
        await pilot.pause()
        await pilot.click(advanced)
        executable = app.screen.query_one("#setup-executable", Input)
        executable.value = str(tmp_path / "missing-editor")
        await pilot.click("#next")
        assert app.screen.step == 0
        assert "executable" in str(app.screen.query_one("#setup-error", Static).render()).lower()
        executable.value = str(editor)
        await pilot.click("#next")
        await pilot.pause()
        assert app.screen.step == 1
        assert not str(app.screen.query_one("#setup-error", Static).render())
        app.screen.query_one("#setup-name", Input).value = "kept-name"
        app.screen.query_one("#setup-path", Input).value = str(repo)
        await pilot.click("#back")
        await pilot.pause()
        assert executable.value == str(editor)
        await pilot.click("#next")
        await pilot.pause()
        assert app.screen.query_one("#setup-name", Input).value == "kept-name"
        await pilot.click("#next")
        await pilot.pause()
        assert "kept-name" in str(app.screen.query_one("#setup-summary", Static).render())
        await pilot.click("#cancel")
    assert not service.store.root.exists()
    assert not service.config.path.exists()


@pytest.mark.parametrize("size", [(110, 40), (60, 24)])
async def test_dashboard_filter_search_and_open_launch_only_fake_editor(
    service, tmp_path, editor, monkeypatch, size
):
    service.config.save("executables.vscode", str(editor))
    capture = tmp_path / "capture"
    monkeypatch.setenv("CAPTURE", str(capture))
    for name in ("alpha", "beta"):
        repo = tmp_path / name
        repo.mkdir()
        service.add_workspace(name, repo)
    service.favorite("beta")
    app = DenApp(service)
    async with app.run_test(size=size) as pilot:
        await pick(pilot, app.query_one("#workspace-filter", Select), "favorites")
        assert app.current == "beta"
        assert not capture.exists()
        await pilot.click("#open-workspace")
        await app.workers.wait_for_complete()
        await pilot.pause()
        result = json.loads(capture.read_text())
        assert result["cwd"] == str(tmp_path / "beta")
        assert result["argv"][-1] == str(tmp_path / "beta")
        assert result["codex_home"] == service.inspect("beta")["codex_home"]
        await pick(pilot, app.query_one("#workspace-filter", Select), "recent")
        assert app.current == "beta"
        await pilot.press("slash")
        await pilot.press(*"missing")
        await pilot.pause()
        assert app.current is None
        assert app.query_one("#open-workspace", Button).disabled
        assert "No workspaces" in str(app.query_one("#details", Static).render())


async def test_import_and_discovery_invalid_inputs_recover_without_writes(service, tmp_path):
    app = DenApp(service)
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_import()
        await pilot.pause()
        await pilot.click("#preview-import")
        assert "Scan" in str(app.screen.query_one("#import-error", Static).render())
        app.screen.query_one("#import-source", Input).value = str(tmp_path / "missing")
        scan = app.screen.query_one("#scan-files", Button)
        scan.scroll_visible(immediate=True)
        scan.focus()
        await pilot.press("enter")
        assert "existing source" in str(app.screen.query_one("#import-error", Static).render())
        await pilot.press("escape")
        app.choose_action("discover")
        await pilot.pause()
        await pilot.click("#register-discovered")
        assert "Select at least one" in str(
            app.screen.query_one("#discovery-error", Static).render()
        )
        await pilot.press("escape")
    assert not service.store.root.exists()


async def test_discovery_partial_success_reports_results_and_refreshes_dashboard(service, tmp_path):
    root = tmp_path / "projects"
    for directory in ("a", "b"):
        (root / directory / "same" / ".git").mkdir(parents=True)
    app = DenApp(service)
    async with app.run_test(size=(110, 40)) as pilot:
        app.choose_action("discover")
        await pilot.pause()
        app.screen.query_one("#discovery-root", Input).value = str(root)
        await pilot.click("#scan-repositories")
        await pilot.pause()
        picker = app.screen.query_one("#discovered")
        assert picker.option_count == 2
        picker.select_all()
        await pilot.click("#register-discovered")
        await pilot.pause()
        await pilot.click("#confirm")
        await app.workers.wait_for_complete()
        await pilot.pause()
        results = json.loads(app.screen.query_one("#review-content", TextArea).text)
        assert sorted(item["success"] for item in results) == [False, True]
        assert "Some registrations failed" in str(
            app.screen.query_one("#operation-error", Static).render()
        )
        assert not app.screen.query_one("#confirm", Button).display
        await pilot.click("#cancel")
        await pilot.pause()
        assert len(app.screen_stack) == 1
        assert len(service.inventory()["workspaces"]) == 1
        assert "01 workspaces" in str(app.query_one("#summary", Static).render())


async def test_review_pending_cannot_be_cancelled_or_confirmed_twice(service):
    from codex_den.ui_forms import ReviewScreen

    entered, release = threading.Event(), threading.Event()
    calls = []

    def operation():
        calls.append(True)
        entered.set()
        if not release.wait(10):
            raise DenError("test operation was not released")

    app = DenApp(service)
    async with app.run_test(size=(80, 24)) as pilot:
        app.push_screen(ReviewScreen("Test apply", {"target": "temporary"}, operation))
        await pilot.pause()
        review = app.screen
        try:
            await pilot.click("#confirm")
            assert await asyncio.to_thread(entered.wait, 5)
            await pilot.press("escape", "enter", "q", "ctrl+c")
            assert app.is_running
            assert app.screen is review
            assert review.query_one("#cancel", Button).disabled
            assert review.query_one("#confirm", Button).disabled
            assert len(calls) == 1
        finally:
            release.set()
            await app.workers.wait_for_complete()
        await pilot.pause()
        assert len(app.screen_stack) == 1


async def test_empty_compare_explains_prerequisites_without_raw_exception(service):
    app = DenApp(service)
    async with app.run_test(size=(80, 24)) as pilot:
        app.choose_action("compare")
        await pilot.pause()
        await pilot.click("#preview")
        message = str(app.screen.query_one("#form-error", Static).render())
        assert "Create an environment" in message
        assert "unpack" not in message
        assert not service.store.root.exists()


async def test_successful_review_worker_survives_dialog_dismissal(service, monkeypatch):
    from codex_den.ui_forms import ReviewScreen

    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    unmounted = asyncio.Event()
    calls = []

    def operation():
        calls.append(True)
        entered.set()
        assert release.wait(5)

    class ObservedReview(ReviewScreen):
        def on_unmount(self):
            unmounted.set()

    app = DenApp(service)
    review = ObservedReview("Apply", {"target": "temporary"}, operation)
    original = app.call_from_thread

    def hold_thread_after_callback(callback, *args, **kwargs):
        result = original(callback, *args, **kwargs)
        if callback == review.finish:
            # Force dismissal to finish before the callback's thread unwinds.
            # A successfully applied operation must still complete normally.
            assert returned.wait(5)
        return result

    monkeypatch.setattr(app, "call_from_thread", hold_thread_after_callback)
    async with app.run_test(size=(80, 24)) as pilot:
        app.push_screen(review)
        await pilot.pause()
        try:
            await pilot.click("#confirm")
            assert await asyncio.to_thread(entered.wait, 5)
            (worker,) = list(app.workers)
            release.set()
            await asyncio.wait_for(unmounted.wait(), 5)
        finally:
            release.set()
            returned.set()
        await worker.wait()
        assert review.applied
        assert calls == [True]
        assert len(app.screen_stack) == 1
