#!/usr/bin/env bash
# Run Anvaya without Docker, inside Ubuntu / WSL:
#   venv + backend deps -> `manage init` if the DB has no rules -> frontend built once -> gunicorn on :5000
#   serving the API and the built frontend.
#
# Usage: scripts/run_local.sh [--rebuild-frontend] [--prerender-audio]
#   --rebuild-frontend  build the frontend even if the sources have not changed
#   --prerender-audio   also synthesize the fixed spoken prompts into the audio cache (needs VERBX_* in .env);
#                       runs in the background, log in ~/.local/anvaya/prerender.log
#
# Everything generated lives outside the repo (Linux filesystem, fast and not synced by OneDrive):
#   ~/.local/anvaya/venv      Python virtualenv          (ANVAYA_LOCAL_HOME overrides ~/.local/anvaya)
#   ~/.local/anvaya/anvaya.db SQLite database            (ANVAYA_DB overrides)
#   ~/.local/anvaya/build     copy of frontend/ + its node_modules and dist/
#   ~/.local/anvaya/node      Node 20, downloaded only if WSL has no Node >= 18 of its own
# Settings come from the repo-root .env (same file docker compose reads); PORT overrides 5000.
set -euo pipefail

LOG_TAG=run_local
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/_env.sh
. "$REPO/scripts/_env.sh"

STATE="${ANVAYA_LOCAL_HOME:-$HOME/.local/anvaya}"
VENV="$STATE/venv"
BUILD="$STATE/build"
PORT="${PORT:-5000}"
NODE_VERSION=20.18.0
declare -A NODE_SHA256=(
  [amd64]=4543670b589593f8fa5f106111fd5139081da42bb165a9239f05195e405f240a
  [arm64]=a9ce85675ba33f00527f6234d90000946c0936fb4fca605f1891bb5f4fe6fb0a
)

REBUILD=0 PRERENDER=0
for arg in "$@"; do
  case "$arg" in
    --rebuild-frontend) REBUILD=1 ;;
    --prerender-audio) PRERENDER=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) die "unknown option: $arg (see --help)" ;;
  esac
done

[ -f "$REPO/backend/wsgi.py" ] || die "run this script from a checkout of the repo"
mkdir -p "$STATE"
load_env "$REPO"

# ------------------------------------------------------------------ Python
PY_SYS="$(linux_cmd python3)" || die "python3 not found. Install it: sudo apt install python3 python3-venv"
"$PY_SYS" -c 'import sys; sys.exit(sys.version_info < (3, 11))' || die "Python 3.11+ needed (found $("$PY_SYS" --version))"

if [ ! -x "$VENV/bin/python" ]; then
  log "creating virtualenv in $VENV"
  if ! "$PY_SYS" -m venv "$VENV" 2>/dev/null; then
    # Ubuntu ships venv without ensurepip unless python3-venv is installed: create it bare, then bootstrap pip.
    rm -rf "$VENV"
    "$PY_SYS" -m venv --without-pip "$VENV" || die "cannot create a virtualenv; install python3-venv (sudo apt install python3-venv)"
    log "python3-venv is not installed; bootstrapping pip with the official get-pip.py"
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$STATE/get-pip.py" || die "could not download get-pip.py"
    "$VENV/bin/python" "$STATE/get-pip.py" --quiet || die "pip bootstrap failed; install python3-venv instead"
    rm -f "$STATE/get-pip.py"
  fi
fi
PY="$VENV/bin/python"
REQ_SHA="$(sha256sum "$REPO/backend/requirements.txt" | cut -d' ' -f1)"
if [ "$(cat "$VENV/.anvaya-requirements.sha256" 2>/dev/null)" != "$REQ_SHA" ]; then
  log "installing backend dependencies"
  "$PY" -m pip install --quiet --disable-pip-version-check -r "$REPO/backend/requirements.txt"
  echo "$REQ_SHA" > "$VENV/.anvaya-requirements.sha256"
fi

# ------------------------------------------------------------------ database
export ANVAYA_DB="${ANVAYA_DB:-$STATE/anvaya.db}"
mkdir -p "$(dirname "$ANVAYA_DB")"
cd "$REPO/backend"
if [ -n "${DATABASE_URL:-}" ]; then
  # Postgres: `manage init` is idempotent (skips an unchanged catalogue), so run it on every start.
  log "initialising the Postgres database from DATABASE_URL (catalogue import is skipped if unchanged)"
  "$PY" -m anvaya.manage init
