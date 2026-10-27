import asyncio
import threading

import pytest
from textual.widgets import Button, LoadingIndicator

from codex_den.config import parse_overrides
from codex_den.ui import DenApp


@pytest.mark.parametrize("enabled", [True, False])
async def test_motion_setting_controls_effects_without_blocking_navigation(
    service, monkeypatch, enabled
):
    monkeypatch.delenv("NO_COLOR", raising=False)
    service.config.overrides = parse_overrides([f"ui.motion={str(enabled).lower()}"])
    app = DenApp(service)
    async with app.run_test(size=(100, 38)) as pilot:
        assert app.motion_enabled is enabled
        await pilot.press("n")
        assert app.screen.query("#field-name")
        await pilot.wait_for_scheduled_animations()
        assert app.screen.query_one(".dialog").styles.opacity == 1
        await pilot.press("escape")
    assert not service.store.root.exists()


@pytest.mark.parametrize(
    "key,value", [("ui.color", "never"), ("ui.plain", True), ("ui.ascii", True)]
)
def test_linear_and_no_color_modes_have_no_motion(service, key, value):
    service.config.overrides[key] = value
    assert not DenApp(service).motion_enabled


@pytest.mark.parametrize("enabled", [True, False])
async def test_launch_progress_is_visible_and_cleared_with_and_without_motion(
    service, tmp_path, monkeypatch, enabled
):
    monkeypatch.delenv("NO_COLOR", raising=False)
    service.config.overrides["ui.motion"] = enabled
    path = tmp_path / "repo"
    path.mkdir()
    service.add_workspace("repo", path)
    entered, release = threading.Event(), threading.Event()

    def open_fake(_):
        entered.set()
        assert release.wait(5)
        return {"frontend": "vscode"}

    monkeypatch.setattr(service, "open", open_fake)
    app = DenApp(service)
    async with app.run_test(size=(80, 24)) as pilot:
        try:
            await pilot.press("o")
            assert await asyncio.to_thread(entered.wait, 5)
            assert str(app.query_one("#open-workspace", Button).label) == "Opening…"
            assert app.query_one("#launch-progress", LoadingIndicator).display is enabled
        finally:
            release.set()
            await app.workers.wait_for_complete()
        await pilot.pause()
        assert str(app.query_one("#open-workspace", Button).label) == "Open editor"
        assert not app.query_one("#launch-progress", LoadingIndicator).display
