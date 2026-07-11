# Retro — audience renders

Three Stage-2 projections of **the same Stage-1 numbers**. An audience re-orders and
filters what it leads with; it **never computes a number Stage 1 did not derive**, and
never introduces a ratio, a cost, or a dollar figure. If a value is not a field of
`audit-export.py`'s JSON (or a named artifact this skill already reads), it does not
belong in any template below.

Three rules carry over from the Execution Contract and are not relaxed here:

- **Derive, don't fabricate.** A missing source is "no data", never a silent zero.
- **Signals, not verdicts.** Report rates and hotspots; never call a sprint good, a
  team fast, or a plan done. The human interprets.
- **Estimates stay labeled.** `est.tokens` is an estimate (chars ÷ 4); carry the word
  "estimate" through into any audience that shows it. **No ROI, no cost-saved, no
  velocity claim** — none of those is a field on disk.

## Windowed vs as-of-now — say which, every time

When the run was windowed (`--since` / `--until`), the export's `windowing` manifest
names exactly which blocks the window touched. Read it and obey it:

- `windowing.windowed_blocks` — the **stream** counts (gates, escalations, parks,
  retries, circuit-breaks, attestations). These describe *the window*.
- `windowing.as_of_now_blocks` — testability, evidence freshness, per-feature review
  state, complexity drift, patch lane. These describe **now**, not the window.

Never narrate an as-of-now number as though it happened during the window. Print the
window's own caveat when one applies: bounds are inclusive and **day-granular**, so a
sprint boundary falling mid-day is unrepresentable and two adjacent windows that share
an endpoint both count that day. `complexity_drift.retries` is **lifetime** even in a
windowed run — the export says so; repeat it rather than quietly showing the number.

---

## `standup` — "where is it stuck right now"

Five lines or fewer. Pairs naturally with a short window (`--since` yesterday).

**Leads with:** parks · retries · circuit-breaks (the autonomy signals) · escalation
hotspots by feature × escalation_type · any `gate: fail` in the window.

**Omits:** testability split, complexity drift, HITL confirm/override detail,
model-tier attestation, patch-lane signals, per-feature review breakdown.

```
Retro — <slug> · standup (<window or "all time">)
Stuck:      <feature> parked (<detail>) | none
Churn:      <N> retries (<feature>: <n>), <N> circuit-breaks | none
Escalated:  <feature> → </ce-spec|/ce-implement|/ce-plan> (<count>)
Gates:      <pass>/<fail> in window
Watch:      <the single loudest signal, or "nothing new">
```

## `sprint-review` — the full retrospective

The default. This is today's report template, unchanged in content or order:
testability → escalation hotspots → autonomy (park/retry/circuit-break) → HITL
attestation (confirm vs override, `basis_shown`) → review-finding disposition →
model-tier attestation → complexity drift → patch lane → signals worth a look.

**Omits nothing** the export derives. When windowed, it **must** print the
day-granularity caveat and mark every as-of-now block as current state.

## `handoff` — "what state am I inheriting"

For an on-call or ownership handover. Deliberately **as-of-now**: a handoff is about
inherited state, not last sprint's activity. If the run was windowed, say that this
section ignores the window, and why.

**Leads with:** evidence freshness (`evidence` stamped / fresh / **stale** /
unstamped, and any STALE gap) · per-feature `verification_present` and review state ·
testability (what is machine-checked vs `manual:judgment`) · abandoned patches ·
unresolved escalations.

**Omits:** sprint-scoped autonomy rates and attestation ratios — those tune the
process, they do not describe the state you are inheriting.

```
Retro — <slug> · handoff (state as of <generated_at>, not windowed)
Evidence:    <fresh>/<stamped> fresh, <stale> STALE  ← re-verify before trusting
Unverified:  <features with no verification.md>
Open review: <features with blocking_high > 0>
Testability: <auto>/<total> automatic; <judgment> need a human to judge
Loose ends:  <abandoned patches, unresolved escalations, or "none">
```

---

**Selection.** The audience is a token in `$ARGUMENTS`
(`standup` | `sprint-review` | `handoff`); when absent, offer it as options on the
existing Stage-0 scope gate, defaulting to `sprint-review`. The audience changes
**only** Stage-2 narration order — Stage 1 runs the same deterministic floor and
produces the same JSON regardless. That is what structurally guarantees an audience
can never invent a number.
