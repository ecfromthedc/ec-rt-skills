---
name: port-audit
description: Audit a Python, Node, or other original against its Rust or cross-language port for CLI, schema, output, side-effect, and failure parity; determine cutover readiness and identify required repo-native fixture evidence. Use when comparing a rewrite to its source, checking port drift, deciding which implementation can become the source of truth, or preparing to retire the original.
---

# Port Audit

Produce one evidence-backed verdict: `READY`, `BLOCKED`, or `NOT_COMPARABLE`.
Default to read-only. Do not fix drift or retire either implementation unless the user asks.

## Establish the contract

1. Read repository instructions and resolve the exact source and port revisions.
2. Trace current entrypoints and callers. Ignore dead modules and roadmap prose.
3. Define equivalent reachable call-chain boundaries before scoring. If responsibilities live at different layers, compare the callers that complete the same behavior; if no boundary can be paired, mark the surface `MISSING` (unresolved boundary) and return `BLOCKED`.
4. Treat the running original as the executable specification unless a committed contract explicitly supersedes it.
5. Inventory observable behavior only:
   - commands, flags, defaults, and exit codes;
   - accepted inputs and validation;
   - stdout, files, JSON, HTTP bodies, and ordering;
   - state mutations and external side effects;
   - error and retry behavior.

Record each surface as `PARITY`, `DRIFT`, `MISSING`, or `N/A` with source and port locations.

## Prove parity

1. Reuse an existing fixture or golden test before creating one.
2. Start with one small fixture that exercises the highest-value common path. Add another only when a distinct critical contract cannot fit the first.
3. Run both implementations on the same local input without credentials or live-service writes.
4. Compare raw bytes when consumers observe bytes. Parse before comparison only when the contract is semantic, such as JSON with irrelevant key ordering.
5. Do not normalize away timestamps, ordering, whitespace, missing fields, or errors unless the committed contract says they are irrelevant.
6. If implementation is authorized, prefer a repo-native regression test in the port repository. Otherwise provide the exact commands and expected comparison without editing.

## Decide cutover readiness

Return `READY` only when every critical reachable surface has parity evidence and the original is no longer required for an uncovered runtime path.

Return `BLOCKED` when any critical surface is missing, drifting, untested, or still operationally owned by the original. Name the smallest next proof or fix.

Return `NOT_COMPARABLE` when the supposed port serves a different contract or the original is already retired by design. Do not force a migration from a stale premise.

## Guardrails

- Keep creative policy, credentials, deployment, and network execution out of fixtures.
- Do not equate matching types, dependencies, line counts, or function names with behavior parity.
- Do not invent a universal runner or shared abstraction. Leave proof where the port's normal test command will keep running it.
- Preserve error paths and side-effect order; successful output alone is insufficient.
- Stop after the first cutover-blocking drift if the user requested only the next actionable issue.

## Report

Use this compact shape:

```markdown
Verdict: READY | BLOCKED | NOT_COMPARABLE
Source: <revision + entrypoint>
Port: <revision + entrypoint>

| Surface | Status | Evidence |
|---|---|---|
| ... | PARITY/DRIFT/MISSING/N/A | paths, fixture, command, or exact mismatch |

Runnable proof: <repo-native command>
Next action: <one smallest action, or "retire original">
```
