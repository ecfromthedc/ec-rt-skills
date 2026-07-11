# ec-rt-skills

A working set of agent skills, Rust CLIs, and Python jobs for a content-marketing ops fleet — built around a maker/checker content gate, a curation (kill-rate) metric, an ops-exhaust content machine, an append-only workload ledger, and a nightly skill-tuner.

These were built for a specific music-marketing stack (Rising Tides) but the pieces are generic and reusable. Adapt the paths and data sources to your own setup.

## What's here

| Component | Lang | What it does |
|---|---|---|
| **`checker/`** | skill (markdown) | Independent content-gate agent. Takes an artifact + a rubric, returns PASS/FAIL with named, quoted violations. The "checker" half of a maker/checker split. |
| **`curation-ledger/`** | Rust CLI | Tracks the generated→shipped ratio per pipeline/page/week. Flags pages shipping >60% of what they generate (under-curating / slop risk). |
| **`workload-ledger/`** | Rust lib + CLI | Append-only structured run log for every fleet job — the "moat." Schema is deliberately boring and FROZEN. |
| **`ops-exhaust/`** | Python | Nightly job that reads operational data (read-only) and drafts case-study / course-bullet / sales-deck-line content into a review queue. Drafts only, no auto-sends. |
| **`skill-tuner/`** | Python | Nightly job that scans Claude Code session transcripts for user corrections + failed-then-fixed tool sequences, scrubs secrets, and proposes CLAUDE.md/skill diffs. Proposals only, never auto-applies. |
| **`shared-helpers/`** | Python + shell | The workload-ledger Python helper + pilot-job wrappers (morning-brief wrapper, mondistro heartbeat probe). |

## Design principles (the doctrine these follow)
1. **Rust** for new daemons/CLIs (rusqlite + clap + chrono + serde; no async, no network where avoidable). **Python** only for extending an existing Python fleet or ML glue.
2. **Read-only on source data; drafts/proposals only on output.** Nothing auto-posts, auto-sends, or auto-spends. Everything client-facing lands in a review queue with a human approval gate.
3. **No hardcoded secrets.** Env files (0600) or a secrets manager. Reference by var name in code.
4. **Boring, stable schemas.** The workload ledger is the long-term data asset — don't add columns casually; evolve shape inside JSON columns.
5. **Docs convention:** every project has `AGENTS.md` (canonical: purpose, stack, verified run commands, key files, gotchas) + a thin `CLAUDE.md` pointer.

## Setup (adapt paths to your machine)

The code currently assumes the original build layout (`~/Projects/active/...`, `~/Documents/Obsidian Vault/...`). The Rust CLIs are machine-agnostic; the Python jobs reference paths via `Path.home()` so they'll work anywhere, but you'll want to:

1. **Point them at your own data sources.** `ops-exhaust` reads from a SQLite dashboard DB + a Postiz-style performance JSONL — swap those for whatever your pipeline produces. The job is otherwise generic (read numbers → draft content with source-cited footers).
2. **Point the checker at your own rubrics** (or use the four included: brand-voice, creator-list, campaign-budget, platform-compliance — they're templates with placeholder values like `[ARTIST]`/`[LABEL]` for you to fill in).
3. **Install the Rust CLIs:**
   ```bash
   cd curation-ledger && cargo build --release   # → target/release/curation-ledger
   cd workload-ledger && cargo build --release   # → target/release/workload-ledger
   ```
4. **Schedule the Python jobs** via launchd (macOS) or cron, running from a TCC-safe path (NOT `~/Documents` on macOS — launchd can't spawn from there without extra grants). See each job's `AGENTS.md` for the schedule + plist shape.

## Testing

Each component has a verified run command in its `AGENTS.md`. The headline checks:
```bash
# Rust CLIs — unit tests
cd curation-ledger && cargo test --release      # 6 tests
cd workload-ledger && cargo test --release      # 6 tests

# Checker — validate fixtures in CI, then run the blind real-model evaluation
python3 checker/eval.py --validate
python3 checker/eval.py                                      # requires authenticated codex CLI

# Python jobs — dry-run (write nothing)
python3 ops-exhaust/ops-exhaust-drafts.py --dry-run
python3 skill-tuner/skill-tuner.py --dry-run --days 1
```

## Layout
```
checker/                      # the content-gate skill
  SKILL.md                    # how to invoke /checker <artifact> <rubric>
  rubrics/                    # the 4 rubric files (templates with placeholders)
  seeds/                      # 6 test artifacts + expected-results contract
curation-ledger/              # Rust CLI — generated vs shipped kill-rate
workload-ledger/              # Rust lib+CLI — the append-only run log (the moat)
ops-exhaust/                  # Python — operational data → review-queue drafts
skill-tuner/                  # Python — transcripts → proposed skill diffs
shared-helpers/               # workload-ledger Python helper + pilot wrappers
```

## Provenance
Built 2026-07-06 as a multi-work-package handoff. Each component was verified end-to-end against real data (not just unit tests) before being shared. See component-level `AGENTS.md` for the full gotchas + run commands.

## License
Shared for internal/team use. Contains no proprietary data — all artist names, client names, and dollar figures have been replaced with placeholders (`[ARTIST]`, `[LABEL]`, `[TRACK A/B/C]`). Replace with your own when adapting.
