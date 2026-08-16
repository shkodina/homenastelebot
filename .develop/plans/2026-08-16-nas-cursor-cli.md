# NAS Cursor CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (this session: inline — user asked to implement immediately). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Cursor → NAS: after confirm, a host-side `agent -p --force` CLI run with full NAS shell; keep cloud Use unchanged.

**Architecture:** Bot writes a job under `xtmp-docker/cursor-nas/<id>/`. Host watcher `scripts/cursor-nas-watch.sh` picks `queued` jobs and runs `agent`. Bot polls `job.json` and sends text + `TELEGRAM_FILES` from `out/` or inline base64.

**Tech Stack:** Python 3, aiogram 3, unittest, bash watcher, systemd unit, Cursor CLI (`agent`).

## Global Constraints

- Cloud Use stays; NAS is a separate button.
- CLI on the **host**, never in the bot container.
- Confirm (`cmd:cursor.nas.yes`) required before launch; no custom MCP.
- Headless: `agent -p --force --output-format text`.
- One NAS job at a time. Poll ~2s, timeout 1200s.
- No secrets in git or logs. `tests/` gitignored. Do not commit unless the user asks.
- Russian UX, new result messages, don't clobber menus.

## Files

- Create: `bot/cursor_nas.py`, `scripts/cursor-nas-watch.sh`, `deploy/homenas-cursor-nas.service.in`, `tests/test_cursor_nas.py`
- Modify: `bot/cursor_wait.py`, `bot/config.py`, `bot/keyboards.py`, `bot/handlers.py`, `bot/middleware.py`, `bot/cursor_media.py` (NAS hint constant ok in `cursor_nas.py`), `compose.sh`, `scripts/install-autostart.sh`, `cnf.example.yaml`, `xtmp-cnf.yaml`, `.develop/*`, `README.md`

---

### Task 1: Wait / draft / confirm state

**Files:** `bot/cursor_wait.py`, `tests/test_cursor_wait.py`

**Produces:** `arm_nas`, `consume_nas`, `put_nas_draft`, `take_nas_draft`, `NasDraft`; `cancel_use` also clears NAS wait+draft; `arm_use` clears NAS.

### Task 2: Config `cursor.nas`

**Files:** `bot/config.py`, `tests/test_config.py`, `cnf.example.yaml`

**Produces:** `CursorNasConfig(enabled, job_dir, timeout_sec)` on `Config.cursor_nas`.

### Task 3: Job enqueue / busy / poll / preview / NAS prompt

**Files:** `bot/cursor_nas.py`, `tests/test_cursor_nas.py`

**Produces:** `build_nas_prompt`, `preview_nas`, `enqueue_job`, `active_job_id`, `read_job`, `wait_job`, `answer_from_job`.

### Task 4: Telegram wiring

**Files:** `bot/keyboards.py`, `bot/handlers.py`, `bot/middleware.py`

NAS button, confirm keyboard, handlers, middleware does not cancel on `cmd:cursor.use|nas|nas.yes`.

### Task 5: Host watcher + systemd + compose

**Files:** `scripts/cursor-nas-watch.sh`, `deploy/homenas-cursor-nas.service.in`, `compose.sh`, `scripts/install-autostart.sh`

### Task 6: Docs, install CLI, rebuild bot image
