#!/usr/bin/env bash
set -euo pipefail

# Хостовый вотчер: бот пишет флаг, этот скрипт делает действие на хосте и удаляет файл.
# restart — перезапуск контейнеров; ftp — start/stop vsftpd.
# Обычно запускается из ./compose.sh start (цикл --loop).

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLAG="${DOCKER_RESTART_FLAG:-$ROOT/xtmp-docker/restart}"
RESULT="${DOCKER_RESTART_RESULT:-$ROOT/xtmp-docker/restart.result}"
FTP_FLAG="${FTP_FLAG:-$ROOT/xtmp-docker/ftp}"
FTP_RESULT="${FTP_RESULT:-$ROOT/xtmp-docker/ftp.result}"
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

sysctl_bin() {
  if [ "$(id -u)" -eq 0 ]; then
    systemctl "$@"
  else
    sudo -n systemctl "$@"
  fi
}

ftp_once() {
  if [ ! -f "$FTP_FLAG" ]; then
    return 0
  fi

  local action service req
  action="$(awk -F= '/^action=/{print $2; exit}' "$FTP_FLAG" || true)"
  service="$(awk -F= '/^service=/{print $2; exit}' "$FTP_FLAG" || true)"
  req="$(awk -F= '/^req=/{print $2; exit}' "$FTP_FLAG" || true)"
  rm -f "$FTP_FLAG"
  mkdir -p "$(dirname "$FTP_RESULT")"
  [ -n "$service" ] || service="vsftpd"

  local ok=0
  local detail=""
  local active=0
  local enabled=0
  set +e
  case "$action" in
    on)
      detail="$(sysctl_bin enable --now "$service" 2>&1)"
      ok=$?
      ;;
    off)
      detail="$(sysctl_bin disable --now "$service" 2>&1)"
      ok=$?
      ;;
    *)
      detail="unknown action: $action"
      ok=1
      ;;
  esac
  sysctl_bin is-active --quiet "$service"
  [ $? -eq 0 ] && active=1
  sysctl_bin is-enabled --quiet "$service"
  [ $? -eq 0 ] && enabled=1
  set -e
  detail="${detail//$'\n'/ }"

  {
    echo "req=$req"
    echo "action=$action"
    echo "service=$service"
    if [ "$ok" -eq 0 ]; then
      echo "ok=1"
    else
      echo "ok=0"
    fi
    echo "active=$active"
    echo "enabled=$enabled"
    echo "detail=$detail"
  } >"$FTP_RESULT"
}

mkdir -p "$(dirname "$FLAG")" "$(dirname "$RESULT")" "$(dirname "$FTP_FLAG")" "$(dirname "$FTP_RESULT")"

if [ "${1:-}" = "--loop" ]; then
  while true; do
    restart_once || true
    ftp_once || true
    sleep 2
  done
fi

restart_once
ftp_once
