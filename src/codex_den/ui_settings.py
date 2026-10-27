"""Easy settings with explicit scope, effective values, and safe reset."""

from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, Select, Static

from .config import DEFAULTS, parse_overrides
from .errors import DenError
from .ui_effects import DialogScreen
from .ui_forms import ReviewScreen


class SettingsScreen(DialogScreen):
    BINDINGS = [("escape", "cancel", "Close")]

    def __init__(self, service):
        super().__init__()
        self.service = service

    def compose(self):
        state = self.service.inventory()
        targets = [("User defaults", "user:")]
        targets += [
            (f"Environment: {e['name']}", f"environment:{e['name']}")
            for e in state["environments"].values()
        ]
        targets += [
            (f"Workspace: {w['name']}", f"workspace:{w['name']}")
            for w in state["workspaces"].values()
        ]
        with Vertical(classes="dialog settings-dialog"):
            yield Label("Settings", classes="dialog-title", markup=False)
            yield Static(
                "Useful defaults first. Changes apply only to the selected scope. Advanced keys use the same validation as config files and CLI flags.",
                classes="muted",
                markup=False,
            )
            with VerticalScroll(classes="settings-content"):
                yield Select(targets, value="user:", allow_blank=False, id="settings-scope")
                yield DataTable(id="settings-table", cursor_type="row")
                yield Select(
                    [(key, key) for key in DEFAULTS],
                    value="frontend",
                    allow_blank=False,
                    id="setting-key",
                )
                yield Input(id="setting-value", placeholder="Value; booleans use true/false")
                yield Static("", id="settings-help", classes="muted", markup=False)
            yield Static("", id="settings-error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Close", id="close-settings")
                yield Button("Reset key", id="reset-setting")
                yield Button("Save setting", variant="primary", id="save-setting")

    def on_mount(self):
        table = self.query_one("#settings-table", DataTable)
        table.add_columns("Setting", "Effective value", "Source")
        self.refresh_values()

    def refresh_values(self):
        scope, target = self.query_one("#settings-scope", Select).value.split(":", 1)
        values, sources = self.service.settings(
            target if scope == "workspace" else None, target if scope == "environment" else None
        )
        table = self.query_one("#settings-table", DataTable)
        table.clear()
        for key, value in values.items():
            table.add_row(Text(key), Text(str(value)), Text(sources[key]), key=key)
        key = self.query_one("#setting-key", Select).value
        self.query_one("#setting-value", Input).value = (
            str(values[key]).lower() if isinstance(values[key], bool) else str(values[key])
        )
        self.query_one("#settings-help", Static).update(
            f"Default: {DEFAULTS[key]}  |  Scope: {scope} {target}\nConfig: {self.service.config.path}"
        )

    def on_select_changed(self, event):
        if self.is_mounted and self.query("#settings-table").first().columns:
            self.refresh_values()

    def on_data_table_row_selected(self, event):
        self.query_one("#setting-key", Select).value = event.row_key.value

    def on_button_pressed(self, event):
        event.stop()
        if event.button.id == "close-settings":
            self.dismiss(True)
            return
        try:
            self.query_one("#settings-error", Static).update("")
            key = self.query_one("#setting-key", Select).value
            scope, target = self.query_one("#settings-scope", Select).value.split(":", 1)
            reset = event.button.id == "reset-setting"
            value = (
                None
                if reset
                else parse_overrides([f"{key}={self.query_one('#setting-value', Input).value}"])[
                    key
                ]
            )

            def save():
                self.service.set_setting(key, value, scope, target or None, reset=reset)

            if scope == "user":
                save()
                self.refresh_values()
                self.notify("Setting reset" if reset else "Setting saved")
            else:
                state = self.service.inventory()
                identifier = (
                    self.service.environment(target)["id"]
                    if scope == "environment"
                    else self.service.workspace(target)["environment"]
                )
                members = [
                    w["name"]
                    for w in state["workspaces"].values()
                    if w["environment"] == identifier
                ]
                self.app.push_screen(
                    ReviewScreen(
                        "Review settings change",
                        {
                            "scope": scope,
                            "target": target,
                            "members": members,
                            "key": key,
                            "value": value,
                            "reset": reset,
                        },
                        save,
                    ),
                    lambda _: self.refresh_values(),
                )
        except (DenError, OSError) as error:
            self.query_one("#settings-error", Static).update(str(error))

    def action_cancel(self):
        self.dismiss(False)
