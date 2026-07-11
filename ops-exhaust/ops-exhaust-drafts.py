#!/usr/bin/env python3
"""ops-exhaust-drafts.py — nightly ops-exhaust content machine (WP3).

Reads campaign/artist operational data (READ-ONLY) and drafts three artifact
types into the Review Queue:
  1. case-study post      — from milestones / tour / deltas
  2. course bullet        — a teachable takeaway from the numbers
  3. sales-deck stat line — a one-liner for the proposal deck

EVERY draft cites its source data at the footer (verifiable). NOTHING is posted,
sent, or spent — drafts land in the Review Queue for human review.

Data sources (read-only):
  - a SQLite dashboard DB — primary: snapshots, tracks, tour_shows, stat_series, meta_ads
  - Postiz performance-snapshots.jsonl — secondary (currently sparse): post engagement

The dashboard DB is the richest source. Postiz is tailed for whatever's there.

Usage:
    python3 ops-exhaust-drafts.py                 # write today's drafts to the Review Queue
    python3 ops-exhaust-drafts.py --dry-run       # print drafts to stdout, don't write
    python3 ops-exhaust-drafts.py --artist monrovia

Doctrine: extends rt-agents (Python OK per plan). Flat-script convention, inline
config, writes to Obsidian Review Queue, logs a run to the workload ledger (WP5).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config (rt-agents convention: inline constants, HOME-rooted paths)
# ---------------------------------------------------------------------------
HOME = Path.home()
RT_AGENTS = HOME / "Projects" / "active" / "rt-agents"
# Artist display name used in draft headers — make this configurable per deployment.
# In the original build this was a specific artist; here it's a placeholder.
ARTIST_NAME = os.environ.get("OPS_EXHAUST_ARTIST", "[ARTIST]")
# Primary SQLite dashboard DB. Adapt the path to wherever your artist-dashboard ingest
# writes. Schema expected: snapshots, tracks, tour_shows, stat_series, meta_ads_campaigns.
DASHBOARD_DB = Path(os.environ.get(
    "OPS_EXHAUST_DASHBOARD_DB",
    str(HOME / "Projects" / "active" / "rt-monrovia-dashboard" / "data" / "monrovia.db"),
))
POSTIZ_PERF = Path(os.environ.get(
    "OPS_EXHAUST_POSTIZ_PERF",
    str(HOME / "Documents" / "Development" / "Postiz Posting Agent" / "data" / "logs" / "performance-snapshots.jsonl"),
))
REVIEW_QUEUE_ROOT = Path(os.environ.get(
    "OPS_EXHAUST_REVIEW_QUEUE",
    str(HOME / "Documents" / "Obsidian Vault" / "Rising Tides OS" / "Review Queue"),
))
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def log(msg: str) -> None:
    print(f"[ops-exhaust] {msg}", flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Source readers (ALL read-only)
# ---------------------------------------------------------------------------
def read_dashboard(db_path: Path) -> dict:
    """Read headline numbers, top tracks, recent tour, recent deltas, ad ROAS."""
    if not db_path.exists():
        log(f"WARN: dashboard DB not found at {db_path}")
        return {}
    # immutable=1 (not mode=ro): the DB runs in WAL mode and has -wal/-shm sidecar files.
    # mode=ro still tries to mmap the -shm, which fails under launchd's security context.
    # immutable=1 promises sqlite the file won't change during the connection → no sidecar access.
    conn = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)  # true read-only, launchd-safe
    conn.row_factory = sqlite3.Row
    out: dict = {"_source": str(db_path)}
    try:
        # latest snapshot
        row = conn.execute("SELECT * FROM snapshots ORDER BY date DESC LIMIT 1").fetchone()
        if row:
            out["snapshot"] = {k: row[k] for k in row.keys()}
        # top 5 tracks by streams
        tracks = conn.execute("SELECT name, streams, popularity FROM tracks ORDER BY streams DESC LIMIT 5").fetchall()
        out["top_tracks"] = [dict(t) for t in tracks]
        # recent tour shows (next/recent 5 by date)
        tour = conn.execute("SELECT date, venue, city, capacity, sold, pct_sold, status FROM tour_shows ORDER BY date DESC LIMIT 5").fetchall()
        out["tour"] = [dict(t) for t in tour]
        # stat_series deltas — most recent 10 non-null diffs
        deltas = conn.execute(
            "SELECT source, metric, timestp, value, diff FROM stat_series WHERE diff IS NOT NULL AND diff != 0 ORDER BY timestp DESC LIMIT 10"
        ).fetchall()
        out["deltas"] = [dict(d) for d in deltas]
        # meta ads — recent active campaigns with ROAS-ish signals
        ads = conn.execute(
            "SELECT name, status, spend, impressions, clicks FROM meta_ads_campaigns WHERE status = 'ACTIVE' ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
        out["ads"] = [dict(a) for a in ads]
    finally:
        conn.close()
    return out


def read_postiz_perf(path: Path) -> dict:
    """Tail Postiz performance snapshots (best-effort; currently sparse)."""
    if not path.exists():
        log(f"INFO: Postiz perf log not found at {path} (sparse data; skipping)")
        return {}
    rows = []
    try:
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        log(f"WARN: could not read Postiz perf log: {e}")
        return {}
    # only keep rows with real engagement numbers
    real = [r for r in rows if any(r.get(k) is not None for k in ("views", "likes", "comments", "shares"))]
    out = {"_source": str(path), "total_snapshots": len(rows), "with_engagement": len(real), "recent": real[-5:]}
    if real:
        log(f"Postiz: {len(real)} snapshots with engagement out of {len(rows)} total")
    else:
        log(f"Postiz: {len(rows)} snapshots, none with engagement values yet (data sparse)")
    return out


# ---------------------------------------------------------------------------
# Drafters — each returns markdown with a verifiable source footer
# ---------------------------------------------------------------------------
def draft_case_study(mon: dict) -> str:
    snap = mon.get("snapshot", {})
    top = mon.get("top_tracks", [])
    tour = mon.get("tour", [])
    deltas = mon.get("deltas", [])

    sp_followers = snap.get("sp_followers")
    sp_listeners = snap.get("sp_monthly_listeners")
    snap_date = snap.get("date")

    # headline: artist scale + top track
    headline_track = top[0] if top else {}
    body = []
    body.append(f"# Case-study post draft — {ARTIST_NAME} ({TODAY})\n")
    body.append("> DRAFT from ops-exhaust machine — review before posting. Numbers are sourced; verify before publish.\n")
    parts = []
    if sp_listeners:
        parts.append(f"{sp_listeners/1_000_000:.2f}M monthly Spotify listeners")
    if sp_followers:
        parts.append(f"{sp_followers:,} Spotify followers")
    if headline_track:
        parts.append(f'"{headline_track["name"].rstrip(".")}" at {headline_track["streams"]:,} streams')
    body.append("**The scale:** " + (" · ".join(parts) if parts else "(no headline numbers available)") + ".\n")

    # recent signal: a notable delta
    if deltas:
        d = deltas[0]
        body.append(f"**Recent signal:** {d['source']} {d['metric']} moved {d['diff']:+,.0f} to {d['value']:,.0f} (as of {d['timestp'][:10]}).\n")

    # tour proof point: strongest recent show
    if tour:
        # pick highest pct_sold
        strongest = max(tour, key=lambda t: (t.get("pct_sold") or 0))
        if strongest.get("pct_sold"):
            body.append(
                f"**Live proof:** {strongest['venue']} ({strongest['city']}) — {strongest['pct_sold']:.0f}% sold "
                f"({strongest['sold']:,}/{strongest['capacity']:,}) on {strongest['date']}, status: {strongest['status']}.\n"
            )

    body.append("**Angle (suggested):** the artist built streaming scale + a selling live bill without a major label push. Lead with the live proof, back it with the streams.\n")
    body.append("\n---\n**Sources:** dashboard.db → snapshots(date=" + str(snap_date) + ") · tracks · tour_shows · stat_series. Re-verify each number against the live dashboard before publish.")
    return "\n".join(body)


def draft_course_bullet(mon: dict) -> str:
    """A teachable takeaway from the numbers — for the RT Viral course / community."""
    ads = mon.get("ads", [])
    deltas = mon.get("deltas", [])
    top = mon.get("top_tracks", [])

    body = [f"# Course bullet draft — {ARTIST_NAME} ({TODAY})\n"]
    body.append("> DRAFT for course material / community post. One teachable takeaway from this week's numbers.\n")

    # Lesson angle: if we have ad data, teach ROAS/engagement; else teach catalog long-tail
    if ads:
        a = ads[0]
        ctr = (a["clicks"] / a["impressions"] * 100) if a.get("impressions") else None
        cpc = (a["spend"] / a["clicks"]) if a.get("clicks") else None
        lesson = (
            f"**Lesson — paid amplification math:** the '{a['name']}' retargeting campaign spent ${a['spend']:.0f} "
            f"for {a['impressions']:,} impressions"
        )
        if ctr is not None:
            lesson += f" at {ctr:.2f}% CTR"
        if cpc is not None:
            lesson += f" (${cpc:.3f}/click)"
        lesson += ". The takeaway: retargeting warm audiences on proven creative is the cheapest paid lever once organic has validated a clip.\n"
        body.append(lesson)
    elif top:
        t1, t2 = top[0], top[-1]
        ratio = t1["streams"] / t2["streams"] if t2.get("streams") else None
        lesson = (
            f"**Lesson — catalog long-tail:** the top track ({t1['streams']:,} streams) "
            f"outperforms the #5 track ({t2['streams']:,} streams)"
        )
        if ratio:
            lesson += f" by {ratio:.1f}x"
        lesson += ". The takeaway: one anchor track does the heavy lifting, but the long tail still compounds — don't retire the back catalog once a track cools.\n"
        body.append(lesson)
    else:
        body.append("**Lesson:** (insufficient data this run — no ad or track numbers to draw a takeaway.)\n")

    body.append("\n---\n**Sources:** dashboard.db → meta_ads_campaigns · tracks. Verify CTR/CPC math before teaching.")
    return "\n".join(body)


def draft_sales_deck_line(mon: dict) -> str:
    """A one-line stat for the proposal/sales deck."""
    snap = mon.get("snapshot", {})
    tour = mon.get("tour", [])
    body = [f"# Sales-deck stat line draft — ({TODAY})\n"]
    body.append("> DRAFT one-liner for the proposal deck. Pick the strongest single number.\n")

    # candidate stat lines, strongest first
    candidates = []
    if snap.get("sp_monthly_listeners"):
        candidates.append(f"{snap['sp_monthly_listeners']/1_000_000:.2f}M monthly listeners built organically")
    if snap.get("sp_followers"):
        candidates.append(f"{snap['sp_followers']:,} Spotify followers")
    if snap.get("tiktok_likes"):
        candidates.append(f"{snap['tiktok_likes']/1_000_000:.1f}M TikTok likes")
    # tour sellout
    sellouts = [t for t in tour if (t.get("pct_sold") or 0) >= 100]
    if sellouts:
        s = sellouts[0]
        candidates.append(f"sold out {s['venue']} ({s['city']}, {s['capacity']:,} cap)")

    if candidates:
        body.append("**Recommended one-liner:** \"" + candidates[0] + ".\"\n")
        body.append("**Alternatives:**")
        for c in candidates[1:4]:
            body.append(f"- \"{c}.\"")
    else:
        body.append("**Recommended one-liner:** (no headline numbers available this run.)")

    body.append("\n---\n**Sources:** dashboard.db → snapshots · tour_shows. Confirm the chosen stat is current before adding to the deck.")
    return "\n".join(body)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def write_draft(name: str, content: str, dry_run: bool) -> Path | None:
    out_dir = REVIEW_QUEUE_ROOT / TODAY[:7]  # Review Queue/2026-07/
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{TODAY}-{name}.md"
    if dry_run:
        print(f"\n========== DRAFT: {name} (dry-run, would write to {path}) ==========\n")
        print(content)
        return None
    path.write_text(content)
    log(f"wrote {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Ops-exhaust content machine")
    parser.add_argument("--artist", default="monrovia", help="artist key (only monrovia supported in v1)")
    parser.add_argument("--dry-run", action="store_true", help="print drafts, don't write files")
    args = parser.parse_args()

    if args.artist != "monrovia":
        log(f"ERROR: only artist='monrovia' is wired in v1 (got '{args.artist}')")
        return 2

    started = now_iso()
    started_dt = datetime.now(timezone.utc)

    # 1. Read sources (read-only)
    log(f"reading dashboard DB ({DASHBOARD_DB})")
    mon = read_dashboard(DASHBOARD_DB)
    log("reading Postiz performance snapshots")
    postiz = read_postiz_perf(POSTIZ_PERF)

    if not mon:
        log("ERROR: no monrovia data — aborting (nothing to draft from)")
        return 1

    # 2. Draft the three artifact types
    drafts: dict[str, str] = {
        "case-study": draft_case_study(mon),
        "course-bullet": draft_course_bullet(mon),
        "sales-deck-line": draft_sales_deck_line(mon),
    }

    # 3. Write (or print)
    written: list[str] = []
    for name, content in drafts.items():
        p = write_draft(name, content, args.dry_run)
        if p:
            written.append(str(p))

    finished = now_iso()
    duration_ms = int((datetime.now(timezone.utc) - started_dt).total_seconds() * 1000)

    # 4. Log the run to the workload ledger (WP5)
    try:
        sys.path.insert(0, str(RT_AGENTS))
        from workload_ledger import log_run
        log_run(
            "ops-exhaust",
            started_at=started, finished_at=finished,
            inputs={
                "sources": ["dashboard.db", "performance-snapshots.jsonl"],
                "read_only": True,
                "snapshot_date": mon.get("snapshot", {}).get("date"),
                "postiz_with_engagement": postiz.get("with_engagement", 0),
            },
            outputs={
                "drafts_written": len(written),
                "draft_paths": written,
                "dry_run": args.dry_run,
            },
            outcome={"status_reason": "ok" if written else "no-drafts", "duration_ms": duration_ms},
            status="ok" if written else "warn",
        )
    except Exception as e:  # noqa: BLE001
        log(f"WARN: could not log to workload ledger: {e}")

    log(f"done: {len(written)} drafts written")
    return 0 if written or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
