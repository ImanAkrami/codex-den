"""One local/CI entry point for formatting, lint, and behavioral verification."""

import subprocess
import sys


def main():
    for arguments in (
        ["ruff", "format", "--check", "src", "tests", "scripts"],
        ["ruff", "check", "src", "tests", "scripts"],
        ["pytest", "--cov=codex_den", "--cov-report=term-missing", "-q"],
    ):
        result = subprocess.run([sys.executable, "-m", *arguments], check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
