"""Regression cases found during the release-readiness review."""

import io
import json
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from codex_den.errors import DenError
from codex_den.storage import lock_file


@pytest.mark.parametrize("position", ["inside", "parent"])
async def test_workspace_cannot_overlap_managed_storage(service, tmp_path, position):
    environment = service.create_environment("owned")
    root = service.environment_path(environment)
    path = root / "codex-home/repository" if position == "inside" else service.store.root.parent
    path.mkdir(exist_ok=True)
    marker = path / "valuable.txt"
    marker.write_text("keep")
    before = service.inventory()
    with pytest.raises(DenError, match="overlap|managed"):
        service.add_workspace("unsafe", path)
    assert marker.read_text() == "keep"
    assert service.inventory() == before


def test_remove_guards_preexisting_nested_repository_registration(service):
    first = service.create_environment("first")
    second = service.create_environment("second")
    repo = service.environment_path(first) / "codex-home/repository"
    repo.mkdir()
    (repo / "valuable.txt").write_text("keep")
    with service.store.transaction() as state:
        state["workspaces"]["old"] = {
            "name": "old",
            "path": str(repo),
            "environment": second["id"],
            "settings": {},
            "favorite": False,
            "last_opened": None,
        }
    with pytest.raises(DenError, match="workspace|repository|overlap"):
        service.remove_environment("first")
    assert (repo / "valuable.txt").read_text() == "keep"


def test_dotenv_variants_are_excluded_from_clone_export_and_import(service, tmp_path):
    source = service.create_environment("source")
    home = service.environment_path(source) / "codex-home"
    skills = home / "skills/demo"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("instructions")
    for name in (
        ".env",
        ".env.local",
        ".env.production",
        ".envrc",
        "id_rsa",
        "key.pem",
        ".netrc",
        ".npmrc",
        ".pypirc",
    ):
        (skills / name).write_text("SYNTHETIC_SECRET=never-share")
    clone = service.clone_environment("source", "clone")
    copied = service.environment_path(clone) / "codex-home/skills/demo"
    assert [p.name for p in copied.iterdir()] == ["SKILL.md"]
    bundle = tmp_path / "portable.den"
    service.export_environment("source", bundle)
    with zipfile.ZipFile(bundle) as archive:
        assert all(b"SYNTHETIC_SECRET" not in archive.read(name) for name in archive.namelist())
    with pytest.raises(DenError):
        service.import_files("clone", home, ["skills/demo/.env.local"])


@pytest.mark.parametrize("feature", ["compression", "encryption"])
def test_unsupported_zip_features_fail_cleanly(service, tmp_path, feature):
    bundle = tmp_path / "unsupported.den"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(
            "manifest.json", json.dumps({"schema_version": 1, "settings": {}, "files": {}})
        )
    data = bytearray(bundle.read_bytes())
    local, central = data.index(b"PK\x03\x04"), data.index(b"PK\x01\x02")
    if feature == "compression":
        data[local + 8 : local + 10] = (99).to_bytes(2, "little")
        data[central + 10 : central + 12] = (99).to_bytes(2, "little")
    else:
        data[local + 6] |= 1
        data[central + 8] |= 1
    bundle.write_bytes(data)
    before = service.inventory()
    with pytest.raises(DenError, match="bundle|Bundle"):
        service.preview_bundle(bundle)
    assert service.inventory() == before


@pytest.mark.parametrize(
    "manifest",
    [
        [],
        None,
        1,
        {"schema_version": 1, "settings": [], "files": {}},
        {"schema_version": 1, "settings": {}, "files": []},
        {"schema_version": True, "settings": {}, "files": {}},
    ],
)
def test_malformed_bundle_shapes_are_domain_errors(service, tmp_path, manifest):
    bundle = tmp_path / "bad.den"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    with pytest.raises(DenError):
        service.import_environment(bundle, "bad")
    assert not service.store.root.exists()


