import json
import os
import subprocess
import sys

import pytest


def cli(tmp_path, *arguments, extra_env=None):
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "home/.config"),
        "XDG_DATA_HOME": str(tmp_path / "home/.local/share"),
    }
    env.pop("CODEX_HOME", None)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-m", "codex_den", *arguments],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def value(result):
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_help_version_non_tty_do_not_create_state(tmp_path):
    for arguments in ((), ("--help",), ("--version",), ("environment", "--help")):
        result = cli(tmp_path, *arguments)
        assert result.returncode == 0, result.stderr
        assert "codex-den" in result.stdout.lower() or "0.1.0" in result.stdout
    assert not (tmp_path / "home").exists()


def test_config_flags_anywhere_and_override_sources_do_not_persist(tmp_path):
    result = value(cli(tmp_path, "config", "show", "--set", "frontend=cursor", "--json"))
    assert result["values"]["frontend"] == "cursor"
    assert result["sources"]["frontend"] == "argument"
    assert not (tmp_path / "home").exists()
    value(cli(tmp_path, "--json", "config", "set", "frontend", "cursor", "--scope", "user"))
    result = value(cli(tmp_path, "config", "show", "--frontend", "vscode", "--json"))
    assert result["values"]["frontend"] == "vscode"
    assert value(cli(tmp_path, "config", "show", "--json"))["values"]["frontend"] == "cursor"


def test_conflicting_overrides_fail_before_creating_state(tmp_path):
    result = cli(
        tmp_path, "environment", "create", "one", "--frontend", "cursor", "--set", "frontend=vscode"
    )
    assert result.returncode != 0
    assert "conflict" in result.stderr.lower()
    assert not (tmp_path / "home").exists()


def test_full_shared_private_feature_workflow(tmp_path):
    repo1, repo2 = tmp_path / "repo1", tmp_path / "repo2"
    repo1.mkdir()
    repo2.mkdir()
    shared = value(cli(tmp_path, "environment", "create", "shared", "--json"))
    for name, path in (("repo1", repo1), ("repo2", repo2)):
        value(
            cli(
                tmp_path,
                "workspace",
                "add",
                name,
                "--path",
                str(path),
                "--environment",
                "shared",
                "--json",
            )
        )
    first = value(cli(tmp_path, "inspect", "repo1", "--json"))
    second = value(cli(tmp_path, "inspect", "repo2", "--json"))
    assert first["editors"] == second["editors"]
    value(cli(tmp_path, "preset", "create", "work", "--from-environment", "shared", "--json"))
    value(cli(tmp_path, "environment", "create", "private", "--preset", "work", "--json"))
    value(cli(tmp_path, "workspace", "favorite", "repo1", "--json"))
    value(
        cli(tmp_path, "workspace", "switch", "repo1", "--environment", "private", "--yes", "--json")
    )
    assert value(cli(tmp_path, "inspect", "repo2", "--json"))["environment"]["id"] == shared["id"]
    bundle = tmp_path / "portable.den"
    value(cli(tmp_path, "environment", "export", "private", "--output", str(bundle), "--json"))
    value(cli(tmp_path, "environment", "import", str(bundle), "--name", "imported", "--json"))
    assert len(value(cli(tmp_path, "list", "--json"))["environments"]) == 3


def test_explicit_editor_launch_with_forwarded_args(tmp_path, editor):
    repo = tmp_path / "repo"
    repo.mkdir()
    value(cli(tmp_path, "workspace", "add", "repo", "--path", str(repo), "--json"))
    capture = tmp_path / "capture"
    result = cli(
        tmp_path,
        "open",
        "repo",
        "--frontend",
        "cursor",
        "--set",
        f"executables.cursor={editor}",
        "--json",
        "--",
        "--new-window",
        "literal $value",
        extra_env={"CAPTURE": str(capture)},
    )
    value(result)
    assert json.loads(capture.read_text())["argv"][-2:] == ["--new-window", "literal $value"]
    assert len(value(cli(tmp_path, "workspace", "recent", "--json"))) == 1


