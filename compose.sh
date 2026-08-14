#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

DOCKER="sudo docker"
whoami | grep -q root && DOCKER="docker"
export DOCKER

WATCH="$PWD/scripts/docker-restart-watch.sh"
WATCH_DIR="$PWD/xtmp-docker"
PIDFILE="$WATCH_DIR/watch.pid"
WATCH_LOG="$WATCH_DIR/watch.log"

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

stop_watcher() {
  local pid
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
    $DOCKER compose ps
    ;;
  restart)
    require_config
    mkdir -p "$WATCH_DIR"
    stop_watcher
    echo "$DOCKER compose restart"
    $DOCKER compose restart
    start_watcher
    $DOCKER compose ps
    ;;
  stop)
    stop_watcher
    echo "$DOCKER compose stop"
    $DOCKER compose stop
    $DOCKER compose ps
    ;;
  *)
    usage
    ;;
esac
