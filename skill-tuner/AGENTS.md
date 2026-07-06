# AGENTS.md — skill-tuner

The nightly loop that turns session-transcript signal into proposed skill/CLAUDE.md diffs — SkillOpt's trajectory-driven skill optimization, made real. Scans `~/.claude/projects/*/*.jsonl` for user corrections and failed-then-fixed tool sequences, extracts evidence, scrubs secrets, and writes a proposal to the Review Queue. **Never auto-applies** — proposals only.

## Stack
Python 3, stdlib only. No LLM call, no network, no deps. The "propose the diff wording" step is deliberately a template + evidence, not an LLM generation — that keeps it free, deterministic, and impossible to auto-apply. A reviewer writes the final wording from the evidence.

## Verified run commands
```bash
python3 skill-tuner.py --dry-run --days 1     # print proposal, write nothing
python3 skill-tuner.py --days 1                # write today's proposal to Review Queue/skill-diffs/
python3 skill-tuner.py --since 2026-07-01      # scan since a date
```
Output: `~/Documents/Obsidian Vault/Rising Tides OS/Review Queue/skill-diffs/YYYY-MM-DD-skill-tuner-proposal.md`

## Signal classes
1. **Corrections** (highest signal) — user messages matching `no,|wrong|incorrect|not right|stop doing|don't|i said|i meant|that's not|correction|actually,? no|never do|...`. Ported from the `dream` skill's Phase 2 greps.
2. **Preferences/decisions** (medium) — `i prefer|always use|never use|from now on|going forward|remember that|...`.
3. **Failed-then-fixed** (net-new, not in dream) — a tool_use that errored followed within ~12 lines by a successful retry of the same tool. Often indicates a missing preventive instruction ("check X before calling Y").

## Secret hygiene
Every extracted snippet runs through the same 11 secret-pattern regexes as `~/.claude/scripts/scrub-transcripts.sh` (Anthropic/OpenAI/GitHub/AWS/Google/Slack/Stripe/Meta keys, Bearer tokens, private-key blocks). Replacement strings are stable → re-runs idempotent. Verified: the written proposal contains **0** secret-pattern matches.

## Key files
- `skill-tuner.py` — everything (~280 lines)
- `~/Library/LaunchAgents/com.risingtides.skill-tuner.plist` — nightly 03:00 schedule (staged, NOT loaded)
- `~/.claude/scripts/scrub-transcripts.sh` — the canonical scrub source (patterns ported here, kept in sync if that file changes)

## Gotchas
- **Transcript path glob is `~/.claude/projects/*/*.jsonl`** (not `*/sessions/*.jsonl` — the dream SKILL.md's Phase 2 references a sessions/ subdir that doesn't exist on this machine).
- **Window is by mtime, not message timestamp.** `--days 1` = transcripts modified in the last 24h. A long-running session touched today counts even if its messages are old — that's correct (the file was active).
- **Long pastes are skipped** (>800 chars) to avoid flagging file contents as "corrections."
- **Failed-then-fixed is heuristic.** It matches same-tool error→success within 12 lines. False positives (a tool that legitimately fails then a different successful call) are possible — that's why a human reviews, and why the proposal clusters by tool name rather than asserting each one is a rule.
- **Pin the model if you add an LLM pass.** The boss-agent dream cron silently failed for days because it pinned model id `claude-fable-5` which doesn't exist for this account (documented in `~/.claude/projects/the boss-agent project memory (project_dream_cron_model_failure.md)`). Any LLM-driven v2 must pin a valid model id and assert non-empty output.
- **Plist staged but NOT loaded** — load with `launchctl load ~/Library/LaunchAgents/com.risingtides.skill-tuner.plist` after sign-off. Same posture as ops-exhaust: don't start a recurring job without approval.
