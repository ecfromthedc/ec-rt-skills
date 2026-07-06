# AGENTS.md — curation-ledger

Kill-rate / curation metric for content pipelines. The thesis (swyx): volume is solved, the ratio is the game. A page shipping >60% of what it generates is under-curating (slop risk); a page shipping ~0% is over-producing. This tool makes the generated→shipped ratio queryable per pipeline/page/week.

## Stack
Rust. `rusqlite` (bundled SQLite) + `clap` + `chrono` + `serde`. No async, no ORM, no network, no external services. Doctrine-fit (existing fleet-sentinel pattern).

## Schema (the long-term asset — keep boring + stable)
```sql
generated(id, pipeline, page, artifact_ref, created_at)        -- UNIQUE(pipeline,page,artifact_ref)
shipped(id, generated_id FK→generated, shipped_at, post_url)   -- UNIQUE(generated_id)
```
- `pipeline` = what produced it (e.g. `mon-distro`, `carousels`, `sales-deck`)
- `page` = the owned destination (e.g. `monrovia.ig`, `monrovia.tt`)
- `artifact_ref` = the join key to the producing pipeline (filename, queue_item_id, url)
- Both tables are **idempotent** on their natural keys: re-logging the same generated artifact or re-shipping it is a no-op, not a duplicate. This matters because pipelines retry; we don't want inflated counts.

Default DB: `~/.curation-ledger/ledger.sqlite` (override with `--db` or `CURATION_LEDGER_DB`).

## Verified run commands
```bash
cargo build --release              # binary: target/release/curation-ledger
cargo test --release               # 6 unit tests, all green

./target/release/curation-ledger log-generated --pipeline mon-distro --page monrovia.ig --artifact-ref ig-001
./target/release/curation-ledger log-shipped --artifact-ref ig-001 --post-url https://instagram.com/p/ig-001
./target/release/curation-ledger report                          # all-time, per pipeline/page
./target/release/curation-ledger report --week 2026-W28          # filter to ISO week
./target/release/curation-ledger report --pipeline mon-distro --json   # machine-readable
./target/release/curation-ledger report --slop-threshold 0.5     # tune the flag threshold
```

## Key files
- `src/main.rs` — everything (~330 lines: schema, CLI, report, tests in one file)
- `Cargo.toml` — 4 deps, all bundled/offline

## Gotchas
- **Idempotency is the contract.** Pipelines can retry `log-generated` / `log-shipped` safely — the natural-key UNIQUE constraints dedupe. Do NOT remove those constraints or counts will inflate on retry.
- **ISO week filter** buckets by the generated timestamp's ISO week. A row generated 2026-07-05 (Sunday, W27) won't appear in a `--week 2026-W28` report even if shipped in W28 — the curation ratio is attributed to the generation week, which is the right semantics (we measure the production batch's kill-rate).
- **`log-shipped` on an unknown `artifact_ref`** exits 2 with an error. The pipeline must log-generated first. The pure helper `ship_artifact()` returns `Result` for programmatic use; the CLI wrapper exits.
- **Not wired into live pipelines yet** (per plan: Claude verifies the tool first). Wiring = one `log-generated` call per artifact produced, one `log-shipped` call per post URL after publish. The `--json` report mode is the integration seam for dashboards.
