"""Three-step setup: editor, workspace, review. No automatic editor launch."""

from pathlib import Path

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from .errors import DenError
from .launch import resolve_executable
from .ui_effects import DialogScreen


class SetupScreen(DialogScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, service):
        super().__init__()
        self.service, self.step = service, 0

    def compose(self):
        values = self.service.config.effective()
        detected = self.service.doctor()["editors"]
        available = [e["frontend"] for e in detected if e["available"]]
        saved = self.service.config.saved()
        selected = (
            self.service.config.overrides.get("frontend")
            or saved.get("frontend")
            or (available[0] if len(available) == 1 else Select.BLANK)
        )
        state = self.service.inventory()
        environments = [("New independent environment", "")] + [
            (f"Share {e['name']}", e["name"]) for e in state["environments"].values()
        ]
        presets = [("Clean defaults", "")] + [(name, name) for name in state["presets"]]
        with Vertical(classes="dialog wizard-dialog"):
            yield Label("Make yourself at home", classes="dialog-title", markup=False)
            yield Static("", id="wizard-progress", classes="muted", markup=False)
            with VerticalScroll(classes="wizard-content"):
                with Vertical(id="step-editor"):
                    yield Label("01 / Choose your editor", classes="section-title", markup=False)
                    yield Static(
                        "Recommended setup uses sensible defaults. Pick the editor for the Codex extension; nothing opens until you choose Open.",
                        classes="muted",
                        markup=False,
                    )
                    yield Select(
                        [("Cursor", "cursor"), ("VS Code", "vscode")],
                        value=selected,
                        id="setup-frontend",
                    )
                    yield Static(
                        "\n".join(
                            f"{e['frontend']}: {e['executable'] or 'not detected'}"
                            for e in detected
                        ),
                        id="editor-readiness",
                        markup=False,
                    )
                    yield Checkbox("Advanced: choose an explicit executable", id="setup-advanced")
                    yield Input(
                        values[f"executables.{selected}"] if selected is not Select.BLANK else "",
                        placeholder="/path/to/editor",
                        id="setup-executable",
                    )
                    yield Static(
                        f"Managed storage: {self.service.store.root}\nConfiguration: {self.service.config.path}\nUse --data-root / --config when starting setup to choose alternate locations.",
                        classes="muted",
                        markup=False,
                    )
                with Vertical(id="step-workspace"):
                    yield Label(
                        "02 / Register your workspace", classes="section-title", markup=False
                    )
                    yield Label("Readable name", markup=False)
                    yield Input(Path.cwd().name, id="setup-name")
                    yield Label("Repository or folder", markup=False)
                    yield Input(str(Path.cwd()), id="setup-path")
                    yield Label("Environment", markup=False)
                    yield Select(environments, value="", allow_blank=False, id="setup-environment")
                    yield Label("Preset for a new environment (optional)", markup=False)
                    yield Select(presets, value="", allow_blank=False, id="setup-preset")
                    yield Static(
                        "Shared environments reuse the Codex home, settings, extensions and per-editor profile for every member.",
                        classes="muted",
                        markup=False,
                    )
                with Vertical(id="step-review"):
                    yield Label("03 / Review your setup", classes="section-title", markup=False)
                    yield Static("", id="setup-summary", markup=False)
                    yield Static(
                        "Register this workspace and save your editor preference. Choose Open from the dashboard when you are ready.",
                        classes="muted",
                        markup=False,
                    )
            yield Static("", id="setup-error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Back", id="back")
                yield Button("Continue", variant="primary", id="next")

    def on_mount(self):
        # Repeated Next presses must not be swallowed by the button flash animation.
        self.query_one("#next", Button).active_effect_duration = 0
        self.show_step()

    def show_step(self):
        self.query_one("#setup-error", Static).update("")
        for index, selector in enumerate(("#step-editor", "#step-workspace", "#step-review")):
            self.query_one(selector).display = self.step == index
        self.query_one("#wizard-progress", Static).update(
            f"RECOMMENDED SETUP   /   {self.step + 1} OF 3"
        )
        self.query_one("#back", Button).disabled = self.step == 0
        self.query_one("#next", Button).label = "Finish setup" if self.step == 2 else "Continue"
        self.query_one("#setup-executable").display = self.query_one(
            "#setup-advanced", Checkbox
        ).value

    def on_checkbox_changed(self, event):
        if event.checkbox.id == "setup-advanced":
            self.query_one("#setup-executable").display = event.value

    def on_select_changed(self, event):
        if event.select.id == "setup-frontend" and event.value is not Select.BLANK:
            self.query_one("#setup-executable", Input).value = self.service.config.effective()[
                f"executables.{event.value}"
            ]

    def choices(self):
        frontend = self.query_one("#setup-frontend", Select).value
        if frontend is Select.BLANK:
            raise DenError(
                "Choose Cursor or VS Code. If neither is detected, install one or provide its executable under Advanced."
            )
        executable = (
            self.query_one("#setup-executable", Input).value
            if self.query_one("#setup-advanced", Checkbox).value
            else self.service.config.effective()[f"executables.{frontend}"]
        )
        resolve_executable(executable)
        name = self.query_one("#setup-name", Input).value
        path = Path(self.query_one("#setup-path", Input).value).expanduser().resolve()
        environment = self.query_one("#setup-environment", Select).value or None
        preset = self.query_one("#setup-preset", Select).value or None
        if self.step > 0:
            self.service.validate_name(name)
            if not path.is_dir():
                raise DenError("Choose an existing workspace directory.")
            if environment and preset:
                raise DenError(
                    "Presets apply to new environments. Choose Clean defaults when joining an existing environment."
                )
        return frontend, executable, name, path, environment, preset

    def on_button_pressed(self, event):
        event.stop()
        try:
            if event.button.id == "cancel":
                self.dismiss(False)
            elif event.button.id == "back":
                self.step = max(0, self.step - 1)
                self.show_step()
            elif event.button.id == "next":
                frontend, executable, name, path, environment, preset = self.choices()
                if self.step < 2:
                    self.step += 1
                    if self.step == 2:
                        members = [
                            w["name"]
                            for w in self.service.inventory()["workspaces"].values()
                            if environment
                            and w["environment"] == self.service.environment(environment)["id"]
                        ]
                        self.query_one("#setup-summary", Static).update(
                            f"Workspace: {name}\nPath: {path}\nEditor: {frontend}\nExecutable: {executable}\nEnvironment: {environment or 'new independent environment'}\nExisting shared members: {', '.join(members) or 'none'}\nPreset: {preset or 'clean defaults'}"
                        )
                    self.show_step()
                else:
                    self.service.setup_workspace(
                        name, path, frontend, executable, environment, preset
                    )
                    self.notify("Setup complete. Select the workspace and choose Open when ready.")
                    self.dismiss(True)
        except (DenError, OSError) as error:
            self.query_one("#setup-error", Static).update(str(error))

    def action_cancel(self):
        self.dismiss(False)
