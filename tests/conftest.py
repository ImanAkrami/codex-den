import pytest

from codex_den.config import Configuration
from codex_den.service import Service
from codex_den.storage import Store


@pytest.fixture
def service(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return Service(
        Store(home / ".local/share/codex-den"),
        Configuration(home / ".config/codex-den/config.toml"),
    )


@pytest.fixture
def editor(tmp_path):
    target = tmp_path / "fake editor"
    target.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
Path(os.environ['CAPTURE']).write_text(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'codex_home': os.environ.get('CODEX_HOME'), 'home': os.environ.get('HOME')}))
sys.exit(int(os.environ.get('EDITOR_STATUS', '0')))
""")
    target.chmod(0o700)
    return target


def manifest(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
