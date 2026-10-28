# Installation

## Standalone executable

Codex Den provides prebuilt Linux executables for x86_64 and ARM64, with glibc 2.35 or newer (including Ubuntu 22.04+). You do not need Python, uv, Git, or sudo. The installer needs curl or wget and standard shell tools including `sha256sum`.

```sh
curl -fsSL https://raw.githubusercontent.com/ImanAkrami/codex-den/main/install.sh | sh
codex-den --version
codex-den setup
```

The executable goes into `~/.local/bin`. Installation verifies its SHA-256 against the versioned release manifest. It never runs the app, installs editors, edits shell profiles, or copies authentication. The application bundles its Python runtime and dependencies; they are extracted privately when the executable starts.

To read the script before running it, or keep a copy for later:

```sh
curl -fsSL https://raw.githubusercontent.com/ImanAkrami/codex-den/main/install.sh -o install.sh
less install.sh
sh install.sh --dry-run
sh install.sh
```

Only run a script from a source you trust. Checksums detect corrupt downloads; they do not independently authenticate the publisher. Release assets include architecture-specific third-party notices and `SHA256SUMS`.

## Pin, update, or remove

```sh
# Pin both the installer and executable to a published version.
curl -fsSL https://github.com/ImanAkrami/codex-den/releases/download/v0.1.0a1/install.sh -o install.sh
sh install.sh --version v0.1.0a1

# Download the current installer when updating to its default release.
curl -fsSL https://raw.githubusercontent.com/ImanAkrami/codex-den/main/install.sh | sh -s -- --update

# Remove only the owned executable; keep all application data.
sh install.sh --uninstall
```

`--version TAG` selects a published release; it does not query GitHub's “latest” endpoint, which excludes previews. A saved installer retains its stamped default version. `--update` installs if absent and safely replaces an owned installation. All installs check ownership: unrelated commands, symlinks, or modified executables are retained and reported. Concurrent changes use an installation lock and ordinary publication failures roll back. After a hard kill, inspect any remaining lock/staged files before retrying.

`codex-den update` and `codex-den uninstall` print commands appropriate to the installed executable's directory. They do not change installations themselves. Uninstall retains configuration, environments, history, and working repositories.

## Custom directory and PATH

```sh
sh install.sh --bin-dir "$HOME/tools/bin"
sh install.sh --bin-dir "$HOME/tools/bin" --update
sh install.sh --bin-dir "$HOME/tools/bin" --uninstall
```

`CODEX_DEN_BIN_DIR` also selects the destination. Use the same directory for future updates/removal. Paths containing spaces are supported. Keep the adjacent `.codex-den-install` ownership record with the command.

If `codex-den` is not found, add its installation directory to PATH using your shell configuration, or run `~/.local/bin/codex-den setup` directly. The installer prints the exact executable path. It does not change PATH automatically.

You can also download the matching executable from [Releases](https://github.com/ImanAkrami/codex-den/releases), verify `SHA256SUMS`, and mark it executable yourself. A manual download has no installer ownership record: update/remove it manually, or install into a separate directory using the script.

## Optional source installation

Contributors and users of other compatible Linux systems can install with [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.12+. uv can obtain the Python runtime; this workflow is separate from the standalone installer.

```sh
git clone https://github.com/ImanAkrami/codex-den.git
cd codex-den
./scripts/install-source.sh
# Or: uv tool install --python 3.12 .
```

The source helper finds its checkout even when run elsewhere. It supports `--source /path/to/checkout`, `--ref TAG_OR_COMMIT`, `--python 3.13`, `--dry-run`, `--update`, and `--uninstall`. Update the checkout before updating a local source install. Use `uv tool dir --bin` to locate its command directory. Remove a direct uv install with `uv tool uninstall codex-den`. If switching installation methods, uninstall using the original method first; the binary installer refuses an existing uv launcher.

To run directly from a checkout without tool installation:

```sh
uv sync --frozen
uv run codex-den
```

Default configuration is `~/.config/codex-den/config.toml`; managed state is `~/.local/share/codex-den/`. XDG variables, `--config`, and `--data-root` select alternate locations. Keep repositories outside managed storage. See [quick start](quick-start.md) for setup and [compatibility](compatibility.md) for release limits.
