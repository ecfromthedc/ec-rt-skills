"""workload_ledger.py — thin helper for rt-agents Python jobs to log runs to the
workload ledger (the moat). Stdlib only (no deps), so it works in any venv.

Usage (the 10-line pattern the plan asked for):

    from workload_ledger import log_run
    log_run("morning-brief",
            started_at=start_ts, finished_at=finished_ts,
            inputs={"sources": ["gmail","calendar","trello"]},
            outputs={"bullets": n, "draft_path": str(path)},
            outcome={"delivered": True}, status="ok")

Contract / schema (do not change casually — boring + stable is the point):
    runs(id, job_label, started_at, finished_at, duration_ms,
         inputs_json, outputs_json, outcome_json, status)

Secrets: NEVER put tokens/PII in inputs/outputs/outcome. This helper does no
scrubbing — the caller is responsible. If unsure, log counts and paths only.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BIN = Path.home() / "Projects" / "active" / "workload-ledger" / "target" / "release" / "workload-ledger"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_run(
    job_label: str,
    *,
    started_at: str | None = None,
    finished_at: str | None = None,
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    status: str = "ok",
) -> int:
    """Log one run to the workload ledger. Returns the ledger row id, or -1 on failure.

    Best-effort: if the ledger binary or db is unavailable, logs to stderr and
    returns -1 rather than crashing the calling job. The ledger is an
    observability tool — it must never take the job down with it.
    """
    if not _BIN.exists():
        print(f"[workload_ledger] binary not found at {_BIN} — run `cargo build --release` in workload-ledger/. Skipping.", flush=True)
        return -1

    started_at = started_at or _now_iso()
    finished_at = finished_at or _now_iso()
    payload = {
        "job_label": job_label,
        "started_at": started_at,
        "finished_at": finished_at,
        "inputs": inputs or {},
        "outputs": outputs or {},
        "outcome": outcome or {},
        "status": status,
    }
    try:
        proc = subprocess.run(
            [str(_BIN), "log-run"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            print(f"[workload_ledger] log-run exited {proc.returncode}: {proc.stderr.strip()}", flush=True)
            return -1
        # parse "logged run id=N ..." for the row id
        for token in proc.stdout.split():
            if token.startswith("id="):
                return int(token.split("=")[1])
        return 0
    except Exception as e:  # noqa: BLE001 — observability must never throw
        print(f"[workload_ledger] failed to log run: {e}", flush=True)
        return -1


if __name__ == "__main__":
    # Self-test: log one run and print the id.
    rid = log_run(
        "workload-ledger-selftest",
        inputs={"argv": os.sys.argv[1:] if hasattr(os, "sys") else []},
        outputs={"selftest": True},
        outcome={"ok": True},
    )
    print(f"selftest logged run id={rid}")
