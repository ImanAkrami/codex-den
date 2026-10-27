"""A keyboard-first workspace dashboard with a shared, testable service layer."""

import json
import os
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.filter import Monochrome, NoColor
from textual.theme import Theme
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    LoadingIndicator,
    OptionList,
    Select,
    Static,
)
from textual.widgets.option_list import Option

from . import __version__
from .cli import lifecycle
from .errors import DenError
from .ui_forms import DiscoveryScreen, FormScreen, ImportScreen, ReviewScreen
from .ui_settings import SettingsScreen
from .ui_wizard import SetupScreen

ACTIONS = [
    ("Register workspace", "workspace"),
    ("Create environment", "environment"),
    ("Clone environment", "clone"),
    ("Save preset", "preset"),
    ("Inspect preset", "preset-inspect"),
    ("Compare configuration", "compare"),
    ("Discover repositories", "discover"),
    ("Join shared environment", "switch"),
    ("Detach into private environment", "detach"),
    ("Copy configuration files", "import"),
    ("Export portable environment", "export"),
    ("Import portable environment", "bundle"),
    ("Remove workspace registration", "unregister"),
    ("Remove unused environment", "remove-environment"),
    ("Delete preset", "remove-preset"),
    ("Clear recent list", "clear-recent"),
    ("Installation wizard", "setup"),
    ("Install Codex extension", "install-extension"),
    ("Settings", "settings"),
    ("Diagnostics", "doctor"),
    ("Update instructions", "update"),
    ("Uninstall instructions", "uninstall"),
]


