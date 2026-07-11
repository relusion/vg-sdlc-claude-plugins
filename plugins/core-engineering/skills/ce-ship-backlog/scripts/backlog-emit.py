#!/usr/bin/env python3
"""backlog-emit.py — deterministic one-way backlog format emitter.

Consumes the neutral intermediate `backlog.json` that /ce-ship-backlog's model
half builds from a feature's `ce-spec.md` + `tasks.json`, and renders it to one
paste/import format. The model reviews the output at the material Write gate and
persists it; this script only transforms — it never reads a spec, never writes a
file, never touches a tracker API. Stdlib only (`json`, `csv`), so it runs with
zero Claude Code present (portability_check picks it up automatically).

The one-way rule is structural here: input is a static artifact, output is text
on stdout, and there is no path back. Emitters replace hand-transcription, not
the human paste/import step.

Neutral schema (`backlog.json`):
    {
      "feature_id": "03-user-profile",
      "spec_path": "docs/plans/<slug>/specs/03-user-profile/ce-spec.md",
      "spec_revision": 2,
      "generated": "2026-07-05",                # informational (ado-md header)
      "story": {
        "title": "03-user-profile: Profile management",
        "description": "One to three sentences.",
        "acceptance_criteria": ["EARS 1", "EARS 2"],
        "tags": ["03-user-profile", "complexity:M", "risk:medium", "security"],
        "from": ".../ce-spec.md @ spec_revision 2"
      },
      "tasks": [
        {"title": "...", "description": "...",
         "tags": ["03-user-profile", "verifies:TC-1,TC-2"],
         "parent": "US-1", "from": ".../ce-spec.md @ spec_revision 2"}
      ],
      "bugs": [                                  # optional; usually empty
        {"title": "...", "description": "...", "tags": [...], "from": "..."}
      ]
    }

The hierarchy rule (one Story, one Task per tasks.json entry, Tasks parent-link
to the Story) is enforced at emit time: the script assigns the Story the local
id `US-1`, numbers Tasks `T-1..T-N` in order, and links every Task to its
`parent` (defaulting to `US-1` — there is exactly one Story per feature). Every
format carries that parent reference in the shape its importer expects; see
`../formats.md` for the per-format field tables.

Usage:
    python3 backlog-emit.py <backlog.json> [--format ado-md|ado-csv|jira-csv|gh-jsonl]

`--format` defaults to `ado-md`, which reproduces the historical paste-markdown
(back-compat). Output goes to stdout. Exit 0 on success, 1 on a malformed
backlog, 2 on a usage error.
"""

import argparse
import csv
import io
import json
import sys

FORMATS = ("ado-md", "ado-csv", "jira-csv", "gh-jsonl")
STORY_ID = "US-1"


def _fail(msg):
    print(f"backlog-emit: {msg}", file=sys.stderr)
    return 1


