# Ship-Backlog — per-format field tables

Companion to `SKILL.md`. The model builds one neutral `backlog.json`; the
`scripts/backlog-emit.py` emitter renders it to the format you pick. This file
documents what each `--format` produces and how the human consumes it. **All
four are one-way** — the emitter writes text, never a tracker; you paste or
import, and drift past that point is a process concern, not a tool feature.

The emitter assigns the local ids and enforces the hierarchy: the Story is
`US-1`, Tasks are `T-1..T-N` in `tasks[]` order, Bugs (if any) are `B-1..B-N`,
and every Task/Bug links to its `parent` (default `US-1`). Each format encodes
that parent link in the shape its importer expects.

---

## `ado-md` (default) — paste-markdown for Azure DevOps Agile

Reproduces the historical paste file. One delimited block per work item; `---`
is the paste boundary. Back-compat: this is what `/core-engineering:ce-ship-backlog` emitted
before the format split, so an existing paste flow is unchanged.

| Block | Fields rendered |
|---|---|
| Header | `# Backlog — <story title>`, source-spec line, `Process: ADO Agile`, `Generated:`, the manual-paste warning |
| Paste checklist | User Story created, Tasks created (N), parents set, tags applied, links added |
| `US-1 — User Story` | Title, Type, Description (blockquote), Acceptance Criteria (fenced, numbered EARS), Tags (backticked), optional Epic `Parent`, `Links: Spec`, `From:` stamp |
| `T-n — Task *(parent: US-1)*` | Title, Type, Description, Tags, `Parent: US-1`, `Links: Spec#task-list`, `From:` stamp |
| `B-n — Bug` | Only if the backlog carries `bugs[]`; same shape as a Task |

Consume: open the file, create the User Story, then each Task with its Parent
set to the Story's assigned id.

---

## `ado-csv` — Azure DevOps native bulk CSV import

RFC-4180 CSV for ADO's **Import Work Items** flow. Columns exactly:

| Column | Story row | Task / Bug row |
|---|---|---|
| `Work Item Type` | `User Story` | `Task` / `Bug` |
| `Title` | story title | task/bug title |
| `Description` | story description | task/bug description |
| `Acceptance Criteria` | numbered EARS block (embedded newlines, CSV-quoted) | empty |
| `Tags` | `; `-joined (ADO's tag separator) | `; `-joined |

Parent link: ADO's CSV importer creates flat items; the Story row is emitted
**before** its Task rows so you can indent the block in the import grid (or set
each Task's Parent to the Story after import). There is no Parent column in
ADO's native CSV schema — that is the documented post-import step.

---

## `jira-csv` — Jira CSV importer (Story + Sub-task rows)

CSV for Jira's **External System Import → CSV**. Sub-tasks link to the Story
through the importer's `Issue Id` / `Parent Id` pairing. Columns:

| Column | Story row | Sub-task / Bug row |
|---|---|---|
| `Issue Type` | `Story` | `Sub-task` / `Bug` |
| `Summary` | story title | task/bug title |
| `Description` | story description | task/bug description |
| `Acceptance Criteria` | numbered EARS block | empty |
| `Labels` | space-joined (Jira splits the Labels field on whitespace at import) | space-joined |
| `Issue Id` | `1` | `2..` |
| `Parent Id` | empty | `1` (the Story's Issue Id) |

Consume: map `Issue Id`→"Issue Id" and `Parent Id`→"Parent (issue id)" in the
importer's field-mapping step; Jira then nests Sub-tasks under the Story. Jira
labels cannot contain spaces — the emitted tags (`03-user-profile`,
`complexity:M`, `verifies:TC-1,TC-2`) are already space-free.

---

## `gh-jsonl` — one JSON object per issue for a `gh issue create` loop

JSON Lines: one issue object per line. GitHub issues have no native
parent/child, so the parent link is advisory — carried both as a `parent`
field and as a `Parent: US-1` line in the body. Object fields:

| Field | Story | Task / Bug |
|---|---|---|
| `id` | `US-1` | `T-n` / `B-n` |
| `type` | `Story` | `Task` / `Bug` |
| `title` | story title | task/bug title |
| `body` | description + `### Acceptance criteria` checklist + `From:` stamp | description + `Parent: US-1` + `From:` stamp |
| `labels` | tag list (JSON array) | tag list |
| `parent` | `null` | `US-1` |

Consume: loop the file through `gh issue create`, reading `.title`, `.body`,
and `.labels[]` per line, e.g.

```bash
while IFS= read -r line; do
  title=$(printf '%s' "$line" | python3 -c 'import json,sys;print(json.load(sys.stdin)["title"])')
  body=$(printf '%s'  "$line" | python3 -c 'import json,sys;print(json.load(sys.stdin)["body"])')
  labels=$(printf '%s' "$line" | python3 -c 'import json,sys;print(",".join(json.load(sys.stdin)["labels"]))')
  gh issue create --title "$title" --body "$body" --label "$labels"
done < backlog/<id>.gh.jsonl
```

Create the Story issue first, then reference its real GitHub number when you
wire up the Tasks (a tracking task-list in the Story body, or a projects
parent field). The emitter cannot know GitHub's assigned numbers — that is the
one-way boundary.
