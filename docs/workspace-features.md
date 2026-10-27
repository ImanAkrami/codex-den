# Workspace features

## Clone and reuse configuration

Clone an environment into an independent home, or save a named preset to create future environments from the same snapshot:

```sh
codex-den environment clone work review
codex-den preset create team --from-environment work
codex-den environment create project --preset team
codex-den preset list
codex-den preset inspect team
```

Clones and presets are point-in-time copies. Later changes to the source or preset do not affect existing environments. Presets can be removed and recreated; in-place editing/reapplication is on the [roadmap](product-roadmap.md).

Supported snapshots include Codex TOML, instructions, skills, editor settings/keybindings, and extension manifest metadata. Editor preferences support JSONC comments and trailing commas; copied output is normalized JSON. Credentials, dotenv/private-key files, histories, caches, sessions, and extension binaries are excluded. Arbitrary text still needs review before sharing.

## Compare

```sh
codex-den config diff --from-environment work --to-environment review
codex-den config diff --from-preset team --to-environment review
```

Comparison is read-only and uses the same snapshot/redaction policy as cloning and export.

## Discover and organize

```sh
codex-den workspace discover ~/projects --max-depth 3
codex-den workspace favorite api
codex-den workspace recent
```

Discovery is bounded, skips symlinks and common cache/state folders, and never registers or opens anything by itself. Select repositories through the menu or explicitly supply `--register PATH`. Bulk results report individual failures while retaining successful registrations.

Favorites and recents are separate. Failed editor launches do not add a recent entry; clearing recents retains favorites and registrations.

## Copy selected files

```sh
codex-den import --environment work --from /path/to/template --include AGENTS.md --include skills --dry-run
codex-den import --environment work --from /path/to/template --include AGENTS.md --include skills
```

Transfers preserve the source and keep conflicts by default. Replacement is explicit, staged, and backed up until the registry commit succeeds. A failed rollback retains recovery data at the reported path. Symlinks, traversal, recursive source/destination overlap, and unsafe destinations are rejected.

## Portable bundles

```sh
codex-den environment export work --output /path/to/work.den
codex-den environment import /path/to/work.den --name imported --dry-run
codex-den environment import /path/to/work.den --name imported --map /old/path=/local/path
```

Bundles contain configuration plus a versioned checksum manifest. Absolute paths in structured configuration keys and values require explicit mappings to existing local destinations. Integrity checks detect corruption; they do not authenticate a bundle's author. Portable export is not a full history/authentication backup.

Limits are 2,000 payload files, 4 MiB per file or manifest, and 32 MiB total payload. Limits apply across the complete snapshot. See [CLI reference](cli.md) and [compatibility](compatibility.md).
