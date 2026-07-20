---
name: ce-ship-backlog
description: |
  Generate paste-ready or importable backlog items from a feature spec — one Story plus one Task per tasks.json item, parent-linked, EARS as the Story's acceptance criteria, linked back to the spec. The model maps the spec into a neutral backlog.json; a stdlib emitter renders it to ADO paste-markdown (default), ADO CSV, Jira CSV, or GitHub-Issues JSONL. One-way only; no API, no sync.
  Triggers: convert a feature spec into ADO / Jira / GitHub backlog tickets or work items — paste-markdown or bulk-import CSV/JSONL emitters.
argument-hint: "[feature-id] [--format ado-md|ado-csv|jira-csv|gh-jsonl]"
allowed-tools: Read, Write, Glob, Grep, Bash, AskUserQuestion, Skill
---

# Ship Backlog

**Invocation input:** Feature id (qualified or unqualified) and optional `--format`: $ARGUMENTS

Generate **paste-ready or importable** backlog items from a feature spec. The
model reads the spec, builds one neutral `backlog.json`, then runs a stdlib
emitter to render the format you pick; the human reviews the output at a
material Write gate and pastes/imports it into the tracker — **one-way** (the
full rule lives in *Cross-cutting rule — One-Way Sync* below).

This is a **bridging utility** — sister to `/core-engineering:ce-ask`, `/core-engineering:ce-ux-audit`, and
`/core-engineering:ce-probe-sec`. Sits outside the SDLC pipeline; reads spec artifacts; runs a
deterministic emitter; writes a single re-runnable output file.

## Runtime Inputs

- **Feature id (required):** e.g. `03-user-profile`, or qualified `<plan-slug>/03-user-profile`. If missing, read `docs/plans/plans.json`, list features with a `specs/<id>/` directory, and ask which to generate.
- **`--format` (optional):** one of `ado-md` (default), `ado-csv`, `jira-csv`, `gh-jsonl`. If absent, confirm the target at Stage 0; `ado-md` is the back-compat default.

`ado-md` and `ado-csv` target ADO **Agile** work-item types (Story + Task). Other ADO process templates (Scrum / CMMI / Basic) are a documented non-goal — see *Honest Limitations* — not a tunable parameter.

## Preconditions

- The feature has a spec — `specs/<id>/ce-spec.md` exists in its plan directory.
- `tasks.json` exists in the same `specs/<id>/` directory.

## Execution Contract

*Gate locator (HITL R5):* print `Gate N of M — <name>` at every interactive gate; compute M from the gates that actually fire this run, never a hardcoded constant.

1. **One-way only.** Spec → `backlog.json` → emitted text → human → tracker. No reverse import, no API, no sync. Drift past the paste/import is the human's concern.
2. **Concise tickets.** Title, short description, AC (Story only), tags, link to spec. **No** Design, Test Cases, Resolved Decisions, or ADR content goes into tickets — those live in `ce-spec.md`.
3. **Hierarchy enforced.** One Story for the feature; one Task per `tasks.json` entry; Tasks parent-link to the Story. The emitter assigns `US-1` / `T-1..T-N` and carries the parent link in each format's native shape.
4. **Stamped.** Every ticket carries `From: <path-to-ce-spec.md> @ spec_revision N` so drift is auditable later.
5. **Read-only on spec / plan / code.** Writes only the emitted backlog file (and, transiently, `backlog.json`). No edits to specs or other artifacts.
6. **Re-runnable.** Re-running overwrites the backlog file in place. Git history is the history.
7. **Deterministic emit.** The model builds `backlog.json`; `scripts/backlog-emit.py` (stdlib `json`/`csv` only) renders every format. The script never reads a spec, never writes a file, never touches a tracker — it transforms `backlog.json` to stdout.

## Model tier (optional)

This transform is the toolset's one safe **cheap-tier** candidate, and the
split made it *more* mechanical: the model only maps `ce-spec.md` + `tasks.json`
into a neutral `backlog.json` (verbatim EARS), and a deterministic stdlib script
does all format rendering. It is one-way, **feeds nothing downstream**, and the
human reviews the full output at the material Write gate (Stage 2.2) before any
paste/import. So it **may** run on a cheaper model if the user chooses — opt-in
and overridable, never a binding `model:` in the skill frontmatter. Every other
stage of the toolset stays on the strong model (see the repo's *Model-tier
policy*).

