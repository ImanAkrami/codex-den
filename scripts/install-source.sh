#!/bin/sh
# Install only Codex Den. Editor applications and shell profiles are never changed.
set -eu
DEFAULT_REF='main'

usage() {
    cat <<'EOF'
Codex Den installer (Linux, no sudo)

Usage: sh scripts/install-source.sh [options]
  --source PATH     Install a local Codex Den checkout (default when available)
  --ref REF         Install a Git tag, branch, or commit from ImanAkrami/codex-den
  --python VERSION  Python interpreter/version for the isolated tool (default 3.12)
  --update          Reinstall this tool with uv --force
  --uninstall       Remove the tool, retaining all configuration and environments
  --dry-run         Print the package-manager arguments without executing them
  --help            Show this help

Requires uv: https://docs.astral.sh/uv/getting-started/installation/
The installer never starts an editor or edits your shell profile.
EOF
}
fail() { printf 'codex-den installer: %s\n' "$*" >&2; exit 2; }
source_dir=''
ref=''
python_version='3.12'
force=0
uninstall=0
dry_run=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --source|--ref|--python)
            [ "$#" -ge 2 ] || fail "$1 requires a value"
            case "$2" in ''|--*) fail "$1 requires a value" ;; esac
            case "$1" in
                --source) source_dir=$2 ;;
                --ref) ref=$2 ;;
                --python) python_version=$2 ;;
            esac
            shift 2 ;;
        --update) force=1; shift ;;
        --uninstall) uninstall=1; shift ;;
        --dry-run) dry_run=1; shift ;;
        *) fail "Unknown option: $1. Use --help." ;;
    esac
done
[ -z "$source_dir" ] || [ -z "$ref" ] || fail 'Use either --source or --ref'
if [ "$uninstall" -eq 1 ]; then
    [ "$force" -eq 0 ] && [ -z "$source_dir" ] && [ -z "$ref" ] || fail '--uninstall cannot be combined with install/update options'
    set -- tool uninstall codex-den
else
    case "$ref" in *[!A-Za-z0-9_./-]*|-*) fail 'Invalid Git reference' ;; esac
    if [ -z "$source_dir" ] && [ -z "$ref" ]; then
        script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd) || script_dir=''
        if [ -f "$script_dir/../pyproject.toml" ] && [ -f "$script_dir/../src/codex_den/__init__.py" ]; then
            script_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
        fi
        if [ -f "$script_dir/pyproject.toml" ] && [ -f "$script_dir/src/codex_den/__init__.py" ]; then
            source_dir=$script_dir
        fi
    fi
    if [ -n "$source_dir" ]; then
        [ -f "$source_dir/pyproject.toml" ] && [ -f "$source_dir/src/codex_den/__init__.py" ] || fail 'Source must be a Codex Den checkout'
        source_dir=$(CDPATH= cd -- "$source_dir" && pwd)
        package=$source_dir
    else
        package="git+https://github.com/ImanAkrami/codex-den.git@${ref:-$DEFAULT_REF}"
    fi
    set -- tool install --python "$python_version"
    if [ "$force" -eq 1 ]; then set -- "$@" --force; fi
    set -- "$@" "$package"
fi
if [ "$dry_run" -eq 1 ]; then
    printf 'Package-manager plan (one argument per line):\n  uv\n'
    printf '  %s\n' "$@"
    exit 0
fi
[ "$(uname -s)" = 'Linux' ] || fail 'This release supports Linux. See docs/compatibility.md.'
command -v uv >/dev/null 2>&1 || fail 'uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/ and rerun this script.'
uv "$@"
if [ "$uninstall" -eq 1 ]; then
    printf 'Codex Den removed. Configuration, environments, and repositories were retained.\n'
else
    printf 'Codex Den installed successfully.\nRun: codex-den setup\nIf the command is not on PATH, use `uv tool dir --bin` to locate it.\n'
fi
