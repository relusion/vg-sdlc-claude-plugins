# The six lessons — harvest recipes, typing discipline, checks

Each lesson lists: what it teaches, the **recorded** sources (harvested in plan-grounded
mode, or from any hand-written docs/ADRs), the **code signal** (always available), the
claim-typing discipline, a comprehension-check shape, and the known-unknown shapes the
lesson typically raises. Every claim taught lands in the dialog as
*(claim — `citation` — type)*; every unknown lands in the register the moment it is
raised.

---

## L1 — Context: what this product is

**Teaches:** what the software does, for whom, and the external world it touches — the
setting the rest of the curriculum lives in.

- **Recorded:** the brief's Problem & Goals and Success Criteria (`docs/briefs/<slug>.md`);
  `feature-plan.md`'s Overview and verbatim Original Project Description; the README's
  own words.
- **Code signal:** package-manifest name/description, entry points, deployment manifests,
  external clients and SDKs (every outbound integration is another actor in the product's
  world), public API surface, webhooks in and out.
- **Typing:** a README sentence is `recorded`; "it talks to Stripe" cited to the client
  code is `enforced` (the dependency is real); "so it probably takes payments online" is
  `inferred` — say so.
- **Check:** *"In your words: what does this product do, for whom, and which external
  systems does it depend on?"*
- **Register when:** market position, competitors, regulatory setting, or why this
  product exists are nowhere recorded — those are context unknowns, not blanks to fill.

## L2 — Actors & roles: who the system serves and distinguishes

**Teaches:** the humans and systems that act on the product, and what each may do.

- **Recorded:** the brief's **Users & Roles**; journey actors in the Journey Map;
  `threat-model.md` trust boundaries (who is untrusted, and where).
- **Code signal:** authorization roles and permission enums, policy/guard middleware,
  user models and tenancy fields, seeded roles in migrations and fixtures, separate
  surfaces (an admin panel vs a customer app), API consumers (keys, scopes), and the
  system actors — schedulers, webhook senders, integration daemons — that act without a
  human.
- **Typing:** a role enum and the check that consults it are `enforced`; a brief persona
  is `recorded`; "admins are probably internal staff" is `inferred`.
- **Check:** *"Name an action actor A can take that actor B cannot — and the code that
  makes it so."*
- **Register when:** the org structure behind the roles, who actually holds each role,
  or approval chains living outside the code are unevidenced.

## L3 — Domain nouns & lifecycles: the things and their states

**Teaches:** the domain nouns, the states each walks through, and the guards between
states.

- **Recorded:** the plan's **Durable-State Closure** table (nouns, access-modes,
  data-classes, lifecycle dispositions); EARS criteria that pin state behaviour.
- **Code signal:** entities/aggregates/models, state enums and state machines,
  transition guards, soft-delete and archival fields, uniqueness constraints, and the
  migration history — a noun's columns over time are its biography.
- **Typing:** a transition guard is `enforced`; a disposition row in the closure table is
  `recorded`; a lifecycle reconstructed from field names alone is `inferred`.
- **Check:** *"Walk `<noun>` through its lifecycle: which states, what forces each
  transition, and what code blocks an illegal one?"*
- **Register when:** a state exists that no code path reaches, or a noun's real-world
  counterpart is ambiguous ("is an Account a person or a company here?") — ask, don't
  decide.

## L4 — Processes & journeys: the flows and the rhythms

**Teaches:** the end-to-end flows the product supports, the schedules it runs on, and
where humans sit inside them.

- **Recorded:** the **Journey Map** (steps, surfaces, expected observables); the brief's
  **Primary Journeys**; per-feature `verification.md` journeys where they exist.
- **Code signal:** routes and handlers grouped by flow, background jobs and their
  schedules (a nightly reconciliation job is business rhythm, not plumbing), queues,
  events and sagas, notification templates (the emails a system sends narrate its
  journeys), inbound and outbound webhooks.
- **Typing:** a traced journey row is `recorded`; a flow reconstructed from a route chain
  is `enforced` step-by-step but `inferred` as a whole — label the stitching.
- **Check:** *"A `<noun>` is created — narrate what happens end to end, and say which
  steps are humans and which are code."*
- **Register when:** what happens off-screen between two steps, who reacts to a
  notification, or any SLA/turnaround expectation is unevidenced — the human process
  around the software is the register's home turf.

## L5 — Rules & invariants: what the system will not allow

**Teaches:** the business rules the code enforces, where each is enforced, and — only
where recorded — why.

- **Recorded:** EARS acceptance criteria (`ce-spec.md` §3, including `[SECURITY: TZ-NNN]`
  and `[CONTRACT: IC-NNN]` obligations), ADR Context/Consequences, the Resolved Project
  Decisions ledger, `docs/decisions/<slug>/` snapshots.
- **Code signal:** validators, database constraints, transaction boundaries, money /
  quantity / rounding logic, limits and quotas, feature flags and entitlements, error
  messages (a good error message states the rule in the user's own language), and test
  names with their assertions — a test suite is a rulebook written as proof.
- **Typing:** the rule itself is `enforced` (cite the rejecting line); its *why* is
  `recorded` only if an ADR/comment/doc states it. The threshold trap: *that* a 14-day
  window exists is enforced; *why 14* is almost always a register entry. "Presumably…"
  is the forbidden move — this lesson is where it tempts hardest.
- **Check:** *"State three invariants this system will not let you violate, each with
  the line that enforces it — and say which of their whys are recorded vs unknown."*
- **Register when:** a rule's rationale, its regulatory origin, or the business
  consequence of it firing is unevidenced.

## L6 — Ubiquitous language: the vocabulary the product is built around

**Teaches:** the product's terms as the repository actually uses them — and where the
vocabulary disagrees with itself.

- **Recorded:** the brief's own nouns and verbs; plan feature names; terms glossed in
  README/docs.
- **Code signal:** entity, route, event, and UI-string names; UI copy vs code names (the
  UI says "Project", the code says `Workspace` — that conflict is high-value domain
  signal); synonyms (two names, one concept), homonyms (one name, two concepts),
  abbreviations and their expansions.
- **Typing:** a term's *usage* is `enforced` by the code that bears it; its *meaning* is
  `recorded` only when a doc defines it; a meaning reconstructed from usage is
  `inferred`.
- **Output shape:** a glossary table — term · meaning as evidenced · citation · type ·
  conflicts — taught in the dialog and reproduced in the primer.
- **Check:** *"Define `<term>` as this codebase uses it — and where would that
  definition mislead a new teammate?"*
- **Register when:** two names compete for one concept (which is canonical?), or a
  term's business meaning visibly diverges from its code meaning — the team owns the
  choice, the tutor owns the evidence.
