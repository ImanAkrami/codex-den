# Maintaining and releasing

## Repository setup

The canonical target is `ImanAkrami/codex-den`. Inspect before creating or connecting it:

```sh
gh auth status
gh repo view ImanAkrami/codex-den
git remote -v
```

When publication is intended and the target does not exist:

```sh
gh repo create ImanAkrami/codex-den --public --source . --remote origin
```

Review the local history and files, then push the intended branch. Set the GitHub default branch to `main` after it exists. Do not change an existing repository's visibility or replace unrelated remotes as part of routine checks.

```sh
gh repo edit ImanAkrami/codex-den \
  --description 'Codex extension workspaces for VS Code and Cursor, managed from your terminal' \
  --add-topic codex --add-topic vscode --add-topic cursor --add-topic cli \
  --enable-issues --enable-wiki=false --delete-branch-on-merge
# Requires repository administration permission.
gh api --method PUT repos/ImanAkrami/codex-den/private-vulnerability-reporting
gh api repos/ImanAkrami/codex-den/private-vulnerability-reporting
```

Verify the private **Report a vulnerability** route before inviting security reports. No public email is needed. Code-of-conduct reports can use GitHub's private abuse-reporting tools; see the community files.

Configure branch protection/rulesets for the actual `Verify / Python 3.12` and `Verify / Python 3.13` checks after CI runs. Require review, prohibit force pushes/deletion of `main`, and read back the configured rules. Protection availability depends on the repository/account; a checked-in workflow does not enable it by itself.

## Pull requests

Keep workflow permissions minimal. Fork PRs must not receive release credentials. Dependency updates require upstream release/documentation review, lock updates, and the complete gate. Maintain stable regression tests, not retries or arbitrary coverage thresholds.

## Release checklist

1. Run `uv sync --frozen`, `uv run python scripts/check.py`, and `uv build` on the exact candidate commit.
2. Verify clean source/wheel installation, PATH/help/version, an update, retained-data uninstall/reinstall, and absence of private data or development artifacts.
3. Regenerate and inspect the demo screenshots if the UI changed; confirm quick-start/CLI examples and package metadata match the candidate.
4. Record opt-in real-editor checks for each supported editor/extension version: home/profile selection, extension operation, process reuse, simultaneous shared use, independent environments, and account/keyring limits. Do not label an unverified preview stable.
5. Confirm `pyproject.toml`, `codex_den.__version__`, changelog, and intended tag agree. Create and push the version tag deliberately.
6. Run **Prepare draft release** with that existing tag. It checks tag/commit/version agreement, runs the gate, builds artifacts, pins the downloadable installer to the tag, creates checksums, and prepares a draft only.
7. Verify draft commit/artifacts/checksums and test the downloadable installer from a disposable account/home before publishing. Read back release and CI status with `gh`.

```sh
gh workflow run release.yml -R ImanAkrami/codex-den -f tag=v0.1.0a1
gh run list -R ImanAkrami/codex-den --workflow release.yml
gh release view v0.1.0a1 -R ImanAkrami/codex-den
```

Registry publication, signing/provenance, and additional platform support require their own verified workflows. The current automation does not publish to a package registry or automatically purge user state.
