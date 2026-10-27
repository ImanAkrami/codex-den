# Troubleshooting

## Command not found

Run `uv tool dir --bin` to locate the installation directory, then add it to PATH using your shell's normal configuration. Reopen the terminal. `uv tool list` shows installed tools. See [installation](installation.md).

## Editor not found or wrong executable

```sh
codex-den doctor
codex-den config set executables.cursor /path/to/cursor
codex-den config set executables.vscode /path/to/code
```

Use an executable installed for your editor. A wrapper may reference a removed AppImage; diagnostics can identify common cases. Opening and extension installation are explicit operations, so installation alone does not establish editor readiness.

## No Codex extension in an environment

Each environment has its own editor extension directory. Install the extension into the selected environment:

```sh
codex-den environment install-codex work --frontend cursor --yes
```

Open the workspace and sign in through the extension. Extension availability and account behavior depend on upstream applications; consult [compatibility](compatibility.md).

## Shared changes affect another project

Workspaces in one environment share its settings, extensions, Codex home, and per-editor profile. Run `codex-den inspect NAME` to review members. Detach a workspace to create an independent environment before making separate changes.

## State is busy or an environment is active

Wait for the current operation and close all editor sessions using the environment. Do not remove lock files to bypass an active operation; locks are kernel-owned. If a recovery path is reported after a failed copy, retain it and restore deliberately from the reported backup.

## Bundle import needs path mappings

Preview with `--dry-run`, then pass an explicit `--map SOURCE=DEST` for each machine-specific path. Destinations must exist. Resolve mappings in both configuration keys and values. File contents, credentials, symlinks, schema, and size constraints still apply.

## Terminal layout or motion

Try `codex-den --plain`, enlarge the terminal, or set `ui.motion=false`. Escape closes a dropdown before its dialog. Long forms scroll as focus moves. Appearance settings apply when the menu restarts.

## Report a problem

Include version, Linux/terminal/editor versions, minimal reproduction, expected/actual behavior, and reviewed `doctor --json` output. Never attach authentication files, session databases, whole homes, or unreviewed bundles. Use [Issues](https://github.com/ImanAkrami/codex-den/issues) for bugs and [private security reporting](../SECURITY.md) for vulnerabilities.
