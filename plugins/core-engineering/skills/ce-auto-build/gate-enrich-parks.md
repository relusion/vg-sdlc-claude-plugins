# Enrich-Parks — on-demand module

Loaded by `auto-build/SKILL.md` only when **enrich-parks mode** is on (a consented
Stage-0 choice). Off by default, so the common run never pays this context. This file
holds the full protocol and guardrails; the SKILL keeps the one-paragraph identity inline.

## Enrich-Parks (scope a park, never resolve it)

Off by default. When **on**, and a spawned agent hits a PARK-class fork that is
**architecturally significant or a genuine multi-option choice** (not a product/business
or destructive park — those carry no engineering option-space to score), the orchestrator
runs the `/ce-decide` discipline to turn the bare parked question into a
**scored decision package** the end-review human can act on fast: the options enumerated,
each axis evidence-tagged, the per-option vector + composite shown, a falsifiable DEAD-IF,
and a **proposed ADR draft** (`Status: proposed`).

It **scopes the choice; it never makes it** — the complement of the Challenger across the
framework's bright line. The Challenger pressures the **engineering** decisions the agent
*may answer* (challenges, never answers); Enrich-Parks enriches the **PARK-class** forks
the agent *must not answer* (scores, never resolves). Guardrails, all mandatory:

- **`reasoned` mode, weights marked agent-inferred.** A parked owner-knowledge decision is
  missing exactly the *situation* (urgency, blast, stakes) `/ce-decide`'s weights derive from —
  so the package runs in `reasoned` evidence mode and marks every situation-derived weight
  **`inferred` ("re-derive these")**. It informs the human; it never pretends to their
  context.
- **Parks the package; does not clear the park.** The feature stays `parked`; the scored
  package + draft ADR ride along as the blocking record for Stage 3. The human decides and
  promotes the ADR — the agent never auto-promotes, never proceeds on the recommendation.
- **Budget-tied, like the other modes.** `/ce-decide` is heavyweight; on a tight budget the
  circuit-breaker may skip enrichment — the bare park still surfaces (no silent loss).
