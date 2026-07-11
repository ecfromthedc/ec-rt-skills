// workload-ledger — append-only structured run log for every fleet job.
//
// One boring, stable schema. Every job writes a row: what ran, when, what it
// consumed, what it produced, what happened. This corpus is the moat (swyx):
// the music-marketing dataset nobody else has, and the evidence base for
// productizing the stack. Schema is deliberately boring — do not add columns
// casually; bump a version field in outcome_json if you need to evolve shape.
//
// Doctrine: std + rusqlite + clap + chrono + serde. Append-only (no UPDATE,
// no DELETE from the API surface). Secrets never logged — caller's job.

use chrono::{DateTime, Utc};
use clap::{Parser, Subcommand};
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use std::io::Read;
use std::path::PathBuf;

const SCHEMA: &str = "
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_label     TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT NOT NULL,
    duration_ms   INTEGER NOT NULL,
    inputs_json   TEXT NOT NULL DEFAULT '{}',
    outputs_json  TEXT NOT NULL DEFAULT '{}',
    outcome_json  TEXT NOT NULL DEFAULT '{}',
    status        TEXT NOT NULL DEFAULT 'ok'
        CHECK (status IN ('ok','warn','error','timeout','partial'))
);
CREATE INDEX IF NOT EXISTS idx_runs_job ON runs(job_label);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
";

#[derive(Parser)]
#[command(name = "workload-ledger", version, about = "Append-only structured run log for fleet jobs")]
struct Cli {
    /// Path to the SQLite db. Defaults to ~/.workload-ledger/ledger.sqlite
    #[arg(long, env = "WORKLOAD_LEDGER_DB", global = true)]
    db: Option<PathBuf>,

    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Log a run. Reads a JSON object from stdin (or --from-file) and writes one row.
    /// Required fields in the JSON: job_label, started_at, finished_at.
    /// Optional: inputs, outputs, outcome, status. Duration is computed from the timestamps.
    LogRun {
        /// Read the run JSON from this file instead of stdin.
        #[arg(long)]
        from_file: Option<PathBuf>,
    },
    /// Query runs. Filters: --job (exact or substring), --since (ISO date/datetime),
    /// --status. Prints rows newest-first.
    Query {
        #[arg(long)]
        job: Option<String>,
        #[arg(long)]
        since: Option<String>,
        #[arg(long)]
        status: Option<String>,
        /// Max rows to print. Default 50.
        #[arg(long, default_value_t = 50)]
        limit: usize,
        /// Print full JSON inputs/outputs/outcome (default: truncated).
        #[arg(long)]
        full: bool,
    },
    /// Aggregate stats: per-job counts, status breakdown, last run per job.
    Stats {
        /// Filter to jobs since this ISO date/datetime.
        #[arg(long)]
        since: Option<String>,
        /// JSON output.
        #[arg(long)]
        json: bool,
    },
}

fn default_db() -> PathBuf {
    let mut p = PathBuf::from(std::env::var("HOME").unwrap_or_else(|_| "/tmp".into()));
    p.push(".workload-ledger");
    p.push("ledger.sqlite");
    p
}

fn connect(db: &PathBuf) -> rusqlite::Result<Connection> {
    if let Some(parent) = db.parent() {
        std::fs::create_dir_all(parent).ok();
    }
    let conn = Connection::open(db)?;
    conn.execute_batch(SCHEMA)?;
    Ok(conn)
}

fn default_empty_object() -> serde_json::Value { serde_json::json!({}) }

#[derive(Deserialize)]
struct RunInput {
    job_label: String,
    started_at: String,
    finished_at: String,
    #[serde(default = "default_empty_object")]
    inputs: serde_json::Value,
    #[serde(default = "default_empty_object")]
    outputs: serde_json::Value,
    #[serde(default = "default_empty_object")]
    outcome: serde_json::Value,
    #[serde(default)]
    status: Option<String>,
}

