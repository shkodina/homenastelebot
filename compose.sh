#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

DOCKER="sudo docker"
whoami | grep -q root && DOCKER="docker"
export DOCKER

WATCH="$PWD/scripts/docker-restart-watch.sh"
NAS_WATCH="$PWD/scripts/cursor-nas-watch.sh"
WATCH_DIR="$PWD/xtmp-docker"
PIDFILE="$WATCH_DIR/watch.pid"
WATCH_LOG="$WATCH_DIR/watch.log"
NAS_PIDFILE="$WATCH_DIR/cursor-nas.pid"
NAS_LOG="$WATCH_DIR/cursor-nas.log"

usage() {
  echo "usage: $0 start|restart|stop" >&2
  exit 1
}

require_config() {
  if [ ! -f xtmp-cnf.yaml ]; then
    echo "Нет xtmp-cnf.yaml — скопируй cnf.example.yaml и заполни telegram.token / allowed_ids" >&2
    exit 1
  fi
}

watcher_running() {
  local pid
  [ -f "$PIDFILE" ] || return 1
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

start_watcher() {
  mkdir -p "$WATCH_DIR"
  chmod +x "$WATCH" 2>/dev/null || true
  if [ "${HOMENASBOT_SKIP_WATCHER:-}" = 1 ]; then
    echo "restart-watch via systemd"
    return 0
  fi
  if systemctl is-active --quiet homenasbot-watch.service 2>/dev/null; then
    echo "restart-watch already via systemd"
    return 0
  fi
  if watcher_running; then
    echo "restart-watch already running pid=$(cat "$PIDFILE")"
    return 0
  fi
  rm -f "$PIDFILE"
  echo "restart-watch --loop"
  nohup env DOCKER="$DOCKER" "$WATCH" --loop >>"$WATCH_LOG" 2>&1 &
  echo $! >"$PIDFILE"
  echo "restart-watch pid=$(cat "$PIDFILE")"
}

nas_watcher_running() {
  local pid
  [ -f "$NAS_PIDFILE" ] || return 1
  pid="$(cat "$NAS_PIDFILE" 2>/dev/null || true)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null
}

start_nas_watcher() {
  mkdir -p "$WATCH_DIR"
  chmod +x "$NAS_WATCH" 2>/dev/null || true
  if [ "${HOMENASBOT_SKIP_WATCHER:-}" = 1 ]; then
    echo "cursor-nas-watch via systemd"
    return 0
  fi
  if systemctl is-active --quiet homenas-cursor-nas.service 2>/dev/null; then
    echo "cursor-nas-watch already via systemd"
    return 0
  fi
  if nas_watcher_running; then
    echo "cursor-nas-watch already running pid=$(cat "$NAS_PIDFILE")"
    return 0
  fi
  rm -f "$NAS_PIDFILE"
  echo "cursor-nas-watch --loop"
  nohup "$NAS_WATCH" --loop >>"$NAS_LOG" 2>&1 &
  echo $! >"$NAS_PIDFILE"
  echo "cursor-nas-watch pid=$(cat "$NAS_PIDFILE")"
}

stop_nas_watcher() {
  local pid
  if systemctl is-active --quiet homenas-cursor-nas.service 2>/dev/null; then
    echo "cursor-nas-watch managed by systemd, skip kill"
    return 0
  fi
  if ! nas_watcher_running; then
    rm -f "$NAS_PIDFILE"
    echo "cursor-nas-watch not running"
    return 0
  fi
  pid="$(cat "$NAS_PIDFILE")"
  echo "stop cursor-nas-watch pid=$pid"
  kill "$pid" 2>/dev/null || true
  local i
  for i in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.2
  done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$NAS_PIDFILE"
}

stop_watcher() {
  local pid
  if systemctl is-active --quiet homenasbot-watch.service 2>/dev/null; then
    echo "restart-watch managed by systemd, skip kill"
    return 0
  fi
  if ! watcher_running; then
    rm -f "$PIDFILE"
    echo "restart-watch not running"
    return 0
  fi
  pid="$(cat "$PIDFILE")"
  echo "stop restart-watch pid=$pid"
  kill "$pid" 2>/dev/null || true
  local i
  for i in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.2
  done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PIDFILE"
}

cmd="${1:-}"
case "$cmd" in
  start)
    require_config
    mkdir -p "$WATCH_DIR"
    echo "$DOCKER compose up -d --no-build"
    $DOCKER compose up -d --no-build
    start_watcher
    start_nas_watcher
    $DOCKER compose ps
    ;;
  restart)
    require_config
    mkdir -p "$WATCH_DIR"
    stop_watcher
    stop_nas_watcher
    echo "$DOCKER compose restart"
    $DOCKER compose restart
    start_watcher
    start_nas_watcher
    $DOCKER compose ps
    ;;
  stop)
    stop_watcher
    stop_nas_watcher
    echo "$DOCKER compose stop"
    $DOCKER compose stop
    $DOCKER compose ps
    ;;
  *)
    usage
    ;;
esac
