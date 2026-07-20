# Autonomous Mode — the auto-build execution overlay for `/core-engineering:ce-spec`

Loaded **only** when `/core-engineering:ce-spec` runs under `/core-engineering:ce-auto-build` (a spawned spec
worker). The interactive `/core-engineering:ce-spec` never loads this file — its Tiered HITL gates
apply as written. Read it once, before Stage 0, and apply it for the whole run.

---

When invoked by `/core-engineering:ce-auto-build`, run without interactive gates, applying auto-build's **Decision Classification**:

- **Auto-resolve** engineering-default unknowns and design choices (record each in the run ledger).
- **Assume & flag** reversible, non-destructive, non-architectural product unknowns — proceed on a clearly-labeled assumption.
- **Park** (return control to the orchestrator; do not proceed) on a blocking product/business unknown with no sensible default, a destructive design choice, an ADR-worthy decision, or a Boundary Conflict. Never silently resolve a blocking business unknown.
- Classify manual test cases as normal, but **defer manual verdicts** to auto-build's end-review.
- **Security obligations are not waivable here.** Emit a `[SECURITY: TZ-NNN]` criterion for every `TZ-NNN` the threat-model assigns this feature (§2.1 Security Criteria). If one is genuinely N/A, **park** it — consent-exclusion needs a human and a `/core-engineering:ce-plan` threat-model edit, which an autonomous spec agent cannot do. Never silently drop an assigned threat (the spec-artifact gate's H5 would block it anyway).
- **Interaction-contract obligations are not waivable here.** Emit a `[CONTRACT: IC-NNN]` criterion + ≥ 1 test case for every `IC-NNN` the `interaction-contract.md` assigns this feature (§2.1 Interaction-Contract Criteria). If one is genuinely N/A, **park** it — consent-exclusion needs a human and a `/core-engineering:ce-plan` interaction-contract edit, which an autonomous spec agent cannot do. Unlike `[SECURITY]` there is **no H5-style hard gate** (a behavioural invariant / NFR is un-derivable from markdown), so *surfacing* the binding is the only backstop — never silently drop an assigned `IC-NNN`.
- **Shared-shape modifications park (§3.5).** The `additive`-vs-`breaking` call on
  a SHARED persisted/wire shape is model-derived and has no mechanical gate.
  Return `parked` with the shape, real consumers, per-consumer impact, and
  cost-if-wrong. The end-review can route the decision to `/core-engineering:ce-decide` or an
  interactive `/core-engineering:ce-spec`; never let an autonomous classification authorize it.
- Any condition that would normally escalate to `/core-engineering:ce-plan` → **park** rather than escalate interactively.

Outside autonomous mode, the Tiered HITL gates throughout this workflow apply as written.