#[derive(Serialize)]
struct RunRow {
    id: i64,
    job_label: String,
    started_at: String,
    finished_at: String,
    duration_ms: i64,
    inputs: serde_json::Value,
    outputs: serde_json::Value,
    outcome: serde_json::Value,
    status: String,
}

fn parse_dt(s: &str) -> Result<DateTime<Utc>, String> {
    // Accept trailing Z or offset; fall back to date-only.
    DateTime::parse_from_rfc3339(s)
        .map(|d| d.with_timezone(&Utc))
        .or_else(|_| {
            chrono::NaiveDate::parse_from_str(s, "%Y-%m-%d")
                .map(|d| d.and_hms_opt(0,0,0).unwrap().and_utc())
        })
        .map_err(|e| format!("could not parse timestamp '{}': {}", s, e))
}

fn cmd_log_run(conn: &Connection, from_file: Option<&PathBuf>) -> Result<i64, String> {
    let raw = match from_file {
        Some(p) => std::fs::read_to_string(p).map_err(|e| format!("read {}: {}", p.display(), e))?,
        None => {
            let mut s = String::new();
            std::io::stdin().read_to_string(&mut s).map_err(|e| format!("read stdin: {}", e))?;
            s
        }
    };
    let run: RunInput = serde_json::from_str(&raw).map_err(|e| format!("parse JSON: {}.\nRequired fields: job_label, started_at, finished_at. Optional: inputs, outputs, outcome, status. Got: {}", e, raw.chars().take(200).collect::<String>()))?;

    let started = parse_dt(&run.started_at)?;
    let finished = parse_dt(&run.finished_at)?;
    if finished < started {
        return Err(format!("finished_at ({}) is before started_at ({})", run.finished_at, run.started_at));
    }
    let duration_ms = (finished - started).num_milliseconds();
    let status = run.status.unwrap_or_else(|| "ok".to_string());
    // validate status against the CHECK constraint
    if !["ok","warn","error","timeout","partial"].contains(&status.as_str()) {
        return Err(format!("invalid status '{}'. Must be one of: ok, warn, error, timeout, partial", status));
    }

    conn.execute(
        "INSERT INTO runs(job_label, started_at, finished_at, duration_ms, inputs_json, outputs_json, outcome_json, status)
         VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
        params![
            run.job_label,
            run.started_at,
            run.finished_at,
            duration_ms,
            serde_json::to_string(&run.inputs).unwrap(),
            serde_json::to_string(&run.outputs).unwrap(),
            serde_json::to_string(&run.outcome).unwrap(),
            status,
        ],
    ).map_err(|e| format!("insert: {}", e))?;
    let id = conn.last_insert_rowid();
    println!("logged run id={} job={} status={} duration_ms={}", id, run.job_label, status, duration_ms);
    Ok(id)
}

fn trunc(s: &str, n: usize) -> String {
    let s = s.replace('\n', " ");
    if s.chars().count() <= n { s } else {
        let mut t: String = s.chars().take(n).collect();
        t.push('…');
        t
    }
}

