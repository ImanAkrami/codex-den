# Testing

## Full gate

```sh
uv sync --frozen
uv run python scripts/check.py
uv build
```

The gate runs Ruff formatting/linting and pytest with subprocess coverage. Coverage identifies gaps; behavioral assertions and failure recovery determine quality. Tests use temporary homes, isolated tool directories, and fake editor binaries. They never require accounts, credentials, or personal editor profiles.

Installation checks use fresh disposable package caches and require network access to resolve build/runtime dependencies. They do not depend on a warm workstation cache.

## Focused checks

```sh
uv run pytest tests/test_review_core.py tests/test_transfers.py tests/test_storage.py -q
uv run pytest tests/test_ui_navigation.py tests/test_ui_operations.py tests/test_motion.py -q
uv run pytest tests/test_terminal.py tests/test_ui_plain.py -q
uv run pytest tests/test_installer.py tests/test_packaging.py -q
```

## Contracts under test

- Private atomic writes, process locks, concurrent operations, and preservation of existing state on malformed input or failures.
- Workspace/storage overlap rejection, repository-safe removal, serialized launches, exact argv/cwd/child environment, and success-only recents.
- Typed configuration, precedence, temporary arguments, read-only previews, menu/direct-command parity, and safe reruns.
- Transfer exclusions, JSONC normalization/redaction, traversal/symlinks, combined size limits, manifest checks, path mapping, and rollback/recovery data.
- Every menu route and picker option in final rendered terminal cells at wide/short sizes; layered Escape, visible actions, literal paths, busy/error/retry, and plain mode.
- Real pseudo-terminal input and restoration, clean-wheel installation, source installer, update/uninstall, and retained data.

Coordinate concurrent tests with events/barriers; use Textual's animation completion rather than timing guesses before hit-testing. Add a reproducer before a behavior fix. Tests should assert outcomes and absence of unintended writes, not merely execute code. Do not add automatic retries to hide failures.

## Screenshots

Run `uv run scripts/screenshots.py` to export demo SVG screens into `docs/images/`. For matching PNGs, use the documented optional renderer in that script. Captures use disposable state, demo repository names, and fake executables; no editor starts.

## Real editors

Real-editor checks are a separate opt-in activity in a disposable user account/environment. Record editor and extension versions plus evidence for profile/home selection, shared/independent behavior, process reuse, simultaneous launches, and account/keyring limits. Fake executables do not establish those upstream behaviors. See [compatibility](compatibility.md) and the [release checklist](maintaining.md).
