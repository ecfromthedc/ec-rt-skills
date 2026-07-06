# Seed artifact — dirty-budget-no-sum (expected: FAIL)
# Rubric: campaign-budget
# PLANTED VIOLATION: budget that doesn't sum (line items don't add to declared total)

## [TRACK A] — [LABEL] campaign budget

| line item | amount |
|---|---|
| Creator fees (8 creators × mid-tier) | $6,000 |
| Content production (12 assets × edited) | $1,800 |
| Strategy & ops (10 hrs) | $1,500 |
| Boosted spend (pass-through, client-direct) | $4,000 |
| **Total** | **$14,500** |

---

**Notes for checker validation:** Planted FAIL — `budget-sums`. The line items sum to $6,000 + $1,800 + $1,500 + $4,000 = **$13,300**, but the declared Total is **$14,500** — off by $1,200, well outside the ±$1 tolerance. The checker must recompute and report the discrepancy. (The pass-through boosted spend is correctly excluded from the fee+cost check but is still itemized, so `all-costs-itemized` should PASS.) All line items are above rate-card floor, so `pricing-above-rate-card` should PASS. Expected: FAIL, 1 violation (`budget-sums`).