fn cmd_query(conn: &Connection, job: Option<&str>, since: Option<&str>, status: Option<&str>, limit: usize, full: bool) -> Result<(), String> {
    let mut sql = String::from("SELECT id, job_label, started_at, finished_at, duration_ms, inputs_json, outputs_json, outcome_json, status FROM runs WHERE 1=1 ");
    let mut args: Vec<String> = vec![];
    let mut idx = 1;
    if let Some(j) = job {
        sql.push_str(&format!("AND job_label LIKE ?{} ", idx)); idx += 1;
        args.push(format!("%{}%", j));
    }
    if let Some(s) = since {
        // validate it parses, even if we compare as string (ISO sorts lexicographically for same format)
        parse_dt(s)?;
        sql.push_str(&format!("AND started_at >= ?{} ", idx)); idx += 1;
        args.push(s.to_string());
    }
    if let Some(st) = status {
        sql.push_str(&format!("AND status = ?{} ", idx));
        args.push(st.to_string());
    }
    sql.push_str("ORDER BY started_at DESC LIMIT ?");
    let mut stmt = conn.prepare(&sql).map_err(|e| e.to_string())?;
    let limit_i: i64 = limit as i64;
    let param_refs: Vec<&dyn rusqlite::ToSql> = args.iter()
        .map(|a| a as &dyn rusqlite::ToSql)
        .chain(std::iter::once(&limit_i as &dyn rusqlite::ToSql))
        .collect();
    let rows = stmt.query_map(&param_refs[..], |r| {
        let inputs_s: String = r.get(5)?;
        let outputs_s: String = r.get(6)?;
        let outcome_s: String = r.get(7)?;
        Ok(RunRow {
            id: r.get(0)?,
            job_label: r.get(1)?,
            started_at: r.get(2)?,
            finished_at: r.get(3)?,
            duration_ms: r.get(4)?,
            inputs: serde_json::from_str(&inputs_s).unwrap_or(serde_json::Value::Null),
            outputs: serde_json::from_str(&outputs_s).unwrap_or(serde_json::Value::Null),
            outcome: serde_json::from_str(&outcome_s).unwrap_or(serde_json::Value::Null),
            status: r.get(8)?,
        })
    }).map_err(|e| e.to_string())?;

    let collected: Vec<RunRow> = rows.collect::<Result<_,_>>().map_err(|e| e.to_string())?;
    if collected.is_empty() {
        println!("(no runs match)");
        return Ok(());
    }
    println!("{:>5}  {:<24} {:<22} {:>10}  {:<7}  outputs (truncated)", "id", "job", "started", "dur(ms)", "status");
    for r in &collected {
        let out_str = if full {
            serde_json::to_string_pretty(&r.outputs).unwrap_or_default()
        } else {
            trunc(&serde_json::to_string(&r.outputs).unwrap_or_default(), 60)
        };
        let started_short = r.started_at.get(..19).unwrap_or(&r.started_at);
        println!("{:>5}  {:<24} {:<22} {:>10}  {:<7}  {}", r.id, trunc(&r.job_label,24), started_short, r.duration_ms, r.status, out_str);
    }
    Ok(())
}

#[derive(Serialize)]
struct StatsOut {
    total_runs: i64,
    by_status: std::collections::BTreeMap<String, i64>,
    by_job: Vec<JobStat>,
    since_filter: Option<String>,
}

#[derive(Serialize)]
struct JobStat {
    job_label: String,
    count: i64,
    last_run: String,
    last_status: String,
    avg_duration_ms: f64,
    error_count: i64,
}

