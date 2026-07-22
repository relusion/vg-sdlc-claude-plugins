"""Tests for skills/ce-brief/scripts/brief-lint.py — the brief.json sidecar contract.

brief-lint closes the spine's least-verified entry stage: ce-brief writes a
brief.json sidecar that ARMS ce-plan's Brief-Aware Skip Contract, yet nothing
validated it before this lint. These pin the 0/1/2 exit contract:

  0 PASS  — sidecar well-formed, the Brief -> Plan skip map is computable;
  1 FAIL  — a hard well-formedness failure (H1 heading / H2 stub description /
            H3 unshipped lens / H4 sidecar shape);
  2 ERROR — inputs missing/unparseable -> the sidecar cannot authorize a skip.

Advisory checks (A1 range-exception reason, A2 durable-noun loop, and A3
open-question count) warn but never change the exit code.
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-brief/scripts/brief-lint.py"

_spec = importlib.util.spec_from_file_location("brief_lint_mod", SCRIPT)
bl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bl)

# A brief that clears every HARD check (H1 headings, H2 self-sufficient
# description, and — paired with GOOD_SIDECAR — H3/H4).
GOOD_MD = """# Project Brief — Fleet Maintenance

## Raw Idea
track vehicle maintenance requests

## Lenses Applied
solutions-architect, business-analyst

## Project Description
This project builds a small internal service that lets an ops user submit and
track maintenance requests against fleet vehicles, with an approval step and a
status dashboard so nothing gets lost between shifts. It must integrate with the
existing auth system and persist to the current Postgres database.

## Problem & Goals
requests get lost between shifts

## Users & Roles
ops user, approver

## Primary Journeys
An ops user creates a request and can later find, edit, and switch between them.

## Scope
- MVP: submit + approve + list

## Success Criteria
zero lost requests

## Technical Context
- Preferred stack: python

## Constraints & Ordering
auth first

## Known Risks & Pitfalls
approval race

## Delivery Target
internal pilot by the end of the quarter

## Reference Documents
- docs/product/fleet-maintenance.md

## Assumptions
single tenant

## Open Questions
- retention policy undecided
- notification channel undecided

