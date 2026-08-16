#!/usr/bin/env bash
set -euo pipefail

# Хостовый воркер: бот кладёт job в xtmp-docker/cursor-nas/<id>/, этот скрипт
# запускает `agent -p --force` на хосте и пишет result/status.
# Не печатать api_key и текст промпта.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JOB_DIR="${CURSOR_NAS_DIR:-$ROOT/xtmp-docker/cursor-nas}"
CNF="${CONFIG_PATH:-$ROOT/xtmp-cnf.yaml}"
AGENT_BIN="${CURSOR_AGENT_BIN:-$HOME/.local/bin/agent}"

read_cfg() {
  python3 - "$CNF" <<'PY'
import re, sys
path = sys.argv[1]
key = ""
timeout = 1200
in_cursor = False
in_nas = False
try:
    lines = open(path, encoding="utf-8").read().splitlines()
except OSError:
    print("")
    print("1200")
    raise SystemExit(0)
for line in lines:
    if re.match(r"^cursor:\s*$", line):
        in_cursor = True
        in_nas = False
        continue
    if in_cursor and re.match(r"^[^\s]", line):
        in_cursor = False
        in_nas = False
    if in_cursor and re.match(r"^  nas:\s*$", line):
        in_nas = True
        continue
    if in_nas and re.match(r"^  \S", line) and not line.startswith("    "):
        in_nas = False
    if in_cursor and not in_nas:
        m = re.match(r'^  api_key:\s*["\']?([^"\'\n]+)', line)
        if m:
            key = m.group(1).strip()
    if in_nas:
        m = re.match(r"^    timeout_sec:\s*(\d+)\s*$", line)
        if m:
            timeout = int(m.group(1))
print(key)
print(timeout)
PY
}

job_update() {
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.loads(open(path, encoding="utf-8").read())
if key == "pid":
    data[key] = int(value) if value else None
else:
    data[key] = value
open(path, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
PY
}

next_queued() {
  python3 - "$JOB_DIR" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
if not root.is_dir():
    raise SystemExit(0)
for child in sorted(root.iterdir()):
    path = child / "job.json"
    if not path.is_file():
        continue
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    if str(job.get("status") or "") == "queued":
        print(child)
        raise SystemExit(0)
PY
}

any_running() {
  python3 - "$JOB_DIR" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
if not root.is_dir():
    raise SystemExit(1)
for child in root.iterdir():
    path = child / "job.json"
    if not path.is_file():
        continue
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    if str(job.get("status") or "") == "running":
        raise SystemExit(0)
raise SystemExit(1)
PY
}

run_once() {
  mkdir -p "$JOB_DIR"
  if any_running; then
    return 0
  fi
  local job
  job="$(next_queued || true)"
  [ -n "${job:-}" ] || return 0

  local json="$job/job.json"
  if [ ! -w "$json" ]; then
    echo "cursor-nas: job not writable by watcher, skip" >&2
    return 0
  fi

  local json="$job/job.json"
  local prompt="$job/prompt.txt"
  local result="$job/result.txt"
  local errf="$job/error.txt"
  : >"$result"
  : >"$errf"

  if [ ! -x "$AGENT_BIN" ] && ! command -v agent >/dev/null 2>&1; then
    echo "agent CLI не найден ($AGENT_BIN). Установи: curl https://cursor.com/install -fsS | bash" >"$errf"
    job_update "$json" status error
    return 0
  fi
  if [ -x "$AGENT_BIN" ]; then
    :
  else
    AGENT_BIN="$(command -v agent)"
  fi

  local cfg_line key timeout
  cfg_line="$(read_cfg)"
  key="$(printf '%s\n' "$cfg_line" | sed -n '1p')"
  timeout="$(printf '%s\n' "$cfg_line" | sed -n '2p')"
  [ -n "$timeout" ] || timeout=1200
  if [ -z "$key" ]; then
    echo "Cursor API key не задан в xtmp-cnf.yaml" >"$errf"
    job_update "$json" status error
    return 0
  fi

  job_update "$json" status running
  (
    cd "$job"
    export CURSOR_API_KEY="$key"
    timeout --signal=TERM --kill-after=15 "$timeout" \
      "$AGENT_BIN" -p --force --output-format text "$(cat "$prompt")" \
      >"$result" 2>"$errf"
    echo $? >"$job/exit.code"
  ) &
  local pid=$!
  job_update "$json" pid "$pid"
  set +e
  wait "$pid"
  local rc=$?
  set -e
  if [ "$rc" -eq 0 ]; then
    job_update "$json" status finished
  else
    if [ ! -s "$errf" ]; then
      echo "agent exited $rc" >"$errf"
    fi
    job_update "$json" status error
  fi
  job_update "$json" pid ""
}

if [ "${1:-}" = "--loop" ]; then
  while true; do
    run_once || true
    sleep 2
  done
fi

run_once
