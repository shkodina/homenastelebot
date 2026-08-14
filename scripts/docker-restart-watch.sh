#!/usr/bin/env bash
set -euo pipefail

# Хостовый вотчер: бот пишет флаг, этот скрипт перезапускает контейнеры и удаляет файл.
# Обычно запускается из ./compose.sh start (цикл --loop).

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLAG="${DOCKER_RESTART_FLAG:-$ROOT/xtmp-docker/restart}"
RESULT="${DOCKER_RESTART_RESULT:-$ROOT/xtmp-docker/restart.result}"
DOCKER="${DOCKER:-docker}"

should_skip() {
  local name="$1"
  local skip_csv="$2"
  local token
  local IFS=','
  for token in $skip_csv; do
    token="${token// /}"
    [ -n "$token" ] || continue
    if [[ "$name" == *"$token"* ]]; then
      return 0
    fi
  done
  return 1
}

restart_once() {
  if [ ! -f "$FLAG" ]; then
    return 0
  fi

  local skip_csv
  skip_csv="$(awk -F= '/^skip=/{print $2; exit}' "$FLAG" || true)"
  rm -f "$FLAG"
  mkdir -p "$(dirname "$RESULT")"

  local -a ids=()
  local id name
  {
    date -Is
    echo "skip=$skip_csv"
    while read -r id name; do
      [ -n "${id:-}" ] || continue
      if should_skip "$name" "$skip_csv"; then
        echo "skip $name"
        continue
      fi
      echo "queue $name"
      ids+=("$id")
    done < <($DOCKER ps --format '{{.ID}} {{.Names}}')

    if [ "${#ids[@]}" -eq 0 ]; then
      echo "nothing to restart"
    else
      $DOCKER restart "${ids[@]}"
    fi
  } >"$RESULT" 2>&1
}

mkdir -p "$(dirname "$FLAG")" "$(dirname "$RESULT")"

if [ "${1:-}" = "--loop" ]; then
  while true; do
    restart_once || true
    sleep 2
  done
fi

restart_once