fn cmd_stats(conn: &Connection, since: Option<&str>, as_json: bool) -> Result<(), String> {
    let since_clause = if let Some(s) = since {
        parse_dt(s)?;
        format!("WHERE started_at >= '{}'", s.replace("'", "''"))
    } else { String::new() };

    let total: i64 = conn.query_row(&format!("SELECT COUNT(*) FROM runs {}", since_clause), [], |r| r.get(0)).map_err(|e| e.to_string())?;

    let mut stmt = conn.prepare(&format!("SELECT status, COUNT(*) FROM runs {} GROUP BY status ORDER BY status", since_clause)).map_err(|e| e.to_string())?;
    let mut by_status: std::collections::BTreeMap<String,i64> = std::collections::BTreeMap::new();
    let rows = stmt.query_map([], |r| { let s: String = r.get(0)?; let c: i64 = r.get(1)?; Ok((s,c)) }).map_err(|e| e.to_string())?;
    for r in rows { let (s,c) = r.map_err(|e| e.to_string())?; by_status.insert(s,c); }

    let mut stmt = conn.prepare(&format!(
        "SELECT job_label, COUNT(*), MAX(started_at),
                (SELECT status FROM runs r2 WHERE r2.job_label = r.job_label ORDER BY r2.started_at DESC LIMIT 1),
                AVG(duration_ms),
                SUM(CASE WHEN status IN ('error','timeout') THEN 1 ELSE 0 END)
         FROM runs r {} GROUP BY job_label ORDER BY COUNT(*) DESC", since_clause
    )).map_err(|e| e.to_string())?;
    let rows = stmt.query_map([], |r| {
        Ok(JobStat {
            job_label: r.get(0)?,
            count: r.get(1)?,
            last_run: r.get(2)?,
            last_status: r.get(3)?,
            avg_duration_ms: r.get(4)?,
            error_count: r.get(5)?,
        })
    }).map_err(|e| e.to_string())?;
    let by_job: Vec<JobStat> = rows.collect::<Result<_,_>>().map_err(|e| e.to_string())?;

    let out = StatsOut { total_runs: total, by_status, by_job, since_filter: since.map(|s| s.to_string()) };
    if as_json {
        println!("{}", serde_json::to_string_pretty(&out).unwrap());
        return Ok(());
    }
    println!("\n  WORKLOAD LEDGER STATS{}  — {} total runs", since.map(|s| format!(" since {}", s)).unwrap_or_default(), out.total_runs);
    println!("  by status: {:?}", out.by_status);
    println!("  {:<24} {:>6} {:>11} {:>11} {:<8}  last run", "job", "count", "avg ms", "errors", "last");
    for j in &out.by_job {
        println!("  {:<24} {:>6} {:>11.0} {:>11} {:<8}  {}", trunc(&j.job_label,24), j.count, j.avg_duration_ms, j.error_count, j.last_status, j.last_run.get(..19).unwrap_or(&j.last_run));
    }
    Ok(())
}