## Cross-cutting rule — One-Way Sync

The spec is the system of record. Tickets are derivatives. **There is no path back.** If a ticket is edited in the tracker after creation, the spec doesn't know — that drift is invisible to this tool. Two practical implications:

- Every ticket includes a `From: …ce-spec.md @ spec_revision N` stamp so a human can compare back manually.
- Re-running regenerates `backlog.json` and the emitted file; the diff between regenerations tells you what *the spec* changed. Tracker-side changes are not captured.

## Cross-cutting rule — Concise Tickets

Tickets must be scan-friendly in the tracker. Each carries:

- **Title** (short, action-oriented)
- **Description** (1–3 sentences — what + why)
- **Acceptance Criteria** (Story only — copied EARS criteria from the spec, verbatim)
- **Tags / Labels** (feature id, complexity, risk profile; for Tasks: the test case ids it verifies)
- **Parent** (Tasks only — points at the Story)
- **Links** (path to `ce-spec.md`)

Tickets **do not** include the spec's Design, Test Case bodies, Resolved Decisions, ADR text, traceability matrix, or assumptions. Those stay in the spec — the ticket links to them.

## Human-in-the-Loop — minimal

Two moments:

- **Stage 0** — confirm the feature id and the target `--format`.
- **Stage 2** — present the emitted backlog and ask: *Write / Adjust / Abort*.

No mid-flow gates. The transformation is mechanical; the human reviews the result, not the process.

---

## Stage 0 — Load and Frame

