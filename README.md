# Codex Den

**A home for your Codex workspaces.**

Manage the Codex extension in **VS Code** and **Cursor** with a terminal dashboard and a scriptable CLI. Give each project its own environment, or let several repositories share settings, skills, extensions, and editor profiles.

[![CI](https://github.com/ImanAkrami/codex-den/actions/workflows/ci.yml/badge.svg)](https://github.com/ImanAkrami/codex-den/actions/workflows/ci.yml) ![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue) ![Linux](https://img.shields.io/badge/platform-Linux-lightgrey) [![MIT license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

![Codex Den dashboard showing shared and independent workspaces](docs/images/dashboard.png)

## Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
git clone https://github.com/ImanAkrami/codex-den.git
cd codex-den
./install.sh
codex-den setup
```

Python 3.12+ runs in an isolated tool environment. Installation needs no sudo, does not edit shell profiles, and never opens an editor. Already have a checkout? Run `./install.sh` there. See [installation](docs/installation.md) for version pinning, updates, uninstall, and PATH troubleshooting.

**Linux preview:** version `0.1.0a1`. See [compatibility](docs/compatibility.md) for platform support and editor-validation requirements.

## Get started

The setup wizard lets you choose an editor, register a folder, and create or join an environment. Review the summary, finish setup, then choose **Open editor** from the dashboard when ready.

[Follow the illustrated quick start →](docs/quick-start.md)

Prefer commands?

```sh
# Create an environment shared by two separate working directories.
codex-den environment create work
codex-den workspace add api --path ~/projects/api --environment work
codex-den workspace add web --path ~/projects/web --environment work

# Review membership and install the extension into its managed profile.
codex-den inspect api
codex-den environment install-codex work --frontend cursor --yes
codex-den open api --frontend cursor
```

Omit `--environment` when registering a workspace to create an independent environment.

## Make it yours

- **One dashboard:** search, favorites, recent workspaces, and keyboard navigation.
- **Independent or shared:** reuse a complete environment across repositories, including the editor profile, extensions, and Codex home. Working folders stay separate.
- **Configuration that travels:** copy selected files, clone environments, save presets, compare settings, and export/import portable bundles.
- **Review before applying:** inspect shared membership, file conflicts, and operation targets. Credentials and runtime files are excluded from configuration transfers.
- **Useful defaults:** choose VS Code or Cursor, then customize through Settings, TOML, or temporary CLI flags.
- **Quiet when needed:** `--plain`, `--no-color`, `NO_COLOR`, and optional motion. No background network checks or automatic editor launches.

```sh
codex-den config set frontend cursor
codex-den config set ui.motion false
codex-den config show --set ui.theme=light --json
codex-den open api --frontend vscode -- --new-window
```

[CLI reference](docs/cli.md) · [Environments](docs/environments.md) · [Workspace features](docs/workspace-features.md) · [Troubleshooting](docs/troubleshooting.md)

## Contribute

```sh
uv sync --frozen
uv run python scripts/check.py
uv build
```

The full gate checks formatting, lint, filesystem/process behavior, concurrency, failure recovery, configuration, terminal interaction, installation, and package contents. Tests use temporary homes and fake editors.

Read [CONTRIBUTING.md](CONTRIBUTING.md), [architecture](docs/architecture.md), [testing](docs/testing.md), and the [roadmap](docs/product-roadmap.md). Bugs and feature requests belong in [GitHub Issues](https://github.com/ImanAkrami/codex-den/issues); vulnerabilities use [private reporting](SECURITY.md).

[MIT licensed](LICENSE). Independent project; not affiliated with OpenAI, Microsoft, or Cursor.
