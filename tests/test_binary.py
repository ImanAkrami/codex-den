"""Build metadata is validated before any native bundling starts."""

import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_binary.py"


@pytest.mark.parametrize(
    "machine,expected",
    [("x86_64", "x86_64"), ("AMD64", "x86_64"), ("aarch64", "aarch64"), ("arm64", "aarch64")],
)
def test_native_asset_name_matches_installer_contract(machine, expected):
    module = runpy.run_path(SCRIPT)
    assert module["asset_name"]("0.1.0a1", machine) == f"codex-den-v0.1.0a1-linux-{expected}"


@pytest.mark.parametrize(
    "version,machine", [("../bad", "x86_64"), ("0.1", "x86_64"), ("0.1.0", "riscv64")]
)
def test_unsupported_native_build_target_is_rejected(version, machine):
    module = runpy.run_path(SCRIPT)
    with pytest.raises(ValueError):
        module["asset_name"](version, machine)


def test_binary_notices_preserve_runtime_and_python_license_text(tmp_path):
    module = runpy.run_path(SCRIPT)
    result = module["write_notices"](tmp_path / "NOTICES", include_bundler=False)
    content = result.read_text()
    assert "Textual" in content or "textual" in content
    assert "Permission is hereby granted" in content
    assert "PYTHON SOFTWARE FOUNDATION LICENSE" in content
    assert "tomli" in content.lower()
