# AGENTS.md — workload-ledger

The append-only structured run log for every fleet job. This is **the moat** (swyx's Agent Labs thesis): every job logs {what ran, inputs, outputs, outcome} to one ledger. The corpus becomes the music-marketing dataset nobody else has — and the evidence base for productizing the stack (the sales deck's "what content actually converted" answered by query).

## The schema (FROZEN — do not change casually)

```sql
runs(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_label     TEXT NOT NULL,                    -- e.g. "morning-brief", "mondistro-schedule"
    started_at    TEXT NOT NULL,                    -- ISO 8601 UTC (caller-provided)
    finished_at   TEXT NOT NULL,                    -- ISO 8601 UTC (caller-provided)
    duration_ms   INTEGER NOT NULL,                 -- computed by the CLI from the two timestamps
    inputs_json   TEXT NOT NULL DEFAULT '{}',       -- what the job consumed (paths, sources, params)
    outputs_json  TEXT NOT NULL DEFAULT '{}',       -- what the job produced (counts, paths, draft refs)
    outcome_json  TEXT NOT NULL DEFAULT '{}',       -- what happened (exit code, errors, side effects)
    status        TEXT NOT NULL DEFAULT 'ok'
                  CHECK (status IN ('ok','warn','error','timeout','partial'))
)
```

**This schema is the long-term data asset.** It is deliberately boring and stable. Rules:
- **Never drop or rename a column.** Add new columns with a DEFAULT and a migration if essential; prefer evolving shape inside `outcome_json` (version it there: `{"outcome_version": 2, ...}`).
- **Append-only at the API surface.** No `UPDATE`, no `DELETE` exposed. Mistakes are part of the record; correct them by logging a new run with a `correction_of` pointer in outcome_json.
- **Secrets never logged.** The caller is responsible. The helper does no scrubbing. If unsure, log counts and paths only — never tokens, never PII, never full email bodies. (Note: `morning-brief.py` has hardcoded tokens today — don't copy them into ledger payloads; flag for separate remediation.)
- **Idempotency is NOT provided** (unlike curation-ledger). Each `log-run` is a distinct run. Pipelines that retry will produce multiple rows — that's correct (a retry is a real event worth recording).

Default DB: `~/.workload-ledger/ledger.sqlite` (override with `--db` or `WORKLOAD_LEDGER_DB`).

## Stack
Rust. `rusqlite` (bundled) + `clap` + `chrono` + `serde`. No async, no network. Doctrine-fit.

## Verified run commands
```bash
cargo build --release                   # binary: target/release/workload-ledger
cargo test --release                    # 6 unit tests, all green

# Log a run from stdin JSON
echo '{"job_label":"my-job","started_at":"2026-07-06T09:00:00Z","finished_at":"2026-07-06T09:00:05Z","outputs":{"n":3}}' \
  | ./target/release/workload-ledger log-run

./target/release/workload-ledger query --job morning-brief --limit 20        # newest-first
./target/release/workload-ledger query --since 2026-07-05 --full             # full JSON
./target/release/workload-ledger stats                                       # per-job aggregates
./target/release/workload-ledger stats --since 2026-07-01 --json             # machine-readable
```

## Python helper (for rt-agents jobs)
`~/Projects/active/rt-agents/workload_ledger.py` — 10-line pattern, stdlib only:
```python
from workload_ledger import log_run
log_run("morning-brief",
        started_at=start_ts, finished_at=finished_ts,
        inputs={"sources": ["gmail","calendar"]},
        outputs={"bullets": n, "draft_path": str(path)},
        outcome={"delivered": True}, status="ok")
```
Best-effort: if the binary/db is unavailable, logs to stderr and returns -1 — **never crashes the calling job** (the ledger is observability; it must not take jobs down with it).

## Key files
- `src/main.rs` — everything (~370 lines incl. tests)
- `~/Projects/active/rt-agents/workload_ledger.py` — Python helper (stdlib)
- `~/Projects/active/rt-agents/morning-brief-ledger-wrap.sh` — pilot wrapper for morning-brief
- `~/Projects/active/rt-agents/mondistro-heartbeat-ledger.py` — pilot heartbeat probe for the mondistro daemon

## Pilot jobs wired (3, per plan)
1. **morning-brief** — wrapped via `morning-brief-ledger-wrap.sh` (drop-in cron replacement). Logs inputs/sources, outputs/obsidian_written + bullets, outcome/exit_code.
2. **mondistro-schedule** — observed via `mondistro-heartbeat-ledger.py` (probe, NOT inline daemon edit — the live Rust daemon needs sign-off to restart). Logs daemon_loaded, heartbeat_age_s, queue_items; status reflects health.
3. **ops-exhaust** — logs inline from the WP3 job (see `HANDOFF-WP3-ops-exhaust.md`).

## Gotchas
- **Heartbeat parsing:** the mondistro scheduler writes `lastTickAt` with `+00:00` offset (not `Z`). The heartbeat probe's `parse_iso` handles Z, +00:00, and offset-less — keep it that way. (First probe run surfaced a parser bug that mis-reported the daemon as `error` despite a fresh heartbeat — now fixed; this is exactly the kind of silent-failure the ledger exists to catch.)
- **`status` is a CHECK constraint.** Adding a new status value requires a schema migration (and updating the CHECK). Current set: ok / warn / error / timeout / partial.
- **`finished_at` must be ≥ `started_at`.** The CLI rejects negative durations with an error (tested).
- **mondistro wiring is a probe, not inline.** To wire the daemon itself (log from inside the Rust schedule loop), that's a code change to the mondistro repo + a daemon restart — needs Eric's sign-off, out of scope for the pilot. The probe gives 95% of the observability value (is the daemon healthy? is the queue progressing?) at zero restart risk.