def test_snapshot_limits_apply_across_all_categories(service, tmp_path, monkeypatch):
    import codex_den.transfers as transfers

    monkeypatch.setattr(transfers, "MAX_FILES", 2)
    source = service.create_environment("source")
    home = service.environment_path(source) / "codex-home"
    (home / "skills/demo").mkdir(parents=True)
    (home / "skills/demo/one.md").write_text("one")
    (home / "skills/demo/two.md").write_text("two")
    (home / "AGENTS.md").write_text("three")
    bundle = tmp_path / "too-large.den"
    with pytest.raises(DenError, match="limit"):
        service.export_environment("source", bundle)
    assert not bundle.exists()


def test_export_at_payload_size_limit_round_trips_with_manifest(service, tmp_path, monkeypatch):
    import codex_den.transfers as transfers

    monkeypatch.setattr(transfers, "MAX_TOTAL", 256)
    source = service.create_environment("source")
    (service.environment_path(source) / "codex-home/AGENTS.md").write_bytes(b"a" * 256)
    bundle = tmp_path / "maximum.den"
    service.export_environment("source", bundle)
    imported = service.import_environment(bundle, "imported")
    assert (service.environment_path(imported) / "codex-home/AGENTS.md").read_bytes() == b"a" * 256


def test_launch_holds_mutation_lock_until_process_started_and_recency_committed(
    service, tmp_path, monkeypatch
):
    import codex_den.service as module

    repo = tmp_path / "repo"
    repo.mkdir()
    service.add_workspace("repo", repo)
    temporary = service.create_environment("temporary")
    entered, release = threading.Event(), threading.Event()

    def launch(plan):
        entered.set()
        assert release.wait(5)
        assert Path(plan.environment["CODEX_HOME"]).is_dir()

    monkeypatch.setattr(module, "execute", launch)
    monkeypatch.setattr(module, "resolve_executable", lambda _: "fake-editor")
    with ThreadPoolExecutor() as pool:
        future = pool.submit(service.open, "repo", environment="temporary")
        try:
            assert entered.wait(5)
            with pytest.raises(DenError, match="busy"):
                with lock_file(service.store.root / ".lock", timeout=0.05):
                    service.remove_environment(temporary["name"])
        finally:
            release.set()
        result = future.result(timeout=5)
    assert result["environment_id"] == temporary["id"]
    assert service.recent()[0]["name"] == "repo"


def test_binary_inspection_is_bounded(service, tmp_path, monkeypatch):
    from codex_den.launch import resolve_executable

    fake = tmp_path / "fake-binary"
    fake.write_bytes(b"binary")
    fake.chmod(0o700)
    seen = []
    original = Path.open

    class Bounded(io.BytesIO):
        def read(self, size=-1):
            seen.append(size)
            assert 0 <= size <= 65536, "inspection must not read the complete binary"
            return super().read(size)

    def opening(path, *args, **kwargs):
        return Bounded(b"binary") if path == fake else original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opening)
    assert resolve_executable(str(fake)) == str(fake)
    service.config.overrides["executables.vscode"] = str(fake)
    service.doctor()
    assert seen == [65536, 65536]


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"environments": {"invalid": None}},
        {
            "workspaces": {
                "invalid": {"name": "invalid", "path": "/tmp/repo", "environment": "missing"}
            }
        },
        {"presets": {"invalid": {"settings": [], "files": {}}}},
    ],
)
def test_nested_registry_corruption_is_reported_and_preserved(service, change):
    service.store.root.mkdir(parents=True)
    state = {"schema_version": 1, "environments": {}, "workspaces": {}, "presets": {}, **change}
    content = json.dumps(state)
    service.store.registry.write_text(content)
    with pytest.raises(DenError, match="registry"):
        service.inventory()
    assert service.store.registry.read_text() == content


def test_export_refuses_oversized_manifest_before_writing(service, tmp_path, monkeypatch):
    import codex_den.transfers as transfers

    monkeypatch.setattr(transfers, "MAX_FILE", 80)
    source = service.create_environment("source")
    (service.environment_path(source) / "codex-home/AGENTS.md").write_text("one")
    output = tmp_path / "oversized-manifest.den"
    with pytest.raises(DenError, match="manifest"):
        service.export_environment("source", output)
    assert not output.exists()
