# Feature-Spec Workflow — Artifact Templates

Output templates for the `spec` skill (orchestrator: `SKILL.md`). Load this
file at **Stage 5.1 (Assemble)** — it is the write-time format reference and is not
needed while framing, resolving unknowns, or designing. Do not reconstruct either
file's format from memory.

---

## `ce-spec.md`

**Tier-scaling — scale effort to feature size (SKILL.md Execution Contract §6).** The
ten sections below are the *full* shape. A **Simple feature with no open unknowns**
omits the sections that would be empty — **omit the empty section, never the
analysis.** The guard is the same every time: *omit a section because it is genuinely
empty, never because the thinking was skipped.*

- **Required always** (they carry the spec and the `spec-lint` H1–H5 contract — a spec
  missing these is not implementation-ready and fails the lint): **§1** Feature &
  Frozen Boundary, **§3** Acceptance Criteria, **§4** Test Cases, **§5** Design, **§6**
  Task List, **§10** Handoff.
- **Omittable when genuinely empty:**
  - **§2 Resolved Decisions** — omit when the feature had no open unknowns to resolve
    (nothing was decided). Never omit to dodge a decision that exists.
  - **§7 Traceability Matrix** — omit when Scope→AC→TC→Task is strictly **1:1** and
    already legible from the section headers (`spec-lint` A3 finds no tokens and stays
    silent). Keep it the moment any row fans out (one AC → many TCs, or shared TCs).
  - **§8 Assumptions & Limitations** — render `None` when there are genuinely none; do
    **not** silently drop it (honest-scoping).
  - **§9 Boundary-Conflict Log** — omit when no feature-file edit or escalation
    occurred (already marked `N/A if none`).
  - Within **§5**, *Shared-Shape Reconciliation* and *Pitfalls honored* are
    `N/A`/omittable when none, as marked.

````markdown
# Spec: <id> — <title>

> Source feature: `../../features/<id>.md`
> Spec revision: 1 · Status: ready-for-implementation

## 1. Feature & Frozen Boundary

**Type:** <type>
**Description:** <one or two sentences>

**Scope (frozen):**
- …

**Non-Goals / Excluded (frozen):**
- …

**Dependencies:**
- Hard: <id> (specced | built)
- Soft: <id> — bridge: <description>

## 2. Resolved Decisions

*(Tier-scaling: omit this section when the feature had no open unknowns to resolve.)*

| # | Question (open unknown) | Decision | Rationale | Decided by | Propagation |
|---|---|---|---|---|---|
| D-1 | … | … | … | human | feature-local · RPD-n · ADR-NNNN |

## 3. Acceptance Criteria

EARS statements — one requirement each, tracing to a Scope item.

### AC-1 — <title>  (covers Scope: <item>)

When <trigger>, the <system> shall <response>.
*(pattern: ubiquitous · event-driven · state-driven · unwanted-behaviour · optional)*

### AC-2 — <title>  [SECURITY: TZ-NNN]  (covers Scope: <item>)

If <untrusted condition>, then the <system> shall <deny / validate / escape>.
*(a **security criterion** — Stage 2.1 Security Criteria; the `[SECURITY: TZ-NNN]`
marker backrefs this feature's threat-model.md obligation and is what spec-lint **H5**
checks. Its test cases are `auto` / `manual:harness-gap`, never `manual:judgment`.)*

### AC-3 — <title>  [CONTRACT: IC-NNN]  (covers Scope: <item>)

If <a message / event is redelivered>, then the <system> shall <apply its effect at most once>.
*(an **interaction-contract criterion** — Stage 2.1 Interaction-Contract Criteria; the
`[CONTRACT: IC-NNN]` marker backrefs this feature's interaction-contract.md obligation
(a behavioural-protocol invariant or an architecture-determining NFR). Its test cases are
`auto` / `manual:harness-gap`, never `manual:judgment`; unlike `[SECURITY]` there is
**no H5-style hard gate** — coverage is human/agent-attested, like §3.5 / §3.6.)*

## 4. Test Cases

### TC-1  (proves AC-1) — modality: http · verification: auto

- Realizes: Journey <name> step <n>   *(omit if not from a journey)*
- Preconditions: …
- Action / input: …
- Expected result: …

### TC-2  (proves AC-1) — modality: manual · verification: manual:judgment

