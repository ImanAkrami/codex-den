# Environments and workspaces

An **environment** owns one Codex home plus separate VS Code and Cursor user-data and extension directories. A **workspace** registers a working folder and associates it with an environment. Stable environment IDs own storage; moving between editors does not create a new environment.

## Independent environments

Registering a workspace without `--environment` creates an independent environment. Independent environments have separate managed homes, profiles, extensions, settings, and histories. Registering different workspaces does not copy or isolate their working files.

## Shared environments

```sh
codex-den environment create shared
codex-den workspace add api --path /path/to/api --environment shared
codex-den workspace add web --path /path/to/web --environment shared
```

Both workspaces share everything managed by the environment, including its Codex home, local authentication state, history, settings, extensions, and the profile for each editor. Their working folders stay separate. VS Code and Cursor have separate editor-specific storage within the shared environment.

A shared setting or extension change can affect every member. Inspection and relevant previews show membership. Close editor sessions before copying configuration, changing membership, or removing an environment.

```sh
codex-den inspect api
codex-den workspace switch api --environment review --dry-run
codex-den workspace switch api --environment review --yes
codex-den workspace detach web --new-environment private --clone-settings --yes
```

Joining changes association without copying either environment. Detaching creates a new environment, optionally copying selected safe configuration, and leaves the original environment intact.

## Ownership and removal

Working directories must be outside managed storage, with no parent/child overlap. Removing a workspace unregisters it while preserving its repository and environment. Removing an unused environment deletes only its managed state; registered members, overlapping repository paths, and detected active processes prevent removal.

State separation does not restrict operating-system filesystem, network, process, or keyring access. See [compatibility](compatibility.md) for process-detection and real-editor validation limits.
