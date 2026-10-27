# Contributing

Contributions that improve workspace workflows, reliability, accessibility, and documentation are welcome. Read the [code of conduct](CODE_OF_CONDUCT.md) before participating.

## Develop

Install Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
uv sync --frozen
uv run codex-den --help
uv run python scripts/check.py
uv build
```

The complete gate includes filesystem/process, concurrency, generated inputs, terminal, installer, and packaging tests. See [testing](docs/testing.md) for focused commands and [architecture](docs/architecture.md) for module boundaries.

For manual experiments, use a temporary home plus explicit `--data-root` and `--config` paths. Never use personal authentication or editor profiles in ordinary tests. Opening a real editor is a separate opt-in check.

## Submit a change

Describe the concrete problem and resulting behavior. Add a failing reproducer before fixing behavior, cover cancellation/failure recovery for mutations, and keep CLI, configuration, UI and docs aligned. Include screenshots for visual changes and disclose any checks not performed.

Keep validation in the shared service layer so commands and menus cannot diverge. Avoid new dependencies unless they solve a clear problem; review primary-source documentation/releases, update `uv.lock`, and run the full gate. Source files, credentials, caches, generated coverage, and personal state do not belong in commits.

Use [Issues](https://github.com/ImanAkrami/codex-den/issues) for bugs and features. Include minimal reproduction and reviewed diagnostics; never attach auth files, histories, whole homes, or unreviewed bundles. Vulnerabilities follow [SECURITY.md](SECURITY.md).

Contributions are distributed under the [MIT license](LICENSE). Maintainers follow the [release guide](docs/maintaining.md).
