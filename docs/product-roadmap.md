# Roadmap

The Linux preview includes independent/shared environments, the dashboard and guided setup, typed settings, snapshots/presets, discovery, selected copying, portable bundles, and package installation. See [workspace features](workspace-features.md) for current behavior.

## Before stable 1.0

- Record Codex extension validation inside both editors: intended home/profile selection, simultaneous launches, process reuse, shared database behavior, and account/keyring limits.
- Strengthen active-process tracking and recovery for detached applications and interrupted filesystem publication.
- Complete terminal accessibility, long-list, light-theme, and performance measurements on a declared support matrix.
- Verify supported Python/platform combinations and published installation paths through CI and release artifacts.

## Planned workflows

- Rename, relocate, and archive workspaces while retaining environment identity.
- Edit and reapply presets with explicit conflict previews.
- Full managed-state backup/restore with separately designed authentication handling.
- Dynamic workspace/environment shell completion.
- Additional platforms after lock/process adapters and installation checks exist.

Changes should keep the common path short: choose an editor, register a folder, review, and open. Advanced settings remain optional. No automatic editor starts, credential imports, data purges, or background updates are planned.
