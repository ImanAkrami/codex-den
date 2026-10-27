import pytest
from hypothesis import given
from hypothesis import strategies as st

from codex_den.config import Configuration, parse_overrides
from codex_den.errors import DenError


def test_defaults_and_temporary_overrides_do_not_write(tmp_path):
    path = tmp_path / "config.toml"
    config = Configuration(path, overrides={"frontend": "cursor"})
    assert config.effective()["frontend"] == "cursor"
    assert config.sources()["frontend"] == "argument"
    assert config.effective()["ui.color"] == "auto"
    assert not path.exists()


def test_configuration_precedence_and_sources(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('schema_version = 1\nfrontend = "vscode"\n[ui]\ncolor = "never"\n')
    config = Configuration(path, overrides={"frontend": "cursor"})
    values = config.effective(environment={"frontend": "vscode"}, workspace={"frontend": "vscode"})
    assert values["frontend"] == "cursor"
    assert values["ui.color"] == "never"
    assert (
        config.sources(environment={}, workspace={"frontend": "vscode"})["frontend"] == "argument"
    )


def test_typed_overrides_reject_conflicts_and_unknown_keys():
    assert parse_overrides(["ui.color=never", "discovery.max_depth=3"]) == {
        "ui.color": "never",
        "discovery.max_depth": 3,
    }
    for raw in (
        ["frontend=cursor", "frontend=vscode"],
        ["unknown.secret=foo"],
        ["discovery.max_depth=-1"],
    ):
        with pytest.raises(DenError):
            parse_overrides(raw)


def test_save_preserves_unrelated_keys_and_reset_is_scoped(tmp_path):
    path = tmp_path / "config.toml"
    config = Configuration(path)
    config.save("frontend", "cursor")
    config.save("ui.color", "never")
    assert Configuration(path).effective()["frontend"] == "cursor"
    config.reset("frontend")
    assert Configuration(path).effective()["frontend"] == "vscode"
    assert Configuration(path).effective()["ui.color"] == "never"
    assert path.stat().st_mode & 0o777 == 0o600


def test_malformed_and_unknown_schema_config_are_preserved(tmp_path):
    for content in ("frontend = [", "schema_version = 999\n", 'unknown = "value"\n'):
        path = tmp_path / "config.toml"
        path.write_text(content)
        with pytest.raises(DenError):
            Configuration(path).effective()
        assert path.read_text() == content


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=40))
def test_arbitrary_executable_strings_are_never_evaluated(value):
    # Executable settings are literal strings, never shell code.
    if "\x00" in value or not value.strip():
        with pytest.raises(DenError):
            parse_overrides([f"executables.cursor={value}"])
    else:
        assert parse_overrides([f"executables.cursor={value}"]) == {"executables.cursor": value}