def test_setup_noninteractive_requires_information_and_is_repeatable(tmp_path, editor):
    result = cli(tmp_path, "setup", "--non-interactive")
    assert result.returncode != 0
    assert not (tmp_path / "home").exists()
    repo = tmp_path / "repo"
    repo.mkdir()
    args = (
        "setup",
        "--path",
        str(repo),
        "--name",
        "repo",
        "--frontend",
        "cursor",
        "--set",
        f"executables.cursor={editor}",
        "--non-interactive",
        "--json",
    )
    value(cli(tmp_path, *args))
    value(cli(tmp_path, *args))
    assert len(value(cli(tmp_path, "list", "--json"))["workspaces"]) == 1


def test_uninstall_and_update_report_package_manager_commands_without_mutation(tmp_path):
    before = list(tmp_path.iterdir())
    for command in ("update", "uninstall"):
        result = value(cli(tmp_path, command, "--json"))
        assert "uv tool" in result["command"]
        assert result["automatic"] is False
    assert list(tmp_path.iterdir()) == before


def test_conflicting_repeated_named_flags_fail_without_state(tmp_path):
    result = cli(
        tmp_path, "environment", "create", "one", "--frontend", "cursor", "--frontend", "vscode"
    )
    assert result.returncode != 0
    assert not (tmp_path / "home").exists()


def test_editor_exit_status_is_forwarded_and_failed_open_is_not_recent(tmp_path, editor):
    repo = tmp_path / "repo"
    repo.mkdir()
    value(cli(tmp_path, "workspace", "add", "repo", "--path", str(repo), "--json"))
    result = cli(
        tmp_path,
        "open",
        "repo",
        "--frontend",
        "cursor",
        "--set",
        f"executables.cursor={editor}",
        extra_env={"CAPTURE": str(tmp_path / "capture"), "EDITOR_STATUS": "7"},
    )
    assert result.returncode == 7
    assert value(cli(tmp_path, "workspace", "recent", "--json")) == []


def test_config_get_honors_environment_and_workspace_scope(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    value(cli(tmp_path, "environment", "create", "work", "--json"))
    value(
        cli(
            tmp_path,
            "workspace",
            "add",
            "repo",
            "--path",
            str(repo),
            "--environment",
            "work",
            "--json",
        )
    )
    value(
        cli(
            tmp_path,
            "config",
            "set",
            "frontend",
            "cursor",
            "--scope",
            "environment",
            "--target",
            "work",
            "--yes",
            "--json",
        )
    )
    result = value(
        cli(
            tmp_path,
            "config",
            "get",
            "frontend",
            "--scope",
            "environment",
            "--target",
            "work",
            "--json",
        )
    )
    assert result["value"] == "cursor"
    assert result["source"] == "environment"
    value(
        cli(
            tmp_path,
            "config",
            "set",
            "frontend",
            "vscode",
            "--scope",
            "workspace",
            "--target",
            "repo",
            "--yes",
            "--json",
        )
    )
    result = value(
        cli(
            tmp_path,
            "config",
            "get",
            "frontend",
            "--scope",
            "workspace",
            "--target",
            "repo",
            "--json",
        )
    )
    assert result["value"] == "vscode"
    assert result["source"] == "workspace"
    result = cli(tmp_path, "config", "get", "frontend", "--scope", "environment", "--json")
    assert result.returncode != 0


@pytest.mark.parametrize("operation", ["update", "uninstall"])
def test_frozen_lifecycle_guidance_needs_no_package_manager(tmp_path, monkeypatch, operation):
    import shlex

    from codex_den.cli import lifecycle

    binary = tmp_path / "bin with spaces $(touch unintended)" / "codex-den"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(binary))
    result = lifecycle(operation)
    assert result["automatic"] is False
    assert "uv " not in result["command"]
    assert "python" not in result["command"].lower()
    assert "--" + operation in result["command"]
    assert shlex.quote(str(binary.parent)) in result["command"]
    assert "retained" in result["note"]
    assert not binary.parent.exists()


def test_direct_download_update_guides_normal_install_and_uninstall_quotes_file(
    tmp_path, monkeypatch
):
    import shlex

    from codex_den.cli import lifecycle

    home = tmp_path / "home"
    binary = tmp_path / "downloads with spaces" / "codex-den-v0.1.0a1-linux-x86_64"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(binary))
    assert str(home / ".local/bin") in lifecycle("update")["command"]
    assert shlex.split(lifecycle("uninstall")["command"]) == ["rm", "--", str(binary)]
    assert not home.exists()
