#!/usr/bin/env bash
# morning-brief-ledger-wrap.sh — wraps morning-brief.py, logs a run to the workload ledger.
#
# This is the pilot-wiring pattern: don't edit the 600-line job. Wrap it, time it,
# capture status, log the run. The wrapper is 20 lines and easy to verify / revert.
#
# Cron line (replace the bare morning-brief.py call with this — adapt path to your layout):
#   0 9 * * * $HOME/Projects/active/rt-agents/morning-brief-ledger-wrap.sh >> $HOME/Projects/active/rt-agents/morning-brief.log 2>&1
set -uo pipefail

JOB="morning-brief"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/morning-brief.py"
START_ISO="$(python3 -c 'from datetime import datetime,timezone; print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
START_EPOCH="$(date +%s)"

# Run the real job; capture exit code + stdout. Don't let set -e kill the ledger log.
OUT="$("$PY" --output obsidian 2>&1)"
RC=$?

FINISH_EPOCH="$(date +%s)"
DUR_MS=$(( (FINISH_EPOCH - START_EPOCH) * 1000 ))
FINISH_ISO="$(python3 -c 'from datetime import datetime,timezone; print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))')"

# Classify status: ok / error. (warn/partial left for future nuance.)
STATUS="ok"
[ "$RC" -ne 0 ] && STATUS="error"

# Extract a couple of safe output signals (counts only, no secrets). The job prints
# "Written to <path>" on obsidian success — capture presence, not contents.
WROTE_OBSIDIAN="$(echo "$OUT" | grep -c 'Written to\|Also written to' || true)"

# Log the run via the Python helper (best-effort, never crashes the wrapper).
python3 "$HERE/workload_ledger.py" >/dev/null 2>&1 || true  # ensure helper importable
python3 - "$JOB" "$START_ISO" "$FINISH_ISO" "$DUR_MS" "$STATUS" "$WROTE_OBSIDIAN" "$RC" <<'PYEOF'
import json, subprocess, sys
from pathlib import Path
job, started, finished, dur_ms, status, wrote, rc = sys.argv[1:8]
binpath = Path.home()/"Projects"/"active"/"workload-ledger"/"target"/"release"/"workload-ledger"
payload = {
    "job_label": job, "started_at": started, "finished_at": finished,
    "inputs": {"argv": ["--output","obsidian"]},
    "outputs": {"obsidian_written": int(wrote) > 0, "stdout_lines": len(sys.argv)},
    "outcome": {"exit_code": int(rc), "duration_ms": int(dur_ms)},
    "status": status,
}
subprocess.run([str(binpath), "log-run"], input=json.dumps(payload), capture_output=True, text=True, timeout=10)
PYEOF

# Echo the job's real output so the wrapper is transparent (and cron logs still work).
echo "$OUT"
exit "$RC"
