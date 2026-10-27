import json
import multiprocessing
import os
from pathlib import Path

import pytest

from codex_den.errors import DenError
from codex_den.storage import Store, atomic_json


def increment(root, ready, start):
    ready.put(True)
    start.wait(10)
    with Store(Path(root)).transaction() as state:
        state["counter"] = state.get("counter", 0) + 1


def test_read_is_write_free(tmp_path):
    root = tmp_path / "data"
    assert Store(root).read()["workspaces"] == {}
    assert not root.exists()


@pytest.mark.parametrize("target", [".codex", ".vscode", ".cursor", ".local/share/vscode-codex"])
def test_refuses_legacy_roots_and_ancestors(tmp_path, monkeypatch, target):
    monkeypatch.setenv("HOME", str(tmp_path))
    for root in (tmp_path / target, tmp_path / target / "child", tmp_path):
        with pytest.raises(DenError, match="overlap"):
            Store(root)


def test_refuses_symlink_into_legacy_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = tmp_path / ".codex"
    legacy.mkdir()
    link = tmp_path / "link"
    link.symlink_to(legacy, target_is_directory=True)
    with pytest.raises(DenError, match="overlap"):
        Store(link / "new")
    assert list(legacy.iterdir()) == []


def test_transaction_is_private_and_rollback_preserves_registry(tmp_path):
    store = Store(tmp_path / "den")
    with store.transaction() as state:
        state["counter"] = 3
    before = store.registry.read_bytes()
    with pytest.raises(RuntimeError):
        with store.transaction() as state:
            state["counter"] = 7
            raise RuntimeError("interrupted")
    assert store.registry.read_bytes() == before
    assert store.root.stat().st_mode & 0o777 == 0o700
    assert store.registry.stat().st_mode & 0o777 == 0o600


def test_parallel_transactions_do_not_lose_updates(tmp_path):
    ctx = multiprocessing.get_context("fork")
    ready, start = ctx.Queue(), ctx.Event()
    root = tmp_path / "den"
    processes = [ctx.Process(target=increment, args=(str(root), ready, start)) for _ in range(5)]
    try:
        for process in processes:
            process.start()
        for _ in processes:
            assert ready.get(timeout=10)
        start.set()
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        assert Store(root).read()["counter"] == 5
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()


def test_failed_atomic_replace_preserves_file_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    atomic_json(target, {"value": "old"})

    def fail(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        atomic_json(target, {"value": "new"})
    assert json.loads(target.read_text()) == {"value": "old"}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.json"]


def test_invalid_registry_is_not_silently_reset(tmp_path):
    store = Store(tmp_path / "den")
    store.root.mkdir()
    store.registry.write_text("{bad json")
    with pytest.raises(DenError, match="registry"):
        store.read()
    assert store.registry.read_text() == "{bad json"


def test_nested_invocation_accepts_its_own_registered_codex_home(service, monkeypatch):
    environment = service.create_environment("owned")
    home = service.environment_path(environment) / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(home))
    reopened = Store(service.store.root)
    with reopened.transaction() as state:
        state["nested_operation"] = True
    assert reopened.read()["nested_operation"]


def test_unregistered_inherited_codex_home_is_still_protected(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "new-den/unowned-home"))
    with pytest.raises(DenError, match="overlap"):
        Store(tmp_path / "new-den")


def test_post_publication_fsync_failure_never_deletes_registered_environment(service, monkeypatch):
    import stat

    original = os.fsync

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("injected directory fsync failure")
        return original(fd)

    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises(DenError, match="applied|published|durability"):
        service.create_environment("new")
    environments = service.inventory()["environments"]
    assert len(environments) == 1
    created = next(iter(environments.values()))
    assert (service.environment_path(created) / "codex-home").is_dir()


@pytest.mark.parametrize(
    "relative", [".config/Code", ".config/Cursor", ".config/Code - Insiders", ".vscode-insiders"]
)
def test_existing_editor_user_data_homes_are_protected(tmp_path, monkeypatch, relative):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for path in (tmp_path / relative, tmp_path / relative / "nested"):
        with pytest.raises(DenError, match="overlap"):
            Store(path)


def test_editor_user_data_under_custom_xdg_config_is_protected(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "custom-config"))
    with pytest.raises(DenError, match="overlap"):
        Store(tmp_path / "custom-config/Code")