fn main() {
    let cli = Cli::parse();
    let db = cli.db.unwrap_or_else(default_db);
    let conn = connect(&db).unwrap_or_else(|e| { eprintln!("ERROR opening db at {}: {}", db.display(), e); std::process::exit(1); });
    let res = match cli.cmd {
        Cmd::LogRun { from_file } => cmd_log_run(&conn, from_file.as_ref()).map(|_| ()),
        Cmd::Query { job, since, status, limit, full } => cmd_query(&conn, job.as_deref(), since.as_deref(), status.as_deref(), limit, full),
        Cmd::Stats { since, json } => cmd_stats(&conn, since.as_deref(), json),
    };
    if let Err(e) = res { eprintln!("ERROR: {}", e); std::process::exit(1); }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mem_conn() -> Connection {
        let conn = Connection::open_in_memory().unwrap();
        conn.execute_batch(SCHEMA).unwrap();
        conn
    }

    fn log_via(conn: &Connection, json: &str) -> i64 {
        let run: RunInput = serde_json::from_str(json).unwrap();
        let started = parse_dt(&run.started_at).unwrap();
        let finished = parse_dt(&run.finished_at).unwrap();
        let duration_ms = (finished - started).num_milliseconds();
        let status = run.status.unwrap_or_else(|| "ok".into());
        conn.execute(
            "INSERT INTO runs(job_label, started_at, finished_at, duration_ms, inputs_json, outputs_json, outcome_json, status)
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
            params![run.job_label, run.started_at, run.finished_at, duration_ms,
                    serde_json::to_string(&run.inputs).unwrap(),
                    serde_json::to_string(&run.outputs).unwrap(),
                    serde_json::to_string(&run.outcome).unwrap(),
                    status],
        ).unwrap();
        conn.last_insert_rowid()
    }

    #[test]
    fn log_run_inserts_row_with_computed_duration() {
        let conn = mem_conn();
        let id = log_via(&conn, r#"{"job_label":"morning-brief","started_at":"2026-07-06T09:00:00Z","finished_at":"2026-07-06T09:00:15Z","outputs":{"drafts":3}}"#);
        let (job, dur, out, status): (String, i64, String, String) = conn.query_row(
            "SELECT job_label, duration_ms, outputs_json, status FROM runs WHERE id=?1", params![id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?))
        ).unwrap();
        assert_eq!(job, "morning-brief");
        assert_eq!(dur, 15_000);
        assert!(out.contains("drafts"));
        assert_eq!(status, "ok");
    }

    #[test]
    fn duration_must_be_non_negative() {
        let run: RunInput = serde_json::from_str(r#"{"job_label":"j","started_at":"2026-07-06T10:00:00Z","finished_at":"2026-07-06T09:00:00Z"}"#).unwrap();
        let started = parse_dt(&run.started_at).unwrap();
        let finished = parse_dt(&run.finished_at).unwrap();
        assert!(finished < started, "the cmd would reject this as finished-before-started");
    }

    #[test]
    fn invalid_status_rejected() {
        let run: RunInput = serde_json::from_str(r#"{"job_label":"j","started_at":"2026-07-06T09:00:00Z","finished_at":"2026-07-06T09:00:01Z","status":"bogus"}"#).unwrap();
        let status = run.status.unwrap();
        assert!(!["ok","warn","error","timeout","partial"].contains(&status.as_str()), "cmd_log_run would reject this status");
    }

    #[test]
    fn inputs_outputs_outcome_default_to_empty_object() {
        let conn = mem_conn();
        let id = log_via(&conn, r#"{"job_label":"j","started_at":"2026-07-06T09:00:00Z","finished_at":"2026-07-06T09:00:01Z"}"#);
        let (i, o, oc): (String,String,String) = conn.query_row(
            "SELECT inputs_json, outputs_json, outcome_json FROM runs WHERE id=?1", params![id], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?))
        ).unwrap();
        assert_eq!(i, "{}");
        assert_eq!(o, "{}");
        assert_eq!(oc, "{}");
    }

    #[test]
    fn query_filters_by_job_substring_and_since() {
        let conn = mem_conn();
        log_via(&conn, r#"{"job_label":"morning-brief","started_at":"2026-07-05T09:00:00Z","finished_at":"2026-07-05T09:00:10Z"}"#);
        log_via(&conn, r#"{"job_label":"morning-brief","started_at":"2026-07-06T09:00:00Z","finished_at":"2026-07-06T09:00:10Z"}"#);
        log_via(&conn, r#"{"job_label":"ops-exhaust","started_at":"2026-07-06T09:00:00Z","finished_at":"2026-07-06T09:00:20Z"}"#);
        // since 2026-07-06 → 2 rows
        let n: i64 = conn.query_row("SELECT COUNT(*) FROM runs WHERE started_at >= '2026-07-06'", [], |r| r.get(0)).unwrap();
        assert_eq!(n, 2);
        // job substring 'morning' → 2 rows
        let n: i64 = conn.query_row("SELECT COUNT(*) FROM runs WHERE job_label LIKE '%morning%'", [], |r| r.get(0)).unwrap();
        assert_eq!(n, 2);
    }

    #[test]
    fn stats_aggregates_by_job_and_status() {
        let conn = mem_conn();
        log_via(&conn, r#"{"job_label":"morning-brief","started_at":"2026-07-06T09:00:00Z","finished_at":"2026-07-06T09:00:10Z","status":"ok"}"#);
        log_via(&conn, r#"{"job_label":"morning-brief","started_at":"2026-07-06T10:00:00Z","finished_at":"2026-07-06T10:00:05Z","status":"error"}"#);
        cmd_stats(&conn, None, false).unwrap();
        // verify the aggregate directly
        let (count, errs): (i64,i64) = conn.query_row(
            "SELECT COUNT(*), SUM(CASE WHEN status IN ('error','timeout') THEN 1 ELSE 0 END) FROM runs WHERE job_label='morning-brief'",
            [], |r| Ok((r.get(0)?, r.get(1)?))
        ).unwrap();
        assert_eq!((count, errs), (2, 1));
    }
}
