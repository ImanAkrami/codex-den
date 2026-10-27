"""Capture real application screens using disposable demonstration data.

SVG: uv run scripts/screenshots.py
PNG: uv run --with cairosvg==2.9.1 scripts/screenshots.py --png

CairoSVG is an optional capture tool, not a runtime dependency. Synthetic display
paths replace temporary directories so no workstation paths enter public assets.
"""

import argparse
import asyncio
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from rich.text import Text
from textual.widgets import Input, Select, Static

from codex_den.config import Configuration
from codex_den.service import Service
from codex_den.storage import Store
from codex_den.ui import DenApp

OUTPUT = Path(__file__).resolve().parents[1] / "docs/images"


class DemoService(Service):
    def inspect(self, name):
        result = super().inspect(name)
        actual = str(self.store.root)
        display = "/home/demo/.local/share/codex-den"
        result["workspace"] = {**result["workspace"], "path": f"/home/demo/projects/{name}"}
        result["codex_home"] = result["codex_home"].replace(actual, display)
        result["editors"] = {
            editor: {key: value.replace(actual, display) for key, value in paths.items()}
            for editor, paths in result["editors"].items()
        }
        return result


async def capture(png=False):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codex-den-demo-") as temporary:
        home = Path(temporary)
        os.environ["HOME"] = temporary
        os.environ.pop("CODEX_HOME", None)
        for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
            os.environ.pop(key, None)
        binary_dir = home / "bin"
        binary_dir.mkdir()
        for name in ("code-demo", "cursor-demo"):
            binary = binary_dir / name
            binary.write_text("#!/bin/sh\nexit 0\n")
            binary.chmod(0o700)
        os.environ["PATH"] = f"{binary_dir}:{os.environ.get('PATH', '')}"
        config = Configuration(
            home / ".config/codex-den/config.toml", {"ui.color": "always", "ui.motion": False}
        )
        config.save("frontend", "cursor")
        config.save("executables.cursor", "cursor-demo")
        config.save("executables.vscode", "code-demo")
        service = DemoService(Store(home / ".local/share/codex-den"), config)
        with patch(
            "codex_den.service.uuid.uuid4", side_effect=[uuid.UUID(int=1), uuid.UUID(int=2)]
        ):
            service.create_environment("work", {"frontend": "cursor"})
            service.create_environment("personal", {"frontend": "vscode"})
        for name, environment in (("api", "work"), ("web", "work"), ("notes", "personal")):
            repo = home / "projects" / name
            repo.mkdir(parents=True)
            service.add_workspace(name, repo, environment)
        service.favorite("api")
        template = home / "templates/team"
        (template / "skills/code-review").mkdir(parents=True)
        (template / "AGENTS.md").write_text("Follow the repository conventions.\n")
        (template / "skills/code-review/SKILL.md").write_text(
            "Review behavior and failure recovery.\n"
        )
        app = DenApp(service)

        async def save(name, pilot):
            for widget in app.screen.query(Static):
                if widget.id in ("brand", "details"):
                    continue
                value = str(widget.render())
                if temporary in value:
                    widget.update(Text(value.replace(temporary, "/home/demo")))
            for widget in app.screen.query(Input):
                widget.value = widget.value.replace(temporary, "/home/demo")
            await pilot.pause()
            screenshot = app.export_screenshot(title="Codex Den")
            screenshot = "\n".join(line.rstrip() for line in screenshot.splitlines()) + "\n"
            assert temporary not in screenshot
            path = OUTPUT / f"{name}.svg"
            path.write_text(screenshot)
            if png:
                import cairosvg

                cairosvg.svg2png(
                    bytestring=screenshot.encode(), write_to=str(path.with_suffix(".png"))
                )

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Workspace labels come from inventory, so give them display-only paths.
            with service.store.transaction() as state:
                for name, item in state["workspaces"].items():
                    item["path"] = f"/home/demo/projects/{name}"
            app.refresh_dashboard()
            await save("dashboard", pilot)
            app.action_setup()
            await pilot.pause()
            await save("setup", pilot)
            await pilot.press("escape")
            app.action_import()
            await pilot.pause()
            app.screen.query_one("#import-environment", Select).value = "work"
            app.screen.query_one("#import-source", Input).value = str(template)
            await pilot.click("#scan-files")
            await pilot.press("space", "down", "space")
            assert set(app.screen.query_one("#import-files").selected) == {"AGENTS.md", "skills"}
            await pilot.resize_terminal(120, 44)
            await save("import", pilot)
            await pilot.press("escape")
            await pilot.resize_terminal(120, 46)
            app.action_settings()
            await pilot.pause()
            await save("settings", pilot)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--png", action="store_true", help="Also render PNGs using optional CairoSVG"
    )
    asyncio.run(capture(parser.parse_args().png))
