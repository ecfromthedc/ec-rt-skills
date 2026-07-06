# Seed artifact — dirty-caption-off-voice (expected: FAIL)
# Rubric: brand-voice
# PLANTED VIOLATION: off-voice caption (promotional framing + emoji clutter + buried hook)

Hey guys!! So today we're dropping something HUGE 🔥🔥🔥

Our new track is an absolute BANGER and you're gonna love it!! ✨ Go stream [TRACK A] right NOW, link in bio, smash that follow button 🙌🔥 and don't forget to pre-save while you're at it!!

This is gonna be our biggest hit yet 💪🚀

---

**Notes for checker validation:** Multiple planted FAILs on brand-voice:
1. `no-promo-language` — "BANGER", "GO STREAM", "smash that follow button", "our biggest hit yet", "out now"-style framing. [ARTIST] voice is oblique; this is peak promotional.
2. `no-emoji-clutter` — 9 emojis across 3 lines, including strings (🔥🔥🔥, 🔥✨). Floor is ≤1.
3. `hook-in-first-line` — first line is "Hey guys!! So today..." (greeting + throat-clearing); the hook (if any) is buried.
4. `single-pov` — mixes operator "we're dropping" + second-person "you're gonna love" + first-person-plural "our biggest hit". Three registers.

CTA rule `mon-cta-required` should still PASS (pre-save [TRACK A] + song name present). Expected: FAIL, ≥3 violations.
