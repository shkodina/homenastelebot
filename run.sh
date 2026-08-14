#!/usr/bin/env bash
set -euo pipefail

DOCKER="sudo docker"
whoami | grep -q root && DOCKER="docker"

if [ ! -f xtmp-cnf.yaml ]; then
  echo "Нет xtmp-cnf.yaml — скопируй cnf.example.yaml и заполни telegram.token / allowed_ids" >&2
  exit 1
fi

echo "$DOCKER build --network=host -t homenasbot-base:latest -f Dockerfile.base ."
$DOCKER build --network=host -t homenasbot-base:latest -f Dockerfile.base .

echo "$DOCKER build --network=host -t homenasbot:latest -f Dockerfile ."
$DOCKER build --network=host -t homenasbot:latest -f Dockerfile .

echo "$DOCKER compose up -d --no-build"
./compose.sh start
