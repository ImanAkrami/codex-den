# Compatibility

## Current release

`0.1.0a1` is a Linux preview, not a stable release. Python 3.12+ is required; the CI matrix targets Python 3.12 and 3.13. Storage uses POSIX locks and process detection uses Linux `/proc`. macOS and Windows are not supported by this release.

The VS Code and Cursor adapters pass a managed user-data directory, extension directory, Codex home, and exact argument list. Automated tests validate these contracts with fake editor executables. They do not establish compatibility with every upstream editor or extension version.

Before a stable release, maintainers must record real-editor checks for both editors: expected Codex home, independent/shared profiles, extension installation, authentication/keyring behavior, simultaneous shared use, and process reuse. See the [release checklist](maintaining.md).

## Operational limits

- A shared environment deliberately shares local authentication and history. Directory separation is not an operating-system sandbox or a guarantee about upstream keyring/account isolation.
- Process detection checks Linux command lines and may miss detached extension processes. Close all editor sessions before copying, reconfiguring, or removing managed state.
- A hard kill between filesystem publication and registry commit may leave an unregistered directory. Do not delete unknown directories as an automatic repair strategy. Maintain backups of valuable state.
- Portable bundles transfer supported configuration, not full authentication/history/profile backups. Review arbitrary text and skill files for sensitive content before sharing.
- JSONC editor preferences are normalized when copied; comments and formatting are not preserved. Codex Den's own TOML setting writes also normalize formatting.
- Update and uninstall commands display package-manager guidance. Automatic purge, preset editing/reapplication, and dynamic name completion remain on the [roadmap](product-roadmap.md).

## Terminal interface

Automated route checks cover 110×40, 80×24, and 70×32 terminal sizes. The dashboard also checks 60×24. Use `--plain` for linear prompts or smaller/assistive terminals. `NO_COLOR`, `--no-color`, and `ui.motion=false` control effects; ASCII mode uses the plain interface.

These checks establish the tested routes and sizes, not every terminal emulator or input combination. See [testing](testing.md) for reproduction and the distinction between automated and real-editor checks.
