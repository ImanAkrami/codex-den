from pathlib import Path

import pytest

from codex_den.errors import DenError


def register(service, tmp_path, name="repo1", environment="shared"):
    path = tmp_path / name
    path.mkdir(exist_ok=True)
    return service.add_workspace(name, path, environment)


def test_shared_workspaces_reuse_entire_environment(service, tmp_path):
    env = service.create_environment("shared")
    first = register(service, tmp_path)
    second = register(service, tmp_path, "repo2")
    assert first["environment"] == second["environment"] == env["id"]
    assert first["path"] != second["path"]
    assert service.inspect("repo1")["codex_home"] == service.inspect("repo2")["codex_home"]
    assert service.inspect("repo1")["editors"] == service.inspect("repo2")["editors"]
    independent = service.create_environment("private")
    assert independent["id"] != env["id"]


def test_names_paths_and_duplicates_are_validated_without_source_writes(service, tmp_path):
    source = tmp_path / "repo"
    source.mkdir()
    service.add_workspace("one", source)
    for name in ("../escape", "", "invalid/name", "line\nbreak"):
        with pytest.raises(DenError):
            service.create_environment(name)
    with pytest.raises(DenError, match="registered"):
        service.add_workspace("duplicate", source)
    assert list(source.iterdir()) == []
    assert len(service.inventory()["environments"]) == 1


def test_switch_preserves_other_members_and_original_homes(service, tmp_path):
    shared = service.create_environment("shared")
    private = service.create_environment("private")
    register(service, tmp_path)
    register(service, tmp_path, "repo2")
    marker = Path(service.inspect("repo1")["codex_home"]) / "instructions.md"
    marker.write_text("keep")
    service.switch_workspace("repo1", "private")
    assert service.inspect("repo1")["environment"]["id"] == private["id"]
    assert service.inspect("repo2")["environment"]["id"] == shared["id"]
    assert marker.read_text() == "keep"


def test_favorites_and_recents_have_stable_order_without_deleting_registration(service, tmp_path):
    service.create_environment("shared")
    register(service, tmp_path)
    register(service, tmp_path, "repo2")
    service.favorite("repo1", True)
    service.record_open("repo1", at=10)
    service.record_open("repo2", at=20)
    service.record_open("repo1", at=30)
    assert [w["name"] for w in service.recent()] == ["repo1", "repo2"]
    service.clear_recent()
    assert service.recent() == []
    assert service.inspect("repo1")["workspace"]["favorite"]
    assert len(service.inventory()["workspaces"]) == 2


def test_discovery_is_bounded_deduplicated_and_read_only(service, tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    for relative in ("one", "deep/two", "node_modules/ignored"):
        repo = projects / relative
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()
    (projects / "alias").symlink_to(projects / "one", target_is_directory=True)
    assert [Path(item["path"]).name for item in service.discover(projects, 1)] == ["one"]
    assert {Path(item["path"]).name for item in service.discover(projects, 3)} == {"one", "two"}
    assert not service.store.root.exists()


def test_remove_workspace_keeps_shared_environment(service, tmp_path):
    env = service.create_environment("shared")
    register(service, tmp_path)
    service.remove_workspace("repo1")
    assert service.inventory()["workspaces"] == {}
    assert env["id"] in service.inventory()["environments"]


def test_remove_referenced_environment_refuses(service, tmp_path):
    service.create_environment("shared")
    register(service, tmp_path)
    with pytest.raises(DenError, match="workspace"):
        service.remove_environment("shared")


def test_detected_active_environment_cannot_be_switched_or_removed(service, tmp_path, monkeypatch):
    shared = service.create_environment("shared")
    service.create_environment("private")
    register(service, tmp_path)
    monkeypatch.setattr(service, "is_active", lambda identifier: identifier == shared["id"])
    with pytest.raises(DenError, match="active"):
        service.switch_workspace("repo1", "private")
    assert service.inspect("repo1")["environment"]["id"] == shared["id"]
