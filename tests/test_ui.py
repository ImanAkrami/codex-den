import pytest
from textual.widgets import Input, OptionList, Select, Static

from codex_den.ui import DenApp


async def test_empty_dashboard_cancel_does_not_create_state(service):
    app = DenApp(service)
    async with app.run_test(size=(110, 36)) as pilot:
        assert "No workspaces" in str(app.query_one("#details", Static).render())
        await pilot.press("q")
    assert not service.store.root.exists()
    assert not service.config.path.exists()


async def test_search_selection_and_favorite_retain_shared_context(service, tmp_path):
    service.create_environment("shared")
    for name in ("alpha", "beta"):
        path = tmp_path / name
        path.mkdir()
        service.add_workspace(name, path, "shared")
    app = DenApp(service)
    async with app.run_test(size=(110, 36)) as pilot:
        app.query_one("#search", Input).value = "beta"
        await pilot.pause()
        assert app.query_one("#workspaces", OptionList).option_count == 1
        assert "shared" in str(app.query_one("#details", Static).render())
        await pilot.click("#favorite")
        assert service.inspect("beta")["workspace"]["favorite"]
        await pilot.resize_terminal(60, 24)
        await pilot.pause()
        assert app.query_one("#search").display
        await pilot.press("q")
    assert service.recent() == []


async def test_create_environment_form_requires_preview_and_cancel_is_write_free(service):
    app = DenApp(service)
    async with app.run_test(size=(110, 40)) as pilot:
        app.action_form("environment")
        await pilot.pause()
        app.screen.query_one("#field-name", Input).value = "new"
        await pilot.click("#preview")
        await pilot.pause()
        assert not service.store.root.exists()
        await pilot.click("#cancel")
        await pilot.pause()
        assert not service.store.root.exists()
        await pilot.press("escape")


async def test_create_environment_confirm_and_settings_save(service):
    app = DenApp(service)
    async with app.run_test(size=(110, 40)) as pilot:
        app.action_form("environment")
        await pilot.pause()
        app.screen.query_one("#field-name", Input).value = "new"
        await pilot.click("#preview")
        await pilot.pause()
        await pilot.click("#confirm")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert service.environment("new")["name"] == "new"
        app.action_settings()
        await pilot.pause()
        app.screen.query_one("#setting-key", Select).value = "frontend"
        app.screen.query_one("#setting-value", Input).value = "cursor"
        await pilot.click("#save-setting")
        await pilot.pause()
        assert service.config.effective()["frontend"] == "cursor"


async def test_setup_wizard_validates_and_finishes_without_launching(service, tmp_path, editor):
    repo = tmp_path / "project"
    repo.mkdir()
    service.config.save("frontend", "cursor")
    service.config.save("executables.cursor", str(editor))
    app = DenApp(service, initial="setup")
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#next")
        await pilot.pause()
        app.screen.query_one("#setup-name", Input).value = "project"
        app.screen.query_one("#setup-path", Input).value = str(repo)
        await pilot.click("#next")
        await pilot.pause()
        assert not service.store.root.exists()
        await pilot.click("#next")
        await pilot.pause()
        assert service.inspect("project")["workspace"]["path"] == str(repo)
        assert service.recent() == []


async def test_import_picker_previews_only_selected_files(service, tmp_path):
    environment = service.create_environment("target")
    source = tmp_path / "template"
    source.mkdir()
    (source / "AGENTS.md").write_text("rules")
    (source / "auth.json").write_text("secret")
    app = DenApp(service)
    async with app.run_test(size=(110, 42)) as pilot:
        app.action_import()
        await pilot.pause()
        app.screen.query_one("#import-source", Input).value = str(source)
        app.screen.query_one("#import-environment", Select).value = "target"
        await pilot.click("#scan-files")
        await pilot.pause()
        picker = app.screen.query_one("#import-files")
        assert picker.option_count == 1
        assert "AGENTS.md" in "\n".join(
            strip.text for strip in app.screen._compositor.render_strips()
        )
        picker.focus()
        await pilot.press("space")
        await pilot.click("#preview-import")
        await pilot.pause()
        home = service.environment_path(environment) / "codex-home"
        assert not (home / "AGENTS.md").exists()
        await pilot.click("#confirm")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert (home / "AGENTS.md").read_text() == "rules"
        assert not (home / "auth.json").exists()


async def test_narrow_dashboard_keeps_workspace_selection_visible(service, tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    service.add_workspace("repo", path)
    app = DenApp(service)
    async with app.run_test(size=(70, 32)) as pilot:
        await pilot.pause()
        listing = app.query_one("#workspaces", OptionList)
        assert listing.region.height >= 3
        assert listing.region.width <= 70
        assert app.query_one("#open-workspace").region.bottom <= 31


async def test_discovery_selection_and_confirmation_registers_workspaces(service, tmp_path):
    root = tmp_path / "projects"
    repo = root / "found"
    (repo / ".git").mkdir(parents=True)
    app = DenApp(service)
    async with app.run_test(size=(110, 42)) as pilot:
        app.choose_action("discover")
        await pilot.pause()
        app.screen.query_one("#discovery-root", Input).value = str(root)
        await pilot.click("#scan-repositories")
        await pilot.pause()
        picker = app.screen.query_one("#discovered")
        assert "found" in "\n".join(strip.text for strip in app.screen._compositor.render_strips())
        picker.focus()
        await pilot.press("space")
        await pilot.click("#register-discovered")
        await pilot.pause()
        await pilot.click("#confirm")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert service.inspect("found")["workspace"]["path"] == str(repo)
        assert app.screen is app.screen_stack[0]


@pytest.mark.parametrize(
    "action, fields, expected",
    [
        ("clone", {"name": "review"}, "environment"),
        ("preset", {"name": "work-preset"}, "preset"),
        ("workspace", {"name": "registered"}, "workspace"),
        ("detach", {"name": "private"}, "detach"),
    ],
)
async def test_operation_forms_apply_the_selected_action(
    service, tmp_path, action, fields, expected
):
    service.create_environment("shared")
    repo = tmp_path / "repo"
    repo.mkdir()
    service.add_workspace("repo", repo, "shared")
    other = tmp_path / "another"
    other.mkdir()
    app = DenApp(service)
    async with app.run_test(size=(110, 42)) as pilot:
        app.action_form(action)
        await pilot.pause()
        for key, value in fields.items():
            app.screen.query_one(f"#field-{key}", Input).value = value
        if action == "workspace":
            app.screen.query_one("#field-path", Input).value = str(other)
        await pilot.click("#preview")
        await pilot.pause()
        await pilot.click("#confirm")
        await app.workers.wait_for_complete()
        await pilot.pause()
        state = service.inventory()
        if expected == "environment":
            assert service.environment("review")["name"] == "review"
        elif expected == "preset":
            assert "work-preset" in state["presets"]
        elif expected == "workspace":
            assert service.workspace("registered")["path"] == str(other)
        else:
            assert service.inspect("repo")["environment"]["name"] == "private"


async def test_no_color_setting_applies_without_requiring_environment_variable(
    service, monkeypatch
):
    from textual.filter import Monochrome

    monkeypatch.delenv("NO_COLOR", raising=False)
    service.config.save("ui.color", "never")
    app = DenApp(service)
    assert any(isinstance(item, Monochrome) for item in app.get_line_filters())
