"""Build a native standalone Linux executable and accompanying license notices."""

import argparse
import importlib.metadata
import platform
import re
import subprocess
import sys
import sysconfig
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def asset_name(version, machine):
    aliases = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", version):
        raise ValueError("Unsupported release version")
    if machine.lower() not in aliases:
        raise ValueError(f"Unsupported binary architecture: {machine}")
    return f"codex-den-v{version}-linux-{aliases[machine.lower()]}"


def write_notices(destination, include_bundler=True):
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    packages = {item["name"]: item for item in lock["package"]}
    names, pending = set(), ["codex-den"]
    while pending:
        name = pending.pop()
        if name in names:
            continue
        names.add(name)
        pending.extend(dependency["name"] for dependency in packages[name].get("dependencies", []))
    if include_bundler:
        names.add("pyinstaller")
    sections = ["Codex Den — bundled software notices\n", (ROOT / "LICENSE").read_text()]
    for name in sorted(names - {"codex-den"}):
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            # Platform-conditional dependencies absent from this native bundle.
            continue
        licenses = [
            path
            for path in distribution.files or []
            if any(part.lower().startswith(("license", "copying")) for part in path.parts)
            and ".dist-info" in str(path)
        ]
        if not licenses:
            raise ValueError(f"Missing bundled dependency license: {name}")
        sections.append(f"\n{'=' * 72}\n{name} {distribution.version}\n")
        sections.extend(
            distribution.locate_file(path).read_text(errors="replace") for path in licenses
        )
    python_license = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
    if not python_license.is_file():
        raise ValueError("Python runtime LICENSE.txt is required to distribute the binary")
    sections.extend(["\nPython runtime\n", python_license.read_text()])
    # Preserve available distro notices for native libraries collected by the freezer.
    for name in (
        "libssl3",
        "libssl3t64",
        "libexpat1",
        "libffi8",
        "zlib1g",
        "libbz2-1.0",
        "liblzma5",
        "libreadline8",
        "libncursesw6",
    ):
        path = Path("/usr/share/doc") / name / "copyright"
        if path.is_file():
            sections.extend([f"\nSystem library: {name}\n", path.read_text(errors="replace")])
    references = set(
        re.findall(r"/usr/share/common-licenses/([A-Za-z0-9.+-]+)", "\n".join(sections))
    )
    for reference in sorted(references):
        reference = reference.rstrip(".")
        path = Path("/usr/share/common-licenses") / reference
        if not path.is_file():
            raise ValueError(f"Missing referenced system license: {reference}")
        sections.extend([f"\nFull license: {reference}\n", path.read_text()])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(sections))
    return destination


def build(output, work):
    if sys.platform != "linux":
        raise ValueError("Native binary builds currently support Linux only")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    from codex_den import __version__

    if version != __version__:
        raise ValueError("Package and runtime versions must agree")
    name = asset_name(version, platform.machine())
    architecture = name.rsplit("-", 1)[-1]
    output, work = output.resolve(), work.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    notices = write_notices(output / f"THIRD_PARTY_NOTICES-linux-{architecture}.txt")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console",
            "--noupx",
            "--name",
            name,
            "--paths",
            str(ROOT / "src"),
            "--distpath",
            str(output),
            "--workpath",
            str(work / "build"),
            "--specpath",
            str(work / "spec"),
            "--collect-all",
            "textual",
            "--recursive-copy-metadata",
            "textual",
            "--collect-data",
            "codex_den",
            "--add-data",
            f"{notices}:codex_den",
            "--exclude-module",
            "pytest",
            "--exclude-module",
            "coverage",
            "--exclude-module",
            "hypothesis",
            "--exclude-module",
            "pexpect",
            str(ROOT / "scripts/frozen_entry.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    return output / name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".cache/binary-build")
    args = parser.parse_args()
    try:
        print(build(args.output_dir, args.work_dir))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Binary build failed: {error}\n")


if __name__ == "__main__":
    main()
