"""Linear terminal interface for plain terminals and assistive tools."""

import json
import shlex
from pathlib import Path

from .config import Configuration, parse_overrides
from .errors import DenError


def plain_setup(service):
    print("Recommended setup. Press Ctrl-C to cancel; no editor starts automatically.")
    current = service.config.effective()
    frontend = (
        input(f"Editor [vscode/cursor] ({current['frontend']}): ").strip() or current["frontend"]
    )
    executable = input(
        f"Executable ({current.get(f'executables.{frontend}', frontend)}): "
    ).strip() or current.get(f"executables.{frontend}", frontend)
    path = Path(input(f"Workspace folder ({Path.cwd()}): ").strip() or Path.cwd()).expanduser()
    name = input(f"Workspace name ({path.name}): ").strip() or path.name
    environment = input("Existing shared environment (blank = new independent): ").strip() or None
    print(
        json.dumps(
            {
                "frontend": frontend,
                "executable": executable,
                "workspace": name,
                "path": str(path),
                "environment": environment or "new independent",
            },
            indent=2,
        )
    )
    if input("Apply setup? [y/N] ").strip().lower() == "y":
        service.setup_workspace(name, path, frontend, executable, environment)
        print("Setup complete. Use open WORKSPACE when ready.")
    else:
        print("Cancelled; nothing was saved.")


def plain_menu(service, initial=None):
    from .cli import command_parser, dispatch, options_parser

    print("Codex Den - plain terminal menu")
    print("Commands: setup | list | open NAME | config show | help | q")
    print("All direct commands are available here. No editor opens automatically.")
    pending = (
        "setup" if initial == "setup" else "config configure" if initial == "settings" else None
    )
    while True:
        try:
            line, pending = (pending, None) if pending else (input("den> ").strip(), None)
            if line in ("q", "quit", "exit"):
                return
            if not line:
                continue
            if line in ("help", "?"):
                command_parser().print_help()
                continue
            if line == "setup":
                plain_setup(service)
                continue
            if line in ("settings", "config configure"):
                values, sources = service.settings()
                print(json.dumps({"values": values, "sources": sources}, indent=2))
                key = input("Setting key (blank = back): ").strip()
                if not key:
                    continue
                raw = input("New value: ")
                value = parse_overrides([f"{key}={raw}"])[key]
                if input(f"Save user setting {key}? [y/N] ").strip().lower() == "y":
                    service.set_setting(key, value)
                    print("Setting saved.")
                continue
            arguments = shlex.split(line)
            extra = []
            if "--" in arguments:
                boundary = arguments.index("--")
                arguments, extra = arguments[:boundary], arguments[boundary + 1 :]
            options, rest = options_parser().parse_known_args(arguments)
            args = command_parser().parse_args(rest)
            if extra and args.command != "open":
                raise DenError("Arguments after -- are supported only by open.")
            if args.command in (None, "menu"):
                continue
            if options.config or options.data_root:
                raise DenError(
                    "Start codex-den with --config/--data-root to change the menu storage context."
                )
            original = service.config
            try:
                overrides = parse_overrides(options.set)
                if options.frontend:
                    if "frontend" in overrides and overrides["frontend"] != options.frontend:
                        raise DenError("Conflicting arguments for frontend.")
                    overrides["frontend"] = options.frontend
                service.config = Configuration(
                    original.path, {**original.overrides, **overrides}, original.explicit
                )
                result = dispatch(service, args, options, extra)
                print(json.dumps(result, indent=2, ensure_ascii=False))
            finally:
                service.config = original
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled; returning to your shell.")
            return
        except (DenError, OSError, ValueError) as error:
            print(f"Error: {error}")
        except SystemExit:
            # argparse help/errors should return to the menu, not exit it.
            continue
