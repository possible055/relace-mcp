#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  clone-dev-tree.sh SRC DST [--exclude PATTERN]...
  clone-dev-tree.sh SRC --branch-name BRANCH [--exclude PATTERN]...
  clone-dev-tree.sh SRC --branch-name BRANCH --checkout-branch BRANCH [--exclude PATTERN]...

Copies a repo into a fresh independent clone, then overlays local-only files from
SRC into DST.

Defaults:
  - always excludes /.git
  - always excludes /benchmark/artifacts/
  - always excludes /.venv/ and rebuilds it in DST
  - fetches origin with --prune after rewriting the destination remote
  - ensures a local main branch exists when origin/main is available
  - always runs uv sync --extra dev in DST
  - installs the pre-commit git hook when .pre-commit-config.yaml is present

Examples:
  clone-dev-tree.sh ~/dev/relace-mcp-main ~/dev/relace-mcp-feature-x
  clone-dev-tree.sh ~/dev/relace-mcp-main --branch-name feat/bg-index-monitor
  clone-dev-tree.sh ~/dev/relace-mcp-main --branch-name feat/target-sample --checkout-branch feat/target-sample
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
  local normalized pattern
  for pattern in "$@"; do
    normalized="${pattern#/}"
    normalized="${normalized%/}"
    tar_excludes+=(
      "--exclude=./$normalized"
      "--exclude=./$normalized/*"
    )
  done
}

normalize_branch_label() {
  local branch normalized
  branch="$1"
  branch="${branch##*/}"
  normalized=$(printf '%s' "$branch" | tr -cs 'A-Za-z0-9._-' '-')
  normalized="${normalized#-}"
  normalized="${normalized%-}"
  printf '%s' "$normalized"
}

derive_destination_basename() {
  local src_basename current_label target_label prefix
  src_basename="$1"
  current_label="$2"
  target_label="$3"

  if [[ -n "$current_label" && "$src_basename" == *-"$current_label" ]]; then
    prefix="${src_basename%-"$current_label"}"
    prefix="${prefix%-}"
    if [[ -n "$prefix" ]]; then
      printf '%s-%s' "$prefix" "$target_label"
      return
    fi
  fi

  printf '%s-%s' "$src_basename" "$target_label"
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
  "/.venv/"
)

branch_name=""
checkout_branch=""
declare -a extra_excludes=()
declare -a positional=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch-name)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --branch-name" >&2
        exit 1
      fi
      branch_name="$2"
      shift 2
      ;;
    --checkout-branch)
      if [[ $# -lt 2 ]]; then
        echo "missing value for --checkout-branch" >&2
        exit 1
      fi
      checkout_branch="$2"
      shift 2
      ;;
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

if [[ -n "$branch_name" ]]; then
  if [[ ${#positional[@]} -ne 1 ]]; then
    usage >&2
    exit 1
  fi
else
  if [[ ${#positional[@]} -ne 2 ]]; then
    usage >&2
    exit 1
  fi
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

if [[ ! -d "$src" ]]; then
  echo "source directory does not exist: $src" >&2
  exit 1
fi

status "validating source git repository"
git -C "$src" rev-parse --is-inside-work-tree >/dev/null
current_branch=$(git -C "$src" branch --show-current)

if [[ -n "$branch_name" ]]; then
  current_label=$(normalize_branch_label "$current_branch")
  target_label=$(normalize_branch_label "$branch_name")

  if [[ -z "$target_label" ]]; then
    echo "could not derive a destination label from --branch-name: $branch_name" >&2
    exit 1
  fi

  src_parent=$(dirname "$src")
  src_basename=$(basename "$src")
  dst_basename=$(derive_destination_basename "$src_basename" "$current_label" "$target_label")
  dst=$(realpath -m "$src_parent/$dst_basename")
  status "derived destination path from branch name '$branch_name': $dst"
else
  dst=$(realpath -m "${positional[1]}")
fi

if [[ "$src" == "$dst" ]]; then
  echo "source and destination must be different" >&2
  exit 1
fi

if [[ -n "$checkout_branch" ]]; then
  git -C "$src" check-ref-format --branch "$checkout_branch" >/dev/null
fi

src_origin_fetch_url=""
src_origin_push_url=""
if git -C "$src" remote get-url origin >/dev/null 2>&1; then
  src_origin_fetch_url=$(git -C "$src" remote get-url origin)
fi
if git -C "$src" remote get-url --push origin >/dev/null 2>&1; then
  src_origin_push_url=$(git -C "$src" remote get-url --push origin)
fi

if [[ -e "$dst" ]]; then
  echo "destination already exists: $dst" >&2
  exit 1
fi

status "preparing destination parent directory"
mkdir -p "$(dirname "$dst")"

status "cloning tracked git history into $dst"
git clone "$src" "$dst"

if [[ -n "$src_origin_fetch_url" ]]; then
  status "setting destination origin to $src_origin_fetch_url"
  git -C "$dst" remote set-url origin "$src_origin_fetch_url"
  if [[ -n "$src_origin_push_url" ]]; then
    git -C "$dst" remote set-url --push origin "$src_origin_push_url"
  fi
  status "fetching destination origin refs"
  git -C "$dst" fetch origin --prune
  if git -C "$dst" show-ref --verify --quiet refs/remotes/origin/main; then
    if git -C "$dst" show-ref --verify --quiet refs/heads/main; then
      status "ensuring local main tracks origin/main"
      git -C "$dst" branch --set-upstream-to=origin/main main >/dev/null
    else
      status "creating local main from origin/main"
      git -C "$dst" branch --track main origin/main >/dev/null
    fi
  else
    warn "origin/main is not available; destination will not have a local main branch"
  fi
else
  warn "source repo has no origin remote; destination origin remains the local clone source"
fi

if [[ -n "$checkout_branch" ]]; then
  status "checking out destination branch $checkout_branch"
  if [[ "$checkout_branch" != "$current_branch" ]]; then
    warn "destination will still overlay source working tree files after branch checkout; tracked differences will appear as local changes in destination"
  fi

  if git -C "$dst" show-ref --verify --quiet "refs/heads/$checkout_branch"; then
    git -C "$dst" switch "$checkout_branch"
  elif git -C "$dst" show-ref --verify --quiet "refs/remotes/origin/$checkout_branch"; then
    git -C "$dst" switch --track -c "$checkout_branch" "origin/$checkout_branch"
  else
    git -C "$dst" switch -c "$checkout_branch"
  fi
fi

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
  status "source contains /.venv but destination will rebuild its own environment"
else
  status "source does not contain /.venv; destination will create a fresh environment"
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

if [[ -f "$dst/.pre-commit-config.yaml" ]]; then
  if [[ -x "$dst/.venv/bin/pre-commit" ]]; then
    status "installing pre-commit hook"
    (
      cd "$dst"
      .venv/bin/pre-commit install
    )
  else
    warn "found .pre-commit-config.yaml but .venv/bin/pre-commit is missing; skipping hook install"
  fi
else
  status "no .pre-commit-config.yaml found; skipping pre-commit hook install"
fi

status "ready: $dst"
