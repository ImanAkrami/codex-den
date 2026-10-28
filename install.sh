#!/bin/sh
# Install a verified standalone executable; no Python, uv, or sudo required.
set -eu
umask 077
DEFAULT_VERSION='v0.1.0a1'
version=$DEFAULT_VERSION
bin_dir=${CODEX_DEN_BIN_DIR:-${HOME:?HOME must be set}/.local/bin}
uninstall=0
update=0
dry_run=0
version_set=0
temporary=''
stage=''
marker_stage=''
backup=''
locked=0
published=0
committed=0
preserve_backup=0

fail() { printf 'codex-den installer: %s\n' "$*" >&2; exit 2; }
usage() {
    cat <<'HELP'
Codex Den — standalone Linux installer

Usage: sh install.sh [options]
  --version TAG   Install a specific release (default version stamped in script)
  --bin-dir PATH  Install directory (default ~/.local/bin, or CODEX_DEN_BIN_DIR)
  --update        Update an owned installation; installs if absent
  --uninstall     Remove only the owned executable, retaining all application data
  --dry-run       Print the plan without downloads or writes
  --help          Show help

Linux x86_64/aarch64, glibc 2.35+. Requires curl or wget and standard shell tools.
No Python or uv is needed. The installer never runs the app or edits shell profiles.
HELP
}
valid_version() {
    printf '%s\n' "$1" | LC_ALL=C awk '/^v[0-9]+\.[0-9]+\.[0-9]+((a|b|rc)[0-9]+)?$/ {ok=1} END {exit !ok}'
}
hash_file() {
    digest=$(sha256sum < "$1") || return 1
    printf '%s' "${digest%% *}"
}
cleanup() {
    status=$?
    trap - 0
    if [ "$published" -eq 1 ] && [ "$committed" -eq 0 ]; then
        if [ -n "$backup" ] && [ -f "$backup" ]; then
            if mv -f -- "$backup" "$target"; then backup=''
            else
                preserve_backup=1
                printf 'Recovery copy retained at: %s\n' "$backup" >&2
            fi
        else
            rm -f -- "$target" || true
        fi
    fi
    for item in "$stage" "$marker_stage"; do
        if [ -n "$item" ]; then rm -f -- "$item" || true; fi
    done
    if [ -n "$backup" ] && [ "$preserve_backup" -eq 0 ]; then rm -f -- "$backup" || true; fi
    if [ "$locked" -eq 1 ]; then rmdir -- "$lock" 2>/dev/null || true; fi
    if [ -n "$temporary" ]; then rm -rf -- "$temporary"; fi
    exit "$status"
}
trap cleanup 0
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --version|--bin-dir)
            [ "$#" -ge 2 ] || fail "$1 requires a value"
            case "$2" in ''|--*) fail "$1 requires a value" ;; esac
            if [ "$1" = '--version' ]; then version=$2; version_set=1; else bin_dir=$2; fi
            shift 2 ;;
        --update) update=1; shift ;;
        --uninstall) uninstall=1; shift ;;
        --dry-run) dry_run=1; shift ;;
        *) fail "Unknown option: $1. Use --help." ;;
    esac
