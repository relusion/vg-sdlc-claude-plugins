"""Executable authoring coverage for the architecture direction workbench."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO
    / "plugins/core-engineering/skills/ce-architecture/scripts/"
    "architecture-workbench.py"
)
OPTIONS_LINT = (
    REPO
    / "plugins/core-engineering/skills/ce-architecture/scripts/"
    "architecture-options-lint.py"
)
SELECTION_LINT = (
    REPO
    / "plugins/core-engineering/skills/ce-plan-audit/scripts/"
    "architecture-selection-lint.py"
)
SELECTION_FIXTURES = REPO / "tests/test_architecture_selection_lint.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wb = _load("architecture_workbench_test_module", SCRIPT)
ol = _load("architecture_workbench_options_lint", OPTIONS_LINT)
sl = _load("architecture_workbench_selection_lint", SELECTION_LINT)
fixtures = _load("architecture_workbench_fixture_source", SELECTION_FIXTURES)


def _semantic_option(option: dict) -> dict:
    return {
        key: copy.deepcopy(value)
        for key, value in option.items()
        if key
        not in {
            "weighted_score",
            "confidence",
            "option_sha256",
        }
    } | {"elimination_reason": None}


def _initial_draft(data: dict) -> dict:
    return {
        "schema_version": 1,
        "decision": {
            "decision": (
                "Choose the whole-solution direction that will bind decomposition."
            ),
            "why_now": "The direction changes boundaries and the feature cut.",
            "current_constraints": (
                "Personal data remains in-region and invalid tokens fail closed."
            ),
            "key_tradeoff": (
                "A01 maximizes repository fit while A02 preserves a stronger "
                "future extraction boundary."
            ),
            "cost_if_wrong": (
                "The team would rework persistence, migration, and operational ownership."
            ),
            "material_gaps_and_inferences": (
                "No blocking gap; option implementation scores remain planning judgments."
            ),
        },
        "options": [_semantic_option(option) for option in data["options"]],
        "uncarried_options": [
            {
                "label": "Independent invitation service",
                "disposition": "uncarried",
                "reason": "No source-backed need for another runtime.",
                "evidence_or_next_check": "Revisit if a deployment-isolation target appears.",
            }
        ],
        "recommendation": {
            "option_id": "A01",
            "basis": "A01 is the highest weighted, source-backed fit for the current frame.",
        },
        "audit_event": {
            "event": "initial-synthesis",
            "human_input": "Initial comparison requested",
            "response": "Compared two complete eligible directions and recommended A01.",
        },
    }


def _pending_draft(
    request: str,
    *,
    before: str = "Add team invitations without widening product scope.",
    after: str = (
        "Add team invitations with restart recovery as an explicit required outcome."
    ),
) -> dict:
    return {
        "schema_version": 1,
        "inherit_comparison": True,
        "frame_change_pending": {
            "request": request,
            "delta": {
                "requirements": [
                    {
                        "field": "project_intent",
                        "before": before,
                        "after": after,
                    }
                ],
                "criterion_weights": [],
                "hard_constraints": [],
                "driver_screen": [],
                "sources": [],
                "quality_attribute_scenarios": [],
                "decision_owner": None,
                "human_reason": "Recovery behavior changes the architecture comparison.",
            },
        },
    }


def _replace_string(value, before: str, after: str):
    if isinstance(value, dict):
        return {
            key: _replace_string(child, before, after)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_replace_string(child, before, after) for child in value]
    if value == before:
        return after
    return value


def _write_fixture(root: Path) -> tuple[Path, Path, dict, dict]:
    _, data = fixtures.build_artifact(root)
    draft_dir = root / "docs/plans/.drafts/smoke"
    draft_dir.mkdir(parents=True, exist_ok=True)
    frame = data["evaluation_frame"]
    exploration = {
        "schema_version": 1,
        "project_slug": data["project_slug"],
        "capability_revision": data["source_capability_revision"],
        "exploration_attempt": data["source_exploration_attempt"],
        "parent_gate_index": 2,
        "parent_gate_total": 8,
        "project_intent": frame["project_intent"],
        "non_goals": frame["non_goals"],
        "decision_owner": frame["decision_owner"],
        "architecture_applicability": frame["architecture_applicability"],
        "driver_screen": frame["driver_screen"],
        "accepted_decisions": frame["accepted_decisions"],
        "material_gaps": frame["material_gaps"],
        "capabilities": frame["capabilities"],
        "journeys": frame["journeys"],
        "hard_constraints": data["hard_constraints"],
        "quality_attribute_scenarios": frame["quality_attribute_scenarios"],
        "criteria": data["criteria"],
        "sources": data["sources"],
    }
    exploration_path = draft_dir / "architecture-exploration.json"
    exploration_path.write_text(
        json.dumps(exploration, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return (
        exploration_path,
        draft_dir / "architecture-options.md",
        data,
        _initial_draft(data),
    )


class ArchitectureWorkbenchContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (
            self.exploration,
            self.report,
            self.selection_fixture,
            self.draft,
        ) = _write_fixture(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def run_render(
        self,
        draft: dict,
        *,
        previous: bool = False,
        expected_previous_sha256: str | None = None,
    ) -> subprocess.CompletedProcess:
        command = [
            sys.executable,
            str(SCRIPT),
            "render",
            "--exploration",
            str(self.exploration),
            "--draft",
            "-",
            "--output",
            str(self.report),
            "--repo-root",
            str(self.root),
            "--json",
        ]
        if previous:
            expected = (
                expected_previous_sha256
                if expected_previous_sha256 is not None
                else hashlib.sha256(self.report.read_bytes()).hexdigest()
            )
            command.extend([
                "--previous-report",
                str(self.report),
                "--expected-previous-sha256",
                expected,
            ])
        return subprocess.run(
            command,
            input=json.dumps(draft),
            text=True,
            capture_output=True,
            check=False,
        )

    def run_resume(
        self,
        expected_report_sha256: str | None = None,
        *,
        recover_persisted: bool = False,
    ) -> subprocess.CompletedProcess:
        command = [
            sys.executable,
            str(SCRIPT),
            "resume-frame-change",
            "--report",
            str(self.report),
            "--repo-root",
            str(self.root),
        ]
        if recover_persisted:
            command.append("--recover-persisted")
        else:
            command.extend(
                ["--expected-report-sha256", expected_report_sha256 or ""]
            )
        command.append("--json")
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )

    @property
    def receipt(self) -> Path:
        return self.report.with_name(wb.FRAME_CHANGE_RECEIPT_NAME)

    def checkpoint_pending(
        self,
        request: str,
        pending_draft: dict | None = None,
    ) -> tuple[str, str, dict]:
        initial = self.run_render(self.draft)
        self.assertEqual(0, initial.returncode, initial.stdout + initial.stderr)
        h1 = hashlib.sha256(self.report.read_bytes()).hexdigest()
        pending_result = self.run_render(
            pending_draft or _pending_draft(request),
            previous=True,
            expected_previous_sha256=h1,
        )
        self.assertEqual(
            0,
            pending_result.returncode,
            pending_result.stdout + pending_result.stderr,
        )
        h2 = hashlib.sha256(self.report.read_bytes()).hexdigest()
        self.assertTrue(self.receipt.is_file())
        return h1, h2, json.loads(pending_result.stdout)

    def apply_requirement_delta(self, pending_draft: dict) -> None:
        exploration = json.loads(self.exploration.read_text(encoding="utf-8"))
        exploration["capability_revision"] += 1
        exploration["exploration_attempt"] += 1
        row = pending_draft["frame_change_pending"]["delta"]["requirements"][0]
        exploration[row["field"]] = copy.deepcopy(row["after"])
        self.exploration.write_text(
            json.dumps(exploration, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

    def frame_revision(self, request: str) -> dict:
        revision = copy.deepcopy(self.draft)
        revision["supersession_reasons"] = []
        revision["audit_event"] = {
            "event": "frame-change",
            "human_input": request,
            "response": "Applied the exact durable delta and recomputed every direction.",
        }
        return revision

    def test_template_exposes_semantic_contract_and_derived_fields(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "template", "--json"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertLessEqual(len(proc.stdout.encode("utf-8")), 4096)
        payload = json.loads(proc.stdout)
        self.assertEqual("pass", payload["status"])
        self.assertIn("option_prototype", payload["contract"])
        self.assertIn("repeat", payload["contract"]["options"])
        self.assertTrue(payload["inherit_revision_skeleton"]["inherit_comparison"])
        self.assertTrue(
            payload["frame_change_pending_revision_skeleton"][
                "inherit_comparison"
            ]
        )
        derived = " ".join(payload["contract"]["derived"])
        self.assertIn("weighted totals", derived)
        self.assertIn("hashes", derived)
        self.assertIn("awaiting-selection", derived)

    def test_initial_render_derives_lint_valid_report_and_checkpoint(self):
        proc = self.run_render(self.draft)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual("pass", payload["status"])
        self.assertEqual(1, payload["workbench_revision"])
        self.assertEqual(["A01", "A02"], payload["eligible_option_ids"])
        report_bytes = self.report.read_bytes()
        self.assertLessEqual(len(report_bytes), 25 * 1024)
        report_text = report_bytes.decode("utf-8")
        for duplicate_marker in (
            "**Exact constraint projection:**",
            "**Exact weighted-comparison projection:**",
            "### Constraint and Score Detail",
            "**Exact source projection:**",
        ):
            self.assertNotIn(duplicate_marker, report_text)
        self.assertEqual(
            hashlib.sha256(report_bytes).hexdigest(),
            payload["report_sha256"],
        )

        projection, report_failures = ol.validate_file(
            self.report, repo_root=self.root
        )
        self.assertEqual([], report_failures)
        self.assertNotIn("selection", projection)
        self.assertEqual(5, projection["options"][0]["weighted_score"])
        self.assertEqual(4, projection["options"][1]["weighted_score"])
        self.assertEqual(
            sl.option_hash(projection["options"][0]),
            projection["options"][0]["option_sha256"],
        )
        self.assertEqual(
            sl.option_set_hash(
                projection["options"], projection["eliminated_options"]
            ),
            projection["option_set_sha256"],
        )

        checkpoint = payload["result"]
        self.assertEqual(2, checkpoint["schema_version"])
        self.assertEqual(
            "awaiting-selection", checkpoint["selection"]["status"]
        )
        selection_path = self.report.with_name("architecture-selection.json")
        selection_path.write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _, incomplete_failures = sl.validate_file(
            selection_path,
            repo_root=self.root,
            allow_incomplete=True,
        )
        self.assertEqual([], incomplete_failures)
        _, active_failures = sl.validate_file(
            selection_path,
            repo_root=self.root,
        )
        self.assertTrue(active_failures)
        self.assertTrue(
            any("selection.status must be one of" in row for row in active_failures),
            active_failures,
        )

    def test_placeholder_decision_surface_cannot_enable_selection(self):
        cases = {
            "current_constraints": "TBD",
            "key_tradeoff": "unknown",
            "cost_if_wrong": "<cost if wrong>",
            "material_gaps_and_inferences": "{{ material gaps }}",
        }
        for field, placeholder in cases.items():
            with self.subTest(field=field, placeholder=placeholder):
                draft = copy.deepcopy(self.draft)
                draft["decision"][field] = placeholder
                proc = self.run_render(draft)
                self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertEqual("fail", payload["status"])
                self.assertNotIn("selection_enabled", payload)
                self.assertTrue(
                    any(
                        f"decision.{field}" in failure
                        and "placeholder" in failure
                        for failure in payload["hard_failures"]
                    ),
                    payload["hard_failures"],
                )
                self.assertFalse(self.report.exists())

    def test_question_revision_carries_exact_question_and_prior_hash(self):
        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        prior_hash = hashlib.sha256(self.report.read_bytes()).hexdigest()
        question = (
            "What evidence or changed constraint would make A02 preferable to A01?"
        )
        answer = (
            "A02 becomes preferable if durable isolation is source-backed and its "
            "migration and operability cost is accepted; current evidence does not."
        )
        revision = {
            "schema_version": 1,
            "inherit_comparison": True,
            "audit_event": {
                "event": "question",
                "human_input": question,
                "response": answer,
            },
        }
        second = self.run_render(revision, previous=True)
        self.assertEqual(0, second.returncode, second.stdout + second.stderr)
        payload = json.loads(second.stdout)
        self.assertEqual(2, payload["workbench_revision"])
        text = self.report.read_text(encoding="utf-8")
        self.assertIn("> Workbench revision: 2", text)
        self.assertIn(question, text)
        self.assertIn(answer, text)
        self.assertIn(prior_hash, text)
        _, failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertEqual([], failures)

    def test_multiline_audit_provenance_round_trips_exactly(self):
        initial_input = "Compare the current frame.\nKeep both credible alternatives."
        initial_response = "Compared A01 and A02.\rRecorded the trade-off."
        self.draft["audit_event"]["human_input"] = initial_input
        self.draft["audit_event"]["response"] = initial_response

        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        first_hash = hashlib.sha256(self.report.read_bytes()).hexdigest()
        _, _, first_audit, _, _, _, _, _ = wb._extract_previous(
            self.report,
            repo_root=self.root,
            expected_sha256=first_hash,
        )
        self.assertEqual(initial_input, first_audit[0][2])
        self.assertEqual(initial_response, first_audit[0][3])

        question = "What changes the recommendation?\r\nShow the evidence boundary."
        answer = "A load-bearing isolation target changes it.\nNo such target is recorded."
        revision = {
            "schema_version": 1,
            "inherit_comparison": True,
            "audit_event": {
                "event": "question",
                "human_input": question,
                "response": answer,
            },
        }
        second = self.run_render(revision, previous=True)
        self.assertEqual(0, second.returncode, second.stdout + second.stderr)
        _, _, audit, _, revision_number, _, _, _ = wb._extract_previous(
            self.report,
            repo_root=self.root,
            expected_sha256=hashlib.sha256(self.report.read_bytes()).hexdigest(),
        )
        self.assertEqual(2, revision_number)
        self.assertEqual(initial_input, audit[0][2])
        self.assertEqual(initial_response, audit[0][3])
        self.assertEqual(question, audit[1][2])
        self.assertEqual(answer, audit[1][3])

    def test_full_frame_revision_accepts_historical_report_and_archives_options(self):
        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        first_payload = json.loads(first.stdout)
        prior_hash = first_payload["report_sha256"]
        prior_options = {
            row["option_id"]: row for row in first_payload["result"]["options"]
        }

        old_source = self.root / "docs/briefs/smoke.md"
        new_source = self.root / "docs/briefs/refreshed.md"
        new_source.write_text(
            "# Refreshed frame\n\nIsolation is now a planning preference.\n",
            encoding="utf-8",
        )
        exploration = json.loads(self.exploration.read_text(encoding="utf-8"))
        exploration = _replace_string(
            exploration,
            "docs/briefs/smoke.md",
            "docs/briefs/refreshed.md",
        )
        exploration["sources"] = [{
            "path": "docs/briefs/refreshed.md",
            "sha256": hashlib.sha256(new_source.read_bytes()).hexdigest(),
            "kind": "brief",
        }]
        exploration["capability_revision"] = 2
        exploration["exploration_attempt"] = 2
        self.exploration.write_text(
            json.dumps(exploration, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        old_source.unlink()

        revision = _replace_string(
            copy.deepcopy(self.draft),
            "docs/briefs/smoke.md",
            "docs/briefs/refreshed.md",
        )
        revision["options"][0]["summary"] = (
            "Direction A01 recomputed against the refreshed planning frame."
        )
        revision["options"][1]["option_id"] = "A03"
        revision["options"][1]["title"] = "Replacement direction A03"
        revision["audit_event"] = {
            "event": "frame-change",
            "human_input": "Refresh the source boundary and replace A02.",
            "response": "Recomputed the comparison against capability revision 2.",
        }
        revision["supersession_reasons"] = [
            {
                "prior_option_id": "A01",
                "reason": "A01 was materially revised for the refreshed frame.",
            },
            {
                "prior_option_id": "A02",
                "reason": "A02 was removed and replaced by A03.",
            },
        ]
        second = self.run_render(
            revision,
            previous=True,
            expected_previous_sha256=prior_hash,
        )
        self.assertEqual(0, second.returncode, second.stdout + second.stderr)
        payload = json.loads(second.stdout)
        self.assertEqual(2, payload["workbench_revision"])
        text = self.report.read_text(encoding="utf-8")
        self.assertIn(prior_hash, text)
        self.assertIn("Independent invitation service", text)
        for option_id in ("A01", "A02"):
            prior = prior_options[option_id]
            self.assertIn(f"{option_id} — {prior['title']}", text)
            self.assertIn(prior["summary"], text)
            self.assertIn(prior["option_sha256"], text)
        self.assertIn("| superseded |", text)
        _, failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertEqual([], failures)

    def test_revision_rejects_a_tampered_expected_previous_hash(self):
        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        original = self.report.read_bytes()
        revision = {
            "schema_version": 1,
            "inherit_comparison": True,
            "audit_event": {
                "event": "question",
                "human_input": "Does the prior report still bind?",
                "response": "It must match the last displayed digest exactly.",
            },
        }
        proc = self.run_render(
            revision,
            previous=True,
            expected_previous_sha256="0" * 64,
        )
        self.assertEqual(1, proc.returncode)
        self.assertIn("does not match", proc.stdout)
        self.assertEqual(original, self.report.read_bytes())

    def test_markdown_payloads_are_inert_and_backslashes_round_trip(self):
        dangerous = (
            r"Windows C:\team\invites [link](https://invalid.example) "
            r"![image](https://invalid.example/x) `inline` *emphasis* "
            r"<img src=x onerror=alert(1)>"
        )
        self.draft["decision"]["key_tradeoff"] = dangerous
        self.draft["options"][0]["title"] = dangerous
        self.draft["options"][0]["responsibilities_and_boundaries"] = [dangerous]
        self.draft["options"][0]["scores"][0]["basis"] = dangerous
        self.draft["recommendation"]["basis"] = dangerous
        self.draft["uncarried_options"][0]["reason"] = dangerous
        self.draft["audit_event"]["response"] = dangerous

        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        text = self.report.read_text(encoding="utf-8")
        rendering_surface = sl._report_rendering_surface(text)
        self.assertNotRegex(
            rendering_surface,
            r"(?<!\\)!?\[[^\]\n]*\]\([^\)\n]*\)",
        )
        self.assertNotIn("<img", rendering_surface)
        self.assertIn(
            sl._normalized_report_text(dangerous),
            sl._normalized_report_text(text),
        )
        _, decision, _, uncarried, _, _, _, _ = wb._extract_previous(
            self.report,
            repo_root=self.root,
            expected_sha256=hashlib.sha256(self.report.read_bytes()).hexdigest(),
        )
        self.assertEqual(dangerous, decision["key_tradeoff"])
        self.assertEqual(dangerous, uncarried[0]["reason"])

        for revision_number in (2, 3):
            revision = {
                "schema_version": 1,
                "inherit_comparison": True,
                "audit_event": {
                    "event": "question",
                    "human_input": f"Revision {revision_number}: {dangerous}",
                    "response": dangerous,
                },
            }
            result = self.run_render(revision, previous=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        _, decision, audit, uncarried, revision, _, _, _ = wb._extract_previous(
            self.report,
            repo_root=self.root,
            expected_sha256=hashlib.sha256(self.report.read_bytes()).hexdigest(),
        )
        self.assertEqual(3, revision)
        self.assertEqual(dangerous, decision["key_tradeoff"])
        self.assertEqual(dangerous, uncarried[0]["reason"])
        self.assertEqual(dangerous, audit[-1][3])

    def test_pending_frame_change_survives_interruption_and_resumes_by_current_hash(self):
        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        selectable_hash_h1 = hashlib.sha256(self.report.read_bytes()).hexdigest()
        request = (
            "Add restart recovery to the decision frame.\r\n"
            "Then recompute every direction before selection."
        )

        pending_result = self.run_render(
            _pending_draft(request),
            previous=True,
            expected_previous_sha256=selectable_hash_h1,
        )
        self.assertEqual(
            0,
            pending_result.returncode,
            pending_result.stdout + pending_result.stderr,
        )
        pending_payload = json.loads(pending_result.stdout)
        self.assertEqual(
            "frame-change-pending", pending_payload["decision_status"]
        )
        self.assertFalse(pending_payload["selection_enabled"])
        self.assertEqual([], pending_payload["eligible_option_ids"])
        pending_hash_h2 = hashlib.sha256(self.report.read_bytes()).hexdigest()
        receipt = self.report.with_name(wb.FRAME_CHANGE_RECEIPT_NAME)
        self.assertTrue(receipt.is_file())
        self.assertNotEqual(selectable_hash_h1, pending_hash_h2)
        self.assertEqual(
            selectable_hash_h1,
            pending_payload["frame_change_pending"]["prior_report_sha256"],
        )

        _, default_failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertTrue(default_failures)
        self.assertTrue(
            any(
                "Decision status must equal `awaiting-selection`" in failure
                or "selectable architecture options report" in failure
                for failure in default_failures
            ),
            default_failures,
        )

        resumed = self.run_resume(pending_hash_h2)
        self.assertEqual(0, resumed.returncode, resumed.stdout + resumed.stderr)
        resume_payload = json.loads(resumed.stdout)
        self.assertEqual(
            selectable_hash_h1,
            resume_payload["selectable_prior_report_sha256"],
        )
        self.assertEqual(
            pending_hash_h2,
            resume_payload["pending_report_sha256"],
        )
        self.assertEqual(
            pending_hash_h2,
            resume_payload["next_expected_previous_sha256"],
        )
        self.assertEqual(
            request,
            resume_payload["frame_change_pending"]["request"],
        )

        pending_bytes = self.report.read_bytes()
        exploration = json.loads(self.exploration.read_text(encoding="utf-8"))
        exploration["capability_revision"] += 1
        exploration["exploration_attempt"] += 1
        exploration["project_intent"] = _pending_draft(request)[
            "frame_change_pending"
        ]["delta"]["requirements"][0]["after"]
        self.exploration.write_text(
            json.dumps(exploration, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

        revision = copy.deepcopy(self.draft)
        revision["supersession_reasons"] = []
        revision["audit_event"] = {
            "event": "frame-change",
            "human_input": request,
            "response": (
                "Applied the durable recovery delta and recomputed the comparison."
            ),
        }

        wrong_hash = self.run_render(
            revision,
            previous=True,
            expected_previous_sha256=selectable_hash_h1,
        )
        self.assertEqual(1, wrong_hash.returncode)
        self.assertIn("does not match", wrong_hash.stdout)
        self.assertEqual(pending_bytes, self.report.read_bytes())

        recomputed = self.run_render(
            revision,
            previous=True,
            expected_previous_sha256=pending_hash_h2,
        )
        self.assertEqual(
            0,
            recomputed.returncode,
            recomputed.stdout + recomputed.stderr,
        )
        recomputed_payload = json.loads(recomputed.stdout)
        self.assertEqual(
            "awaiting-selection", recomputed_payload["decision_status"]
        )
        self.assertEqual(3, recomputed_payload["workbench_revision"])
        self.assertFalse(receipt.exists())
        final_hash = hashlib.sha256(self.report.read_bytes()).hexdigest()
        (
            _,
            _,
            audit,
            _,
            revision_number,
            _,
            status,
            pending,
        ) = wb._extract_previous(
            self.report,
            repo_root=self.root,
            expected_sha256=final_hash,
        )
        self.assertEqual(3, revision_number)
        self.assertEqual("awaiting-selection", status)
        self.assertIsNone(pending)
        self.assertEqual(
            ["initial-synthesis", "frame-change-pending", "frame-change"],
            [row[1] for row in audit],
        )
        self.assertEqual(request, audit[1][2])
        self.assertEqual(selectable_hash_h1, audit[1][4])
        self.assertEqual(request, audit[2][2])
        self.assertEqual(pending_hash_h2, audit[2][4])
        _, final_failures = ol.validate_file(self.report, repo_root=self.root)
        self.assertEqual([], final_failures)

    def test_pending_delta_is_typed_and_every_exact_member_must_be_applied(self):
        request = "Apply every approved decision-frame adjustment exactly."
        exploration = json.loads(self.exploration.read_text(encoding="utf-8"))
        new_source_bytes = (
            b"# Updated frame\n\nRestart recovery is a required outcome.\n"
        )
        source_before = copy.deepcopy(exploration["sources"][0])
        source_after = {
            **source_before,
            "sha256": hashlib.sha256(new_source_bytes).hexdigest(),
        }
        constraint_before = copy.deepcopy(exploration["hard_constraints"][0])
        constraint_after = {
            **constraint_before,
            "statement": "Personal data remains in-region through restart recovery.",
        }
        driver_before = copy.deepcopy(exploration["driver_screen"][1])
        driver_after = {
            **driver_before,
            "basis": "Restart recovery now confirms this driver assessment.",
        }
        scenario_before = copy.deepcopy(
            exploration["quality_attribute_scenarios"][0]
        )
        scenario_after = {
            **scenario_before,
            "response": "Reject safely and preserve restart-recovery state.",
        }
        owner_before = copy.deepcopy(exploration["decision_owner"])
        owner_after = {
            "identity_or_role": "Platform Architecture Council",
            "authority_basis": (
                "Repository governance delegates this adjusted direction to "
                "the Platform Architecture Council."
            ),
        }
        intent_after = (
            "Add team invitations with explicit restart-recovery behavior."
        )
        pending = {
            "schema_version": 1,
            "inherit_comparison": True,
            "frame_change_pending": {
                "request": request,
                "delta": {
                    "requirements": [{
                        "field": "project_intent",
                        "before": exploration["project_intent"],
                        "after": intent_after,
                    }],
                    "criterion_weights": [
                        {
                            "criterion_id": exploration["criteria"][0]["id"],
                            "before": exploration["criteria"][0]["weight"],
                            "after": 0.20,
                        },
                        {
                            "criterion_id": exploration["criteria"][1]["id"],
                            "before": exploration["criteria"][1]["weight"],
                            "after": 0.25,
                        },
                    ],
                    "hard_constraints": [{
                        "constraint_id": constraint_before["id"],
                        "before": constraint_before,
                        "after": constraint_after,
                    }],
                    "driver_screen": [{
                        "driver_id": driver_before["id"],
                        "before": driver_before,
                        "after": driver_after,
                    }],
                    "sources": [{
                        "path": source_before["path"],
                        "before": source_before,
                        "after": source_after,
                    }],
                    "quality_attribute_scenarios": [{
                        "scenario_id": scenario_before["id"],
                        "before": scenario_before,
                        "after": scenario_after,
                    }],
                    "decision_owner": {
                        "before": owner_before,
                        "after": owner_after,
                    },
                    "human_reason": (
                        "Every member changes eligibility, ranking, evidence, "
                        "or human decision authority."
                    ),
                },
            },
        }
        _, h2, payload = self.checkpoint_pending(request, pending)
        self.assertEqual(
            pending["frame_change_pending"]["delta"],
            payload["frame_change_pending"]["delta"],
        )
        pending_bytes = self.report.read_bytes()
        receipt_bytes = self.receipt.read_bytes()

        unrelated = copy.deepcopy(exploration)
        unrelated["capability_revision"] += 1
        unrelated["exploration_attempt"] += 1
        unrelated["non_goals"].append("Unrequested mutation.")
        self.exploration.write_text(
            json.dumps(unrelated, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        rejected = self.run_render(
            self.frame_revision(request),
            previous=True,
            expected_previous_sha256=h2,
        )
        self.assertEqual(1, rejected.returncode)
        self.assertIn("every durable decision-frame delta member", rejected.stdout)
        self.assertIn("unrelated frame mutation", rejected.stdout)
        self.assertEqual(pending_bytes, self.report.read_bytes())
        self.assertEqual(receipt_bytes, self.receipt.read_bytes())

        applied = copy.deepcopy(exploration)
        applied["capability_revision"] += 1
        applied["exploration_attempt"] += 1
        applied["project_intent"] = intent_after
        for row in pending["frame_change_pending"]["delta"]["criterion_weights"]:
            for criterion in applied["criteria"]:
                if criterion["id"] == row["criterion_id"]:
                    criterion["weight"] = row["after"]
        applied["hard_constraints"][0] = constraint_after
        driver_ids_before = [row["id"] for row in applied["driver_screen"]]
        for index, driver in enumerate(applied["driver_screen"]):
            if driver["id"] == driver_after["id"]:
                applied["driver_screen"][index] = driver_after
        applied["sources"][0] = source_after
        applied["quality_attribute_scenarios"][0] = scenario_after
        applied["decision_owner"] = owner_after
        (self.root / source_after["path"]).write_bytes(new_source_bytes)
        self.exploration.write_text(
            json.dumps(applied, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        recomputed = self.run_render(
            self.frame_revision(request),
            previous=True,
            expected_previous_sha256=h2,
        )
        self.assertEqual(
            0,
            recomputed.returncode,
            recomputed.stdout + recomputed.stderr,
        )
        result = json.loads(recomputed.stdout)["result"]
        self.assertEqual(
            driver_ids_before,
            [
                row["id"]
                for row in result["evaluation_frame"]["driver_screen"]
            ],
        )
        self.assertEqual(list(sl.DRIVER_IDS), driver_ids_before)
        self.assertFalse(self.receipt.exists())

    def test_pending_delta_rejects_untyped_decision_owner(self):
        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        pending = _pending_draft("Change the decision owner.")
        pending["frame_change_pending"]["delta"]["requirements"] = []
        pending["frame_change_pending"]["delta"][
            "decision_owner"
        ] = "Platform Architecture Council"
        result = self.run_render(pending, previous=True)
        self.assertEqual(1, result.returncode)
        self.assertIn(
            "decision_owner must be null or an object with before and after",
            result.stdout,
        )

    def test_pending_post_replace_failure_restores_selectable_report_h1(self):
        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        selectable_bytes_h1 = self.report.read_bytes()
        selectable_hash_h1 = hashlib.sha256(selectable_bytes_h1).hexdigest()
        pending_path = self.root / "pending.json"
        pending_path.write_text(
            json.dumps(_pending_draft("Adjust the recovery requirement.")),
            encoding="utf-8",
        )
        args = SimpleNamespace(
            exploration=self.exploration,
            draft=str(pending_path),
            output=self.report,
            repo_root=self.root,
            previous_report=self.report,
            expected_previous_sha256=selectable_hash_h1,
        )
        real_validate = wb.sl.validate_document

        def fail_pending(data, **kwargs):
            selection = data.get("selection")
            if (
                isinstance(selection, dict)
                and selection.get("status") == "frame-change-pending"
            ):
                return ["injected pending checkpoint failure"]
            return real_validate(data, **kwargs)

        with mock.patch.object(wb.sl, "validate_document", side_effect=fail_pending):
            with self.assertRaisesRegex(
                wb.WorkbenchInputError,
                "injected pending checkpoint failure",
            ):
                wb._render_command(args)
        self.assertEqual(selectable_bytes_h1, self.report.read_bytes())
        self.assertFalse(self.receipt.exists())

    def test_recovery_discards_receipt_when_crash_precedes_h2_replace(self):
        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        h1_bytes = self.report.read_bytes()
        h1 = hashlib.sha256(h1_bytes).hexdigest()
        request = "Persist restart recovery before recomputing."
        pending_path = self.root / "pending.json"
        pending_path.write_text(
            json.dumps(_pending_draft(request)),
            encoding="utf-8",
        )
        args = SimpleNamespace(
            exploration=self.exploration,
            draft=str(pending_path),
            output=self.report,
            repo_root=self.root,
            previous_report=self.report,
            expected_previous_sha256=h1,
        )
        with mock.patch.object(
            wb,
            "_atomic_replace",
            side_effect=SystemExit("simulated crash before H2 replace"),
        ):
            with self.assertRaises(SystemExit):
                wb._render_command(args)
        self.assertEqual(h1_bytes, self.report.read_bytes())
        self.assertTrue(self.receipt.is_file())

        recovered = self.run_resume(recover_persisted=True)
        self.assertEqual(
            0,
            recovered.returncode,
            recovered.stdout + recovered.stderr,
        )
        payload = json.loads(recovered.stdout)
        self.assertEqual("prepared-receipt-discarded", payload["recovery_state"])
        self.assertEqual(h1, payload["report_sha256"])
        self.assertTrue(payload["selection_enabled"])
        self.assertFalse(self.receipt.exists())
        self.assertEqual(h1_bytes, self.report.read_bytes())

    def test_recovery_uses_independent_receipt_when_h2_stdout_was_lost(self):
        request = "Persist a restart-recovery adjustment."
        h1, h2, pending_payload = self.checkpoint_pending(request)

        # Treat the successful render response as lost; recovery starts only
        # from the independently persisted control receipt and report bytes.
        recovered = self.run_resume(recover_persisted=True)
        self.assertEqual(
            0,
            recovered.returncode,
            recovered.stdout + recovered.stderr,
        )
        payload = json.loads(recovered.stdout)
        self.assertEqual("persisted-pending-recovered", payload["recovery_state"])
        self.assertEqual(h1, payload["selectable_prior_report_sha256"])
        self.assertEqual(h2, payload["pending_report_sha256"])
        self.assertEqual(h2, payload["next_expected_previous_sha256"])
        self.assertEqual(
            pending_payload["frame_change_pending"]["delta"],
            payload["frame_change_pending"]["delta"],
        )
        self.assertTrue(self.receipt.exists())

    def test_recovery_never_self_trusts_h2_without_its_control_receipt(self):
        _, h2, _ = self.checkpoint_pending(
            "Persist a receipt-bound recovery adjustment."
        )
        self.receipt.unlink()
        recovered = self.run_resume(recover_persisted=True)
        self.assertEqual(2, recovered.returncode)
        self.assertIn("could not open frame-change control receipt", recovered.stdout)
        self.assertEqual(h2, hashlib.sha256(self.report.read_bytes()).hexdigest())

    def test_failed_recompute_restores_h2_and_retains_receipt(self):
        request = "Apply restart recovery before selection."
        pending = _pending_draft(request)
        _, h2, _ = self.checkpoint_pending(request, pending)
        h2_bytes = self.report.read_bytes()
        receipt_bytes = self.receipt.read_bytes()
        self.apply_requirement_delta(pending)
        revision_path = self.root / "revision.json"
        revision_path.write_text(
            json.dumps(self.frame_revision(request)),
            encoding="utf-8",
        )
        args = SimpleNamespace(
            exploration=self.exploration,
            draft=str(revision_path),
            output=self.report,
            repo_root=self.root,
            previous_report=self.report,
            expected_previous_sha256=h2,
        )
        with mock.patch.object(
            wb.ol,
            "validate_file",
            return_value=(None, ["injected H3 validation failure"]),
        ):
            with self.assertRaisesRegex(
                wb.WorkbenchInputError,
                "injected H3 validation failure",
            ):
                wb._render_command(args)
        self.assertEqual(h2_bytes, self.report.read_bytes())
        self.assertEqual(receipt_bytes, self.receipt.read_bytes())
        resumed = self.run_resume(h2)
        self.assertEqual(0, resumed.returncode, resumed.stdout + resumed.stderr)

    def test_recovery_consumes_stale_receipt_after_validated_h3(self):
        request = "Apply restart recovery and recompute the comparison."
        pending = _pending_draft(request)
        h1, h2, _ = self.checkpoint_pending(request, pending)
        self.apply_requirement_delta(pending)
        revision_path = self.root / "revision.json"
        revision_path.write_text(
            json.dumps(self.frame_revision(request)),
            encoding="utf-8",
        )
        args = SimpleNamespace(
            exploration=self.exploration,
            draft=str(revision_path),
            output=self.report,
            repo_root=self.root,
            previous_report=self.report,
            expected_previous_sha256=h2,
        )
        with mock.patch.object(
            wb,
            "_remove_frame_change_receipt",
            side_effect=wb.WorkbenchIOError(
                "simulated cleanup failure before receipt removal"
            ),
        ):
            with self.assertRaises(wb.WorkbenchIOError):
                wb._render_command(args)
        h3 = hashlib.sha256(self.report.read_bytes()).hexdigest()
        self.assertNotIn(h3, {h1, h2})
        self.assertTrue(self.receipt.is_file())

        recovered = self.run_resume(recover_persisted=True)
        self.assertEqual(
            0,
            recovered.returncode,
            recovered.stdout + recovered.stderr,
        )
        payload = json.loads(recovered.stdout)
        self.assertEqual(
            "validated-h3-receipt-consumed",
            payload["recovery_state"],
        )
        self.assertEqual(h3, payload["report_sha256"])
        self.assertEqual(h2, payload["pending_report_sha256"])
        self.assertTrue(payload["selection_enabled"])
        self.assertFalse(self.receipt.exists())

    def test_pending_checkpoint_preserves_preexisting_receipt_symlink(self):
        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        h1 = hashlib.sha256(self.report.read_bytes()).hexdigest()
        target = self.root / "untrusted-control.json"
        target.write_text('{"do_not_overwrite": true}\\n', encoding="utf-8")
        self.receipt.symlink_to(target)

        pending = self.run_render(
            _pending_draft("Do not overwrite an existing receipt."),
            previous=True,
            expected_previous_sha256=h1,
        )
        self.assertEqual(1, pending.returncode)
        self.assertIn("control receipt already exists", pending.stdout)
        self.assertTrue(self.receipt.is_symlink())
        self.assertEqual('{"do_not_overwrite": true}\\n', target.read_text())

    def test_unknown_score_evidence_is_low_confidence_and_explicit(self):
        for score in self.draft["options"][1]["scores"]:
            score["evidence_state"] = "unknown"
            score["evidence"] = [
                "unknown: option tactic has not been validated in this repository"
            ]
        missing_disclosure = self.run_render(self.draft)
        self.assertEqual(1, missing_disclosure.returncode)
        self.assertIn(
            "rank-changing unknown score evidence must be explicit",
            missing_disclosure.stdout,
        )
        self.assertFalse(self.report.exists())

        self.draft["decision"]["material_gaps_and_inferences"] = (
            "Unknown validation evidence for A02 can change the ranking; gather "
            "evidence or park before accepting the cost if wrong."
        )
        rendered = self.run_render(self.draft)
        self.assertEqual(0, rendered.returncode, rendered.stdout + rendered.stderr)
        payload = json.loads(rendered.stdout)
        by_id = {
            option["option_id"]: option for option in payload["result"]["options"]
        }
        self.assertEqual("low", by_id["A02"]["confidence"])
        self.assertEqual("low", payload["result"]["recommendation"]["confidence"])
        self.assertEqual(
            "unstable", payload["result"]["recommendation"]["sensitivity"]
        )
        self.assertIsNotNone(
            payload["result"]["recommendation"]["sensitivity_witness"]
        )

    def test_initial_post_replace_failure_removes_the_new_output(self):
        draft_path = self.root / "semantic-draft.json"
        draft_path.write_text(json.dumps(self.draft), encoding="utf-8")
        args = SimpleNamespace(
            exploration=self.exploration,
            draft=str(draft_path),
            output=self.report,
            repo_root=self.root,
            previous_report=None,
            expected_previous_sha256=None,
        )
        with mock.patch.object(
            wb.ol,
            "validate_file",
            side_effect=RuntimeError("injected post-replace failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "post-replace"):
                wb._render_command(args)
        self.assertFalse(self.report.exists())

    def test_awaiting_selection_requires_the_complete_valid_comparison(self):
        proc = self.run_render(self.draft)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        checkpoint = json.loads(proc.stdout)["result"]
        selection_path = self.report.with_name("architecture-selection.json")

        missing_options = copy.deepcopy(checkpoint)
        del missing_options["options"]
        selection_path.write_text(
            json.dumps(missing_options, indent=2) + "\n", encoding="utf-8"
        )
        _, failures = sl.validate_file(
            selection_path,
            repo_root=self.root,
            allow_incomplete=True,
        )
        self.assertTrue(any("missing key(s): options" in row for row in failures))

        invalid_ranking = copy.deepcopy(checkpoint)
        invalid_ranking["recommendation"]["option_id"] = "A02"
        selection_path.write_text(
            json.dumps(invalid_ranking, indent=2) + "\n", encoding="utf-8"
        )
        _, failures = sl.validate_file(
            selection_path,
            repo_root=self.root,
            allow_incomplete=True,
        )
        self.assertTrue(
            any("highest weighted-score" in row for row in failures),
            failures,
        )

        reportless = copy.deepcopy(checkpoint)
        reportless["architecture_options_report"] = {
            "schema_version": 1,
            "status": "not-produced",
            "path": None,
            "sha256": None,
            "reason": "No report.",
        }
        selection_path.write_text(
            json.dumps(reportless, indent=2) + "\n", encoding="utf-8"
        )
        _, failures = sl.validate_file(
            selection_path,
            repo_root=self.root,
            allow_incomplete=True,
        )
        self.assertTrue(
            any("awaiting-selection requires a present" in row for row in failures),
            failures,
        )

    def test_invalid_recommendation_fails_without_writing_report(self):
        self.draft["recommendation"]["option_id"] = "A02"
        proc = self.run_render(self.draft)
        self.assertEqual(1, proc.returncode)
        payload = json.loads(proc.stdout)
        self.assertEqual("fail", payload["status"])
        self.assertTrue(
            any("highest weighted-score" in row for row in payload["hard_failures"])
        )
        self.assertFalse(self.report.exists())

    def test_semantic_input_cannot_fabricate_superseded_history(self):
        self.draft["uncarried_options"][0]["disposition"] = "superseded"
        proc = self.run_render(self.draft)
        self.assertEqual(1, proc.returncode)
        payload = json.loads(proc.stdout)
        self.assertEqual("fail", payload["status"])
        self.assertIn(
            "uncarried_options[0].disposition must be "
            "`dominance-pruned` or `uncarried`",
            payload["hard_failures"],
        )
        self.assertFalse(self.report.exists())

    def test_failed_revision_restores_the_exact_previous_report(self):
        first = self.run_render(self.draft)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        original = self.report.read_bytes()
        invalid = {
            "schema_version": 1,
            "inherit_comparison": True,
            "audit_event": {
                "event": "initial-synthesis",
                "human_input": "This is not a valid revision event.",
                "response": "The prior report must remain unchanged.",
            },
        }
        proc = self.run_render(invalid, previous=True)
        self.assertEqual(1, proc.returncode)
        self.assertEqual(original, self.report.read_bytes())

    def test_output_symlink_is_rejected_without_following_it(self):
        outside = self.root / "outside.md"
        outside.write_text("unchanged\n", encoding="utf-8")
        self.report.symlink_to(outside)
        proc = self.run_render(self.draft)
        self.assertEqual(2, proc.returncode)
        self.assertEqual("unchanged\n", outside.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
