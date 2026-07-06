# Rubric — campaign-budget

Math integrity for campaign budgets. The maker produces a budget block (fees + platform costs = total, with per-line pricing); the checker confirms the arithmetic closes and pricing isn't below the rate-card floor. A budget that doesn't sum is a budget that can't be sent to a client.

**Applies to:** `budget`, `campaign-budget`, `proposal-pricing`, `invoice-block`. NOT captions/creator-lists.

---

## Rule syntax for SUM rules
A budget block must be parseable into line items. Accept formats:
- Markdown table with a numeric column (header contains `$`, `amount`, `cost`, or `fee`)
- Bullet list with `$N` or `N` (with `$`/`k`/`,`) per line and a `Total:` / `Subtotal:` line
- JSON/structured (preferred for pipeline-generated budgets): `{"line_items": [...], "total": N}`

The checker extracts all numeric line items (stripping `$`, `,`, `k` → ×1000) and the declared total, then re-sums.

---

## Rules

### MUST — fees + platform costs sum to declared total
`rule_id: budget-sums`
The sum of all line items MUST equal the declared `Total:` within ±$1 (rounding tolerance). FAIL if the sum is off by more than $1, quoting the line items, the re-computed sum, and the declared total. A budget that doesn't close is a non-negotiable FAIL — it will be questioned by the client or the AP department and erodes trust.

Edge cases the checker handles:
- Subtotals: if `Subtotal:` exists and `Subtotal + tax/platform_fee = Total`, that's valid — re-verify each tier.
- Percentages: a line like "Platform fee: 15% of subtotal" is parsed as `0.15 × subtotal` and added; if the percentage produces a non-integer, round to the cent and note it.
- Pass-throughs: lines explicitly marked `pass-through`, `reimbursable`, or `client-direct` are excluded from the fee+cost sum (they're not RT revenue) but must still appear in the block — a missing pass-through line FAILs `all-costs-itemized` instead.

### MUST — pricing at or above rate-card minimum
`rule_id: pricing-above-rate-card`
`CROSS-CHECK: ~/Documents/Obsidian Vault/Rising Tides OS/Reference/rubrics/rate-card.md`
Each line item's unit price must be ≥ the rate-card minimum for its category. A line below floor = FAIL (undercutting the rate card erodes the whole book; see RT-PRODUCTIZATION-MODEL: price against per-campaign spend, never against tool budgets). Report which line, its price, and the rate-card floor.

**Rate card (default — override via the CROSS-CHECK file):**
| category | floor |
|---|---|
| creator fee (micro, <100k followers) | $250 |
| creator fee (mid, 100k–1M) | $750 |
| creator fee (macro, >1M) | $2,500 |
| content production (per asset, edited) | $150 |
| strategy/ops (per hour) | $150 |
| boosted spend (pass-through) | n/a (client-direct) |
If `rate-card.md` exists at the CROSS-CHECK path, it overrides this table.

### MUST — every cost itemized (no lump sum without breakdown)
`rule_id: all-costs-itemized`
A `Total:` line with no line items, or a single catch-all like "Campaign: $15,000" with no breakdown, = FAIL. Every dollar in the total must trace to a named line item (creator fees, production, platform, strategy, pass-through). Clients (especially label AP departments) require an itemized invoice to pay — a lump sum stalls in AP.

### MUST NOT — negative or zero line items (without an explicit discount line)
`rule_id: no-zero-lines`
A line item of $0 or negative = FAIL unless it's explicitly labeled `discount`, `waiver`, `credit`, or `adjustment`. A bare `$0` line is usually a parsing error or a dropped field; surface it rather than let it through.

### SHOULD — pass-throughs flagged (informational)
`rule_id: passthroughs-flagged`
Informational only. Flag (don't FAIL) if paid spend, influencer fees, or shoot costs aren't marked as pass-throughs — per the productization model these should be separate line items, not buried in RT revenue.

---

## Source files this rubric derives from
- `RT-PRODUCTIZATION-MODEL.md` — "Paid spend + influencer fees always pass through as separate line items"; price against per-campaign spend, not tool budgets
- Rate card defaults above; override via `~/Documents/Obsidian Vault/Rising Tides OS/Reference/rubrics/rate-card.md`
