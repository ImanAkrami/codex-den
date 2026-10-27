# CLI reference — 0.1.0a1

Codex Den is an early Linux alpha for the Codex extension inside VS Code and Cursor. `codex-den --help` and subcommand `--help` describe the installed parser. No-argument invocation opens the terminal UI on a terminal and prints help on noninteractive streams.

## Terminal navigation

Use Tab/Shift-Tab to move between controls and arrow keys to navigate lists. Enter opens a dropdown or activates a button; Escape closes an expanded dropdown first, then closes its dialog on a second press. After scanning configuration files or repositories, the results receive focus: use arrows and Space to choose items, then Preview and Confirm to apply.

The dashboard offers `/` to search, `n` to register, `s` for settings, Ctrl-N for setup, `o` to open the selected workspace, and `q` to quit. Favorites and Recent stay available in the workspace filter at narrow widths. Long forms scroll as focus moves; dialog action buttons stay visible. Use `--plain` for a linear interface. See [testing](testing.md) for automated coverage and [compatibility](compatibility.md) for terminal sizes.

## Common options

Common options may appear before or after subcommands, but before the editor argument boundary `--`:

| Option | Effect |
| --- | --- |
| `--config PATH` | Read an explicitly chosen TOML configuration; missing/invalid files fail |
| `--data-root PATH` | Select a separate registry and managed storage; does not migrate existing state |
| `--frontend vscode\|cursor` | Override the editor for this invocation |
| `--environment NAME_OR_ID` | Select an existing environment where the command supports it |
| `--workspace NAME` | Workspace context for inspecting effective configuration |
| `--set KEY=VALUE` | Repeatable typed temporary setting override |
| `--json` | JSON output without decorations |
| `--plain` | Linear interactive menu |
| `--no-color` | Disable color; `NO_COLOR` is respected |
| `--non-interactive` | Fail rather than ask a question |
| `--dry-run` | Preview supported direct commands without writing state |
| `--yes` | Confirm the explicitly targeted operation; does not grant unrelated overwrites |

Bundle-import dry runs validate archive integrity and show source-machine paths that need explicit mapping before apply. Environment/workspace creation previews do not perform every filesystem mutation check. Diagnostics and `config show` remain write-free.

Invocation arguments override workspace preferences, then environment preferences, then user configuration, then defaults. An environment selected for a one-time open does not reassign the workspace. Saved changes use `config set/reset` or explicit creation/registration/switch operations.

## Settings schema

TOML configuration is optional. Example:

```toml
schema_version = 1
frontend = "cursor"

[executables]
vscode = "code"
cursor = "/usr/bin/cursor"

[ui]
color = "auto"
theme = "dark"
motion = true
plain = false
ascii = false

[discovery]
max_depth = 3
```

| Key | Default | Allowed value |
| --- | --- | --- |
| `frontend` | `vscode` | `vscode`, `cursor` |
| `executables.vscode` | `code` | Nonempty literal executable path/name |
| `executables.cursor` | `cursor` | Nonempty literal executable path/name |
| `ui.color` | `auto` | `auto`, `never`, `always` |
| `ui.theme` | `dark` | `dark`, `light` |
| `ui.motion` | `true` | Boolean; plain/no-color modes suppress motion |
| `ui.plain` | `false` | Boolean |
| `ui.ascii` | `false` | Boolean; selects the ASCII/plain interface |
| `discovery.max_depth` | `3` | Integer 1–20 |

`--set` string values are literal; booleans and integers use TOML typing. This alpha has no list-valued settings. Equivalent duplicate overrides are allowed; contradictory overrides and unknown keys fail. Known values and source layers are shown by `config show`.

```bash
codex-den config show --workspace repo1 --json
codex-den config get frontend
codex-den config set frontend cursor --scope user
codex-den config set frontend vscode --scope environment --target work --yes
codex-den config reset frontend --scope workspace --target repo1 --yes
codex-den config configure
```

Shared changes require review/confirmation. Reset removes the selected preference only; it does not delete profiles, histories, or registrations. Malformed configurations are retained and reported; they are not silently replaced.

## Setup and opening

```bash
codex-den setup
codex-den setup --path /path/to/repo --name repo --frontend cursor --non-interactive
codex-den environment install-codex work --frontend cursor --yes
codex-den open repo --frontend cursor -- --new-window
codex-den open repo --environment review --dry-run --json
```

The wizard offers editor selection, workspace/environment selection, optional presets and executable customization, and a final summary. Storage locations can be selected when starting the wizard using `--data-root` and `--config`. Rerunning setup retains existing registrations. Opening is explicit, and recency records a successful launch request, not proof that a detached GUI finished starting.

Editor arguments after `--` are preserved as argv without shell evaluation. Profile, extension-directory, and user-data flags are reserved, including abbreviations/equal forms. Child processes receive only their environment's `CODEX_HOME`; inherited VS Code/Cursor routing variables are removed without changing the parent process.

