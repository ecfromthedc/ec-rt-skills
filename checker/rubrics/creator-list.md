# Rubric — creator-list

Blacklist cross-check for any shortlist of creators being considered for a campaign. The maker proposes a list; the checker confirms none of them are on the Avoid List before the list reaches a client or a brief goes out.

**Applies to:** `creator-list`, `outreach-batch`, `campaign-brief` (when it names creators). NOT captions/budgets.

---

## Rules

### MUST — no blacklisted creator (cross-check)
`rule_id: no-blacklisted-creator`
`CROSS-CHECK: ~/Documents/Obsidian Vault/Rising Tides OS/Memory/Creator Database/Creator Avoid List.md`
Every creator in the artifact must be matched (case-insensitive) against the Creator Avoid List — by **handle** (`@handle`), **display name**, and **real name** if the list carries one. A match on any of those three = FAIL. Report the matched Avoid-List entry verbatim (which section — Ghosted / Underperformers / Difficult — and the notes). One blacklisted creator fails the whole list; do not grade on a curve.

### MUST — each creator has a handle or verifiable identifier
`rule_id: identifiable-creator`
Every entry must have either a platform handle (`@...`), a profile URL, or a real name. "That one guy from the truck videos" or "the dancer who went viral last month" = FAIL — unidentifiable, can't be cross-checked, can't be briefed. A creator you can't look up is a creator you can't vet.

### MUST NOT — duplicates within the list
`rule_id: no-duplicate-creators`
The same creator (same handle or same name) may not appear twice in one shortlist. FAIL with both entries quoted. Duplicates mean the maker didn't dedupe; downstream that becomes a double-outreach.

### MUST — list size within campaign scope (informational, FAILs only when extreme)
`rule_id: list-size-sane`
Informational in the 5–50 range. FAIL only if: 0 creators (empty list sent for review) or >200 (un-vetted spam list, not a shortlist). A real shortlist has been curated.

### SHOULD — niche/audience fit noted (informational)
`rule_id: niche-fit-noted`
Informational only. Flag (don't FAIL) if the list is all one niche with no audience-fit justification, or mixes niches with no campaign-relevance logic. Vetting quality is the maker's call to defend; the checker only ensures the floor (no blacklist, identifiable, deduped).

---

## Source files this rubric derives from
- `~/Documents/Obsidian Vault/Rising Tides OS/Memory/Creator Database/Creator Avoid List.md` — the canonical cross-check source (sections: Ghosted / Underperformers / Difficult to Work With)
- Note: as of 2026-07-06 the Avoid List is a blank template (`[Creator Name]` placeholders, 0 real entries). The checker still runs the cross-check; a blacklisted-creator FAIL only fires when a real entry exists and matches. Seed the list before relying on this rule in production.
