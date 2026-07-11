#!/usr/bin/env python3
"""Docs-drift checker — manifest-driven example replay.

docs/EXAMPLES.md publishes real captured command outputs as the framework's
evidence layer. On its own that is a *snapshot*: nothing proves the commands
still produce what the doc quotes. This checker turns the snapshot into a
standing guarantee.

docs/examples-manifest.json indexes every EXAMPLES.md example with the command
that produced it and the anchors the doc quotes. For each `deterministic: true`
entry (golden lint replays, `--help`-class outputs — all free, no model call),
docs_drift re-runs the command and diffs `expected_anchors` against the actual
output; drift (a missing anchor or an unexpected exit code) turns CI red. So a
mutated golden artifact, or an EXAMPLES.md excerpt that no longer matches its
source, can no longer pass silently.

`deterministic: false` entries are historical live model runs: this checker
lists them but never executes them (they cost money). EXAMPLES labels them as
historical snapshots; BENCHMARKS owns the dated current-evidence status and its
recency ratchet. They are examples, not silently current benchmark claims.

Coverage is self-policing: every `Provenance:` line in EXAMPLES.md must be
covered by a manifest entry, so the manifest cannot silently under-cover the doc.

Stdlib-only and offline by construction: the only commands it runs are the
deterministic entries the manifest declares, and it makes no network or model
calls of its own.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_REL = "docs/examples-manifest.json"
DEFAULT_DOC_REL = "docs/EXAMPLES.md"
VALID_SOURCES = {"live-eval", "golden"}
REPLAY_TIMEOUT_S = 120

# A manifest entry's required keys and their python types. `expected_exit` is
# optional (defaults to 0); `note` is free-form and ignored here.
REQUIRED_KEYS: dict[str, type | tuple[type, ...]] = {
    "id": str,
    "doc_anchor": str,
    "source": str,
    "deterministic": bool,
    "command": list,
    "expected_anchors": list,
}


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def load_manifest(root: Path, errors: list[str]) -> tuple[list[dict], str]:
    path = root / MANIFEST_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing: {MANIFEST_REL}")
        return [], DEFAULT_DOC_REL
    except (OSError, ValueError) as exc:
        errors.append(f"{MANIFEST_REL}: unreadable or invalid JSON: {exc}")
        return [], DEFAULT_DOC_REL
    if not isinstance(data, dict):
        errors.append(f"{MANIFEST_REL}: top level must be an object")
        return [], DEFAULT_DOC_REL
    doc_rel = data.get("doc", DEFAULT_DOC_REL)
    if not isinstance(doc_rel, str) or not doc_rel:
        errors.append(f"{MANIFEST_REL}: 'doc' must be a non-empty string")
        doc_rel = DEFAULT_DOC_REL
    examples = data.get("examples")
    if not isinstance(examples, list) or not examples:
        errors.append(f"{MANIFEST_REL}: 'examples' must be a non-empty list")
        return [], doc_rel
    return examples, doc_rel


def validate_entry(index: int, entry: object, errors: list[str]) -> bool:
    """Structural validation of one manifest entry. Returns True if the entry
    is well-formed enough to attempt a replay."""
    where = f"{MANIFEST_REL}: examples[{index}]"
    if not isinstance(entry, dict):
        errors.append(f"{where}: must be an object")
        return False
    ok = True
    for key, typ in REQUIRED_KEYS.items():
        if key not in entry:
            errors.append(f"{where}: missing required key {key!r}")
            ok = False
            continue
        # bool is a subclass of int, so guard it explicitly.
        value = entry[key]
        if typ is bool and not isinstance(value, bool):
            errors.append(f"{where}: {key!r} must be a boolean")
            ok = False
        elif typ is not bool and not isinstance(value, typ):
            errors.append(f"{where}: {key!r} must be {typ.__name__}")
            ok = False
    if not ok:
        return False
    if not entry["id"]:
        errors.append(f"{where}: 'id' must be non-empty")
        ok = False
    if not entry["doc_anchor"]:
        errors.append(f"{where}: 'doc_anchor' must be non-empty")
        ok = False
    if entry["source"] not in VALID_SOURCES:
        errors.append(
            f"{where}: 'source' {entry['source']!r} not in {sorted(VALID_SOURCES)}"
        )
        ok = False
    command = entry["command"]
    if not command or not all(isinstance(part, str) for part in command):
        errors.append(f"{where}: 'command' must be a non-empty list of strings")
        ok = False
    anchors = entry["expected_anchors"]
    if not all(isinstance(a, str) for a in anchors):
        errors.append(f"{where}: 'expected_anchors' must be a list of strings")
        ok = False
    if entry["deterministic"] and not anchors:
        errors.append(
            f"{where}: a deterministic entry must declare at least one "
            "expected anchor to diff against — otherwise the replay proves nothing"
        )
        ok = False
    exit_code = entry.get("expected_exit", 0)
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        errors.append(f"{where}: 'expected_exit' must be an integer")
        ok = False
    return ok


def check_ids_unique(entries: list[dict], errors: list[str]) -> None:
    seen: set[str] = set()
    for entry in entries:
        eid = entry.get("id")
        if not isinstance(eid, str) or not eid:
            continue
        if eid in seen:
            errors.append(f"{MANIFEST_REL}: duplicate example id {eid!r}")
        seen.add(eid)


def doc_sections(text: str) -> list[tuple[str, str]]:
    """Split EXAMPLES.md into (heading-line, body) pairs on `## ` headings."""
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(body)))
            heading = line
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body)))
    return sections


def check_coverage(doc_text: str, doc_rel: str, entries: list[dict],
                   errors: list[str]) -> None:
    """Two-way binding between EXAMPLES.md and the manifest.

    (a) Every EXAMPLES.md section carrying a `Provenance` line must be covered
        by an entry whose doc_anchor is a substring of that heading — so a new
        example added to the doc without a manifest entry fails here (the
        manifest cannot silently under-cover the doc).
    (b) Every entry's doc_anchor must be a substring of some `## ` heading — so
        a manifest entry pointing at a section that no longer exists fails too.
    """
    sections = doc_sections(doc_text)
    headings = [heading for heading, _ in sections]
    anchors = [e["doc_anchor"] for e in entries if isinstance(e.get("doc_anchor"), str)]

    for heading, body in sections:
        if "Provenance" not in body:
            continue
        if not any(anchor and anchor in heading for anchor in anchors):
            errors.append(
                f"{doc_rel}: section {heading!r} has a Provenance line but no "
                f"{MANIFEST_REL} entry covers it — add a manifest entry so the "
                "example is replayed or recency-tracked, never trusted on age"
            )

    for anchor in anchors:
        if not any(anchor in heading for heading in headings):
            errors.append(
                f"{MANIFEST_REL}: doc_anchor {anchor!r} matches no `## ` heading "
                f"in {doc_rel} — the example section was renamed or removed"
            )


def replay(root: Path, entry: dict, errors: list[str]) -> None:
    """Run one deterministic entry's command and diff expected_anchors against
    the combined stdout+stderr."""
    eid = entry.get("id", "?")
    command = entry["command"]
    expected_exit = entry.get("expected_exit", 0)
    try:
        proc = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=REPLAY_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        errors.append(f"{eid}: replay command not found: {exc}")
        return
    except OSError as exc:
        errors.append(f"{eid}: replay command failed to launch: {exc}")
        return
    except subprocess.TimeoutExpired:
        errors.append(
            f"{eid}: replay command exceeded {REPLAY_TIMEOUT_S}s — a deterministic "
            "example must be cheap (golden lint / --help-class), never a model run"
        )
        return

    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != expected_exit:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        first = detail[0] if detail else ""
        errors.append(
            f"{eid}: replay of {' '.join(command)!r} exited {proc.returncode} "
            f"(expected {expected_exit}){f': {first}' if first else ''}"
        )
        return
    for anchor in entry["expected_anchors"]:
        if anchor not in output:
            errors.append(
                f"{eid}: docs drift — EXAMPLES.md quotes {anchor!r} but the "
                f"replay of {' '.join(command)!r} no longer produces it "
                "(re-run the example and refresh the excerpt, or fix the source)"
            )


def run(root: Path) -> tuple[int, list[str]]:
    errors: list[str] = []
    entries, doc_rel = load_manifest(root, errors)
    if not entries:
        return 0, errors

    valid: list[dict] = []
    for index, entry in enumerate(entries):
        if validate_entry(index, entry, errors):
            valid.append(entry)
    check_ids_unique(valid, errors)

    doc_path = root / doc_rel
    try:
        doc_text = doc_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"{doc_rel}: cannot read: {exc}")
        doc_text = ""
    if doc_text:
        check_coverage(doc_text, doc_rel, valid, errors)

    replayed = 0
    for entry in valid:
        if entry.get("deterministic"):
            replay(root, entry, errors)
            replayed += 1
    return replayed, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay the captured example commands in docs/examples-manifest.json"
    )
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    replayed, errors = run(root)
    if errors:
        print(
            f"docs-drift: FAIL - {len(errors)} issue(s):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  x {error}", file=sys.stderr)
        return 1
    print(
        f"docs-drift: OK - {replayed} deterministic example(s) replayed, "
        "coverage verified, 0 issues."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
