"""Exercise rendered controls with real input, rather than assigning Select.value."""

import pytest
from textual.widgets import Select

from codex_den.ui import DenApp


def screen_text(app):
    """Final composed terminal cells, including overlay clipping and occlusion."""
    return "\n".join(strip.text for strip in app.screen._compositor.render_strips())


@pytest.mark.parametrize("size", [(110, 40), (70, 32)])
async def test_action_dropdown_renders_items_and_keyboard_selection(service, size):
    app = DenApp(service)
    async with app.run_test(size=size) as pilot:
        await pilot.click("#actions")
        await pilot.pause()
        assert "Register workspace" in screen_text(app)
        assert "Clone environment" in screen_text(app)
        await pilot.press("end")
        await pilot.pause()
        assert "Uninstall instructions" in screen_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert "Uninstall instructions" in screen_text(app)
        assert app.screen.query("#review-content")
        await pilot.click("#cancel")
        assert app.query_one("#actions", Select).value is Select.BLANK
    assert not service.store.root.exists()
    assert not service.config.path.exists()


# Keep this list explicit: adding a menu entry requires extending the path audit.
ROUTES = [
    ("Register workspace", "workspace", "FormScreen"),
    ("Create environment", "environment", "FormScreen"),
    ("Clone environment", "clone", "FormScreen"),
    ("Save preset", "preset", "FormScreen"),
    ("Inspect preset", "preset-inspect", "FormScreen"),
    ("Compare configuration", "compare", "FormScreen"),
    ("Discover repositories", "discover", "DiscoveryScreen"),
    ("Join shared environment", "switch", "FormScreen"),
    ("Detach into private environment", "detach", "FormScreen"),
    ("Copy configuration files", "import", "ImportScreen"),
    ("Export portable environment", "export", "FormScreen"),
    ("Import portable environment", "bundle", "FormScreen"),
    ("Remove workspace registration", "unregister", "FormScreen"),
    ("Remove unused environment", "remove-environment", "FormScreen"),
    ("Delete preset", "remove-preset", "FormScreen"),
    ("Clear recent list", "clear-recent", "ReviewScreen"),
    ("Installation wizard", "setup", "SetupScreen"),
    ("Install Codex extension", "install-extension", "FormScreen"),
    ("Settings", "settings", "SettingsScreen"),
    ("Diagnostics", "doctor", "ReviewScreen"),
    ("Update instructions", "update", "ReviewScreen"),
    ("Uninstall instructions", "uninstall", "ReviewScreen"),
]


def files_under(root):
    return {
        str(p.relative_to(root)): p.read_bytes() if p.is_file() else None for p in root.rglob("*")
    }


async def exercise_select(app, pilot, select):
    """Open each picker and check every option in the final rendered viewport."""
    await pilot.wait_for_scheduled_animations()
    select.scroll_visible(animate=False, immediate=True)
    select.focus()
    await pilot.wait_for_scheduled_animations()
    await pilot.press("enter", "home")
    overlay = select.query_one("SelectOverlay")
    for index in range(overlay.option_count):
        await pilot.pause()
        label = str(overlay.get_option_at_index(index).prompt)
        region = overlay.content_region
        text = " ".join(
            strip.crop(region.x, region.right).text.strip()
            for strip in app.screen._compositor.render_strips()[region.y : region.bottom]
        )
        # Wrapping may split long labels. Ignore whitespace, not missing characters.
        assert "".join(label.split()) in "".join(text.split()), (select.id, label, text)
        if index + 1 < overlay.option_count:
            await pilot.press("down")
    await pilot.press("escape")
    assert not select.expanded


