# Feature-Patch — Artifact Reference  *(write-time)*

Reference file for the `patch` skill (orchestrator: `SKILL.md`; run flow: `stages.md`). Load this when you write the lease (Stage 0), write the artifacts (Stage 1), and close (Stage 4) — do not reconstruct these formats from memory.

**Next:** return to `${CLAUDE_SKILL_DIR}/stages.md` for the run flow.

---

## Artifact Layout

```
docs/plans/patch-<date>-<slug>/
  features/00-<slug>.md          # frozen Boundary anchor + pointer to the lease
  specs/00-<slug>/
    eligibility.json             # the lightness lease: 7 verdicts, decided_by:human, base_ref, frozen_files, file_cap
    ce-spec.md                   # the real 10-section template, patch-scaled
    tasks.json                   # execution-ordered, modality-tagged, files ⊆ lease
    verification.md              # written on Accept
  .metrics.jsonl                 # canonical schema, stage:"patch"
```
Plus a `plans.json` entry with `origin: "patch"`. It lives **inside `docs/plans/`**
on purpose — coherence with every downstream tool — and a re-run against the same
slug is a revision, not a duplicate.

## `eligibility.json`

```json
{
  "slug": "<slug>",
  "decided_by": "human",
  "accepted_at": "<ISO-8601>",
  "base_ref": "<git rev at Stage 0>",
  "file_cap": 5,
  "frozen_files": ["path/a", "path/b"],
  "clauses": {
    "C1_bounded_surface":     {"verdict": "yes", "kind": "mechanical", "evidence": "…"},
    "C2_no_durable_noun":     {"verdict": "yes", "kind": "mechanical", "evidence": "…"},
    "C3_no_new_interface":    {"verdict": "yes", "kind": "human", "attested_by": "human", "evidence": "…"},
    "C4_no_blast_radius":     {"verdict": "yes", "kind": "mechanical", "evidence": "…"},
    "C5_reversible":          {"verdict": "yes", "kind": "mechanical", "evidence": "…"},
    "C6_no_reviewer_trigger": {"verdict": "yes", "kind": "human", "attested_by": "human", "evidence": "…"},
    "C7_no_open_unknown":     {"verdict": "yes", "kind": "human", "attested_by": "human", "evidence": "…"}
  }
}
```

## `express-log.jsonl`  *(the express fold's only persistent record)*

The **express fold** (SKILL.md → *The express fold*; run flow in `stages.md`) writes
**no** `patch-<date>-<slug>/` directory, **no** `eligibility.json`, `ce-spec.md`,
`tasks.json`, `verification.md`, and **no** `plans.json` entry. Its entire durable
footprint is **one appended line** in a single repo-wide log:

```
docs/plans/express-log.jsonl      # append-only; one line per accepted express change
```

One JSON object per line, appended **only on Accept** at the combined gate:

```json
{
  "ts": "<date>",
  "desc": "<the change request, one line>",
  "files": ["path/a", "path/b"],
  "base_ref": "<git HEAD at E-Step 1>",
  "tests": {"red": true, "green": true, "command": "<the test command run>"},
  "screen": "clean",
  "c6_c7": "attested-in-gate",
  "decision": "accept",
  "decided_by": "human"
}
```

- `screen: "clean"` records that the mechanical `patch-lint --express` (E1–E4) plus the
  `--express --post` diff end check (H8/H9/H10) both passed — the precondition that made
  the one-gate lane legitimate.
- `c6_c7: "attested-in-gate"` records that C6/C7 were human-attested in the single
  combined gate (the documented R3 deviation), never auto-certified.
- `decision` is `accept` (a Discard writes **no** line — the log is the accepted-change
  ledger); `decided_by: "human"` is mandatory.
- `/ce-retro` reads this log's **express-lane frequency + discard rate** as the
  salami-slicing smell signal (several featherweight edits composing one un-specced
  feature). Best-effort, append-only, and never gates the run.

## Metrics  *(best-effort, optional)*

After Stage 4 (or a promotion), append a line to
`docs/plans/patch-<date>-<slug>/.metrics.jsonl` per the `retro` schema:
`stage: "patch"`, a `stage-complete` event on Accept, the Stage-2/4 `gate` events,
and on graduation an `escalation` with `escalation_type: "/ce-plan"` and
`detail: "patch-promote:…"`. Derive every field from data in hand, label token
figures estimates, and **never** let metrics block the run. `/ce-retro`
reads it — including the **patch-promotion rate**, the signal that tells you whether
the file cap is too generous.
