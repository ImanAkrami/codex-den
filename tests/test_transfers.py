import hashlib
import json
import zipfile

import pytest

from codex_den.errors import DenError


def seed(service):
    environment = service.create_environment("source", {"frontend": "cursor"})
    home = service.environment_path(environment) / "codex-home"
    (home / "skills/example").mkdir(parents=True)
    (home / "skills/example/SKILL.md").write_text("useful instructions")
    (home / "auth.json").write_text("sensitive auth")
    (home / "state_5.sqlite").write_bytes(b"private history")
    (home / "config.toml").write_text('model = "example"\napi_key = "secret-token"\n')
    return environment, home


def test_clone_is_independent_and_excludes_authentication_and_history(service):
    source, home = seed(service)
    cloned = service.clone_environment("source", "clone")
    clone_home = service.environment_path(cloned) / "codex-home"
    assert cloned["id"] != source["id"]
    assert (clone_home / "skills/example/SKILL.md").read_text() == "useful instructions"
    assert not (clone_home / "auth.json").exists()
    assert not (clone_home / "state_5.sqlite").exists()
    assert "secret-token" not in (clone_home / "config.toml").read_text()
    (clone_home / "skills/example/SKILL.md").write_text("changed")
    assert (home / "skills/example/SKILL.md").read_text() == "useful instructions"


def test_presets_are_snapshots_and_explicit_creation_options_win(service):
    source, home = seed(service)
    service.save_preset("work", "source")
    (home / "skills/example/SKILL.md").write_text("new source content")
    created = service.create_environment("new", {"frontend": "vscode"}, preset="work")
    assert created["settings"]["frontend"] == "vscode"
    assert (
        service.environment_path(created) / "codex-home/skills/example/SKILL.md"
    ).read_text() == "useful instructions"
    service.delete_preset("work")
    assert service.environment("new")["id"] == created["id"]


def test_comparison_is_read_only_and_redacts_secrets(service):
    seed(service)
    service.clone_environment("source", "clone")
    clone = service.environment_path(service.environment("clone")) / "codex-home/config.toml"
    clone.write_text('model = "other"\napi_key = "another-secret"\n')
    before = service.store.registry.read_bytes()
    diff = service.compare("source", "clone")
    assert "config.toml" in json.dumps(diff)
    assert "example" in json.dumps(diff) and "other" in json.dumps(diff)
    assert "secret-token" not in json.dumps(diff)
    assert "another-secret" not in json.dumps(diff)
    assert service.store.registry.read_bytes() == before


def test_import_dry_run_and_conflicts_preserve_existing_files(service, tmp_path):
    environment = service.create_environment("target")
    source = tmp_path / "template"
    source.mkdir()
    (source / "AGENTS.md").write_text("new")
    target = service.environment_path(environment) / "codex-home/AGENTS.md"
    target.write_text("old")
    before = service.store.registry.read_bytes()
    plan = service.import_files("target", source, ["AGENTS.md"], dry_run=True)
    assert plan[0]["conflict"]
    assert target.read_text() == "old"
    assert before == service.store.registry.read_bytes()
    service.import_files("target", source, ["AGENTS.md"])
    assert target.read_text() == "old"
    service.import_files("target", source, ["AGENTS.md"], replace=True)
    assert target.read_text() == "new"
    assert (source / "AGENTS.md").read_text() == "new"


@pytest.mark.parametrize("selected", ["../escape", "/tmp/escape", "auth.json", "state_5.sqlite"])
def test_import_rejects_unsafe_or_sensitive_selection(service, tmp_path, selected):
    service.create_environment("target")
    with pytest.raises(DenError):
        service.import_files("target", tmp_path, [selected], dry_run=True)


