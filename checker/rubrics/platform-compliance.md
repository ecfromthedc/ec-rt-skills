# Rubric — platform-compliance

Format-rotation and anti-fingerprint compliance for content batches. Enforces LAWS.md **law 0** (the variation mandate): never ship a batch of near-identical clips — one master prompt run N times reads as spam and gets suppressed by unoriginal-content detection. This rubric is the fleet-wide application of that law.

**Applies to:** `batch`, `post-batch`, `clip-set`, `production-manifest`. NOT single captions/creator-lists/budgets (a single artifact can't violate rotation — that's a batch-level property).

---

## Rule syntax for fingerprint detection
A batch is parseable into per-clip/per-post records, each with at least: an `anchor` (the visual scene/setting), a `prompt` or `template_id`, and a `format`. The checker groups records by format, then within each format checks anchor diversity and template/prompt repetition.

---

## Rules

### MUST — anchor diversity within each format (law 0)
`rule_id: anchor-rotation`
Within any single format, the batch must draw from an **anchor bank** — multiple distinct anchors (different angle, setting, time-of-day, composition; same subject for brand). FAIL if any single anchor accounts for more than ~20% of a format's clips (i.e. >5 clips out of 25 off one anchor), OR if the entire format's batch uses fewer than 3 distinct anchors. Quote the anchor distribution (count per anchor). LAWS.md law 0: *"one anchor = one look... clips distributed across it (~4-5 clips/anchor)."*

### MUST — no single master-prompt fingerprint across the batch
`rule_id: no-master-prompt-fingerprint`
No single prompt or template may produce more than ~20% of the clips in a format. FAIL if one `prompt` / `template_id` dominates, quoting the repeated prompt and its clip count. This is the core of law 0: *"A master prompt is the RECIPE; the deliverable is a rotated set, never one prompt run N times."* Near-duplicate prompts (same structure, only a token swapped) count as the same prompt for this rule.

### MUST — format rotation across the batch (informational → FAIL at extremes)
`rule_id: format-rotation`
Informational if the batch spans ≥2 formats. FAIL only if: the entire batch is one format AND one anchor AND one prompt (a pure-duplicate batch — guaranteed suppression). A healthy batch rotates formats (truck-scenic / truck-ugc / silhouette / reel / carousel); a single-format batch must at least rotate anchors and prompts (covered by the two rules above).

### MUST NOT — identical captions across clips
`rule_id: no-duplicate-captions`
No two clips in a batch may ship with byte-identical captions. FAIL with both quoted. Near-identical captions (same text, one word or emoji swapped) count as duplicates — FAIL with a note. The caption-variation mandate is the textual twin of law 0's visual mandate.

### MUST — each clip traceable to its anchor and prompt (informational)
`rule_id: clip-provenance`
Informational only. Flag (don't FAIL) if any clip record lacks an `anchor` or `prompt`/`template_id` field — without provenance the rotation rules can't be evaluated, which usually means the maker didn't tag the batch. Provenance is how the checker (and a future reviewer) reconstructs what shipped.

---

## Source files this rubric derives from
- `~/Documents/Development/prompting agent/LAWS.md` — law 0 (variation mandate), law 20 (parked-vehicle wheel-lock — not enforced here, that's a per-clip physics rule for a different rubric)
- The "law 0" framing comes from the prompt bake-off council findings; this rubric is its fleet-wide enforcement.
