"""Reusable operation forms, explicit change review, and selective import UI."""

import json
from pathlib import Path

from rich.text import Text
from textual import work
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Label, Select, SelectionList, Static, TextArea

from .errors import DenError
from .transfers import safe_relative
from .ui_effects import DialogScreen


class ReviewScreen(DialogScreen):
    BINDINGS = [("escape", "cancel", "Back")]

    def __init__(self, title, preview, operation=None):
        super().__init__()
        self.heading, self.preview, self.operation = title, preview, operation
        self.applied = False

    def compose(self):
        with Vertical(classes="dialog review"):
            yield Label(self.heading, classes="dialog-title", markup=False)
            yield Static(
                "Review the target, shared members, and changes before applying.",
                classes="muted",
                markup=False,
            )
            yield TextArea(
                json.dumps(self.preview, indent=2, ensure_ascii=False),
                read_only=True,
                id="review-content",
                soft_wrap=True,
            )
            yield Static("", id="operation-error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Back" if self.operation else "Close", id="cancel")
                if self.operation:
                    yield Button("Confirm changes", variant="primary", id="confirm")

    def on_mount(self):
        if self.operation:
            # Disabled state and the Applying label already communicate progress.
            # A lingering click flash must not swallow a fast retry after failure.
            self.query_one("#confirm", Button).active_effect_duration = 0

    def on_button_pressed(self, event):
        event.stop()
        if event.button.id == "cancel":
            self.dismiss(self.applied)
        elif event.button.id == "confirm":
            event.button.disabled = True
            event.button.label = "Applying…"
            self.query_one("#cancel", Button).disabled = True
            self.apply_operation()

    @work(thread=True, exclusive=True)
    def apply_operation(self):
        try:
            result = self.operation()
        except (DenError, OSError, ValueError) as error:
            self.app.call_from_thread(self.show_error, error)
        else:
            self.app.call_from_thread(self.finish, result)

    def show_error(self, error):
        message = (
            str(error)
            if isinstance(error, DenError)
            else "Operation failed. Check paths/permissions and retry; existing state was retained where possible."
        )
        self.query_one("#operation-error", Static).update(message)
        self.query_one("#cancel", Button).disabled = False
        self.query_one("#confirm", Button).disabled = False
        self.query_one("#confirm", Button).label = "Retry changes"

    def finish(self, result):
        self.applied = True
        if isinstance(result, list) and any(
            isinstance(item, dict) and item.get("success") is False for item in result
        ):
            self.query_one("#review-content", TextArea).load_text(json.dumps(result, indent=2))
            self.query_one("#operation-error", Static).update(
                "Some registrations failed. Successful registrations were retained; review each result."
            )
            self.query_one("#confirm", Button).display = False
            self.query_one("#cancel", Button).disabled = False
            self.query_one("#cancel", Button).label = "Close results"
            return
        self.app.notify("Changes applied", severity="information")
        self.dismiss(True)

    def action_cancel(self):
        if not self.workers:
            self.dismiss(False)


class FormScreen(DialogScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, title, description, fields, prepare):
        super().__init__()
        self.heading, self.description = title, description
        self.fields, self.prepare = fields, prepare

    def compose(self):
        with Vertical(classes="dialog form-dialog"):
            yield Label(self.heading, classes="dialog-title", markup=False)
            yield Static(self.description, classes="muted", markup=False)
            with VerticalScroll(classes="form-fields"):
                for key, label, default, choices in self.fields:
                    yield Label(label, markup=False)
                    if choices is not None:
                        yield Select(choices, value=default, allow_blank=False, id=f"field-{key}")
                    else:
                        yield Input(str(default), id=f"field-{key}")
            yield Static("", id="form-error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Preview", variant="primary", id="preview")

    def values(self):
        return {key: self.query_one(f"#field-{key}").value for key, *_ in self.fields}

    def on_button_pressed(self, event):
        event.stop()
        if event.button.id == "cancel":
            self.dismiss(False)
            return
        if event.button.id == "preview":
            try:
                preview, operation = self.prepare(self.values())
                self.app.push_screen(ReviewScreen(self.heading, preview, operation), self.completed)
            except (DenError, ValueError, OSError) as error:
                self.query_one("#form-error", Static).update(str(error))

    def completed(self, applied):
        if applied:
            self.dismiss(True)

    def action_cancel(self):
        self.dismiss(False)


