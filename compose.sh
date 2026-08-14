#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

DOCKER="sudo docker"
whoami | grep -q root && DOCKER="docker"

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

cmd="${1:-}"
case "$cmd" in
  start)
    require_config
    echo "$DOCKER compose up -d --no-build"
    $DOCKER compose up -d --no-build
    $DOCKER compose ps
    ;;
  restart)
    require_config
    echo "$DOCKER compose restart"
    $DOCKER compose restart
    $DOCKER compose ps
    ;;
  stop)
    echo "$DOCKER compose stop"
    $DOCKER compose stop
    $DOCKER compose ps
    ;;
  *)
    usage
    ;;
esac