def test_import_rejects_symlinks_and_overlapping_source(service, tmp_path):
    environment = service.create_environment("target")
    source = tmp_path / "template"
    source.mkdir()
    (source / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(DenError, match="symlink"):
        service.import_files("target", source, ["link"])
    home = service.environment_path(environment) / "codex-home"
    with pytest.raises(DenError, match="overlap"):
        service.import_files("target", home, ["skills"])


def test_portable_bundle_import_assigns_new_identity_and_checks_integrity(service, tmp_path):
    environment, _ = seed(service)
    bundle = tmp_path / "work.den"
    service.export_environment("source", bundle)
    imported = service.import_environment(bundle, "imported")
    assert imported["id"] != environment["id"]
    assert (
        service.environment_path(imported) / "codex-home/skills/example/SKILL.md"
    ).read_text() == "useful instructions"
    with zipfile.ZipFile(bundle) as archive:
        assert not any("auth.json" in name or "sqlite" in name for name in archive.namelist())
    broken = tmp_path / "broken.den"
    with zipfile.ZipFile(bundle) as archive, zipfile.ZipFile(broken, "w") as changed:
        for name in archive.namelist():
            changed.writestr(name, b"tampered" if name.endswith("SKILL.md") else archive.read(name))
    with pytest.raises(DenError, match="integrity"):
        service.import_environment(broken, "bad")
    assert not any(e["name"] == "bad" for e in service.inventory()["environments"].values())


def test_hostile_archive_cannot_write_outside_environment(service, tmp_path):
    bundle = tmp_path / "hostile.den"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "settings": {},
                    "files": {"../../escape": hashlib.sha256(b"bad").hexdigest()},
                }
            ),
        )
        archive.writestr("../../escape", b"bad")
    with pytest.raises(DenError):
        service.import_environment(bundle, "hostile")
    assert not (tmp_path / "escape").exists()


def test_detach_clone_preserves_original_membership_and_settings(service, tmp_path):
    source, _ = seed(service)
    for name in ("repo1", "repo2"):
        path = tmp_path / name
        path.mkdir()
        service.add_workspace(name, path, "source")
    service.detach_workspace("repo1", "private", clone_settings=True)
    assert service.inspect("repo1")["environment"]["name"] == "private"
    assert service.inspect("repo2")["environment"]["id"] == source["id"]
    assert service.inspect("repo1")["codex_home"] != service.inspect("repo2")["codex_home"]


def test_import_registry_failure_restores_overwritten_files(service, tmp_path, monkeypatch):
    import codex_den.storage as storage

    environment = service.create_environment("target")
    home = service.environment_path(environment) / "codex-home"
    (home / "AGENTS.md").write_text("old rules")
    source = tmp_path / "source"
    source.mkdir()
    (source / "AGENTS.md").write_text("new rules")
    before = service.store.registry.read_bytes()

    def fail(*args):
        raise OSError("injected registry write failure")

    monkeypatch.setattr(storage, "atomic_json", fail)
    with pytest.raises(OSError):
        service.import_files("target", source, ["AGENTS.md"], replace=True)
    assert (home / "AGENTS.md").read_text() == "old rules"
    assert service.store.registry.read_bytes() == before
    assert not list(service.store.root.glob(".import-*"))


def test_create_failure_leaves_no_published_or_orphan_environment(service, monkeypatch):
    import codex_den.storage as storage

    def fail(*args):
        raise OSError("injected full disk")

    monkeypatch.setattr(storage, "atomic_json", fail)
    with pytest.raises(OSError):
        service.create_environment("new")
    assert service.inventory()["environments"] == {}
    assert list((service.store.root / "environments").iterdir()) == []


def test_bundle_can_include_extension_manifest_as_metadata(service, tmp_path):
    environment, _ = seed(service)
    (service.environment_path(environment) / "extensions.json").write_text('["openai.chatgpt"]')
    bundle = tmp_path / "manifest.den"
    service.export_environment("source", bundle)
    created = service.import_environment(bundle, "imported")
    assert json.loads((service.environment_path(created) / "extensions.json").read_text()) == [
        "openai.chatgpt"
    ]


def test_bundle_cannot_install_editor_extension_binaries(service, tmp_path):
    content = b'{"name":"malicious-extension"}'
    path = "editors/cursor/extensions/evil/package.json"
    bundle = tmp_path / "extension.den"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "settings": {},
                    "files": {path: hashlib.sha256(content).hexdigest()},
                }
            ),
        )
        archive.writestr(path, content)
    with pytest.raises(DenError, match="destination"):
        service.import_environment(bundle, "unsafe")
    assert service.inventory()["environments"] == {}


def test_portable_import_requires_explicit_mapping_of_machine_paths(service, tmp_path):
    environment, home = seed(service)
    (home / "config.toml").write_text('[mcp_servers.local]\ncommand = "/old/machine/tool"\n')
    bundle = tmp_path / "paths.den"
    service.export_environment("source", bundle)
    with pytest.raises(DenError, match="map"):
        service.import_environment(bundle, "unmapped")
    local_tool = tmp_path / "new tool"
    local_tool.write_text("not executed by import")
    imported = service.import_environment(
        bundle, "mapped", path_map={"/old/machine/tool": str(local_tool)}
    )
    import tomllib

    config = tomllib.loads(
        (service.environment_path(imported) / "codex-home/config.toml").read_text()
    )
    assert config["mcp_servers"]["local"]["command"] == str(local_tool)
    assert "old/machine" in (home / "config.toml").read_text()


