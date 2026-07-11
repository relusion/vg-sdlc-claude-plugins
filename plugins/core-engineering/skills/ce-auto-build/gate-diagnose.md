# Auto-Build — Diagnose Gate  *(on-demand module)*

Gate module for the `ce-auto-build` skill (orchestrator: `SKILL.md`). **Loaded only when diagnose mode is on** — a consented Stage-0 choice. It fires on a failed verification-artifact gate (pipeline step 5) or a reproducible blocking review finding (step 6), root-causing the failure before the orchestrator retries or parks.

**Next:** return to the pipeline in `SKILL.md` (steps 5–6) with the routed outcome (a targeted re-implement, or a park).

---

## Diagnose Gate (root-cause a failure before retrying)

The verification and review gates *detect* a failure; the **diagnose gate**
*explains* it before the orchestrator acts. Without it a failed gate re-spawns
implement **blind** to the cause — spending the retry cap on a guess, or parking a
fixable bug. With it (diagnose mode on; **off by default** — see the note below),
each failure is root-caused first, so the orchestrator either retries with a target
or parks early on a cause retries cannot fix. It fires **only on a failure** (not
every feature), from the verification-artifact gate (step 5) or a **reproducible**
blocking review finding (step 6).

- **Substrate-independent:** spawned mode runs a fresh **debug subagent**
  (`debug`, autonomous mode, under the Spawn Contract); in-context mode runs
  a self-diagnosis pass with the identical protocol. It is a **gate** — its outcome
  is recorded in the run report's Diagnoses table before the orchestrator acts.
- **Inputs (on disk + prompt):** the failing evidence (which gate failed; the
  failing test / criterion / correctness finding), the code on disk, the spec as
  contract. It reproduces → localizes → classifies → writes `specs/<id>/diagnosis.md`
  → returns `DebugResult { class, cause file:line, confidence }`.
- **Diagnosis gate (real, on disk — and miss-safe):** require **both** a `class`
  returned by *this* spawn **and** `test -f specs/<id>/diagnosis.md`. Because
  `diagnosis.md` is cumulative (`debug` appends a `DX-N`; prior entries
  stay), a stale-but-present file does **not** satisfy the gate — this pass's
  returned class is the gate signal, the file is its evidence. **A debug spawn that
  crashes or returns no class is a debug failure → fall back to the blind path:
  re-spawn implement directly, consuming one verification-retry (retry cap →
  circuit-break), recorded as a degradation.** At most one debug miss per
  gate-failure, so the verification gate always terminates in retry-or-circuit-break.
  When the debug spawn returns a class, record the routing step with
  `run-state.py advance <id> diagnosing` (a neutral routing transition — neither a
  pass nor a fail; it emits the routing metric and marks the resume re-enter point),
  then dispose by class.
- **Route by class** (the four `debug` Stage-3 classes; **any non-`bug`
  class parks**, so a future or `indeterminate` outcome can never fall through) —
  each disposition is a `run-state.py` call, never a hand-kept counter:
  - **bug** → re-spawn implement, threading the diagnosis pointer
    (`specs/<id>/diagnosis.md`) into its prompt so the attempt targets the named
    locus. **`ce-spec.md` + `tasks.json` remain authoritative**; the diagnosis is a
    read-only pointer to where the *existing* contract was violated — if its
    recommended approach cannot be reconciled with the spec's design / ADRs, that is
    itself a `spec-gap` → park (it was never a bug). The re-implement consumes **one**
    verification-retry — `run-state.py retry <id>` (**exit 1 = retry cap reached →
    circuit-break**).
  - **spec-gap** → **`run-state.py park <id> --class spec-gap`** (Boundary/spec class — the new contract is the owner's).
  - **structural** → **`run-state.py park <id> --class structural`** (architecturally significant / cross-feature).
  - **not-a-code-defect** (environmental / flaky / external, or an unreproducible /
    indeterminate outcome) → **`run-state.py park <id> --class not-a-code-defect`** for the end-review with the evidence — never
    burn a retry on a cause no code change fixes.
  Every diagnose-driven park is a **normal park**: the `park` call increments the
  **consecutive-park counter** exactly like a spawn-returned `status:"parked"`, so
  the consecutive-park circuit-breaker (`breaker-check`) still bounds a run that
  parks feature after feature.
- **Retry accounting is `run-state.py retry`'s, not a hand-kept counter:** the
  debug spawn (`advance <id> diagnosing`) does **not** itself consume a
  verification-retry; only the subsequent re-implement issues `run-state.py retry <id>`,
  which owns the per-feature `retry_counts` and returns **exit 1 when the cap is
  reached** so the caller cannot miscount. A feature gets ≤ retry-cap targeted
  (debug → implement) cycles before circuit-break — bounded — and parks (`run-state.py
  park`) **earlier** than the blind path on spec / structural / not-a-code-defect
  causes.
- **It replaces the guess, not a layer:** the bug-vs-spec-gap call is made on
  reproduced evidence where **confirmed**, and **flagged** where `suspected` (the
  Diagnoses table's Confidence column carries this to the end-review). It never
  patches code or edits the spec (`debug`'s *Diagnose, Do Not Fix* lock) —
  every outcome is a bounded retry or a park, the same two terminal states the blind
  path already produces.
- **Resume:** `run-state.py advance <id> diagnosing` persists the routing status
  (`last_completed_gate: "diagnosing"`); the routing class rides as the companion
  cache `last_diagnosis: { dx_id, class }` (the one resume field outside `run-state.py`'s
  schema, preserved across its atomic writes). A feature parked at the diagnose gate is a
  normal terminal park, disk-revalidated on resume (disk wins). A run interrupted **after**
  a `bug` diagnosis but **before** its re-implement re-enters at the re-implement step from
  the persisted `class` — **not** a fresh debug spawn; the existing `specs/<id>/diagnosis.md`
  stays the human-readable evidence the re-implement threads in. See *Resume* in `SKILL.md`
  for why the class is read from `state.json`, not the cumulative `diagnosis.md`.
- **Bounds & limit:** tied to the Stage 0 budget and metered like every spawn. Like
  the Challenger and Review gates it **raises the floor, not the ceiling** — it
  shares the model's blind spots, so a mis-diagnosis surfaces as the next failure
  (re-entering within the cap) or at the end-review. History bisection is skipped
  under autonomy (`debug`'s Autonomous Mode).

**Default off.** Unlike the record-only challenger (`material-only`) and review
(`advisory`) defaults, diagnose mode changes **control flow** — it reroutes
retry-vs-park and shifts which circuit-breaker bounds the run (a spec-gap /
structural / not-a-code-defect cause now **parks early** instead of burning retries
to `failed`, moving the halt onto the consecutive-park cap). That is the
deliberately-opt-in precedent of `blocking-on-high`, not the record-only defaults,
so it is **off by default** and turned on as a consented Stage-0 choice — surfaced
at the Stage 0 confirmation and the end-review. When on, the built/parked/failed
split differs from an off run by design; every such reclassification shows in the
Diagnoses table.