elif "$PY" - "$ANVAYA_DB" <<'EOF' 2>/dev/null
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
sys.exit(0 if c.execute("SELECT COUNT(*) FROM rules WHERE active=1").fetchone()[0] else 1)
EOF
then
  log "database ready: $ANVAYA_DB"
else
  log "initialising database $ANVAYA_DB (catalogue import + rules + staff accounts)"
  "$PY" -m anvaya.manage init
fi

# ------------------------------------------------------------------ frontend (built once)
node_bin() {
  local n
  if n="$(linux_cmd node)" && "$n" -e 'process.exit(+process.versions.node.split(".")[0] < 18)' 2>/dev/null; then
    dirname "$n"; return 0
  fi
  local arch dir
  arch="$(linux_arch)"
  dir="$STATE/node/node-v$NODE_VERSION-linux-${arch/amd64/x64}"
  if [ ! -x "$dir/bin/node" ]; then
    log "no Node >= 18 inside WSL; downloading Node $NODE_VERSION into $STATE/node (not system-wide)" >&2
    local tarball="$STATE/node/node-v$NODE_VERSION-linux-${arch/amd64/x64}.tar.xz"
    fetch_pinned "https://nodejs.org/dist/v$NODE_VERSION/$(basename "$tarball")" "$tarball" "${NODE_SHA256[$arch]}" >&2
    tar -xJf "$tarball" -C "$STATE/node"
    rm -f "$tarball"
  fi
  echo "$dir/bin"
}

SOURCES=(frontend backend/anvaya/data backend/tests/fixtures)  # same inputs as the Dockerfile's web stage
src_stamp() {
  (cd "$REPO" && find "${SOURCES[@]}" -type f -not -path '*/node_modules/*' -not -path 'frontend/dist/*' \
     -not -name tsconfig.tsbuildinfo -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
}

STAMP="$(src_stamp)"
if [ "$REBUILD" = 0 ] && [ -f "$BUILD/frontend/dist/index.html" ] && [ "$(cat "$BUILD/.stamp" 2>/dev/null)" = "$STAMP" ]; then
  log "frontend already built for these sources"
else
  NODE_DIR="$(node_bin)"
  export PATH="$NODE_DIR:$PATH"
  log "building frontend with Node $(node --version) in $BUILD (the repo's node_modules are left alone)"
  mkdir -p "$BUILD/frontend"
  find "$BUILD/frontend" -mindepth 1 -maxdepth 1 ! -name node_modules -exec rm -rf {} +
  rm -rf "$BUILD/backend"
  (cd "$REPO" && tar -cf - --exclude=node_modules --exclude=frontend/dist --exclude=tsconfig.tsbuildinfo "${SOURCES[@]}") \
    | (cd "$BUILD" && tar -xf -)
  LOCK_SHA="$(sha256sum "$BUILD/frontend/package-lock.json" | cut -d' ' -f1)"
  if [ "$(cat "$BUILD/.lock.sha256" 2>/dev/null)" != "$LOCK_SHA" ] || [ ! -d "$BUILD/frontend/node_modules" ]; then
    (cd "$BUILD/frontend" && npm ci --no-audit --no-fund --loglevel=error)
    echo "$LOCK_SHA" > "$BUILD/.lock.sha256"
  fi
  (cd "$BUILD/frontend" && npm run build --silent)
  echo "$STAMP" > "$BUILD/.stamp"
fi
export ANVAYA_FRONTEND_DIST="$BUILD/frontend/dist"

# ------------------------------------------------------------------ serve
if [ "$PRERENDER" = 1 ]; then
  log "prerendering spoken prompts in the background (log: $STATE/prerender.log)"
  nohup "$PY" -m anvaya.manage prerender-audio > "$STATE/prerender.log" 2>&1 &
fi

log "starting gunicorn on http://localhost:$PORT  (ready check: http://localhost:$PORT/api/v1/ready)"
# One worker + threads, as in the Docker image: prometheus_client counters are per process.
exec "$VENV/bin/gunicorn" -w 1 --threads 8 -b "0.0.0.0:$PORT" --chdir "$REPO/backend" wsgi:app
