# Installation

Codex Den currently supports Linux and Python 3.12+. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first. The installer uses uv's isolated tool environments; it never installs editors, modifies shell profiles, copies authentication, or opens applications.

## From a checkout

```sh
git clone https://github.com/ImanAkrami/codex-den.git
cd codex-den
./install.sh
codex-den --version
codex-den setup
```

The script locates its own checkout even when run from another directory. Use `--source /path/to/codex-den` to choose a different checkout. Paths containing spaces are supported.

Without the helper script, the equivalent is:

```sh
uv tool install --python 3.12 .
```

## Pin a version

Install a published tag, branch, or full commit from the project repository:

```sh
REF=main # Replace with a published tag or full commit to pin it.
./install.sh --ref "$REF"
./install.sh --python 3.13
```

For online installation after choosing a source revision, download and inspect its `install.sh`, then run it with `--ref` set to that same revision. Pinning a full commit provides a reproducible source reference; branch names follow their current contents. No package-registry install is advertised until a package is published.

## Inspect, update, or remove

```sh
./install.sh --dry-run
./install.sh --update
./install.sh --ref "$REF" --update
./install.sh --uninstall
```

`--dry-run` prints arguments and performs no installation. `--update` replaces only the Codex Den tool. Update a local checkout first if using the default local source. `--uninstall` removes the tool and retains all configuration, environments, history, and repositories.

For an installation made directly with uv, `uv tool uninstall codex-den` removes the command. `codex-den update` and `codex-den uninstall` display package-manager instructions; they do not alter installations themselves.

## PATH and storage

If `codex-den` is not found, run `uv tool dir --bin` and add the displayed directory to PATH using your shell's normal configuration. The installer does not edit that configuration automatically.

Default configuration is `~/.config/codex-den/config.toml`; managed state is `~/.local/share/codex-den/`. XDG variables, `--config`, and `--data-root` can select alternate locations. Keep working repositories outside managed storage. Existing editor/agent homes and executable directories cannot be used as state destinations.

## Try without installation

```sh
uv sync --frozen
uv run codex-den
```

See [quick start](quick-start.md) for the wizard and [compatibility](compatibility.md) for release limits.
