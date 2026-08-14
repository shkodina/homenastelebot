#!/usr/bin/env bash
set -euo pipefail

# Ставит systemd-юниты бота и вотчера restart, включает автозапуск.
# Путь к репе подставляется из текущего каталога, в git не хардкодится.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

install_unit() {
  local src="$1"
  local dest="$2"
  sed "s|@ROOT@|$ROOT|g" "$src" | $SUDO tee "$dest" >/dev/null
}

install_unit "$ROOT/deploy/homenasbot.service.in" /etc/systemd/system/homenasbot.service
install_unit "$ROOT/deploy/homenasbot-watch.service.in" /etc/systemd/system/homenasbot-watch.service

$SUDO chmod +x "$ROOT/compose.sh" "$ROOT/scripts/docker-restart-watch.sh"
$SUDO systemctl daemon-reload
$SUDO systemctl enable docker.service
$SUDO systemctl enable homenasbot.service homenasbot-watch.service
$SUDO systemctl restart homenasbot.service

echo "enabled: docker, homenasbot, homenasbot-watch"
$SUDO systemctl is-enabled homenasbot.service homenasbot-watch.service
$SUDO systemctl --no-pager --full status homenasbot.service homenasbot-watch.service || true
