# Stage 2–3 — Decompose, order, and route specifications

Load this stage after Stage 1A has either:

- validated a fresh selected/deferred architecture binding; or
- recorded an evidenced `not-required` screen for final approval.

Decompose the approved outcome, not the repository by layer and not the chosen
architecture by component.

## 2. Bind the current decision frame

Carry forward:

- Scope Lock, target users, and observable outcome;
- accepted decisions, constraints, assumptions, and unknowns;
- capability and journey ids;
- selected architecture option id/hash, or the provisional
  `not-required`/human-deferred disposition;
- relevant repository evidence and source hashes.

If any of those inputs changed after Stage 1A, return there before slicing.

## 2.1 Produce independently verifiable features

A feature is the smallest coherent delivery slice that creates user,
operational, migration, or platform value and can be verified independently.
Prefer vertical slices. Use foundation or enabling features only when a later
slice cannot safely ship without them.

For every feature record:

- stable ordered id `01-<slug>`, title, type, and concise value description;
- included and excluded behavior;
- public, data, integration, deployment, and operational surfaces;
- boundary-owner categories for shared responsibilities;
- hard and soft dependencies, unlocks, and ship order;
- affected journeys and observable validation target;
- durable nouns read, created, amended, retained, exported, erased, or retired;
- security/data classifications and known threat/interaction obligations;
- open unknowns with owner and next check;
- risk profile and final complexity.

Do not use a foundation feature to hide broad setup work. Give it a concrete
consumer and testable exit condition.

## 2.2 Choose the specification route

Persist one machine authority on every `plan.json.features[]` entry:
`"specification_route": "compact"|"explicit"`. Project it once in the feature
Markdown as `**Specification route:** compact|explicit`; do not duplicate it in
the YAML metadata.

Compact is disqualified—and the route is `explicit`—when:

- `final_complexity` is `Complex`;
- a security/privacy obligation or security reviewer trigger is present;
- the feature owns or changes an external/public API, CLI, event, schema, or
  configuration contract;
- a hard-dependency interface is unresolved;
- the feature owns or changes a cross-feature flow, shared shape, or interaction
  contract;
- material migration, concurrency, failure, compatibility, destructive, or
  irreversible design remains;
- any product, scope, boundary, acceptance-adequacy, or `manual:judgment`
  decision remains, or behavior, acceptance, test location, validation
  commands, and a small ordered task cut are not all known.

Otherwise use `compact`. A stable built dependency or already selected
architecture direction does not disqualify compact by itself. Compact does not
skip the canonical spec artifacts `ce-spec.md`, `tasks.json`, or `spec-lint.py`;
implementation composes and lints them before code. Explicit routes run
`/core-engineering:ce-spec <slug>/<id>` as a distinct user-visible workflow.

Downstream workflows re-run this exact screen as a drift guard. If the current
facts no longer support the manifest route, return to Plan Stage R; never
silently reinterpret or override the approved route.

## 3. Order, size, and risk-rank

Order by hard dependency, then by earliest independently verifiable value.
Keep soft dependencies explicit but do not let them masquerade as blockers.

Use repository-relative evidence for:

- **complexity:** `Simple`, `Moderate`, or `Complex`;
- **risk:** `low`, `medium`, or `high`;
- **session fit:** `standard` unless a material slice truly cannot fit one
  implementation session.

Complexity is explanatory, not a gate. Risk controls specification depth,
review focus, verification breadth, and required human decisions.

## 3.1 Candidate integrity checks

Before showing the candidate, check:

- every in-scope capability and journey is owned or explicitly excluded;
- hard dependencies resolve and point earlier;
- no feature owns an unbounded horizontal layer without a consumer;
- boundary-owner categories have one clear owner;
- public and durable surfaces have creation, consumption, change, and retirement
  coverage where applicable;
- every feature has a runnable validation target;
- compact specification routes satisfy every rule above.

Repair deterministic or obvious local defects without asking. Ask only when a
repair changes scope, ownership, sequencing, security acceptance, architecture,
or another human-owned decision.

## 3.2 Re-screen architecture after decomposition

Run the Stage 1A driver screen again over concrete feature boundaries.

- A new positive/unknown load-bearing driver invalidates a prior
  `not-required`, deferred, or selected frame. Return to Stage 1A.
- A selected direction whose option consequences no longer match the feature
  cut returns to Stage 1A.
- Otherwise retain the existing binding and record the clean re-screen.

Do this before any small-plan shortcut. Feature count alone never proves
architecture or security is not applicable.

## 3.3 Checkpoint

Increment `candidate_revision` and save the candidate features, dependency
graph, journey mapping, risk/complexity, specification routes, and architecture
re-screen result under `docs/plans/.drafts/<slug>/`.

Do not ask for a generic “candidate looks right” confirmation. The remaining
stages run closure checks and surface only material exceptions before the one
Final Plan Approval.

**Next:** load `${CLAUDE_SKILL_DIR}/stage-4-7-gates.md`.
