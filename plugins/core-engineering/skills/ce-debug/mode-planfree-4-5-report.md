# ce-debug (plan-free mode) — Stage 4–5: Discrimination Plan, Report and Route

Stage file for the `ce-debug` skill's **plan-free mode** (orchestrator: `SKILL.md`). Covers the discrimination plan, the Stage-5 report-and-route gate, the report template, and the closing. Load this file after Stage 3 is complete.

**Next:** this is the last stage file — the run ends with the Closing block below.

---

## Stage 4 — Discrimination Plan

For every hypothesis not yet `confirmed` or `refuted`: name the **cheapest
observation that settles it** — a specific log query, a broker/console counter, a
metric, a live config value, a thread/stack dump, a *proposed* (never applied)
instrumentation line, or a consented local repro. Order the plan by cost. Where
one observation discriminates several hypotheses at once, say so — that one goes
first.

This plan is the tool's primary deliverable whenever the Static Ceiling holds: it
converts "I can't know from here" into "here is exactly what to go look at."

## Stage 5 — Report and Route  [material]

Write `docs/investigations/<date>-<slug>.md` per the template below. Present
the ranked hypotheses and the route options; the **human picks**, and the choice
is recorded in the report.

| Outcome | Route |
|---|---|
| `confirmed` cause; small, bounded fix | `/ce-patch` |
| Top-ranked `suspected` whose discriminator the human **declines to fetch** | stop without a code-change route; record the accepted uncertainty and the unfetched discriminator |
| Cause is structural — cross-component, design, ownership | `/ce-plan` |
| Component turns out to be a spec-owned pipeline feature | switch to **planned mode** — load `${CLAUDE_SKILL_DIR}/mode-planned.md` and diagnose against the contract (this report is the failure signal) |
| Cause needs numeric / performance proof | `/ce-probe-perf` |
| Security-shaped cause | `/ce-review` Security lens (static) · `/ce-probe-sec` (dynamic) |
| Environmental / external — no code change fixes it | the human + ops, armed with the discrimination-plan items |
| Nothing above `suspected` | run the discrimination plan; re-invoke with the new evidence |

---

## Report Template — `docs/investigations/<date>-<slug>.md`

````markdown
# Investigation — <date> · <slug>

> Component: <path-or-name>   ·   Symptom class: <class> (module: <file> | generic fallback: synthesized module (unverified) | generic fallback: module <file> FAILED TO LOAD)
> Environment: <env>   ·   Onset: <when>   ·   What changed: <summary | unknown>
> Runtime evidence: none provided — all grades ceiling-capped | <sources: logs(<level>) · metrics · broker console · dumps> (redacted)
> Execution consent: none | tests | repro (<what ran>)
> Hypotheses: <T>  (<C> confirmed · <S> suspected · <R> refuted)
> Plan-awareness: not a planned feature | spec-owned by <plan>/<id> — human chose to proceed here

## Symptom

<the restated symptom — concrete, observable, with the onset and blast radius>

## Mechanism Map

<the mapped path, each node cited `file:line`; configuration as loaded; the
what-changed git summary>

## Hypotheses (ranked)

### H-N — <name>  [confirmed | suspected | refuted]

- **Bank:** <family-entry id | unbanked | synthesized>
- **Mechanism here:** <how this code exhibits it> (`file:line`)
- **Evidence:** <code cite / config key / commit / quoted log line + source — one per line>
- **Discriminator:** <the observation that settles it — or what confirmed/refuted it>
- **If confirmed, route:** <skill | ops>

## Ruled Out by Construction

- <bank family> — <the mechanism this code does not have>

## Discrimination Plan (ordered by cost)

| # | Hypothesis | Observation | Where / how | Settles it as |
|---|---|---|---|---|

## Proposed Module  *(fallback runs only)*

Synthesized skeleton: `docs/investigations/proposed-modules/<date>-<class>.md`
— unverified; a candidate for human review into the skill's `symptoms/` library.

## Route

<the human's chosen route — or "pending discrimination plan">

## Open Questions / Stops

| # | When | Question asked | Human's answer | Effect on run |
|---|---|---|---|---|
````

---

## Closing

```text
Investigation complete: <slug> — <date>
Component:  <component>  ·  Class: <class>
Hypotheses: <T> (<C> confirmed · <S> suspected · <R> refuted)
Top lead:   H-N — <name> [state]
Next:       <chosen route | run the discrimination plan>
Report:     docs/investigations/<date>-<slug>.md
Proposed:   docs/investigations/proposed-modules/<date>-<class>.md   (fallback runs only)
```

Never patch; never commit; never deploy. The report routes — the routed lane fixes.
