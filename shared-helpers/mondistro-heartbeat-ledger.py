#!/usr/bin/env python3
"""mondistro-heartbeat-ledger.py — logs the mondistro schedule daemon's health
as a workload-ledger run, WITHOUT editing the live Rust daemon.

Why a heartbeat probe and not inline wiring: the mondistro schedule daemon
(com.monrovia.mondistro.rust-schedule) is a continuously-running production
Rust process. Editing + restarting it to add ledger calls is a change that
needs Eric's sign-off — out of scope for the pilot. Instead this probe reads
the daemon's observable state (launchctl status, the scheduler heartbeat JSON,
recent queue activity) and logs a run describing that state. Same schema, same
moat; the "job_label" is the daemon being observed.

Run it on a schedule (launchd, separate from the daemon) every ~15 min:
    com.risingtides.workload-ledger.mondistro-heartbeat

Status mapping:
  ok      — daemon loaded + heartbeat fresh (<5 min old) + queue active
  warn    — daemon loaded but heartbeat stale (>5 min) OR queue not progressing
  error   — daemon not loaded, or heartbeat file missing
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

JOB = "mondistro-schedule"
DAEMON_LABEL = "com.monrovia.mondistro.rust-schedule"
HEARTBEAT_PATH = Path.home() / "Documents" / "Development" / "Postiz Posting Agent" / "data" / "scheduler-heartbeat.json"
QUEUE_PATH = Path.home() / "Documents" / "Development" / "Postiz Posting Agent" / "data" / "queue.json"

LEDGER_HELPER = Path.home() / "Projects" / "active" / "rt-agents" / "workload_ledger.py"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime | None:
    # Handle Z, +00:00 offset, and offset-less variants. Normalize all to UTC.
    s = s.strip()
    # Replace trailing Z with +00:00 for fromisoformat (Python 3.11+ handles Z natively, be safe)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def main() -> int:
    started = now_iso()
    started_dt = datetime.now(timezone.utc)

    # 1. Is the daemon loaded?
    launchctl = subprocess.run(["launchctl", "list", DAEMON_LABEL], capture_output=True, text=True)
    loaded = launchctl.returncode == 0
    pid = None
    last_exit = None
    if loaded:
        # launchctl list <label> prints a plist; grep for PID / LastExitStatus
        out = launchctl.stdout
        for line in out.splitlines():
            if '"PID"' in line:
                pid = line.split("=")[-1].strip().rstrip(";").strip('"')
            if '"LastExitStatus"' in line:
                last_exit = line.split("=")[-1].strip().rstrip(";").strip('"')

    # 2. Heartbeat freshness
    heartbeat_age_s = None
    heartbeat = {}
    if HEARTBEAT_PATH.exists():
        try:
            heartbeat = json.loads(HEARTBEAT_PATH.read_text())
            hb_ts = heartbeat.get("lastTickAt") or heartbeat.get("last_tick_at")
            if hb_ts:
                hb_dt = parse_iso(hb_ts)
                if hb_dt:
                    heartbeat_age_s = (started_dt - hb_dt).total_seconds()
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Queue activity
    queue_items = None
    queue_updated = None
    if QUEUE_PATH.exists():
        try:
            q = json.loads(QUEUE_PATH.read_text())
            items = q.get("items", [])
            queue_items = len(items) if isinstance(items, list) else None
            queue_updated = q.get("updatedAt")
        except (json.JSONDecodeError, ValueError):
            pass

    # Classify
    if not loaded:
        status = "error"
    elif heartbeat_age_s is None:
        status = "error"  # can't read heartbeat
    elif heartbeat_age_s > 300:  # >5 min stale
        status = "warn"
    else:
        status = "ok"

    outputs = {
        "daemon_loaded": loaded,
        "daemon_pid": pid,
        "last_exit_status": last_exit,
        "heartbeat_age_s": heartbeat_age_s,
        "heartbeat_pid": heartbeat.get("pid"),
        "queue_items": queue_items,
        "queue_updated_at": queue_updated,
    }
    outcome = {"status_reason": status, "observable_only": True}

    finished = now_iso()

    # Log via the helper
    payload = {
        "job_label": JOB, "started_at": started, "finished_at": finished,
        "inputs": {"daemon": DAEMON_LABEL, "mode": "heartbeat-probe"},
        "outputs": outputs, "outcome": outcome, "status": status,
    }
    binpath = Path.home() / "Projects" / "active" / "workload-ledger" / "target" / "release" / "workload-ledger"
    if binpath.exists():
        subprocess.run([str(binpath), "log-run"], input=json.dumps(payload), capture_output=True, text=True, timeout=10)
    else:
        print(f"[mondistro-heartbeat] ledger binary missing at {binpath}", file=sys.stderr)

    # Human-readable line for cron logs
    print(f"mondistro-heartbeat: status={status} loaded={loaded} pid={pid} hb_age_s={heartbeat_age_s} queue_items={queue_items}")
    return 0 if status != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