## Decision Log
chose approval-before-dispatch
"""

_SECTIONS = {
    "raw-idea": "answered", "lenses-applied": "answered",
    "project-description": "answered", "problem-goals": "answered",
    "users-roles": "answered", "primary-journeys": "answered",
    "scope": "answered", "success-criteria": "answered",
    "technical-context": "answered", "constraints-ordering": "open",
    "known-risks-pitfalls": "open", "delivery-target": "answered",
    "reference-documents": "answered", "assumptions": "answered",
    "open-questions": "open", "decision-log": "answered",
}
GOOD_SIDECAR = {
    "schema_version": 2,
    "brief_sha256": hashlib.sha256(GOOD_MD.encode("utf-8")).hexdigest(),
    "sections": dict(_SECTIONS),
    "lenses": ["solutions-architect", "business-analyst"], "open_questions": 2,
}


def _write_case(d: Path, md=GOOD_MD, sidecar=GOOD_SIDECAR, lenses=("solutions-architect", "business-analyst")):
    """Lay down brief.md + brief.json + a personas dir with the given lens files."""
    personas = d / "personas"
    personas.mkdir(exist_ok=True)
    for lens in lenses:
        (personas / f"{lens}.md").write_text("## Role\nx\n", encoding="utf-8")
    brief = d / "brief.md"
    brief.write_text(md, encoding="utf-8")
    if sidecar is not None:
        (d / "brief.json").write_text(
            sidecar if isinstance(sidecar, str) else json.dumps(sidecar),
            encoding="utf-8")
    return brief, personas


def run_json(
    brief: Path,
    personas: Path,
    sidecar: Path | None = None,
    extra: tuple[str, ...] = (),
):
    argv = [sys.executable, str(SCRIPT), str(brief),
            "--personas-dir", str(personas), "--json"]
    if sidecar is not None:
        argv += ["--sidecar", str(sidecar)]
    argv += list(extra)
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"_stdout": proc.stdout, "_stderr": proc.stderr}
    return payload, proc.returncode


class BriefLintGreen(unittest.TestCase):
    def test_wellformed_pair_passes(self):
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td))
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 0, payload)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["hard_failures"], [])

    def test_advisories_do_not_fail(self):
        # One lens with no stated exception (A1) + open_questions mismatch (A3)
        # must warn but keep exit 0.
        sc = dict(GOOD_SIDECAR)
        sc["lenses"] = ["solutions-architect"]
        sc["open_questions"] = 5
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar=sc, lenses=("solutions-architect",))
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 0, payload)
            self.assertTrue(any(a.startswith("A1") for a in payload["advisory"]))
            self.assertTrue(any(a.startswith("A3") for a in payload["advisory"]))

    def test_disputed_state_is_valid(self):
        sc = dict(GOOD_SIDECAR)
        sc["sections"] = dict(_SECTIONS)
        sc["sections"]["technical-context"] = "disputed"
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar=sc)
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 0, payload)

    def test_plan_consumer_can_revalidate_without_the_persona_library(self):
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td))
            for persona in personas.iterdir():
                persona.unlink()
            payload, rc = run_json(
                brief, personas, extra=("--skip-persona-check",)
            )
            self.assertEqual(rc, 0, payload)


class BriefLintRed(unittest.TestCase):
    def test_missing_heading_fails(self):
        md = GOOD_MD.replace("## Decision Log\nchose approval-before-dispatch\n", "")
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), md=md)
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 1)
            self.assertTrue(any("H1" in f and "Decision Log" in f
                                for f in payload["hard_failures"]))

    def test_stub_description_fails(self):
        md = GOOD_MD.replace(
            GOOD_MD.split("## Project Description\n")[1].split("\n## Problem")[0],
            "<synthesized 1–2 paragraphs>")
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), md=md)
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 1)
            self.assertTrue(any(f.startswith("H2") for f in payload["hard_failures"]))

    def test_unshipped_lens_fails(self):
        # sidecar names a lens with no personas/<lens>.md — the dangling
        # "UX/design lens" class of reference.
        sc = dict(GOOD_SIDECAR)
        sc["lenses"] = ["solutions-architect", "ux-design"]
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar=sc)  # only SA/BA files exist
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 1)
            self.assertTrue(any("H3" in f and "ux-design" in f
                                for f in payload["hard_failures"]))

    def test_bad_section_state_fails(self):
        sc = dict(GOOD_SIDECAR)
        sc["sections"] = dict(_SECTIONS)
        sc["sections"]["scope"] = "maybe"
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar=sc)
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 1)
            self.assertTrue(any(f.startswith("H4") and "scope" in f
                                for f in payload["hard_failures"]))

    def test_wrong_schema_version_fails(self):
        sc = dict(GOOD_SIDECAR)
        sc["schema_version"] = 1
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar=sc)
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 1)
            self.assertTrue(any("schema_version" in f for f in payload["hard_failures"]))

    def test_non_int_open_questions_fails(self):
        sc = dict(GOOD_SIDECAR)
        sc["open_questions"] = "two"
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar=sc)
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 1)
            self.assertTrue(any("open_questions" in f for f in payload["hard_failures"]))

    def test_empty_sections_fails(self):
        sc = dict(GOOD_SIDECAR)
        sc["sections"] = {}
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar=sc)
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 1)
            self.assertTrue(any("sections" in f for f in payload["hard_failures"]))

    def test_stale_markdown_hash_fails(self):
        sc = dict(GOOD_SIDECAR)
        sc["brief_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar=sc)
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 1)
            self.assertTrue(any(f.startswith("H5 brief_sha256")
                                for f in payload["hard_failures"]))

    def test_answered_empty_section_cannot_authorize_a_skip(self):
        md = GOOD_MD.replace(
            "## Users & Roles\nops user, approver\n", "## Users & Roles\n"
        )
        sc = dict(GOOD_SIDECAR)
        sc["brief_sha256"] = hashlib.sha256(md.encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), md=md, sidecar=sc)
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 1)
            self.assertTrue(any("sections[users-roles]" in f
                                for f in payload["hard_failures"]))

    def test_missing_delivery_target_cannot_pass_when_claimed_answered(self):
        md = GOOD_MD.replace(
            "## Delivery Target\ninternal pilot by the end of the quarter\n\n",
            "",
        )
        sc = dict(GOOD_SIDECAR)
        sc["brief_sha256"] = hashlib.sha256(md.encode("utf-8")).hexdigest()
        self.assertEqual(sc["sections"]["delivery-target"], "answered")

        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), md=md, sidecar=sc)
            payload, rc = run_json(brief, personas)

        self.assertEqual(rc, 1)
        joined = " ".join(payload["hard_failures"])
        self.assertIn("Delivery Target", joined)
        self.assertIn("sections[delivery-target]", joined)

    def test_missing_section_status_is_hard_failure(self):
        sc = dict(GOOD_SIDECAR)
        sc["sections"] = dict(_SECTIONS)
        del sc["sections"]["primary-journeys"]
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar=sc)
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 1)
            self.assertTrue(any("missing required slug" in f
                                for f in payload["hard_failures"]))


class BriefLintDegrade(unittest.TestCase):
    def test_missing_sidecar_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar=None)
            payload, rc = run_json(brief, personas,
                                   sidecar=Path(td) / "nope.json")
            self.assertEqual(rc, 2)
            self.assertEqual(payload["status"], "error")

    def test_garbled_sidecar_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            brief, personas = _write_case(Path(td), sidecar="{not valid json")
            payload, rc = run_json(brief, personas)
            self.assertEqual(rc, 2)
            self.assertEqual(payload["status"], "error")

    def test_no_args_is_house_contract(self):
        # portability: bare invocation exits within {0,1,2} (argparse -> 2), no crash.
        proc = subprocess.run([sys.executable, str(SCRIPT)],
                              capture_output=True, text=True, timeout=30)
        self.assertIn(proc.returncode, (0, 1, 2))
        self.assertNotIn("Traceback", proc.stderr)


class BriefLintUnit(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(bl.slugify("Problem & Goals"), "problem-goals")
        self.assertEqual(bl.slugify("Known Risks & Pitfalls"), "known-risks-pitfalls")

    def test_placeholder_has_no_content(self):
        self.assertEqual(bl._content_len("<synthesized 1–2 paragraphs>"), 0)
        self.assertGreater(bl._content_len("real prose here"), 0)


if __name__ == "__main__":
    unittest.main()
