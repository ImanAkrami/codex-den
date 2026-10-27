import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from codex_den.errors import DenError
from codex_den.transfers import sanitize

EDITOR = "editors/vscode/user-data/User/settings.json"


@pytest.mark.parametrize(
    "content",
    [
        b'{// comment\n "font": 14,}',
        b'{/* comment */ "font":14, /* another */}',
        b'\xef\xbb\xbf{"font":14,}',
        b'{"font": 14 /* / and * */}',
    ],
)
def test_editor_jsonc_supports_comments_trailing_commas_and_bom(content):
    assert json.loads(sanitize(EDITOR, content)) == {"font": 14}


def test_editor_keybindings_and_sensitive_fields(service):
    environment = service.create_environment("source")
    settings = service.environment_path(environment) / EDITOR
    settings.parent.mkdir(parents=True)
    settings.write_text(
        '{ // note\n"editor.fontSize": 14, "api_key": "synthetic", "url": "https://example.com/a/*/", }'
    )
    source = settings.read_bytes()
    clone = service.clone_environment("source", "clone")
    copied = service.environment_path(clone) / EDITOR
    assert json.loads(copied.read_bytes()) == {
        "editor.fontSize": 14,
        "url": "https://example.com/a/*/",
    }
    assert settings.read_bytes() == source
    result = sanitize(EDITOR.replace("settings.json", "keybindings.json"), b'[{"key":"ctrl+k",},]')
    assert json.loads(result) == [{"key": "ctrl+k"}]


@pytest.mark.parametrize(
    "content",
    [
        b'{"x":1 /* never closed',
        b'{"x":,}',
        b'{"x":1,,}',
        b"{unquoted:1}",
        b'{"x":0x10}',
        b'{"x":"line\nbreak"}',
        b'{"x":1} garbage',
        b"{,}",
        b"[,]",
        b'{"x":[,]}',
    ],
)
def test_invalid_jsonc_is_rejected(content):
    with pytest.raises(DenError):
        sanitize(EDITOR, content)


def test_non_editor_json_remains_strict():
    with pytest.raises(DenError):
        sanitize("extensions.json", b'["extension",]')


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=80))
def test_jsonc_string_contents_survive_comments_and_trailing_commas(value):
    encoded = ('{/* outer */ "value": ' + json.dumps(value) + ", // tail\n}").encode()
    assert json.loads(sanitize(EDITOR, encoded)) == {"value": value}