@pytest.mark.parametrize("size", [(110, 40), (80, 24), (70, 32)])
async def test_every_menu_route_and_picker_is_visible_and_cancel_is_write_free(
    service, tmp_path, editor, size
):
    from codex_den.ui import ACTIONS

    assert ACTIONS == [(label, action) for label, action, _ in ROUTES]
    service.config.save("executables.vscode", str(editor))
    service.config.save("frontend", "vscode")
    for name in ("alpha", "beta"):
        service.create_environment(name)
        repo = tmp_path / name
        repo.mkdir()
        service.add_workspace(name, repo, name)
    service.save_preset("template", "alpha")
    before = files_under(service.store.root), files_under(service.config.path.parent)
    app = DenApp(service)
    async with app.run_test(size=size) as pilot:
        for label, action, screen_class in ROUTES:
            select = app.query_one("#actions", Select)
            select.focus()
            # Exercise built-in typeahead; use the shortest unambiguous prefix.
            prefix = next(
                label[:length].lower()
                for length in range(1, len(label) + 1)
                if sum(other.lower().startswith(label[:length].lower()) for other, *_ in ROUTES)
                == 1
            )
            await pilot.press("enter", *("space" if c == " " else c for c in prefix), "enter")
            await pilot.pause()
            assert type(app.screen).__name__ == screen_class, action
            for picker in app.screen.query(Select):
                if picker.display and picker.visible and picker.region:
                    await exercise_select(app, pilot, picker)
            if action == "setup":
                await pilot.click("#next")
                await pilot.pause()
                assert app.screen.step == 1
                for picker in app.screen.query("#step-workspace Select"):
                    await exercise_select(app, pilot, picker)
            close = "#close-settings" if action == "settings" else "#cancel"
            app.screen.query_one(close).scroll_visible(immediate=True)
            await pilot.pause()
            assert await pilot.click(close), action
            await pilot.pause()
            assert len(app.screen_stack) == 1, action
    assert (files_under(service.store.root), files_under(service.config.path.parent)) == before


@pytest.mark.parametrize("action", ["environment", "import", "discover", "setup", "settings"])
async def test_escape_closes_picker_before_dialog(service, action):
    app = DenApp(service)
    async with app.run_test(size=(110, 40)) as pilot:
        app.choose_action(action)
        await pilot.pause()
        dialog = app.screen
        picker = dialog.query(Select).first()
        picker.focus()
        await pilot.press("enter")
        assert picker.expanded
        await pilot.press("escape")
        assert app.screen is dialog
        assert not picker.expanded
        await pilot.press("escape")
        assert len(app.screen_stack) == 1
    assert not service.store.root.exists()
    assert not service.config.path.exists()


@pytest.mark.parametrize("action", ["environment", "settings", "import", "discover", "setup"])
@pytest.mark.parametrize("size", [(80, 24), (70, 32)])
async def test_dialog_actions_are_visible_without_scrolling(service, action, size):
    app = DenApp(service)
    async with app.run_test(size=size) as pilot:
        app.choose_action(action)
        await pilot.pause()
        button = app.screen.query_one("#close-settings" if action == "settings" else "#cancel")
        assert "Cancel" in screen_text(app) or "Close" in screen_text(app)
        assert app.screen.get_widget_at(*button.region.center)[0] is button
        assert await pilot.click(button)
        assert len(app.screen_stack) == 1


async def test_resize_with_modal_updates_underlying_dashboard(service, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    service.add_workspace("repo", repo)
    app = DenApp(service)
    async with app.run_test(size=(110, 40)) as pilot:
        app.action_settings()
        await pilot.pause()
        await pilot.resize_terminal(70, 32)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.has_class("narrow")
        assert app.query_one("#detail-pane").region.y > app.query_one("#workspace-pane").region.y
        assert "repo / repo" in screen_text(app)


@pytest.mark.parametrize("size", [(60, 24), (80, 24), (70, 32)])
async def test_short_dashboard_keeps_workspace_rows_and_open_action_visible(
    service, tmp_path, size
):
    path = tmp_path / "repo"
    path.mkdir()
    service.add_workspace("repo", path)
    app = DenApp(service)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        assert "repo" in screen_text(app)
        assert "Open editor" in screen_text(app)
        button = app.query_one("#open-workspace")
        assert app.screen.get_widget_at(*button.region.center)[0] is button
        assert app.query_one("#workspaces").region.height >= 2


@pytest.mark.parametrize(
    "control, shortcut, expected",
    [
        ("#register", "n", "FormScreen"),
        ("#new-environment", None, "FormScreen"),
        ("#settings", "s", "SettingsScreen"),
        (None, "ctrl+n", "SetupScreen"),
    ],
)
async def test_toolbar_buttons_and_shortcuts_open_and_cancel(service, control, shortcut, expected):
    app = DenApp(service)
    async with app.run_test(size=(80, 24)) as pilot:
        if control:
            assert await pilot.click(control)
            await pilot.pause()
            assert type(app.screen).__name__ == expected
            await pilot.press("escape")
        if shortcut:
            await pilot.press(shortcut)
            await pilot.pause()
            assert type(app.screen).__name__ == expected
            await pilot.press("escape")
        assert len(app.screen_stack) == 1
    assert not service.store.root.exists()
    assert not service.config.path.exists()