- Reason: aesthetic taste — palette / brand feel / delight (assembled-surface layout & readability is **Surface-Quality** §2.1, checkable, **not** judgment)
- Preconditions: …
- Action / input: …
- Expected result: …

## 5. Design

**Files to create / modify:**
- `path` — <what>

**Integration points:**
- …

**Patterns & conventions:**
- …

**Data / schema:**
- `<shape>` — NEW | SHARED — <what changes>

**Shared-Shape Reconciliation** — one `shared-shape-modify` block per SHARED shape this feature modifies (§3.5). `N/A` if this feature modifies no shared shape.

```text
shared-shape-modify: <shape name / path>
  consumers:
    - <feature-id / client / migration> — additive | breaking — <how it is affected>
  disposition: additive-only | breaking → Boundary Conflict BC-n
```

**Cross-Feature Flow** (§3.6) — `traced` (every cross-feature sequence this design realizes matches a plan Journey Map row) · `new flow → Boundary Conflict BC-n` (a new untraced flow escalated) · `N/A` (this feature realizes no cross-feature sequence).

**Test harness mapping:**
- TC-1 → `path/to/test` — <approach>

**Pitfalls honored:**
- …

## 6. Task List

### T-1 — <title>  (verifies: TC-1, TC-2)

- Change: `path` — <what>
- Verification: <test cases / command>
- Notes: <pitfalls, conventions>

## 7. Traceability Matrix

*(Tier-scaling: omit this section when Scope→AC→TC→Task is strictly 1:1 and legible from the section headers; keep it the moment any row fans out.)*

| Scope item | Acceptance Criteria | Test Cases | Tasks |
|---|---|---|---|
| … | AC-1 | TC-1, TC-2 | T-1, T-2 |

**Journey coverage** — the journey steps this feature owns (plan Journey Map `Owned By` = this feature). `N/A` if this feature owns no journey steps.

| Journey · step | Modality | Expected observable | Test Cases |
|---|---|---|---|
| <name> · 3 | browser | confirmation shows the new item's id | TC-1 |

## 8. Assumptions & Limitations

*(Tier-scaling: render `None` when there are genuinely none — do not silently drop.)*

- …

## 9. Boundary-Conflict Log

Feature-file edits made during this spec, or escalations raised. `N/A` if none.

| # | Conflict | Resolution | `features/<id>.md` change |
|---|---|---|---|

## 10. Handoff

Implement the task list in order. Each task is complete when its test cases pass.
````

## `tasks.json`

```json
{
  "feature_id": "<id>",
  "spec_revision": 1,
  "tasks": [
    {
      "id": "T-1",
      "description": "…",
      "files": ["path"],
      "verifies": ["TC-1", "TC-2"],
      "order": 1,
      "status": "todo"
    }
  ]
}
```

`tasks` is in execution order. Every `verifies` entry must be a test case id that
exists in `ce-spec.md`. `/core-engineering:ce-spec` authors each task with `status: "todo"` and writes
**none** of the evidence fields below — they are the spec's contract, not its outcome.

**Implement-written evidence fields (additive; `/core-engineering:ce-spec` never writes them).** When
`/core-engineering:ce-implement` marks a task `done`, it *stamps* it with proof of completion
(`task-evidence.py`) rather than flipping a bare flag — three fields land on the task
object:

| Field | Written | Meaning |
|---|---|---|
| `completed_at` | task marked `done` | UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`) — when done-ness was recorded. |
| `commit_sha` | done (per-task) / feature commit (per-feature/none) | full sha of the commit holding the proven change; `null` until committed. The freshness check (`/core-engineering:ce-verify`, `/core-engineering:ce-ship-release`) reads it to verdict a task `fresh` vs `stale` against HEAD. |
| `test_run_digest` | task marked `done` | `sha256:<hex>` test-run fingerprint, projected **verbatim** from the task's PASS marker in `.test-guard/<id>/passes.json` (the source of truth); `null` for a task with no `auto` test and no captured log — never fabricated. |

These are **additive and optional**: `spec-lint.py`'s H1–H4 read only `id`, `verifies`,
and `status`, so their presence never affects the lint (a stamped `tasks.json` still
passes). The full artifact model is in `docs/HOW-IT-WORKS.md` §2.