The alpha does not automatically install editors or the Codex extension. Use the explicit managed-profile extension-install action after creating an environment. Actual extension availability in each editor requires runtime validation.

## Environments, workspaces and presets

```bash
codex-den environment create work --frontend cursor
codex-den environment create another --preset work-preset
codex-den environment clone work review
codex-den workspace add repo1 --path /path/to/repo1 --environment work
codex-den workspace add repo2 --path /path/to/repo2 --environment work
codex-den workspace switch repo1 --environment review --dry-run
codex-den workspace switch repo1 --environment review --yes
codex-den workspace detach repo2 --new-environment private --clone-settings --yes
codex-den workspace favorite repo1
codex-den workspace unfavorite repo1
codex-den workspace recent
codex-den workspace clear-recent
codex-den workspace remove repo1 --yes
codex-den environment remove review --yes
codex-den preset create work-preset --from-environment work
codex-den preset list
codex-den preset inspect work-preset
codex-den preset remove work-preset --yes
```

Removing a workspace retains its repository and environment. Removing an environment deletes its managed state and refuses registered members or detected active processes. Process detection currently inspects Linux process command lines and cannot guarantee detection of every detached/editor extension process. Do not reconfigure/remove state with an editor using it.

Clones/presets copy selected supported configuration, instructions, skills, editor settings, and extension-manifest metadata. They exclude auth/history/runtime state and do not link back to the source. Editing a preset does not change previously created environments; preset replacement currently uses explicit removal and recreation.

## Discovery and comparison

```bash
codex-den workspace discover /path/to/projects --max-depth 3
codex-den workspace discover /path/to/projects --register /path/to/projects/repo1 --environment work
codex-den config diff --from-environment work --to-environment review
codex-den config diff --from-preset work-preset --to-environment review
```

Discovery is bounded and read-only until explicit registration. It skips symlinks and known state/cache directories. Bulk registration reports successes/failures individually, retains successful registrations, and does not launch editors. The UI provides multi-selection. Comparison is read-only and excludes known structured secret fields and authentication/session files.

## Selected imports and portable bundles

```bash
codex-den import --environment work --from /path/to/template --include skills --include AGENTS.md --dry-run
codex-den import --environment work --from /path/to/template --include skills --include AGENTS.md
codex-den import --environment work --from /path/to/template --include config.toml --replace --yes
codex-den environment export work --output /path/to/work.den
codex-den environment import /path/to/work.den --name imported-work --dry-run
codex-den environment import /path/to/work.den --name imported-work --map /old/tool=/new/tool
```

Imports keep destination conflicts unless replacement is explicit. Sources are unchanged; failed apply/registry writes restore overwritten destination content. Portable ZIP bundles have a versioned manifest and per-file SHA-256 checks. Limits: 2,000 payload files, 4 MiB per file or manifest, 32 MiB total uncompressed payload. Integrity checks detect corruption; they do not authenticate who created the bundle.

Supported snapshot paths are Codex `config.toml`, `AGENTS.md`, `instructions.md`, `skills/`, each editor's `User/settings.json` and `User/keybindings.json`, and optional extension manifest metadata. Editor settings/keybindings accept JSONC comments and trailing commas and are normalized to JSON when transferred. Extension binaries are never bundled or installed on import.

Known secret fields are removed from structured TOML/JSON, and sensitive/runtime paths are excluded. Arbitrary text/skill files can contain secrets: inspect selections before sharing. Absolute path keys and values in structured Codex/editor settings require explicit `--map SOURCE=DEST` assignments to existing local destinations. The UI accepts mappings as a JSON object and previews unresolved paths. Review arbitrary instruction/skill text separately; it is not rewritten automatically. Portable export is configuration transfer, not a full history/authentication backup.

## Diagnostics and lifecycle

```bash
codex-den list --json
codex-den inspect repo1 --json
codex-den doctor --json
codex-den update
codex-den uninstall
codex-den completion bash
```

`doctor` reports paths and static executable availability, identifies common AppImage wrapper concerns, and does not start applications or validate login. Completion currently supplies top-level command names for Bash/Zsh/Fish; dynamic registered-name completion remains planned.

Update/uninstall commands display package-manager guidance without changing installations or deleting data. Use `uv tool uninstall codex-den` or the matching installer. No automatic data purge or background update checks run.

Exit statuses: 0 success, 2 usage/configuration/domain validation, 1 filesystem/operational failure, 130 cancellation. Failed editor launches forward the editor exit status; termination by a signal uses 128 plus its signal number.

Interactive menu/setup/configure entry points reject `--dry-run`; use the corresponding direct command to preview changes. UI appearance settings apply after restarting the menu. Setup saves only the chosen frontend/executable; unrelated invocation overrides remain temporary.
