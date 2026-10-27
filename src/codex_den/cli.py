"""Scriptable commands and the interactive entry point share one service layer."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .config import Configuration, parse_overrides
from .errors import DenError
from .service import Service
from .storage import Store


class UniqueValue(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        previous = getattr(namespace, self.dest, None)
        if previous is not None and previous != values:
            parser.error(f"Conflicting values for {option_string}.")
        setattr(namespace, self.dest, values)


def options_parser():
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument(
        "--config", action=UniqueValue, type=Path, help="Explicit TOML configuration file"
    )
    parser.add_argument(
        "--data-root", action=UniqueValue, type=Path, help="Separate managed storage root"
    )
    parser.add_argument("--frontend", action=UniqueValue, choices=["vscode", "cursor"])
    parser.add_argument("--environment", action=UniqueValue, help="Environment name or ID")
    parser.add_argument(
        "--workspace", action=UniqueValue, help="Workspace context for effective settings"
    )
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--plain", action="store_true", help="Linear interactive menu")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--non-interactive", action="store_true", help="Fail rather than prompt")
    parser.add_argument("--yes", action="store_true", help="Confirm an explicit reviewed operation")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing state")
    return parser


def command_parser():
    parser = argparse.ArgumentParser(
        prog="codex-den",
        description="A home for your Codex workspaces. Manage the Codex extension in VS Code or Cursor.",
        allow_abbrev=False,
        parents=[options_parser()],
    )
    parser.add_argument("--version", action="version", version=f"codex-den {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("menu", help="Open the interactive command menu")
    commands.add_parser("list", help="List workspaces, environments and presets")
    inspect = commands.add_parser("inspect", help="Inspect a workspace and its shared state")
    inspect.add_argument("name")
    commands.add_parser("doctor", help="Read-only installation and editor diagnostics")
    opening = commands.add_parser("open", help="Explicitly open an editor workspace")
    opening.add_argument("name")
    setup = commands.add_parser("setup", help="Guided or noninteractive first-time setup")
    setup.add_argument("--path", type=Path)
    setup.add_argument("--name")
    for name in ("update", "uninstall"):
        commands.add_parser(name, help=f"Show safe package-manager {name} instructions")
    completion = commands.add_parser("completion", help="Print shell completion integration")
    completion.add_argument("shell", choices=["bash", "zsh", "fish"])

    environments = commands.add_parser(
        "environment", help="Manage named environments"
    ).add_subparsers(dest="action", required=True)
    create = environments.add_parser("create")
    create.add_argument("name")
    create.add_argument("--preset")
    install = environments.add_parser(
        "install-codex", help="Explicitly install the Codex extension into a managed editor profile"
    )
    install.add_argument("name")
    clone = environments.add_parser("clone")
    clone.add_argument("source")
    clone.add_argument("name")
    remove = environments.add_parser("remove")
    remove.add_argument("name")
    export = environments.add_parser("export")
    export.add_argument("name")
    export.add_argument("--output", required=True, type=Path)
    importing = environments.add_parser("import")
    importing.add_argument("bundle", type=Path)
    importing.add_argument("--name", required=True)
    importing.add_argument("--map", action="append", default=[], metavar="SOURCE=DEST")

    workspaces = commands.add_parser(
        "workspace", help="Register, discover and organize repositories"
    ).add_subparsers(dest="action", required=True)
    add = workspaces.add_parser("add")
    add.add_argument("name")
    add.add_argument("--path", required=True, type=Path)
    discover = workspaces.add_parser("discover")
    discover.add_argument("path", type=Path)
    discover.add_argument("--max-depth", type=int)
    discover.add_argument("--exclude", action="append", default=[])
    discover.add_argument(
        "--register",
        action="append",
        default=[],
        metavar="PATH",
        help="Explicit discovered paths to register",
    )
    switch = workspaces.add_parser("switch")
    switch.add_argument("name")
    detach = workspaces.add_parser("detach")
    detach.add_argument("name")
    detach.add_argument("--new-environment", required=True)
    detach.add_argument("--clone-settings", action="store_true")
    for name in ("favorite", "unfavorite", "remove"):
        item = workspaces.add_parser(name)
        item.add_argument("name")
    workspaces.add_parser("recent")
    workspaces.add_parser("clear-recent")

    presets = commands.add_parser("preset", help="Reusable configuration snapshots").add_subparsers(
        dest="action", required=True
    )
    create = presets.add_parser("create")
    create.add_argument("name")
    create.add_argument("--from-environment", required=True)
    for name in ("inspect", "remove"):
        item = presets.add_parser(name)
        item.add_argument("name")
    presets.add_parser("list")

    configs = commands.add_parser(
        "config", help="Inspect, edit and compare settings"
    ).add_subparsers(dest="action", required=True)
    configs.add_parser("show")
    configs.add_parser("configure")
    for name in ("get", "set", "reset"):
        item = configs.add_parser(name)
        item.add_argument("key")
        if name == "set":
            item.add_argument("value")
        item.add_argument("--scope", choices=["user", "environment", "workspace"], default="user")
        item.add_argument("--target")
    diff = configs.add_parser("diff")
    left = diff.add_mutually_exclusive_group(required=True)
    left.add_argument("--from-environment", dest="source")
    left.add_argument("--from-preset", dest="source_preset")
    right = diff.add_mutually_exclusive_group(required=True)
    right.add_argument("--to-environment", dest="destination")
    right.add_argument("--to-preset", dest="destination_preset")
    importing = commands.add_parser("import", help="Copy selected configuration files or folders")
    importing.add_argument("--from", dest="source", required=True, type=Path)
    importing.add_argument("--include", action="append", default=[])
    importing.add_argument(
        "--replace", action="store_true", help="Back up and replace selected conflicts"
    )
    return parser


def build_service(options):
    overrides = parse_overrides(options.set)
    for key, value in (
        ("frontend", options.frontend),
        ("ui.color", "never" if options.no_color else None),
        ("ui.plain", True if options.plain else None),
    ):
        if value is not None:
            if key in overrides and overrides[key] != value:
                raise DenError(f"Conflicting arguments for {key}.")
            overrides[key] = value
    home = Path.home()
    config_path = (
        options.config
        or Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "codex-den/config.toml"
    )
    data_root = (
        options.data_root
        or Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "codex-den"
    )
    configuration = Configuration(
        config_path, overrides=overrides, explicit=options.config is not None
    )
    configuration.effective()
    return Service(Store(data_root), configuration)


def inventory(service):
    state = service.inventory()
    return {
        "environments": list(state["environments"].values()),
        "workspaces": list(state["workspaces"].values()),
        "presets": sorted(state["presets"]),
    }


def lifecycle(operation):
    return {
        "operation": operation,
        "automatic": False,
        "command": 'uv tool install --force "git+https://github.com/ImanAkrami/codex-den.git@main"'
        if operation == "update"
        else "uv tool uninstall codex-den",
        "pipx_command": 'pipx install --force "git+https://github.com/ImanAkrami/codex-den.git@main"'
        if operation == "update"
        else "pipx uninstall codex-den",
        "note": "Use the package manager that installed this tool. For a local checkout, update the checkout and reinstall from its path. No package registry release exists yet. Configuration, environments, and repositories are retained.",
    }


def confirm(options, description):
    if options.yes or options.dry_run:
        return
    if options.non_interactive or not sys.stdin.isatty():
        raise DenError(
            f"{description}. Review with --dry-run, then confirm the explicit operation with --yes."
        )
    if input(f"{description}\nContinue? [y/N] ").strip().lower() != "y":
        raise DenError("Cancelled; no changes were applied.")


def dispatch(service, args, options, extra):
    command, action = args.command, getattr(args, "action", None)
    if command == "list":
        return inventory(service)
    if command == "inspect":
        return service.inspect(args.name)
    if command == "doctor":
        return service.doctor()
    if command in ("update", "uninstall"):
        return lifecycle(command)
    if command == "open":
        if options.dry_run:
            return service.plan_open(
                args.name, options.frontend, options.environment, extra
            ).public()
        return service.open(args.name, options.frontend, options.environment, extra)
    if command == "environment":
        if action == "install-codex":
            if options.dry_run:
                return {
                    "environment": args.name,
                    "frontend": options.frontend,
                    "extension": "openai.chatgpt",
                }
            confirm(
                options,
                f"Install Codex extension in {args.name}; only its managed editor profile is affected",
            )
            return service.install_codex_extension(args.name, options.frontend)
        if action == "create":
            if options.dry_run:
                return {
                    "create": args.name,
                    "preset": args.preset,
                    "settings": service.config.overrides,
                }
            return service.create_environment(args.name, service.config.overrides, args.preset)
        if action == "clone":
            if options.dry_run:
                return {
                    "clone": args.source,
                    "name": args.name,
                    "files": list(service.snapshot(args.source)["files"]),
                }
            return service.clone_environment(args.source, args.name)
        if action == "export":
            if options.dry_run:
                return {
                    "output": str(args.output),
                    "files": list(service.snapshot(args.name)["files"]),
                }
            return service.export_environment(args.name, args.output)
        if action == "import":
            mappings = {}
            for item in args.map:
                source, separator, target = item.partition("=")
                if (
                    not separator
                    or not source
                    or not target
                    or (source in mappings and mappings[source] != target)
                ):
                    raise DenError("Path mappings use unique SOURCE=DEST assignments.")
                mappings[source] = target
            if options.dry_run:
                return {"name": args.name, **service.preview_bundle(args.bundle, mappings)}
            return service.import_environment(args.bundle, args.name, mappings)
        if action == "remove":
            environment = service.environment(args.name)
            confirm(options, f"Remove environment {environment['name']} and its managed state")
            if not options.dry_run:
                service.remove_environment(args.name)
            return {"removed": args.name, "dry_run": options.dry_run}
    if command == "workspace":
        if action == "add":
            if options.dry_run:
                return {
                    "name": args.name,
                    "path": str(args.path.resolve()),
                    "environment": options.environment or "new independent environment",
                }
            return service.add_workspace(args.name, args.path, options.environment)
        if action == "discover":
            found = service.discover(
                args.path,
                args.max_depth
                if args.max_depth is not None
                else service.config.effective()["discovery.max_depth"],
                args.exclude,
            )
            requested = {str(Path(p).expanduser().resolve()) for p in args.register}
            if requested - {item["path"] for item in found}:
                raise DenError("Requested registration path was not in the discovery results.")
            if requested and not options.dry_run:
                results = []
                for item in found:
                    if item["path"] in requested and not item["registered"]:
                        try:
                            registered = service.add_workspace(
                                item["name"], item["path"], options.environment
                            )
                            results.append({"workspace": registered, "success": True})
                        except DenError as error:
                            results.append(
                                {"path": item["path"], "success": False, "error": str(error)}
                            )
                return {"discovered": found, "registration": results}
            return found
        if action == "switch":
            if not options.environment:
                raise DenError("Switch requires --environment NAME.")
            preview = service.inspect(args.name)
            target = service.environment(options.environment)
            confirm(
                options,
                f"Switch {args.name} from {preview['environment']['name']} to {target['name']}; shared members: {', '.join(preview['members'])}",
            )
            return (
                {"from": preview, "to": target}
                if options.dry_run
                else service.switch_workspace(args.name, options.environment)
            )
        if action == "detach":
            confirm(
                options, f"Detach {args.name} into independent environment {args.new_environment}"
            )
            return (
                {"workspace": args.name, "new_environment": args.new_environment}
                if options.dry_run
                else service.detach_workspace(args.name, args.new_environment, args.clone_settings)
            )
        if action in ("favorite", "unfavorite"):
            if not options.dry_run:
                service.favorite(args.name, action == "favorite")
            return {"workspace": args.name, "favorite": action == "favorite"}
        if action == "recent":
            return service.recent()
        if action == "clear-recent":
            if not options.dry_run:
                service.clear_recent()
            return {"cleared": "recents", "registrations_retained": True}
        if action == "remove":
            confirm(
                options, f"Unregister {args.name}; repository and environment files are retained"
            )
            if not options.dry_run:
                service.remove_workspace(args.name)
            return {"unregistered": args.name}
    if command == "preset":
        if action == "create":
            return (
                {"name": args.name, "files": list(service.snapshot(args.from_environment)["files"])}
                if options.dry_run
                else service.save_preset(args.name, args.from_environment)
            )
        if action == "list":
            return sorted(service.inventory()["presets"])
        if action == "inspect":
            preset = service.inventory()["presets"].get(args.name)
            if preset is None:
                raise DenError("Preset not found.")
            return {
                "name": args.name,
                "settings": preset["settings"],
                "files": list(preset["files"]),
            }
        if action == "remove":
            confirm(options, f"Remove preset {args.name}; existing environments are unchanged")
            if not options.dry_run:
                service.delete_preset(args.name)
            return {"removed": args.name}
    if command == "config":
        if action == "show":
            values, sources = service.settings(options.workspace, options.environment)
            return {"values": values, "sources": sources, "config": str(service.config.path)}
        if action == "get":
            if args.scope != "user":
                if not args.target:
                    raise DenError("Scoped config get requires --target NAME.")
                if options.workspace or options.environment:
                    raise DenError(
                        "Choose either --scope/--target or --workspace/--environment context, not both."
                    )
                values, sources = service.settings(
                    workspace=args.target if args.scope == "workspace" else None,
                    environment=args.target if args.scope == "environment" else None,
                )
            else:
                if args.target:
                    raise DenError(
                        "User settings have no --target; choose an environment or workspace scope."
                    )
                values, sources = service.settings(options.workspace, options.environment)
            if args.key not in values:
                raise DenError("Unknown setting; use config show.")
            return {"key": args.key, "value": values[args.key], "source": sources[args.key]}
        if action in ("set", "reset"):
            value = (
                parse_overrides([f"{args.key}={args.value}"])[args.key] if action == "set" else None
            )
            if args.scope != "user":
                confirm(
                    options,
                    f"Change {args.scope} settings for {args.target}; other shared workspaces may be affected",
                )
            if not options.dry_run:
                service.set_setting(
                    args.key, value, args.scope, args.target, reset=action == "reset"
                )
            return {
                "key": args.key,
                "scope": args.scope,
                "target": args.target,
                "operation": action,
                "value": value,
            }
        if action == "diff":
            return service.compare(
                args.source or args.source_preset,
                args.destination or args.destination_preset,
                bool(args.source_preset),
                bool(args.destination_preset),
            )
    if command == "import":
        if not options.environment:
            raise DenError("Import requires --environment NAME.")
        preview = service.import_files(options.environment, args.source, args.include, dry_run=True)
        if options.dry_run:
            return preview
        if args.replace:
            confirm(
                options, "Replace selected configuration conflicts in the destination environment"
            )
        return service.import_files(
            options.environment, args.source, args.include, replace=args.replace
        )
    if command == "setup":
        if not args.path or not args.name or not options.frontend:
            raise DenError(
                "Noninteractive setup requires --path, --name and --frontend. Run setup in a terminal for the wizard."
            )
        # Resolve the editor before any state changes.
        from .launch import resolve_executable

        resolve_executable(service.config.effective()[f"executables.{options.frontend}"])
        if options.dry_run:
            return {
                "name": args.name,
                "path": str(args.path.resolve()),
                "frontend": options.frontend,
                "environment": options.environment or "new",
            }
        result = service.setup_workspace(
            args.name,
            args.path,
            options.frontend,
            service.config.effective()[f"executables.{options.frontend}"],
            options.environment,
        )
        return {
            "workspace": result,
            "next": f"codex-den open {args.name}",
            "editor_launched": False,
        }
    raise DenError("Choose a command; see codex-den --help.")


def shell_completion(shell):
    words = "menu setup open list inspect doctor environment workspace preset config import update uninstall completion"
    if shell == "bash":
        return f'_codex_den_complete() {{ COMPREPLY=( $(compgen -W "{words}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}\ncomplete -F _codex_den_complete codex-den'
    if shell == "zsh":
        return f'#compdef codex-den\n_arguments "1:command:({words})"'
    return "\n".join(f"complete -c codex-den -f -a {word}" for word in words.split())


def main(argv=None):
    original = list(sys.argv[1:] if argv is None else argv)
    head, extra = original, []
    if "--" in head:
        boundary = head.index("--")
        head, extra = head[:boundary], head[boundary + 1 :]
    parser = command_parser()
    options, remaining = options_parser().parse_known_args(head)
    args = parser.parse_args(remaining)
    if not head and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        parser.print_help()
        return 0
    if args.command == "completion":
        print(shell_completion(args.shell))
        return 0
    if extra and args.command != "open":
        parser.error("arguments after -- are supported only by open")
    try:
        service = build_service(options)
        interactive = (
            args.command in (None, "menu")
            or (args.command == "setup" and not args.path)
            or (args.command == "config" and args.action == "configure")
        )
        if interactive:
            if options.dry_run:
                raise DenError(
                    "Interactive menus do not support --dry-run. Use a direct command to preview changes without writing state."
                )
            if options.non_interactive or not sys.stdin.isatty() or not sys.stdout.isatty():
                raise DenError(
                    "This action needs an interactive terminal. Use direct commands or complete setup arguments."
                )
            from .ui import launch_ui

            launch_ui(
                service,
                plain=options.plain,
                initial="setup"
                if args.command == "setup"
                else "settings"
                if args.command == "config"
                else None,
            )
            return 0
        result = dispatch(service, args, options, extra)
        if options.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            from rich.console import Console

            Console(no_color=options.no_color or bool(os.environ.get("NO_COLOR"))).print_json(
                data=result
            )
        return 0
    except DenError as error:
        print(f"codex-den: {error}", file=sys.stderr)
        return error.exit_code
    except (OSError, ValueError) as error:
        print(
            f"codex-den: operation failed ({type(error).__name__}). Check paths, permissions and available disk space; run doctor.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("codex-den: cancelled.", file=sys.stderr)
        return 130
