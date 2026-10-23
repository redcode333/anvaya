#!/usr/bin/env bash
# Prometheus (:9090) + Grafana (:3000) without Docker, inside Ubuntu / WSL, for an app started with
# scripts/run_local.sh (or any app reachable on localhost:5000).
#
# Pinned Linux release binaries (same versions as docker-compose.yml, sha256-verified) are downloaded once into
# ~/.local/anvaya-monitoring — never into the repo. The repo's own configs are used; the only changes, written to
# ~/.local/anvaya-monitoring/conf, are the hostnames Docker networking provides (anvaya:5000 -> localhost:5000,
# prometheus:9090 -> localhost:9090) and the dashboards path. Ctrl-C stops both.
#
# Usage: scripts/run_monitoring_local.sh        (PROMETHEUS_PORT / GRAFANA_PORT override 9090 / 3000)
# Settings from the repo-root .env: GRAFANA_ADMIN_PASSWORD (default anvaya-grafana; applied when Grafana's data
# directory is first created), GRAFANA_ANONYMOUS=true|false (read-only anonymous viewing, default true).
set -euo pipefail

LOG_TAG=monitoring
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/_env.sh
. "$REPO/scripts/_env.sh"

HOME_DIR="${ANVAYA_MONITORING_HOME:-$HOME/.local/anvaya-monitoring}"
PROM_PORT="${PROMETHEUS_PORT:-9090}"
GRAFANA_PORT="${GRAFANA_PORT:-3000}"
PROM_VERSION=2.54.1
GRAFANA_VERSION=11.2.2
declare -A PROM_SHA256=(
  [amd64]=31715ef65e8a898d0f97c8c08c03b6b9afe485ac84e1698bcfec90fc6e62924f
  [arm64]=3d9946ca730f2679bbd63e9d40e559a0ba227a638d237e723af1a99bd7098263
)
declare -A GRAFANA_SHA256=(
  [amd64]=860197db2000579589b02fbce724af5d008289efd208637f56ea311bdb726cfa
  [arm64]=b96563d3cfe3acaba472937d7005b987b03bf6c941da4ea90c5f76759548aafc
)

load_env "$REPO"
ARCH="$(linux_arch)"
mkdir -p "$HOME_DIR/dist" "$HOME_DIR/data/prometheus" "$HOME_DIR/data/grafana" "$HOME_DIR/logs"

# ------------------------------------------------------------------ binaries
PROM_HOME="$HOME_DIR/prometheus-$PROM_VERSION.linux-$ARCH"
if [ ! -x "$PROM_HOME/prometheus" ]; then
  tgz="$HOME_DIR/dist/prometheus-$PROM_VERSION.linux-$ARCH.tar.gz"
  fetch_pinned "https://github.com/prometheus/prometheus/releases/download/v$PROM_VERSION/$(basename "$tgz")" \
    "$tgz" "${PROM_SHA256[$ARCH]}"
  tar -xzf "$tgz" -C "$HOME_DIR"
fi

GRAFANA_HOME="$HOME_DIR/grafana-v$GRAFANA_VERSION"
if [ ! -x "$GRAFANA_HOME/bin/grafana" ]; then
  tgz="$HOME_DIR/dist/grafana-$GRAFANA_VERSION.linux-$ARCH.tar.gz"
  fetch_pinned "https://dl.grafana.com/oss/release/$(basename "$tgz")" "$tgz" "${GRAFANA_SHA256[$ARCH]}"
  tar -xzf "$tgz" -C "$HOME_DIR"
  [ -x "$GRAFANA_HOME/bin/grafana" ] || GRAFANA_HOME="$(find "$HOME_DIR" -maxdepth 1 -type d -name "grafana*$GRAFANA_VERSION*" | head -1)"
fi
[ -x "$GRAFANA_HOME/bin/grafana" ] || die "Grafana binary not found under $HOME_DIR"

# ------------------------------------------------------------------ configs (derived from the repo's)
CONF="$HOME_DIR/conf"
rm -rf "$CONF"
mkdir -p "$CONF/grafana/provisioning/datasources" "$CONF/grafana/provisioning/dashboards"
sed 's#anvaya:5000#localhost:5000#' "$REPO/monitoring/prometheus/prometheus.yml" > "$CONF/prometheus.yml"
sed "s#http://prometheus:9090#http://localhost:$PROM_PORT#" \
  "$REPO/monitoring/grafana/provisioning/datasources/prometheus.yml" > "$CONF/grafana/provisioning/datasources/prometheus.yml"
sed "s#/var/lib/grafana/dashboards#$REPO/monitoring/grafana/dashboards#" \
  "$REPO/monitoring/grafana/provisioning/dashboards/dashboards.yml" > "$CONF/grafana/provisioning/dashboards/dashboards.yml"

# ------------------------------------------------------------------ run
pids=()
cleanup() { trap - INT TERM EXIT; [ ${#pids[@]} -gt 0 ] && kill "${pids[@]}" 2>/dev/null; wait 2>/dev/null; log "stopped"; }
trap cleanup INT TERM EXIT

"$PROM_HOME/prometheus" \
  --config.file="$CONF/prometheus.yml" \
  --storage.tsdb.path="$HOME_DIR/data/prometheus" \
  --storage.tsdb.retention.time=7d \
  --web.listen-address="0.0.0.0:$PROM_PORT" \
  > "$HOME_DIR/logs/prometheus.log" 2>&1 &
pids+=($!)

ANON="$(printf '%s' "${GRAFANA_ANONYMOUS:-true}" | tr '[:upper:]' '[:lower:]')"
[ "$ANON" = true ] || [ "$ANON" = false ] || die "GRAFANA_ANONYMOUS must be true or false"
GF_PATHS_DATA="$HOME_DIR/data/grafana" \
GF_PATHS_LOGS="$HOME_DIR/logs" \
GF_PATHS_PLUGINS="$HOME_DIR/data/grafana/plugins" \
GF_PATHS_PROVISIONING="$CONF/grafana/provisioning" \
GF_SERVER_HTTP_PORT="$GRAFANA_PORT" \
GF_SECURITY_ADMIN_USER=admin \
GF_SECURITY_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-anvaya-grafana}" \
GF_AUTH_ANONYMOUS_ENABLED="$ANON" \
GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \
GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH="$REPO/monitoring/grafana/dashboards/anvaya.json" \
GF_USERS_ALLOW_SIGN_UP=false \
GF_ANALYTICS_REPORTING_ENABLED=false \
GF_ANALYTICS_CHECK_FOR_UPDATES=false \
  "$GRAFANA_HOME/bin/grafana" server --homepath "$GRAFANA_HOME" \
  > "$HOME_DIR/logs/grafana.stdout.log" 2>&1 &
pids+=($!)

log "Prometheus $PROM_VERSION → http://localhost:$PROM_PORT  (scrapes http://localhost:5000/metrics; log $HOME_DIR/logs/prometheus.log)"
log "Grafana $GRAFANA_VERSION → http://localhost:$GRAFANA_PORT  (anonymous viewing: $ANON; admin user 'admin'; log $HOME_DIR/logs/)"
log "Ctrl-C stops both"
wait -n "${pids[@]}" || true
die "a monitoring process exited — see the logs in $HOME_DIR/logs"
