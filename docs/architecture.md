# Architecture

Codex Den is a Python 3.12+ package with one console entry point. The Linux adapter uses POSIX file locks and `/proc` process inspection.

## Shared operations

`Service` owns environment/workspace lifecycle, configuration scopes, launch planning, discovery, favorites, and recents. `TransferOperations` handles snapshots, selected copies, presets, comparison, and bundles. CLI and terminal screens call these shared operations; business rules do not live only in UI event handlers.

`Configuration` defines a typed schema, TOML parsing, effective-value sources, and exact-key writes under a process lock. Invocation overrides remain temporary. Explicit setup saves its chosen editor/executable; unrelated invocation settings are not persisted.

`Store` owns the versioned JSON registry, canonical UUID paths, private writes, nested metadata validation, and process locks. Read-only commands do not initialize directories. Writes use same-directory temporary files, fsync, and atomic replacement.

## Storage

```text
<config-root>/codex-den/config.toml
<data-root>/codex-den/
  .lock
  registry.json
  environments/<uuid>/
    codex-home/
    editors/vscode/user-data/
    editors/vscode/extensions/
    editors/cursor/user-data/
    editors/cursor/extensions/
    extensions.json
```

Workspace associations reference environments; shared members reuse every environment-managed path. Working directories cannot overlap managed storage. Existing editor/agent homes, inherited unmanaged Codex homes, executable directories, and overlapping symlinks are rejected as storage roots.

## Transfers

Selections use regular files without following symlinks and enforce aggregate count/size limits. Structured settings remove known secret fields. Editor JSONC is parsed with a scanner that removes comments/trailing commas outside strings, then the JSON decoder validates it. Stored/copied output is normalized JSON.

Imports stage new content and retain originals until registry commit. Rollback happens under the same lock; failed restoration preserves recovery files. A post-publication durability error is distinguished from failure before publication so already registered state is not deleted.

Bundles contain supported configuration and a versioned SHA-256 manifest. Imports receive new identities, validate shapes/checksums/destinations, and require explicit mappings for machine-specific paths. Checksums are integrity checks, not publisher authentication.

## Launches and UI

`LaunchPlan` contains executable, exact argv, cwd, and child environment. Launch planning/validation, execution, and success-only recency updates are serialized with metadata mutations. Child processes receive the managed Codex home and sanitized editor IPC environment. Arguments never pass through a shell. Executable inspection reads a bounded prefix without executing diagnostics.

Textual screens provide dashboard, forms, reviews, setup, settings, and selection. Long content scrolls within bounded dialogs; actions remain visible. Normal key bindings let a focused dropdown consume Escape before its dialog. Optional opacity/hover effects do not gate input; in-flight guards prevent duplicate operations. Plain mode uses the same parser/service contracts.

See [testing](testing.md) for verification and [compatibility](compatibility.md) for detached-process, hard-interruption, account/keyring, and terminal limits.