class DenApp(App):
    TITLE = "Codex Den"
    SUB_TITLE = "A home for your Codex workspaces"
    CSS_PATH = "ui.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("o", "open_workspace", "Open"),
        Binding("n", "form('workspace')", "Register"),
        Binding("s", "settings", "Settings"),
        Binding("slash", "search", "Search"),
        Binding("ctrl+n", "setup", "Setup"),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, service, initial=None):
        super().__init__()
        self.service, self.initial = service, initial
        self.color_mode = service.config.effective()["ui.color"]
        values = service.config.effective()
        self.motion_enabled = bool(
            values["ui.motion"]
            and not values["ui.plain"]
            and not values["ui.ascii"]
            and self.color_mode != "never"
            and not (os.environ.get("NO_COLOR") and self.color_mode != "always")
            and self.animation_level != "none"
        )
        if not self.motion_enabled:
            self.animation_level = "none"
        self.current = None
        self.opening = False
        self.register_theme(
            Theme(
                name="den",
                primary="#d9b16b",
                secondary="#8cae9d",
                accent="#d9b16b",
                foreground="#e6e1d8",
                background="#14191d",
                surface="#1b2227",
                panel="#20292f",
                success="#91b89d",
                warning="#d9b16b",
                error="#db8a82",
            )
        )
        self.theme = "den" if service.config.effective()["ui.theme"] == "dark" else "textual-light"

    def get_line_filters(self):
        filters = list(super().get_line_filters())
        mode = getattr(self, "color_mode", "auto")
        if mode == "always":
            filters = [item for item in filters if not isinstance(item, (Monochrome, NoColor))]
        elif mode == "never" and not any(isinstance(item, Monochrome) for item in filters):
            filters.append(Monochrome())
        return filters

    def compose(self) -> ComposeResult:
        with Vertical(id="shell"):
            with Horizontal(id="masthead"):
                yield Static("CODEX [b]DEN[/b]", id="brand")
                yield Static("A home for your workspaces", id="tagline")
                yield Static(f"v{__version__}", id="edition")
            yield Static("", id="summary")
            with Horizontal(id="toolbar"):
                yield Button("Register workspace", id="register", variant="primary")
                yield Button("New environment", id="new-environment")
                yield Button("Settings", id="settings")
                yield Select(ACTIONS, prompt="More actions…", id="actions")
            with Horizontal(id="dashboard"):
                with Vertical(id="workspace-pane"):
                    yield Label("WORKSPACES", classes="section-title")
                    yield Input(placeholder="Search name, path, environment…", id="search")
                    yield Select(
                        [
                            ("All workspaces", "all"),
                            ("Favorites", "favorites"),
                            ("Recent", "recent"),
                        ],
                        value="all",
                        allow_blank=False,
                        compact=True,
                        id="workspace-filter",
                    )
                    yield OptionList(id="workspaces")
                with Vertical(id="detail-pane"):
                    yield Label("YOUR NEXT WORKSPACE", id="detail-heading", classes="section-title")
                    yield Static("", id="details")
                    yield LoadingIndicator(id="launch-progress")
                    with Horizontal(id="workspace-actions"):
                        yield Button("Open editor", variant="primary", id="open-workspace")
                        yield Button("Favorite", id="favorite")
            yield Static("Your workspaces, organized.", id="statusline")
        yield Footer()

    def on_resize(self, event):
        self.screen_stack[0].set_class(event.size.width < 85, "narrow")
        if self.is_mounted and self.query("#details"):
            self.call_after_refresh(self.refresh_details)

    def on_mount(self):
        self.query_one("#favorite", Button).active_effect_duration = 0
        self.query_one("#launch-progress").display = False
        if self.motion_enabled:
            heading = self.query_one("#masthead")
            heading.styles.opacity = 0.7
            heading.styles.animate("opacity", 1.0, duration=0.18, easing="out_cubic")
        self.refresh_dashboard()
        self.query_one("#workspaces", OptionList).focus()
        if self.initial == "setup":
            self.action_setup()
        elif self.initial == "settings":
            self.action_settings()

    def refresh_dashboard(self, *_):
        state = self.service.inventory()
        count, environments = len(state["workspaces"]), len(state["environments"])
        self.query_one("#summary", Static).update(
            f"{count:02d} workspaces   /   {environments:02d} environments   /   VS Code + Cursor"
        )
        query = self.query_one("#search", Input).value.casefold()
        filter_mode = self.query_one("#workspace-filter", Select).value
        items = list(state["workspaces"].values())
        if filter_mode == "recent":
            items = self.service.recent()
        else:
            items.sort(key=lambda item: (not item["favorite"], item["name"].casefold()))
        visible = []
        for item in items:
            environment = self.service.environment(item["environment"], state)
            if filter_mode == "favorites" and not item["favorite"]:
                continue
            if query not in f"{item['name']} {item['path']} {environment['name']}".casefold():
                continue
            visible.append((item, environment))
        listing = self.query_one("#workspaces", OptionList)
        old = self.current
        listing.clear_options()
        for item, environment in visible:
            label = Text()
            label.append("* " if item["favorite"] else "  ", style="bold #d9b16b")
            label.append(item["name"], style="bold")
            label.append(f"\n  {environment['name']}", style="dim")
            listing.add_option(Option(label, id=item["name"]))
        names = [item["name"] for item, _ in visible]
        self.current = old if old in names else (names[0] if names else None)
        if self.current:
            listing.highlighted = names.index(self.current)
        self.refresh_details()

    def refresh_details(self):
        self.query_one("#open-workspace", Button).label = (
            "Opening…" if self.opening else "Open editor"
        )
        self.query_one("#launch-progress").display = self.opening and self.motion_enabled
        details = self.query_one("#details", Static)
        if not self.current:
            details.update(
                Text(
                    "No workspaces here yet.\n\nRegister a repository or run the installation wizard.\n\nEach workspace can have its own environment, or share a complete environment with others.\n\nNothing launches until you choose Open."
                )
            )
            self.query_one("#open-workspace", Button).disabled = True
            self.query_one("#favorite", Button).disabled = True
            return
        info = self.service.inspect(self.current)
        values, _ = self.service.settings(self.current)
        environment = info["environment"]
        if self.screen_stack[0].has_class("narrow"):
            self.query_one("#details", Static).update(
                Text(
                    f"{self.current} / {environment['name']} / {values['frontend']}\nMembers: {', '.join(info['members'])}"
                )
            )
            self.query_one("#open-workspace", Button).disabled = self.opening
            favorite = self.query_one("#favorite", Button)
            favorite.disabled = False
            favorite.label = "Unfavorite" if info["workspace"]["favorite"] else "Favorite"
            return
        text = Text()
        text.append(f"{self.current}\n", style="bold #d9b16b")
        text.append(f"{info['workspace']['path']}\n\n")
        text.append("ENVIRONMENT\n", style="dim")
        text.append(
            f"{environment['name']}  /  {'shared' if len(info['members']) > 1 else 'independent'}\n"
        )
        text.append(f"Members: {', '.join(info['members'])}\n\n")
        text.append("EDITOR\n", style="dim")
        text.append(
            f"{'Cursor' if values['frontend'] == 'cursor' else 'VS Code'}  /  Codex extension\n\n"
        )
        text.append("CODEX HOME\n", style="dim")
        text.append(f"{info['codex_home']}\n\n")
        text.append(
            "Shared members use the same Codex home, settings, extensions and editor profile.",
            style="dim",
        )
        details.update(text)
        self.query_one("#open-workspace", Button).disabled = self.opening
        favorite = self.query_one("#favorite", Button)
        favorite.disabled = False
        favorite.label = "Unfavorite" if info["workspace"]["favorite"] else "Favorite"

    def on_input_changed(self, event):
        if event.input.id == "search":
            self.refresh_dashboard()

    def on_option_list_option_highlighted(self, event):
        if event.option_list.id == "workspaces":
            self.current = event.option.id
            self.refresh_details()

    def on_select_changed(self, event):
        if event.select.id == "workspace-filter":
            self.refresh_dashboard()
        elif event.select.id == "actions" and event.value is not Select.BLANK:
            selected = event.value
            event.select.value = Select.BLANK
            self.choose_action(selected)

    def on_button_pressed(self, event):
        if event.button.id == "register":
            self.action_form("workspace")
        elif event.button.id == "new-environment":
            self.action_form("environment")
        elif event.button.id == "settings":
            self.action_settings()
        elif event.button.id == "open-workspace":
            self.action_open_workspace()
        elif event.button.id == "favorite" and self.current:
            try:
                current = self.service.workspace(self.current)
                self.service.favorite(self.current, not current["favorite"])
                self.refresh_dashboard()
            except (DenError, OSError) as error:
                self.notify(str(error), severity="error", markup=False)

    def action_search(self):
        self.query_one("#search", Input).focus()

    def action_settings(self):
        self.push_screen(SettingsScreen(self.service), self.refresh_dashboard)

    def action_setup(self):
        self.push_screen(SetupScreen(self.service), self.refresh_dashboard)

    def action_import(self):
        self.push_screen(ImportScreen(self.service), self.refresh_dashboard)

    def choose_action(self, action):
        if action == "settings":
            self.action_settings()
        elif action == "setup":
            self.action_setup()
        elif action == "import":
            self.action_import()
        elif action == "discover":
            self.push_screen(DiscoveryScreen(self.service), self.refresh_dashboard)
        elif action == "doctor":
            self.push_screen(ReviewScreen("Diagnostics", self.service.doctor()))
        elif action in ("update", "uninstall"):
            self.push_screen(ReviewScreen(f"{action.title()} instructions", lifecycle(action)))
        elif action == "clear-recent":
            self.push_screen(
                ReviewScreen(
                    "Clear recent workspaces",
                    {"retained": "favorites, registrations and all environment data"},
                    self.service.clear_recent,
                ),
                self.refresh_dashboard,
            )
        else:
            self.action_form(action)

    def action_form(self, action):
        state = self.service.inventory()
        envs = [(e["name"], e["name"]) for e in state["environments"].values()]
        workspaces = [(w["name"], w["name"]) for w in state["workspaces"].values()]
        presets = [(name, name) for name in state["presets"]]

        def field(key, label, choices=None, default=""):
            if choices is not None:
                choices = choices or [("None available — create one first", "")]
                if default not in [value for _, value in choices]:
                    default = choices[0][1]
            return key, label, default, choices

        fields, prepare, title = (
            [],
            None,
            dict((value, label) for label, value in ACTIONS).get(action, action),
        )
        if action == "environment":
            fields = [
                field("name", "Environment name"),
                field("preset", "Preset", [("Clean defaults", ""), *presets]),
            ]

            def prepare(v):
                self.service.validate_name(v["name"])
                return v, lambda: self.service.create_environment(
                    v["name"], preset=v["preset"] or None
                )
        elif action == "workspace":
            fields = [
                field("name", "Workspace name"),
                field("path", "Folder", default=str(Path.cwd())),
                field("environment", "Environment", [("New independent environment", ""), *envs]),
            ]

            def prepare(v):
                self.service.validate_name(v["name"])
                if not Path(v["path"]).expanduser().is_dir():
                    raise DenError("Choose an existing directory.")
                return v, lambda: self.service.add_workspace(
                    v["name"], v["path"], v["environment"] or None
                )
        elif action in ("clone", "preset"):
            fields = [
                field("source", "Source environment", envs),
                field("name", "New environment name" if action == "clone" else "Preset name"),
            ]

            def prepare(v):
                self.service.validate_name(v["name"])
                snapshot = self.service.snapshot(v["source"])
                operation = (
                    self.service.clone_environment
                    if action == "clone"
                    else self.service.save_preset
                )
                return {
                    **v,
                    "files": list(snapshot["files"]),
                    "settings": snapshot["settings"],
                    "excluded": ["credentials", "history", "runtime state"],
                }, (lambda: operation(v["source"], v["name"])) if action == "clone" else (
                    lambda: operation(v["name"], v["source"])
                )
        elif action == "compare":
            choices = [(f"Environment: {name}", f"environment:{name}") for name, _ in envs] + [
                (f"Preset: {name}", f"preset:{name}") for name, _ in presets
            ]
            fields = [
                field("source", "Compare from", choices),
                field("destination", "Compare to", choices),
            ]

            def prepare(v):
                if not v["source"] or not v["destination"]:
                    raise DenError(
                        "Create an environment or save a preset before comparing configuration."
                    )
                left_kind, left = v["source"].split(":", 1)
                right_kind, right = v["destination"].split(":", 1)
                return self.service.compare(
                    left, right, left_kind == "preset", right_kind == "preset"
                ), None
        elif action in ("switch", "detach", "unregister"):
            fields = [field("workspace", "Workspace", workspaces, self.current or "")]
            if action == "switch":
                fields.append(field("environment", "Destination shared environment", envs))
            elif action == "detach":
                fields += [
                    field("name", "New independent environment name"),
                    field(
                        "clone",
                        "Starting configuration",
                        [("Clone selected safe settings", "yes"), ("Clean defaults", "no")],
                        "yes",
                    ),
                ]

            def prepare(v):
                info = self.service.inspect(v["workspace"])
                operation = (
                    (lambda: self.service.switch_workspace(v["workspace"], v["environment"]))
                    if action == "switch"
                    else (
                        lambda: self.service.detach_workspace(
                            v["workspace"], v["name"], v["clone"] == "yes"
                        )
                    )
                    if action == "detach"
                    else (lambda: self.service.remove_workspace(v["workspace"]))
                )
                return {
                    **v,
                    "current_environment": info["environment"]["name"],
                    "current_members": info["members"],
                    "preserved": "repository files and original environments",
                }, operation
        elif action == "install-extension":
            fields = [
                field("environment", "Environment", envs),
                field("frontend", "Editor", [("Cursor", "cursor"), ("VS Code", "vscode")]),
            ]

            def prepare(v):
                return {
                    **v,
                    "extension": "openai.chatgpt",
                    "note": "Uses this environment's private editor profile/extensions directory",
                }, lambda: self.service.install_codex_extension(v["environment"], v["frontend"])
        elif action == "export":
            fields = [
                field("environment", "Environment", envs),
                field("path", "Export bundle path", default=str(Path.home() / "work.den")),
            ]

            def prepare(v):
                snapshot = self.service.snapshot(v["environment"])
                return {
                    **v,
                    "files": list(snapshot["files"]),
                    "excluded": ["credentials", "history", "runtime state"],
                }, lambda: self.service.export_environment(v["environment"], v["path"])
        elif action == "bundle":
            fields = [
                field("path", "Portable bundle path"),
                field("name", "New environment name"),
                field("mappings", "Path mappings as a JSON object (optional)", default="{}"),
            ]

            def prepare(v):
                mappings = json.loads(v["mappings"])
                if not isinstance(mappings, dict):
                    raise DenError("Path mappings must be a JSON object of source-to-local paths.")
                preview = self.service.preview_bundle(v["path"], mappings)
                return {**v, **preview}, lambda: self.service.import_environment(
                    v["path"], v["name"], mappings
                )
        elif action == "remove-environment":
            fields = [field("environment", "Unused environment to remove", envs)]

            def prepare(v):
                environment = self.service.environment(v["environment"])
                members = [
                    w["name"]
                    for w in state["workspaces"].values()
                    if w["environment"] == environment["id"]
                ]
                if members:
                    raise DenError(
                        f"Environment is used by {', '.join(members)}. Reassign or unregister them first."
                    )
                return {
                    "environment": environment,
                    "warning": "Deletes this unused environment and its managed state",
                }, lambda: self.service.remove_environment(v["environment"])
        elif action in ("preset-inspect", "remove-preset"):
            fields = [field("preset", "Preset", presets)]

            def prepare(v):
                preset = state["presets"].get(v["preset"])
                if preset is None:
                    raise DenError("Create a preset first.")
                return {
                    "name": v["preset"],
                    "settings": preset["settings"],
                    "files": list(preset["files"]),
                }, (
                    lambda: self.service.delete_preset(v["preset"])
                ) if action == "remove-preset" else None

        if prepare:
            self.push_screen(
                FormScreen(
                    title,
                    "Choose your target. Preview before any changes are applied.",
                    fields,
                    prepare,
                ),
                self.refresh_dashboard,
            )

    def action_open_workspace(self):
        if self.current and not self.opening:
            self.opening = True
            self.query_one("#open-workspace", Button).disabled = True
            self.query_one("#open-workspace", Button).label = "Opening…"
            self.query_one("#launch-progress").display = self.motion_enabled
            self.open_selected(self.current)

    @work(thread=True, exclusive=True)
    def open_selected(self, name):
        try:
            result = self.service.open(name)
        except (DenError, OSError) as error:
            self.call_from_thread(
                self.notify, str(error), severity="error", timeout=10, markup=False
            )
        else:
            self.call_from_thread(
                self.notify, f"Opened {name} in {result['frontend']}", markup=False
            )
        finally:
            self.call_from_thread(self.finish_open)

    def finish_open(self):
        self.opening = False
        self.refresh_dashboard()


def launch_ui(service, plain=False, initial=None):
    if plain or service.config.effective()["ui.plain"] or service.config.effective()["ui.ascii"]:
        from .ui_plain import plain_menu

        plain_menu(service, initial=initial)
    else:
        DenApp(service, initial=initial).run()
