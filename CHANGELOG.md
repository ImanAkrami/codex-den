# Changelog

## 0.1.0a1 — Linux preview

### Added

- Independent/shared Codex environments for VS Code and Cursor, including per-editor profiles and extensions.
- Keyboard-first dashboard, guided setup, scoped settings, search, favorites/recents, and plain mode.
- Selected configuration copying, independent clones, presets, comparison, repository discovery, and portable bundles.
- Typed temporary CLI arguments, JSON output, diagnostics, and exact editor-argument forwarding.
- Optional terminal effects and visible launch progress, with motion/plain/no-color controls.
- One-command Linux x86_64/ARM64 installation with bundled Python, verified release checksums, safe updates, and retained-data uninstall; no Python or uv prerequisite.
- Optional source installer with checkout/ref selection and managed tool environments.
- Illustrated quick start, reproducible demo captures, community guides, CI and draft-release tooling.

### Reliability

- Private atomic state, process locks, serialized launches, validated metadata, repository/storage separation, and recovery-preserving transfers.
- Credential/runtime exclusions, JSONC editor preferences, aggregate snapshot limits, bundle shape/integrity validation, and explicit path mappings.
- Rendered picker/navigation, Escape, short-terminal layouts, literal paths, cancellation/retry, setup precedence, and menu/command parity checks.
- Review dialogs close after their background operation finishes; native executables restore system library routing before launching editors.
- Source archives use an explicit file list to exclude local build artifacts and development state.

This preview's support and validation requirements are described in [compatibility](docs/compatibility.md).
