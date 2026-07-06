# Seed artifact — dirty-batch-format-fingerprint (expected: FAIL)
# Rubric: platform-compliance
# PLANTED VIOLATION: format-fingerprint repeat — one master prompt run 8 times, one anchor

## Batch manifest — [TRACK B] clip set (25 clips)

format: truck-scenic
anchor_bank: [truck-dusk-field]

| clip_id | anchor | prompt | caption |
|---|---|---|---|
| hf-001 | truck-dusk-field | "warm natural exposure, vintage truck in field at dusk, clear open sky, no lettering" | Driving with the windows down |
| hf-002 | truck-dusk-field | "warm natural exposure, vintage truck in field at dusk, clear open sky, no lettering" | Driving with the windows down |
| hf-003 | truck-dusk-field | "warm natural exposure, vintage truck in field at dusk, clear open sky, no lettering" | Driving with the windows down |
| hf-004 | truck-dusk-field | "warm natural exposure, vintage truck in field at dusk, clear open sky, no lettering" | Driving with the windows down |
| hf-005 | truck-dusk-field | "warm natural exposure, vintage truck in field at dusk, clear open sky, no lettering" | Driving with the windows down |
| hf-006 | truck-dusk-field | "warm natural exposure, vintage truck in field at dusk, clear open sky, no lettering" | Driving with the windows down |
| hf-007 | truck-dusk-field | "warm natural exposure, vintage truck in field at dusk, clear open sky, no lettering" | Driving with the windows down |
| hf-008 | truck-dusk-field | "warm natural exposure, vintage truck in field at dusk, clear open sky, no lettering" | Driving with the windows down |
| hf-009 | truck-dusk-field | "warm natural exposure, vintage truck in field at dusk, clear open sky, no lettering" | Driving with the windows down |
| hf-010 | truck-dusk-field | "warm natural exposure, vintage truck in field at dusk, clear open sky, no lettering" | Driving with the windows down |

(15 more identical rows omitted for brevity — all truck-dusk-field, same prompt, same caption)

---

**Notes for checker validation:** Three planted FAILs on platform-compliance (this is law 0's exact nightmare scenario):
1. `anchor-rotation` — 1 anchor (truck-dusk-field) for 100% of clips; rule fails at >20% per anchor and <3 distinct anchors. Both thresholds blown.
2. `no-master-prompt-fingerprint` — 1 prompt for 100% of clips; rule fails at >20%. Law 0: "never one prompt run N times."
3. `no-duplicate-captions` — every clip has the byte-identical caption "Driving with the windows down".

`format-rotation` is informational here (single format) but combined with single anchor + single prompt this is a pure-duplicate batch → also FAILs the extreme clause. Expected: FAIL, ≥3 violations.