class ImportScreen(DialogScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, service):
        super().__init__()
        self.service = service
        self.source = None

    def compose(self):
        choices = [
            (e["name"], e["name"]) for e in self.service.inventory()["environments"].values()
        ]
        with Vertical(classes="dialog import-dialog"):
            yield Label("Import selected configuration", classes="dialog-title", markup=False)
            yield Static(
                "Copy a snapshot. Credentials and history are excluded. Scan first, then choose exactly what to copy.",
                classes="muted",
                markup=False,
            )
            with VerticalScroll(classes="picker-content"):
                yield Label(
                    "Destination environment (all its workspaces share these settings)",
                    markup=False,
                )
                yield Select(
                    choices,
                    value=choices[0][1] if choices else Select.BLANK,
                    id="import-environment",
                )
                yield Label("Source folder", markup=False)
                yield Input(placeholder="/path/to/your/template", id="import-source")
                yield Button("Scan files", id="scan-files")
                yield SelectionList(id="import-files")
                yield Checkbox("Replace conflicts (default: keep destination)", id="import-replace")
            yield Static("", id="import-error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Preview selection", variant="primary", id="preview-import")

    def on_button_pressed(self, event):
        event.stop()
        try:
            if event.button.id == "cancel":
                self.dismiss(False)
            elif event.button.id == "scan-files":
                source = Path(self.query_one("#import-source", Input).value).expanduser().resolve()
                if not source.is_dir():
                    raise DenError("Choose an existing source folder.")
                picker = self.query_one("#import-files", SelectionList)
                picker.clear_options()
                for child in sorted(source.iterdir()):
                    try:
                        safe_relative(child.name)
                    except DenError:
                        continue
                    if not child.is_symlink() and not child.name.startswith("."):
                        picker.add_option(
                            (
                                Text(f"{child.name}{'/' if child.is_dir() else ''}"),
                                child.name,
                                False,
                            )
                        )
                self.source = source
                if picker.option_count:
                    picker.highlighted = 0
                    picker.focus()
            elif event.button.id == "preview-import":
                if self.source is None or str(self.source) != str(
                    Path(self.query_one("#import-source", Input).value).expanduser().resolve()
                ):
                    raise DenError("Scan the selected source folder first.")
                environment = self.query_one("#import-environment", Select).value
                if environment is Select.BLANK:
                    raise DenError("Create or choose a destination environment first.")
                selected = self.query_one("#import-files", SelectionList).selected
                replace = self.query_one("#import-replace", Checkbox).value
                preview = self.service.import_files(
                    environment, self.source, selected, dry_run=True
                )
                members = [
                    w["name"]
                    for w in self.service.inventory()["workspaces"].values()
                    if w["environment"] == self.service.environment(environment)["id"]
                ]

                def operation():
                    return self.service.import_files(
                        environment, self.source, selected, replace=replace
                    )

                self.app.push_screen(
                    ReviewScreen(
                        "Review configuration import",
                        {
                            "environment": environment,
                            "members": members,
                            "replace": replace,
                            "files": preview,
                        },
                        operation,
                    ),
                    self.completed,
                )
        except (DenError, OSError, ValueError) as error:
            self.query_one("#import-error", Static).update(str(error))

    def completed(self, applied):
        if applied:
            self.dismiss(True)

    def action_cancel(self):
        self.dismiss(False)


class DiscoveryScreen(DialogScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, service):
        super().__init__()
        self.service = service
        self.found = []

    def compose(self):
        choices = [("Independent environment for each repo", "")] + [
            (f"Share: {e['name']}", e["name"])
            for e in self.service.inventory()["environments"].values()
        ]
        with Vertical(classes="dialog import-dialog"):
            yield Label("Discover repositories", classes="dialog-title", markup=False)
            yield Static(
                "Scan a chosen projects folder. Select repositories to register; scanning never changes their files.",
                classes="muted",
                markup=False,
            )
            with VerticalScroll(classes="picker-content"):
                yield Input(str(Path.cwd().parent), id="discovery-root")
                yield Select(
                    [(str(n), n) for n in range(1, 21)],
                    value=self.service.config.effective()["discovery.max_depth"],
                    allow_blank=False,
                    id="discovery-depth",
                )
                yield Button("Scan repositories", id="scan-repositories")
                yield SelectionList(id="discovered")
                yield Select(choices, value="", allow_blank=False, id="discovery-environment")
            yield Static("", id="discovery-error", classes="error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Preview registration", variant="primary", id="register-discovered")

    def on_button_pressed(self, event):
        event.stop()
        try:
            if event.button.id == "cancel":
                self.dismiss(False)
            elif event.button.id == "scan-repositories":
                self.found = self.service.discover(
                    self.query_one("#discovery-root", Input).value,
                    self.query_one("#discovery-depth", Select).value,
                )
                picker = self.query_one("#discovered", SelectionList)
                picker.clear_options()
                for item in self.found:
                    if not item["registered"]:
                        picker.add_option(
                            (Text(f"{item['name']} — {item['path']}"), item["path"], False)
                        )
                if picker.option_count:
                    picker.highlighted = 0
                    picker.focus()
            elif event.button.id == "register-discovered":
                selected = self.query_one("#discovered", SelectionList).selected
                if not selected:
                    raise DenError("Select at least one discovered repository.")
                environment = self.query_one("#discovery-environment", Select).value or None
                items = [item for item in self.found if item["path"] in selected]

                def register():
                    results = []
                    for item in items:
                        try:
                            results.append(
                                {
                                    "workspace": self.service.add_workspace(
                                        item["name"], item["path"], environment
                                    ),
                                    "success": True,
                                }
                            )
                        except DenError as error:
                            results.append(
                                {"path": item["path"], "success": False, "error": str(error)}
                            )
                    return results

                self.app.push_screen(
                    ReviewScreen(
                        "Review workspace registration",
                        {"repositories": items, "environment": environment or "new per repository"},
                        register,
                    ),
                    self.completed,
                )
        except (DenError, OSError, ValueError) as error:
            self.query_one("#discovery-error", Static).update(str(error))

    def completed(self, applied):
        if applied:
            self.dismiss(True)

    def action_cancel(self):
        self.dismiss(False)