1. Resolve the feature via `docs/plans/plans.json` (registry-first; ask if the id is ambiguous across plans).
2. Read `ce-spec.md` and `tasks.json` from `docs/plans/<slug>/specs/<id>/`, `plan.json` from `docs/plans/<slug>/` (it carries `final_complexity` and the risk profile per feature id — the source of the Story's `complexity:` / `risk:` tags), and `features/<id>.md` from `docs/plans/<slug>/` — its frontmatter `reviewer_triggers` list is the source of the Story's reviewer-trigger tags (`security`, `auth`, `persistence`, …). If the feature file is absent, emit no reviewer-trigger tags and say so (no silent omission).
3. Note `spec_revision` from `ce-spec.md`'s header.
4. Confirm the target `--format` (default `ado-md`).

---

## Stage 1 — Build the neutral `backlog.json`

Map the spec into one neutral intermediate — the model's only real work. This is
what the emitter consumes; the per-format field tables live in
**`${CLAUDE_SKILL_DIR}/formats.md`** (read it if you need to explain an output),
but the model never format-specific-renders — it only fills this schema.

Build the hierarchy: **1 Story + N Tasks (one per `tasks.json` entry)**.

```json
{
  "feature_id": "<id>",
  "spec_path": "docs/plans/<slug>/specs/<id>/ce-spec.md",
  "spec_revision": <N>,
  "generated": "<date>",
  "story": {
    "title": "<id>: <feature title from ce-spec.md>",
    "description": "<1–3 sentence feature description; trim if longer>",
    "acceptance_criteria": ["<EARS criterion 1, verbatim>", "<EARS 2>", "…"],
    "tags": ["<id>", "complexity:<final>", "risk:<profile>", "<reviewer-trigger…>"],
    "from": "docs/plans/<slug>/specs/<id>/ce-spec.md @ spec_revision <N>"
  },
  "tasks": [
    {
      "title": "<task title from tasks.json, short form>",
      "description": "<task notes from the spec's Task List section, concise>",
      "tags": ["<id>", "verifies:TC-1,TC-2"],
      "parent": "US-1",
      "from": "docs/plans/<slug>/specs/<id>/ce-spec.md @ spec_revision <N>"
    }
  ],
  "bugs": []
}
```

**Field sourcing** (unchanged from the historical field tables):

- `story.title` = `<id>: <feature title>`; `story.description` = the spec's feature description; `story.acceptance_criteria` = the EARS criteria from spec Section 3, **copied verbatim**, one per array entry.
- `story.tags` = `<id>`, `complexity:<final>`, `risk:<profile>` (both from `plan.json` for this id), plus the feature's `reviewer_triggers`.
- Each `tasks[]` entry = one `tasks.json` item; `tags` include `verifies:<TC-…>` from the task's `verifies` field; `parent` is `US-1` (the single Story).
- **Optional Bug.** If the spec's *Boundary-Conflict Log* has entries marked as known regressions or pending fixes, add one `bugs[]` entry each. Most specs have none — leave `bugs` empty.
- The `From: <spec> @ spec_revision N` stamp is preserved per item via each object's `from`.

Write `backlog.json` to `docs/plans/<slug>/backlog/<id>.backlog.json` (create `backlog/` if absent) — the emitter's input and the diff-able record of what the spec said this run.

---

## Stage 2 — Emit, Present, Approve, Write

### 2.1 Emit

Run the emitter for the chosen format (stdout only — it writes no file):

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/backlog-emit.py" \
  docs/plans/<slug>/backlog/<id>.backlog.json --format <ado-md|ado-csv|jira-csv|gh-jsonl>
```

`ado-md` is the default and reproduces the historical paste-markdown. The
emitter assigns `US-1` / `T-1..T-N`, enforces the one-Story hierarchy, and
encodes the parent link in each format's native shape (see `formats.md`).

### 2.2 Present, then Approve  [material]

Show the human a summary line — `<N> Tasks under 1 Story for feature <id>, format <fmt>` — and the full emitted output for review. Then ask: *Write / Adjust / Abort*.

- **Write** — proceed to 2.3.
- **Adjust** — point at what to change; fix `backlog.json`, re-emit, re-present.
- **Abort** — stop without writing the output file.

### 2.3 Write

Write the emitted text to `docs/plans/<slug>/backlog/<id>.<ext>` — `.md` for `ado-md` (back-compat), `.ado.csv`, `.jira.csv`, or `.gh.jsonl` for the others. **Overwrite** if re-running. Git history is the history.

Confirm:

```text
Backlog generated: <slug>/<id>
Tickets: 1 Story + <N> Tasks
Format:  <fmt>
Input:   docs/plans/<slug>/backlog/<id>.backlog.json
File:    docs/plans/<slug>/backlog/<id>.<ext>

To land it:
  ado-md   → open the file; paste each `---`-delimited block; set Task parents to the Story.
  ado-csv  → ADO Boards → Import Work Items → the CSV; parent Tasks in the import grid.
  jira-csv → Jira → External System Import → CSV; map Issue Id / Parent Id to nest Sub-tasks.
  gh-jsonl → loop each line through `gh issue create` (see formats.md).
```

---

## Escalation

If the spec is missing, stale, or internally inconsistent, route to `/core-engineering:ce-spec`.
If multiple features need coordinated tracker structure, route to `/core-engineering:ce-plan` or a
human-owned backlog process. This skill emits paste-ready / importable work items
only; it never syncs with a tracker.

## Honest Limitations

- **One-way, Agile-shaped.** No reverse sync from any tracker back to the spec — a ticket edited after import is drift this tool can't see (the *Cross-cutting rule — One-Way Sync* states the mechanism). The ADO emitters target **Agile** work-item types only; Scrum (Product Backlog Item), CMMI (Requirement), and Basic (Issue/Task/Epic) need different types and fields — a documented non-goal, not a stubbed parameter.
- **No external IDs.** The emitter uses placeholder labels (`US-1`, `T-1`, …). The tracker assigns real IDs at paste/import time; the human writes those back into the file if they want a record.
- **Parent linkage is best-effort per tracker.** ADO CSV creates flat items (parent in the grid); Jira nests Sub-tasks via `Issue Id`/`Parent Id`; GitHub has no native issue parent, so `gh-jsonl` carries the link advisorily (a `parent` field + a `Parent:` body line). `ado-md` labels each Task's parent inline.
- **Drift is a process problem, not a tool feature.** The spec stays the source of truth; keeping tickets and spec in sync after paste/import is the team's discipline. This tool only regenerates from the spec.
- **Emit, never sync.** Four one-way formats (paste-markdown, ADO CSV, Jira CSV, GitHub JSONL). No `azdo`/`jira`/tracker API, no reverse import. A tracker API or reverse sync is a non-goal — the one-way rule is the skill's identity, not a missing feature.
- **Single feature at a time.** Matches the rest of the toolset's per-feature granularity. Multi-spec batch would produce an unreadable wall and confuse parent-child linking.