def hold_registry(root, ready, release):
    from codex_den.storage import Store

    with Store(root).transaction():
        ready.set()
        release.wait(10)


def test_snapshot_does_not_read_through_another_writer(service, monkeypatch):
    import multiprocessing

    import codex_den.storage as storage

    seed(service)
    ctx = multiprocessing.get_context("fork")
    ready, release = ctx.Event(), ctx.Event()
    process = ctx.Process(target=hold_registry, args=(service.store.root, ready, release))
    process.start()
    try:
        assert ready.wait(10)
        original = storage.lock_file
        monkeypatch.setattr(storage, "lock_file", lambda path, **kwargs: original(path, timeout=0))
        with pytest.raises(DenError, match="busy"):
            service.snapshot("source")
    finally:
        release.set()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join()


def test_import_holds_registry_lock_until_rollback_finishes(service, tmp_path, monkeypatch):
    import fcntl
    import os

    import codex_den.storage as storage

    environment = service.create_environment("target")
    home = service.environment_path(environment) / "codex-home"
    target = home / "AGENTS.md"
    target.write_text("old")
    source = tmp_path / "source"
    source.mkdir()
    (source / "AGENTS.md").write_text("new")
    held = []
    original_replace = os.replace

    def inspect_restore(source_path, destination_path):
        if str(source_path).endswith("old-0"):
            fd = os.open(service.store.root / ".lock", os.O_RDWR)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    held.append(True)
                else:
                    held.append(False)
            finally:
                os.close(fd)
        return original_replace(source_path, destination_path)

    def fail(*args):
        raise OSError("injected registry commit failure")

    monkeypatch.setattr(storage, "atomic_json", fail)
    monkeypatch.setattr(os, "replace", inspect_restore)
    with pytest.raises(OSError):
        service.import_files("target", source, ["AGENTS.md"], replace=True)
    assert target.read_text() == "old"
    assert held == [True], (
        "rollback must finish before another writer can acquire the registry lock"
    )


def test_failed_rollback_keeps_original_backup_for_recovery(service, tmp_path, monkeypatch):
    import os

    import codex_den.storage as storage

    environment = service.create_environment("target")
    home = service.environment_path(environment) / "codex-home"
    (home / "AGENTS.md").write_text("valuable original")
    source = tmp_path / "source"
    source.mkdir()
    (source / "AGENTS.md").write_text("new")
    real_replace = os.replace

    def fail_restore(src, dst):
        if str(src).endswith("old-0"):
            raise OSError("persistent restore failure")
        return real_replace(src, dst)

    def fail_commit(*args):
        raise OSError("registry failure")

    monkeypatch.setattr(os, "replace", fail_restore)
    monkeypatch.setattr(storage, "atomic_json", fail_commit)
    with pytest.raises(DenError, match="backup|recovery"):
        service.import_files("target", source, ["AGENTS.md"], replace=True)
    backups = list(service.store.root.glob(".import-*/old-0"))
    assert len(backups) == 1
    assert backups[0].read_text() == "valuable original"


def test_bundle_remaps_project_paths_in_toml_table_keys(service, tmp_path):
    environment, home = seed(service)
    (home / "config.toml").write_text(
        '[projects."/old-machine/repository"]\ntrust_level = "trusted"\n'
    )
    bundle = tmp_path / "project-path.den"
    service.export_environment("source", bundle)
    preview = service.preview_bundle(bundle)
    assert preview["unresolved_paths"] == ["/old-machine/repository"]
    with pytest.raises(DenError, match="map"):
        service.import_environment(bundle, "unmapped")
    repo = tmp_path / "new repo"
    repo.mkdir()
    imported = service.import_environment(bundle, "mapped", {"/old-machine/repository": str(repo)})
    import tomllib

    data = tomllib.loads(
        (service.environment_path(imported) / "codex-home/config.toml").read_text()
    )
    assert data["projects"] == {str(repo): {"trust_level": "trusted"}}


def test_remapping_cannot_silently_merge_different_project_keys(service, tmp_path):
    environment, home = seed(service)
    (home / "config.toml").write_text(
        '[projects."/old/a"]\ntrust_level = "trusted"\n[projects."/old/b"]\ntrust_level = "untrusted"\n'
    )
    bundle = tmp_path / "collisions.den"
    service.export_environment("source", bundle)
    repo = tmp_path / "new"
    repo.mkdir()
    with pytest.raises(DenError, match="duplicate|collision|conflict"):
        service.import_environment(bundle, "bad", {"/old/a": str(repo), "/old/b": str(repo)})