done
valid_version "$version" || fail 'Invalid release version; use a tag such as v0.1.0a1.'
[ "$uninstall" -eq 0 ] || { [ "$update" -eq 0 ] && [ "$version_set" -eq 0 ]; } || fail '--uninstall cannot be combined with update/version options'
case "$bin_dir" in /*) ;; *) bin_dir="$(pwd)/$bin_dir" ;; esac
target=$bin_dir/codex-den
marker=$bin_dir/.codex-den-install
lock=$bin_dir/.codex-den-install.lock

owned=0
validate_owned() {
    owned=0
    [ ! -L "$target" ] && [ ! -L "$marker" ] || fail 'Refusing a symlink installation. Remove it with its original installer or choose --bin-dir.'
    if [ -e "$target" ] || [ -e "$marker" ]; then
        [ -f "$target" ] && [ -f "$marker" ] || fail 'Existing target is not an owned Codex Den installation. Use its original installer or choose --bin-dir.'
        [ "$(awk 'END {print NR}' "$marker")" = '1' ] || fail 'Invalid installation ownership record.'
        IFS=' ' read -r saved_digest saved_version extra < "$marker" || fail 'Invalid installation ownership record.'
        [ -z "$extra" ] && [ "${#saved_digest}" -eq 64 ] || fail 'Invalid installation ownership record.'
        case "$saved_digest" in *[!0-9a-f]*) fail 'Invalid installation ownership record.' ;; esac
        valid_version "$saved_version" || fail 'Invalid installation ownership version.'
        [ "$(hash_file "$target")" = "$saved_digest" ] || fail 'Installed file has changed; refusing to overwrite or remove it.'
        owned=1
    fi
}
command -v sha256sum >/dev/null 2>&1 || fail 'sha256sum is required to verify the download.'
validate_owned
if [ "$uninstall" -eq 1 ]; then
    if [ "$dry_run" -eq 1 ]; then printf 'Would remove owned executable: %s\nApplication data will be retained.\n' "$target"; exit 0; fi
    if [ "$owned" -eq 0 ]; then printf 'Codex Den is not installed here.\n'; exit 0; fi
else
    [ "$(uname -s)" = 'Linux' ] || fail 'Standalone builds support Linux. See the source installation guide for other environments.'
    case "$(uname -m)" in
        x86_64|amd64|AMD64) architecture=x86_64 ;;
        aarch64|arm64) architecture=aarch64 ;;
        *) fail 'Unsupported CPU architecture; use the source installation workflow.' ;;
    esac
    libc=$(getconf GNU_LIBC_VERSION 2>/dev/null || true)
    printf '%s\n' "$libc" | LC_ALL=C awk '$1=="glibc" && $2 ~ /^[0-9]+\.[0-9]+$/ {split($2,v,"."); ok=(v[1]>2 || (v[1]==2 && v[2]>=35))} END {exit !ok}' || fail 'This binary requires glibc 2.35 or newer. Use source installation on other Linux systems.'
    asset=codex-den-$version-linux-$architecture
    base_url=https://github.com/ImanAkrami/codex-den/releases/download/$version
    if [ "$dry_run" -eq 1 ]; then printf 'Would download: %s/%s\nWould verify SHA256SUMS and install: %s\n' "$base_url" "$asset" "$target"; exit 0; fi
    download() {
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL --connect-timeout 20 --max-time 180 "$1" -o "$2"
        elif command -v wget >/dev/null 2>&1; then
            wget -q --timeout=180 "$1" -O "$2"
        else fail 'curl or wget is required to download the release.'
        fi
    }
    temporary=$(mktemp -d)
    download "$base_url/SHA256SUMS" "$temporary/SHA256SUMS"
    download "$base_url/$asset" "$temporary/binary"
    expected=$(LC_ALL=C awk -v wanted="$asset" '$2==wanted {count++; digest=$1; if(NF!=2) bad=1} END {if(bad || count!=1 || length(digest)!=64 || digest ~ /[^0-9a-f]/) exit 1; print digest}' "$temporary/SHA256SUMS") || fail 'Missing, malformed, or duplicate checksum record for this binary.'
    [ "$(hash_file "$temporary/binary")" = "$expected" ] || fail 'Download checksum failed. Existing installation was retained.'
fi
mkdir -p -- "$bin_dir"
if ! mkdir -- "$lock" 2>/dev/null; then fail "Another installation is active (lock: $lock)."; fi
locked=1
validate_owned
if [ "$uninstall" -eq 1 ]; then
    backup=$(mktemp "$bin_dir/.codex-den-backup.XXXXXX")
    mv -f -- "$target" "$backup"
    published=1
    rm -- "$marker"
    committed=1
    printf 'Codex Den removed. Configuration, environments, and repositories were retained.\n'
    exit 0
fi
if [ "$owned" -eq 1 ]; then
    backup=$(mktemp "$bin_dir/.codex-den-backup.XXXXXX")
    cp -p -- "$target" "$backup"
fi
stage=$(mktemp "$bin_dir/.codex-den.XXXXXX")
cp -- "$temporary/binary" "$stage"
chmod 755 "$stage"
marker_stage=$(mktemp "$bin_dir/.codex-den-meta.XXXXXX")
printf '%s %s\n' "$expected" "$version" > "$marker_stage"
mv -f -- "$stage" "$target"
published=1
mv -f -- "$marker_stage" "$marker"
committed=1
printf 'Codex Den %s installed: %s\nRun: codex-den setup\n' "$version" "$target"
case ":${PATH-}:" in
    *":$bin_dir:"*) ;;
    *)
        quoted_target=$(printf '%s' "$target" | sed "s/'/'\\\\''/g")
        printf "This directory is outside PATH.\nRun directly: '%s' setup\nAdd %s to PATH using your shell configuration.\n" "$quoted_target" "$bin_dir"
        ;;
esac
