# Working on Codex Den

Codex Den manages the Codex extension inside VS Code and Cursor. It is not a replacement Codex CLI or an OS sandbox.

## Boundaries

- Never change, invoke, replace, move, or migrate any existing user launcher automatically. Never test against real Codex/editor homes, auth files, profiles, or extension installations.
- Use the package's own `codex-den` entry point and state namespace. Preserve unrelated working-tree changes. Set `CODEX_HOME` only in launched children; remove inherited editor IPC routing variables there.
- All ordinary tests use temporary homes/state and fake editor binaries. Real-editor validation is a separate opt-in procedure; state its evidence and limits accurately.
- Do not publish packages/releases, create public remote repositories, or change repository visibility as a side effect of local checks.

## Map

- `src/codex_den/storage.py`: private atomic state and process locks; legacy-path protection.
- `config.py`: typed schema, TOML, precedence, and temporary overrides.
- `service.py`, `transfers.py`, `launch.py`: shared operations, safe snapshots/bundles, exact editor argv/environment.
- `cli.py`: argparse interface and noninteractive behavior.
- `ui*.py`, `ui.tcss`: terminal dashboard, forms, wizard, settings, plain fallback.
- `tests/`: unit, integration, property-based, terminal/Pilot, packaging and coexistence checks.
- `docs/`: accepted requirements, implementation state, CLI and architecture guidance.

## Development

Requires Python 3.12+ and uv. Run `uv sync --frozen` once, then `uv run python scripts/check.py` for the complete gate. Use `uv run pytest tests/test_NAME.py -q` for focused work, `uv run ruff format src tests scripts` for formatting, and `uv build` for distributions.

Add a reproducing test before changing behavior. Assert observable results, exact launch boundaries, no unintended writes, and failure recovery. Keep core operations out of UI event handlers so menu and commands cannot diverge. Test traversal, symlinks, unsafe destinations, malformed state, cancellation, and concurrent operations when relevant.

Read `docs/environments.md`, `docs/workspace-features.md`, and `docs/product-roadmap.md` before changing contracts. Keep `README.md` and `docs/cli.md` accurate about the supported preview behavior and compatibility matrix. New dependencies require primary-source release/documentation review and lockfile updates.
