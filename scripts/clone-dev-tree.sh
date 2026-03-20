#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  clone-dev-tree.sh SRC DST [--exclude PATTERN]...

Copies a repo into a fresh independent clone, then overlays local-only files from
SRC into DST.

Defaults:
  - always excludes /.git
  - always excludes /benchmark/artifacts/
  - always copies /.venv if present in SRC
  - always runs uv sync --extra dev in DST

Examples:
  clone-dev-tree.sh ~/dev/relace-mcp-main ~/dev/relace-mcp-feature-x
  clone-dev-tree.sh ~/dev/relace-mcp-main ~/dev/relace-mcp-feature-x \
    --exclude '/.pytest_cache/' \
    --exclude '/plans/'
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

pick_copy_backend() {
  if command -v rsync >/dev/null 2>&1; then
    printf 'rsync'
    return
  fi

  if command -v tar >/dev/null 2>&1; then
    printf 'tar'
    return
  fi

  echo "missing required command: rsync or tar" >&2
  exit 1
}

append_tar_excludes() {
  local pattern
  for pattern in "$@"; do
    tar_excludes+=("--exclude=./${pattern#/}")
  done
}

status() {
  printf '[status] %s\n' "$*"
}

warn() {
  printf '[warn] %s\n' "$*" >&2
}

readonly DEFAULT_EXCLUDES=(
  "/.git"
  "/benchmark/artifacts/"
)

declare -a extra_excludes=()
declare -a positional=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --exclude)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --exclude" >&2
        exit 1
      fi
      extra_excludes+=("--exclude=$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      positional+=("$1")
      shift
      ;;
  esac
done

if [[ ${#positional[@]} -ne 2 ]]; then
  usage >&2
  exit 1
fi

status "arguments parsed"
status "checking required commands"
require_cmd git
require_cmd realpath
require_cmd uv
copy_backend=$(pick_copy_backend)
status "copy backend: $copy_backend"

status "resolving source and destination paths"
src=$(realpath "${positional[0]}")
dst=$(realpath -m "${positional[1]}")

if [[ ! -d "$src" ]]; then
  echo "source directory does not exist: $src" >&2
  exit 1
fi

if [[ "$src" == "$dst" ]]; then
  echo "source and destination must be different" >&2
  exit 1
fi

status "validating source git repository"
git -C "$src" rev-parse --is-inside-work-tree >/dev/null

if [[ -e "$dst" ]]; then
  echo "destination already exists: $dst" >&2
  exit 1
fi

status "preparing destination parent directory"
mkdir -p "$(dirname "$dst")"

status "cloning tracked git history into $dst"
git clone "$src" "$dst"

declare -a rsync_excludes=()
declare -a tar_excludes=()

status "loading built-in exclude rules"
for pattern in "${DEFAULT_EXCLUDES[@]}"; do
  status "built-in exclude: $pattern"
  rsync_excludes+=("--exclude=$pattern")
done
append_tar_excludes "${DEFAULT_EXCLUDES[@]}"

if [[ ${#extra_excludes[@]} -eq 0 ]]; then
  status "no temporary extra excludes"
else
  status "loading temporary extra excludes"
  for exclude_arg in "${extra_excludes[@]}"; do
    status "extra exclude: ${exclude_arg#--exclude=}"
    rsync_excludes+=("$exclude_arg")
    append_tar_excludes "${exclude_arg#--exclude=}"
  done
fi

if [[ -d "$src/.venv" ]]; then
  status "source contains /.venv and it will be copied before sync"
  warn "copied virtual environments are path-sensitive; if tools still reference the old path, delete $dst/.venv and rerun 'uv sync --extra dev'"
else
  status "source does not contain /.venv"
fi

status "overlaying local files from source into destination"
if [[ "$copy_backend" == "rsync" ]]; then
  rsync -a "${rsync_excludes[@]}" "$src"/ "$dst"/
else
  tar -C "$src" "${tar_excludes[@]}" -cf - . | tar -C "$dst" -xf -
fi

status "syncing destination environment with uv"
(
  cd "$dst"
  uv sync --extra dev
)

status "ready: $dst"
