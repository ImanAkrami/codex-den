"""Validate a version tag and prepare local release assets without publishing."""

import argparse
import hashlib
import re
import subprocess
import tomllib
from pathlib import Path


def validate_tag(tag):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", tag):
        raise ValueError("Unsupported version tag")
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    if tag != f"v{version}":
        raise ValueError("Tag must match the checked-out package version")
    tagged = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"], text=True
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if tagged != head:
        raise ValueError("Artifacts must be built from the tagged commit")
    return version


def prepare_artifacts(tag, version, destination):
    artifacts = sorted(destination.glob(f"codex_den-{version}-*.whl"))
    source_archive = destination / f"codex_den-{version}.tar.gz"
    if len(artifacts) != 1 or not source_archive.is_file():
        raise ValueError("Build one wheel and source archive for the selected version first")
    artifacts.append(source_archive)
    for architecture in ("x86_64", "aarch64"):
        artifacts.extend(
            [
                destination / f"codex-den-{tag}-linux-{architecture}",
                destination / f"THIRD_PARTY_NOTICES-linux-{architecture}.txt",
            ]
        )
    if any(path.is_symlink() or not path.is_file() for path in artifacts):
        raise ValueError("Build both native executables and their notices before preparing assets")
    source = Path("install.sh").read_text()
    pattern = r"^DEFAULT_VERSION='v[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?'$"
    if len(re.findall(pattern, source, flags=re.MULTILINE)) != 1:
        raise ValueError("Installer default version could not be pinned")
    installer = destination / "install.sh"
    installer.write_text(re.sub(pattern, f"DEFAULT_VERSION='{tag}'", source, flags=re.MULTILINE))
    installer.chmod(0o755)
    artifacts.append(installer)
    checksums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts
    )
    (destination / "SHA256SUMS").write_text(checksums)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--artifacts", type=Path, help="Prepare assets in this build directory")
    args = parser.parse_args()
    try:
        version = validate_tag(args.tag)
        if args.artifacts is not None:
            prepare_artifacts(args.tag, version, args.artifacts)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release preparation failed: {error}\n")


if __name__ == "__main__":
    main()