def load_backlog(path):
    """Read + shape-check the neutral backlog. Returns (data, error-or-None)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None, f"no such backlog file: {path}"
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot read {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"{path} is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, f"{path}: top level must be a JSON object"
    story = data.get("story")
    if not isinstance(story, dict) or not str(story.get("title", "")).strip():
        return None, f"{path}: missing a `story` object with a non-empty title"
    tasks = data.get("tasks", [])
    if not isinstance(tasks, list):
        return None, f"{path}: `tasks` must be a list"
    for i, task in enumerate(tasks):
        if not isinstance(task, dict) or not str(task.get("title", "")).strip():
            return None, f"{path}: tasks[{i}] must be an object with a title"
    bugs = data.get("bugs", [])
    if not isinstance(bugs, list):
        return None, f"{path}: `bugs` must be a list"
    return data, None


def _task_id(index):
    return f"T-{index + 1}"


def _tags(item):
    return [str(t) for t in item.get("tags", []) if str(t).strip()]


def _criteria(story):
    return [str(c) for c in story.get("acceptance_criteria", []) if str(c).strip()]


# --------------------------------------------------------------------------- #
# ado-md — the historical paste-markdown (default, back-compat)
# --------------------------------------------------------------------------- #

def emit_ado_md(b):
    story = b["story"]
    tasks = b.get("tasks", [])
    bugs = b.get("bugs", [])
    spec_path = b.get("spec_path", "")
    revision = b.get("spec_revision", "")
    generated = b.get("generated", "")
    story_from = story.get("from", "")
    lines = []
    lines.append(f"# Backlog — {story['title']}")
    lines.append("")
    lines.append(f"> Source spec: `{spec_path}` @ spec_revision {revision}")
    lines.append("> Process: ADO Agile")
    lines.append(f"> Generated: {generated}")
    lines.append("> **Manual paste only — no sync back to spec.**")
    lines.append("")
    lines.append("## Paste checklist")
    lines.append("")
    lines.append("- [ ] User Story created — note its ID for the Task parents below")
    lines.append(f"- [ ] Tasks created ({len(tasks)} total)")
    lines.append("- [ ] Each Task's Parent set to the Story")
    lines.append("- [ ] Tags applied per ticket")
    lines.append("- [ ] Links to ce-spec.md added (if your ADO setup allows external links)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## {STORY_ID} — User Story")
    lines.append("")
    lines.append(f"**Title:** {story['title']}")
    lines.append("")
    lines.append("**Type:** User Story")
    lines.append("")
    lines.append("**Description:**")
    lines.append("")
    lines.append(f"> {story.get('description', '')}")
    lines.append("")
    lines.append("**Acceptance Criteria** *(paste into ADO's AC field, markdown-friendly):*")
    lines.append("")
    lines.append("```")
    criteria = _criteria(story)
    if criteria:
        for i, crit in enumerate(criteria, 1):
            lines.append(f"{i}. {crit}")
    lines.append("```")
    lines.append("")
    tag_str = ", ".join(f"`{t}`" for t in _tags(story))
    lines.append(f"**Tags:** {tag_str}")
    lines.append("")
    lines.append("**Parent:** *(optional — link to an Epic / Feature in ADO if your project uses one)*")
    lines.append("")
    lines.append("**Links:**")
    lines.append(f"- Spec: `{spec_path}`")
    lines.append("")
    lines.append(f"**From:** {story_from}")
    lines.append("")
    lines.append("---")
    for idx, task in enumerate(tasks):
        tid = _task_id(idx)
        parent = task.get("parent") or STORY_ID
        lines.append("")
        lines.append(f"## {tid} — Task  *(parent: {parent})*")
        lines.append("")
        lines.append(f"**Title:** {task['title']}")
        lines.append("")
        lines.append("**Type:** Task")
        lines.append("")
        lines.append("**Description:**")
        lines.append("")
        lines.append(f"> {task.get('description', '')}")
        lines.append("")
        lines.append(f"**Tags:** {', '.join(f'`{t}`' for t in _tags(task))}")
        lines.append("")
        lines.append(f"**Parent:** {parent}")
        lines.append("")
        lines.append("**Links:**")
        lines.append(f"- Spec: `{spec_path}#task-list`")
        lines.append("")
        lines.append(f"**From:** {task.get('from', '')}")
        lines.append("")
        lines.append("---")
    for idx, bug in enumerate(bugs):
        bid = f"B-{idx + 1}"
        parent = bug.get("parent") or STORY_ID
        lines.append("")
        lines.append(f"## {bid} — Bug  *(parent: {parent})*")
        lines.append("")
        lines.append(f"**Title:** {bug['title']}")
        lines.append("")
        lines.append("**Type:** Bug")
        lines.append("")
        lines.append("**Description:**")
        lines.append("")
        lines.append(f"> {bug.get('description', '')}")
        lines.append("")
        lines.append(f"**Tags:** {', '.join(f'`{t}`' for t in _tags(bug))}")
        lines.append("")
        lines.append(f"**Parent:** {parent}")
        lines.append("")
        lines.append(f"**From:** {bug.get('from', '')}")
        lines.append("")
        lines.append("---")
    return "\n".join(lines) + "\n"


def _csv_string(rows):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# ado-csv — ADO's native bulk CSV import
# --------------------------------------------------------------------------- #

def emit_ado_csv(b):
    story = b["story"]
    tasks = b.get("tasks", [])
    bugs = b.get("bugs", [])
    rows = [["Work Item Type", "Title", "Description",
             "Acceptance Criteria", "Tags"]]
    # ADO tags are semicolon-separated; AC is one markdown-ish block.
    rows.append([
        "User Story",
        story["title"],
        story.get("description", ""),
        "\n".join(f"{i}. {c}" for i, c in enumerate(_criteria(story), 1)),
        "; ".join(_tags(story)),
    ])
    for task in tasks:
        rows.append([
            "Task",
            task["title"],
            task.get("description", ""),
            "",
            "; ".join(_tags(task)),
        ])
    for bug in bugs:
        rows.append([
            "Bug",
            bug["title"],
            bug.get("description", ""),
            "",
            "; ".join(_tags(bug)),
        ])
    return _csv_string(rows)


# --------------------------------------------------------------------------- #
# jira-csv — Jira's CSV importer (Story + Sub-task rows, Issue Id/Parent Id link)
# --------------------------------------------------------------------------- #

def emit_jira_csv(b):
    story = b["story"]
    tasks = b.get("tasks", [])
    bugs = b.get("bugs", [])
    rows = [["Issue Type", "Summary", "Description",
             "Acceptance Criteria", "Labels", "Issue Id", "Parent Id"]]
    story_iid = "1"
    rows.append([
        "Story",
        story["title"],
        story.get("description", ""),
        "\n".join(f"{i}. {c}" for i, c in enumerate(_criteria(story), 1)),
        # Jira splits the Labels field on whitespace at import time.
        " ".join(_tags(story)),
        story_iid,
        "",
    ])
    next_iid = 2
    for task in tasks:
        rows.append([
            "Sub-task",
            task["title"],
            task.get("description", ""),
            "",
            " ".join(_tags(task)),
            str(next_iid),
            story_iid,
        ])
        next_iid += 1
    for bug in bugs:
        rows.append([
            "Bug",
            bug["title"],
            bug.get("description", ""),
            "",
            " ".join(_tags(bug)),
            str(next_iid),
            story_iid,
        ])
        next_iid += 1
    return _csv_string(rows)


# --------------------------------------------------------------------------- #
# gh-jsonl — one JSON object per issue for a `gh issue create` loop
# --------------------------------------------------------------------------- #

def _gh_story_body(story):
    parts = [story.get("description", "").strip()]
    criteria = _criteria(story)
    if criteria:
        parts.append("### Acceptance criteria\n"
                     + "\n".join(f"- [ ] {c}" for c in criteria))
    frm = story.get("from", "")
    if frm:
        parts.append(f"From: {frm}")
    return "\n\n".join(p for p in parts if p)


def _gh_task_body(task, parent):
    parts = [task.get("description", "").strip(), f"Parent: {parent}"]
    frm = task.get("from", "")
    if frm:
        parts.append(f"From: {frm}")
    return "\n\n".join(p for p in parts if p)


def emit_gh_jsonl(b):
    story = b["story"]
    tasks = b.get("tasks", [])
    bugs = b.get("bugs", [])
    objs = []
    objs.append({
        "id": STORY_ID,
        "type": "Story",
        "title": story["title"],
        "body": _gh_story_body(story),
        "labels": _tags(story),
        "parent": None,
    })
    for idx, task in enumerate(tasks):
        parent = task.get("parent") or STORY_ID
        objs.append({
            "id": _task_id(idx),
            "type": "Task",
            "title": task["title"],
            "body": _gh_task_body(task, parent),
            "labels": _tags(task),
            "parent": parent,
        })
    for idx, bug in enumerate(bugs):
        parent = bug.get("parent") or STORY_ID
        objs.append({
            "id": f"B-{idx + 1}",
            "type": "Bug",
            "title": bug["title"],
            "body": _gh_task_body(bug, parent),
            "labels": _tags(bug),
            "parent": parent,
        })
    return "\n".join(json.dumps(o, ensure_ascii=False) for o in objs) + "\n"


EMITTERS = {
    "ado-md": emit_ado_md,
    "ado-csv": emit_ado_csv,
    "jira-csv": emit_jira_csv,
    "gh-jsonl": emit_gh_jsonl,
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="backlog-emit.py",
        description="Render a neutral backlog.json to a paste/import format "
                    "(one-way; stdout only).",
    )
    parser.add_argument("backlog", help="path to the neutral backlog.json")
    parser.add_argument(
        "--format", choices=FORMATS, default="ado-md",
        help="output format (default: ado-md — the historical paste-markdown)",
    )
    args = parser.parse_args(argv)

    data, err = load_backlog(args.backlog)
    if err:
        return _fail(err)
    sys.stdout.write(EMITTERS[args.format](data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
