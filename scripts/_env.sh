# Shared by scripts/run_local.sh and scripts/run_monitoring_local.sh (sourced, not run).
# Reads the repo-root .env the way docker compose does: KEY=VALUE lines, optional quotes, "#" comments.
# Lines are exported as plain strings — never evaluated as shell — and values are never printed.
# Variables already set in the environment win over .env.

log() { printf '\033[1m[%s]\033[0m %s\n' "${LOG_TAG:-anvaya}" "$*"; }
die() { printf '[%s] ERROR: %s\n' "${LOG_TAG:-anvaya}" "$*" >&2; exit 1; }

load_env() {
  local f="$1/.env" line key val n=0
  if [ ! -f "$f" ]; then
    log "no .env found — optional integrations (VerbX, LLM providers) stay off; demo passwords are used"
    return 0
  fi
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
    key="${BASH_REMATCH[2]}"
    val="${BASH_REMATCH[3]}"
    if [[ "$val" =~ ^\"(.*)\"[[:space:]]*$ ]] || [[ "$val" =~ ^\'(.*)\'[[:space:]]*$ ]]; then
      val="${BASH_REMATCH[1]}"
    else
      val="${val%%[[:space:]]#*}"                 # unquoted: " # comment" ends the value
      val="${val%"${val##*[![:space:]]}"}"        # trim trailing spaces
    fi
    if [ -z "${!key+x}" ]; then
      export "$key=$val"
      n=$((n + 1))
    fi
  done < "$f"
  log "loaded $n settings from .env (values not shown)"
}

# sha256 of a downloaded file must match the pinned value.
verify_sha256() {
  local file="$1" want="$2" got
  got="$(sha256sum "$file" | cut -d' ' -f1)"
  [ "$got" = "$want" ] || { rm -f "$file"; die "checksum mismatch for $(basename "$file") (expected $want, got $got)"; }
}

# Download url to dest once (atomic rename), verifying the pinned checksum.
fetch_pinned() {
  local url="$1" dest="$2" sha="$3"
  if [ -f "$dest" ]; then verify_sha256 "$dest" "$sha"; return 0; fi
  log "downloading $(basename "$dest")"
  mkdir -p "$(dirname "$dest")"
  local progress=-sS
  [ -t 2 ] && progress=--progress-bar
  curl -fL --retry 3 "$progress" -o "$dest.part" "$url" || die "download failed: $url"
  mv "$dest.part" "$dest"
  verify_sha256 "$dest" "$sha"
}

linux_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo amd64 ;;
    aarch64|arm64) echo arm64 ;;
    *) die "unsupported CPU architecture $(uname -m)" ;;
  esac
}

# A Linux binary, not a Windows one reached through WSL's PATH interop (/mnt/c/...).
linux_cmd() {
  local p
  p="$(command -v "$1" 2>/dev/null)" || return 1
  case "$p" in /mnt/*) return 1 ;; esac
  printf '%s\n' "$p"
}
