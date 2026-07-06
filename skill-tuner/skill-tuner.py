#!/usr/bin/env python3
"""skill-tuner.py — nightly skill-tuner loop (WP7).

Scans Claude Code session transcripts (~/.claude/projects/*/*.jsonl) for two
signal classes, extracts evidence with context, scrubs secrets, and proposes
CLAUDE.md/skill diffs as patch files into the Review Queue. NEVER auto-applies
— proposals only. A human (or an LLM pass in review) decides what to merge.

Signal classes (the "mistakes become written rules automatically" loop):
  1. User corrections — explicit "no", "wrong", "actually", "I meant",
     "stop doing", "don't", "that's not". The highest-signal class (from dream
     skill Phase 2).
  2. Failed-then-fixed sequences — a tool_use that errored, followed shortly by
     a corrected tool_use that succeeded. Net-new detector not in dream's greps.

Secret hygiene: every extracted snippet is run through the same secret-pattern
scrub as scrub-transcripts.sh (patterns ported below). No secret ever lands in
a proposed diff.

Usage:
    python3 skill-tuner.py                       # scan yesterday's transcripts
    python3 skill-tuner.py --days 3              # scan last 3 days
    python3 skill-tuner.py --since 2026-07-05    # scan since a date
    python3 skill-tuner.py --dry-run             # print proposals, don't write

Doctrine: deterministic Python, no LLM call, no network. The "propose the diff
wording" step is deliberately a template + evidence, not an LLM generation —
that keeps it free, fast, and impossible to auto-apply. A reviewer (human or
LLM-in-review) writes the final wording from the evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
PROJECTS_DIR = HOME / ".claude" / "projects"
GLOBAL_CLAUDE_MD = HOME / ".claude" / "CLAUDE.md"
OUT_DIR = HOME / "Documents" / "Obsidian Vault" / "Rising Tides OS" / "Review Queue" / "skill-diffs"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# Signal patterns
# ---------------------------------------------------------------------------
# User-correction triggers (ported from dream skill Phase 2 — highest signal).
# Matched case-insensitive against user-message text.
CORRECTION_RE = re.compile(
    r"\b(no,|wrong|incorrect|not right|stop doing|don't do|don't use|i said|i meant|"
    r"that's not|correction|actually,? no|i told you|we don't|never do|"
    r"stop using|remove that|i didn't ask for)\b",
    re.IGNORECASE,
)
# Preference/decision triggers (slightly lower signal — captured separately).
PREFERENCE_RE = re.compile(
    r"\b(i prefer|always use|never use|i like|i don't like|from now on|"
    r"going forward|remember that|make sure to|default to|we always)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Secret-scrub patterns (ported from ~/.claude/scripts/scrub-transcripts.sh).
# Replacement strings are stable so re-runs are idempotent. NEVER log secrets.
# ---------------------------------------------------------------------------
SECRET_PATTERNS = [
    (re.compile(r"sk-ant-(api03|admin01)-[A-Za-z0-9_-]{20,}"), "[REDACTED:ANTHROPIC_KEY]"),
    (re.compile(r"sk-(proj-)?[A-Za-z0-9_-]{32,}"), "[REDACTED:OPENAI_KEY]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "[REDACTED:GITHUB_PAT]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:AWS_ACCESS_KEY]"),
    (re.compile(r'aws_secret_access_key["\'\\: =]+[A-Za-z0-9/+]{40}'), "[REDACTED:AWS_SECRET]"),
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "[REDACTED:GOOGLE_API_KEY]"),
    (re.compile(r"xox[abprs]-[0-9A-Za-z-]{10,}"), "[REDACTED:SLACK_TOKEN]"),
    (re.compile(r"sk_(live|test)_[A-Za-z0-9]{24,}"), "[REDACTED:STRIPE_KEY]"),
    (re.compile(r"EAA[A-Za-z0-9]{50,}"), "[REDACTED:META_ACCESS_TOKEN]"),
    (re.compile(r"Bearer [A-Za-z0-9._~+/=-]{30,}"), "Bearer [REDACTED:BEARER]"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "[REDACTED:PRIVATE_KEY_BLOCK]"),
]


def scrub(text: str) -> str:
    """Run all secret patterns. Idempotent — re-scrubbing a scrubbed string is a no-op."""
    for pat, repl in SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text


# ---------------------------------------------------------------------------
# Transcript scanning
# ---------------------------------------------------------------------------
def iter_transcripts(since: datetime) -> list[Path]:
    """All *.jsonl transcripts modified on or after `since`, across all projects."""
    out = []
    if not PROJECTS_DIR.exists():
        return out
    for proj in PROJECTS_DIR.iterdir():
        if not proj.is_dir():
            continue
        for f in proj.glob("*.jsonl"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime >= since:
                out.append(f)
    return out


def extract_user_text(obj: dict) -> str | None:
    """Pull the plain text of a user message line. Returns None if not a user text message."""
    if obj.get("type") != "user":
        return None
    msg = obj.get("message", {})
    if msg.get("role") != "user":
        return None
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # content blocks; collect text blocks
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(parts) if parts else None
    return None


def scan_transcript(path: Path) -> list[dict]:
    """Return a list of signal records from one transcript."""
    signals: list[dict] = []
    proj_name = path.parent.name
    try:
        with path.open() as f:
            lines = f.readlines()
    except OSError:
        return signals

    # First pass: collect user messages with their line index + timestamp.
    user_msgs: list[tuple[int, str, str | None]] = []  # (line_idx, text, timestamp)
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = extract_user_text(obj)
        if text:
            ts = obj.get("timestamp")
            user_msgs.append((i, text, ts))

    # Detect corrections + preferences on user messages.
    for idx, text, ts in user_msgs:
        # skip very long pastes (likely file contents, not real corrections)
        if len(text) > 800:
            continue
        if CORRECTION_RE.search(text):
            kind = "correction"
        elif PREFERENCE_RE.search(text):
            kind = "preference"
        else:
            continue
        # extract the sentence containing the trigger for tight evidence
        snippet = extract_sentence(text, CORRECTION_RE if kind == "correction" else PREFERENCE_RE)
        signals.append({
            "kind": kind,
            "project": proj_name,
            "transcript": path.name,
            "line": idx,
            "timestamp": ts,
            "user_text": scrub(snippet),
        })

    # Second signal class: failed-then-fixed tool sequences.
    # A tool_use line whose result is an error, followed (within ~6 lines) by a
    # tool_use of the same tool that's not flagged as error. We approximate by
    # scanning for tool_result lines containing error markers.
    tool_results = []  # (line_idx, toolu_id, is_error, tool_name_guess)
    tool_uses = {}     # toolu_id -> tool_name, keyed by the use line
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # tool_use blocks live inside assistant message content
        if obj.get("type") == "assistant":
            content = obj.get("message", {}).get("content", [])
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tool_uses[b.get("id")] = b.get("name", "?")
        # tool_result blocks live in user messages with content arrays
        if obj.get("type") == "user":
            content = obj.get("message", {}).get("content", [])
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        tu_id = b.get("tool_use_id")
                        is_err = bool(b.get("is_error")) or _looks_like_error(b.get("content", ""))
                        tool_results.append((i, tu_id, is_err, tool_uses.get(tu_id, "?"), str(b.get("content", ""))[:200]))

    # find error results followed within 6 lines by another use of the same tool that's ok
    for j, (idx, tu_id, is_err, name, _err_snip) in enumerate(tool_results):
        if not is_err:
            continue
        # look ahead in tool_results for a same-tool success within a small line window
        for k in range(j + 1, min(j + 4, len(tool_results))):
            idx2, _tu2, is_err2, name2, _ok_snip = tool_results[k]
            if name2 == name and not is_err2 and (idx2 - idx) <= 12:
                signals.append({
                    "kind": "failed-then-fixed",
                    "project": proj_name,
                    "transcript": path.name,
                    "line": idx,
                    "tool": name,
                    "evidence": scrub(f"tool '{name}' errored at line {idx}, succeeded again at line {idx2}"),
                })
                break  # one record per error

    return signals


def _looks_like_error(content) -> bool:
    s = str(content).lower()
    return any(m in s for m in ("error", "errno", "exception", "failed:", "not found", "no such file", "command not found"))


def extract_sentence(text: str, trigger: re.Pattern) -> str:
    """Return the sentence (or line) of `text` containing the first trigger match."""
    m = trigger.search(text)
    if not m:
        return text[:200]
    # find sentence boundaries around the match
    start = text.rfind(".", 0, m.start())
    start = 0 if start == -1 else start + 1
    end = text.find(".", m.end())
    end = len(text) if end == -1 else end + 1
    return text[start:end].strip()[:300]


# ---------------------------------------------------------------------------
# Proposal rendering
# ---------------------------------------------------------------------------
def render_proposal(signals: list[dict]) -> str:
    """Render a human-reviewable proposal doc with evidence + suggested diff shape."""
    corrections = [s for s in signals if s["kind"] == "correction"]
    preferences = [s for s in signals if s["kind"] == "preference"]
    ftfs = [s for s in signals if s["kind"] == "failed-then-fixed"]

    out = []
    out.append(f"# Skill-tuner proposals — {TODAY}\n")
    out.append("> PROPOSALS ONLY — nothing is auto-applied. Each item is evidence from real transcripts. "
               "A human (or an LLM pass in review) decides the final CLAUDE.md / skill wording from the evidence, "
               "then applies the diff manually. Secrets scrubbed.\n")
    out.append(f"**Scan:** {len(signals)} signals — {len(corrections)} corrections, {len(preferences)} preferences, {len(ftfs)} failed-then-fixed sequences.\n")

    if corrections:
        out.append("\n## Corrections (highest signal — user explicitly said 'no/wrong/actually')\n")
        seen = set()
        for s in corrections:
            key = s["user_text"][:60]
            if key in seen:
                continue
            seen.add(key)
            out.append(f"- **`{s['project'][:40]}`** ({s.get('timestamp','?')[:10] if s.get('timestamp') else 'no-ts'}): "
                        f"\"{s['user_text']}\"")
            out.append(f"  - *source: `{s['transcript']}` line {s['line']}*")
            out.append(f"  - *suggested action: if this is a recurring 'don't do X', add a one-line rule to the relevant CLAUDE.md / skill.*")

    if preferences:
        out.append("\n## Preferences / decisions (medium signal)\n")
        seen = set()
        for s in preferences:
            key = s["user_text"][:60]
            if key in seen:
                continue
            seen.add(key)
            out.append(f"- **`{s['project'][:40]}`** ({s.get('timestamp','?')[:10] if s.get('timestamp') else 'no-ts'}): "
                        f"\"{s['user_text']}\"")
            out.append(f"  - *source: `{s['transcript']}` line {s['line']}*")

    if ftfs:
        out.append("\n## Failed-then-fixed sequences (operational signal — a tool errored then succeeded)\n")
        out.append("These often indicate a missing instruction ('always check X before calling tool Y'). "
                   "Cluster by tool to find the pattern.\n")
        from collections import Counter
        by_tool = Counter(s["tool"] for s in ftfs)
        for tool, n in by_tool.most_common():
            out.append(f"- **`{tool}`** — {n} error→recovery sequences")
        out.append("\n*Examine a sample in the transcripts to decide if a preventive rule is worth adding.*")

    if not signals:
        out.append("\n*(no signals found this scan — either no recent transcripts or a quiet period.)*")

    out.append("\n---\n**Diff targets** (where proposed rules would land): "
               f"`{GLOBAL_CLAUDE_MD}` (global), project-level `CLAUDE.md`/`AGENTS.md`, "
               f"or specific `~/.claude/skills/*/SKILL.md` files. "
               f"Apply manually after review — this file is the proposal, not the patch.")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Nightly skill-tuner")
    parser.add_argument("--days", type=int, default=1, help="scan transcripts modified in last N days (default 1)")
    parser.add_argument("--since", help="scan transcripts modified since ISO date (overrides --days)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    else:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)

    print(f"[skill-tuner] scanning transcripts modified since {since.strftime('%Y-%m-%d %H:%M UTC')}", flush=True)
    transcripts = iter_transcripts(since)
    print(f"[skill-tuner] {len(transcripts)} transcripts in window", flush=True)
    if not transcripts:
        print("[skill-tuner] no transcripts to scan — nothing to propose")
        return 0

    all_signals: list[dict] = []
    for t in transcripts:
        all_signals.extend(scan_transcript(t))

    # de-dup near-identical signals within the same project
    print(f"[skill-tuner] {len(all_signals)} raw signals extracted", flush=True)

    proposal = render_proposal(all_signals)

    out_path = OUT_DIR / f"{TODAY}-skill-tuner-proposal.md"
    if args.dry_run:
        print(f"\n========== PROPOSAL (dry-run, would write to {out_path}) ==========\n")
        print(proposal)
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(proposal)
    print(f"[skill-tuner] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
