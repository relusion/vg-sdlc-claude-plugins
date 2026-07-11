# ce-debug (plan-free mode) — Stage 1–3: Map, Hypothesize, Evidence

Stage file for the `ce-debug` skill's **plan-free mode** (orchestrator: `SKILL.md`). Covers the mechanism map, hypothesis generation, and the evidence pass. Load this file after Stage 0 is complete.

**Next:** when Stage 3 is complete, load `${CLAUDE_SKILL_DIR}/mode-planfree-4-5-report.md`.

---

## Stage 1 — Map the Mechanism

Targeted recon of the suspect path only — **cheap-first**: glob/grep/symbol search
to locate, then selective reads of the relevant ranges; never bulk-read. Map the
mechanism end-to-end as the loaded module's *mechanism-map checklist* directs —
typically: entry points, the processing loop and its supervision, the
completion/ack path, every error path, retry/backoff/dead-letter policy,
concurrency primitives and their limits, connection/credential lifecycle, the
configuration *as actually loaded* (including per-environment overrides), and the
logging points on each of those paths.

Then run **what-changed evidence**: `git log`/`blame` over the mapped files around
the symptom's onset — a recent change near the mechanism is prime evidence.

Output: a **mechanism map**, every node cited `file:line` (config keys and their
resolved values cited to their source).

## Stage 2 — Generate Hypotheses

Walk the loaded module's **failure-mode bank** against the mechanism map:

- Include a bank entry **iff its mechanism precondition exists in this code**
  (no ordering scopes → no key-starvation hypothesis). Record the families ruled
  out *by construction* in one line each — visible, not silent.
- Add **unbanked hypotheses** the map itself suggests. The bank raises the floor
  for the known failure modes; only the code walk catches the unnamed.
- Where the module provides a **signal → family triage** table, order the bank
  walk by it against the intake answers — prioritization only; never skip a
  family whose mechanism exists in the code.

Each hypothesis gets: `H-N`, a name, the mechanism *as it appears in this code*
(`file:line`), and its bank reference (or `unbanked`).

*(On a fallback run the Stage-0.5 skeleton stands in for the module — its
entries are walked and graded the same way but referenced as `synthesized`,
never given a curated bank id.)*

## Stage 3 — Evidence Pass

For each hypothesis, hunt **discriminating** evidence — evidence that moves it,
not evidence that merely coexists with it:

- the code path itself (`file:line`),
- configuration values as loaded,
- git history near the onset,
- the **provided runtime evidence** — quote log/metric lines (redacted per
  contract item 4) with source and timestamp; save larger captures to
  `docs/investigations/evidence/<date>-<slug>/H-N.*`.

Grade each `confirmed | suspected | refuted` per the Static Ceiling, then **rank**
by state, mechanism fit, and what-changed proximity. Human-provided testimony
(e.g. "a restart fixes it") is admissible, weighed as testimony and labeled as
such — it classifies families well but confirms nothing alone.
