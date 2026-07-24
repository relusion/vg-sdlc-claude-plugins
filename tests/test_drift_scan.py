#!/usr/bin/env python3
"""Tests for scripts/drift_scan.py — the post-merge drift engine.

A clean multi-feature plan fixture is seeded, then each HARD finding class is
mutation-tested red (the fixture doubles as a drifted-plan fixture): plan-lint
FAIL, spec-lint FAIL, a disarmed H5 security gate, an orphan spec, a phantom
[SECURITY: TZ-NNN], and a two-way registry break. The two ADVISORY classes
(retired-surface residue, spec-claimed-file drift) are proven not to change the
exit code, --advisory-only is proven to force exit 0, and a git-materialization
test proves the scan judges COMMITTED state (an uncommitted edit is invisible).

Runs the script as a subprocess so the real 0/1/2 exit contract and the stable
JSON shape are what is asserted.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DRIFT_SCAN = REPO_ROOT / "scripts" / "drift_scan.py"
SELECTION_LINT = (
    REPO_ROOT
    / "plugins/core-engineering/skills/ce-plan-audit/scripts"
    / "architecture-selection-lint.py"
)

_selection_spec = importlib.util.spec_from_file_location(
    "architecture_selection_lint_for_drift_tests",
    SELECTION_LINT,
)
assert _selection_spec is not None and _selection_spec.loader is not None
selection_lint = importlib.util.module_from_spec(_selection_spec)
_selection_spec.loader.exec_module(selection_lint)


# --- the clean fixture ------------------------------------------------------

def not_applicable_selection(architecture_input: str) -> dict:
    """Current-schema human disposition for a feature-local plan."""
    source_path = "docs/plans/acme/architecture-input.md"
    sources = [{
        "path": source_path,
        "sha256": hashlib.sha256(architecture_input.encode("utf-8")).hexdigest(),
        "kind": "planning-input",
    }]
    criteria = [
        {
            "id": criterion,
            "weight": weight,
            "basis": f"Confirmed priority for {criterion}.",
        }
        for criterion, weight in zip(
            selection_lint.CRITERIA,
            (0.25, 0.20, 0.15, 0.15, 0.15, 0.10),
        )
    ]
    data = {
        "schema_version": 2,
        "project_slug": "acme",
        "exploration_id": "AEX-not-applicable-r1",
        "source_capability_revision": 1,
        "source_exploration_attempt": 1,
        "source_input_sha256": "0" * 64,
        "evaluation_frame": {
            "project_intent": "Deliver the two bounded Acme features in the existing application.",
            "non_goals": ["Introduce a new platform, runtime, or shared protocol."],
            "decision_owner": {
                "identity_or_role": "Repository Architecture Owner",
                "authority_basis": (
                    "This test fixture assigns architecture applicability "
                    "approval to the repository architecture owner."
                ),
            },
            "architecture_applicability": "not-required",
            "driver_screen": [
                {
                    "id": driver_id,
                    "verdict": "negative",
                    "basis": f"No {driver_id} architecture driver applies to this fixture.",
                    "evidence": [source_path],
                }
                for driver_id in selection_lint.DRIVER_IDS
            ],
            "accepted_decisions": [],
            "material_gaps": [],
            "capabilities": [
                {
                    "id": "C01",
                    "outcome": "An administrator can invite a user.",
                    "actors": ["administrator", "invitee"],
                    "data": ["invitation"],
                    "integrations": ["existing application"],
                    "observable": "An invitation can be created.",
                },
                {
                    "id": "C02",
                    "outcome": "An administrator can list invitations.",
                    "actors": ["administrator"],
                    "data": ["invitation"],
                    "integrations": ["existing application"],
                    "observable": "Pending invitations are listed.",
                },
            ],
            "journeys": [
                {
                    "id": "J01",
                    "outcome": "An administrator manages team invitations.",
                    "actors": ["administrator"],
                    "capability_refs": ["C01", "C02"],
                    "steps": ["Create an invitation.", "List pending invitations."],
                    "observable": "The invitation is visible in the pending list.",
                }
            ],
            "quality_attribute_scenarios": [],
        },
        "blocking_decision": None,
        "sources": sources,
        "evidence_fingerprint": selection_lint.canonical_sha256(sources),
        "criteria": criteria,
        "hard_constraints": [],
        "options": [],
        "eliminated_options": [],
        "option_set_sha256": selection_lint.option_set_hash([], []),
        "recommendation": {
            "option_id": None,
            "confidence": "high",
            "sensitivity": "not-applicable",
            "sensitivity_witness": None,
            "basis": "Every canonical architecture driver is negative for this fixture.",
        },
        "architecture_options_report": {
            "schema_version": 1,
            "status": "not-produced",
            "path": None,
            "sha256": None,
            "reason": "Architecture applicability is not-required.",
        },
        "selection": {
            "status": "not-applicable",
            "option_id": None,
            "option_sha256": None,
            "decided_by": "human",
            "approved_by": None,
            "rationale": "The human confirmed that feature-local planning is sufficient.",
        },
        "next_owner": "ce-plan",
    }
    data["source_input_sha256"] = selection_lint.source_input_hash(data)
    return data


def clean_fixture() -> dict[str, str]:
    """A well-formed, drift-free two-feature plan. drift_scan must PASS it."""
    tasks_foo = {
        "feature_id": "01-foo",
        "tasks": [
            {"id": "T-1", "verifies": ["TC-1"], "files": ["src/foo.py"], "status": "done"},
            {"id": "T-2", "verifies": ["TC-2"], "files": ["src/foo.py"], "status": "done"},
        ],
    }
    tasks_bar = {
        "feature_id": "02-bar",
        "tasks": [
            {"id": "T-1", "verifies": ["TC-1"], "files": ["src/bar.py"], "status": "done"},
        ],
    }
    spec_foo = (
        "# Spec: 01-foo — Invite a user\n\n"
        "## 5. Acceptance Criteria\n\n"
        "### AC-1 [SECURITY: TZ-001] Only admins may invite\n\n"
        "Admin-only creation.\n\n"
        "## 6. Test Cases\n\n"
        "### TC-1 (proves AC-1)\n\n"
        "modality: http\nverification: auto\n\n"
        "### TC-2 (proves AC-1)\n\n"
        "modality: manual\nverification: manual:judgment\n\n"
        "## 6b. Tasks\n\n"
        "### T-1\n\nImplement the admin check.\n\n"
        "### T-2\n\nImplement listing.\n\n"
        "## 7. Traceability\n\n"
        "| Task | TC | AC |\n|---|---|---|\n"
        "| T-1 | TC-1 | AC-1 |\n| T-2 | TC-2 | AC-1 |\n"
    )
    spec_bar = (
        "# Spec: 02-bar — List invitations\n\n"
        "## 5. Acceptance Criteria\n\n"
        "### AC-1 Pending invitations are listed\n\n"
        "## 6. Test Cases\n\n"
        "### TC-1 (proves AC-1)\n\n"
        "modality: cli\nverification: auto\n\n"
        "## 6b. Tasks\n\n"
        "### T-1\n\nImplement listing.\n\n"
        "## 7. Traceability\n\n"
        "| Task | TC | AC |\n|---|---|---|\n| T-1 | TC-1 | AC-1 |\n"
    )
    threat_model = (
        "# Threat Model\n\n"
        "security_obligations:\n"
        "  - feature: 01-foo\n"
        "    threat_ids: [TZ-001]\n\n"
        "## TZ-001 — Admin-only invite\n\n"
        "Only admins may create invitations.\n"
    )
    feature_plan = (
        "# Acme\n\n## Features\n\n"
        "| ID | Title |\n|---|---|\n| 01-foo | Foo |\n| 02-bar | Bar |\n"
    )
    architecture_input = (
        "# Architecture Applicability\n\n"
        "Both features remain within the existing application boundary.\n"
    )
    selection = not_applicable_selection(architecture_input)
    selection_json = json.dumps(selection, indent=2)
    plan_json = {
        "project_slug": "acme",
        "status": "planned",
        "plan_revision": 1,
        "plan_tier": "standard",
        "architecture_disposition": {
            "decision": "not-required",
            "triggers": [],
            "rationale": "The bounded fixture introduces no architecture driver.",
            "decided_by": "human",
            "convergence": {
                "status": "not-applicable",
                "iteration_count": 0,
                "summary": "Architecture shaping is not applicable to this fixture.",
                "decision_refs": [],
            },
            "direction": {
                "status": "not-applicable",
                "artifact": "architecture-selection.json",
                "artifact_sha256": hashlib.sha256(
                    selection_json.encode("utf-8")
                ).hexdigest(),
                "exploration_id": selection["exploration_id"],
                "selected_option_id": None,
                "selected_option_sha256": None,
                "decided_by": "human",
                "summary": "The human confirmed that no direction selection is needed.",
            },
        },
        "relates_to": [],
        "features": [
            {"id": "01-foo", "title": "Foo", "file": "features/01-foo.md",
             "type": "foundation", "final_complexity": "Simple",
             "specification_route": "explicit", "risk_profile": "low", "ship_order": 1,
             "dependencies": {"hard": [], "soft": []}},
            {"id": "02-bar", "title": "Bar", "file": "features/02-bar.md",
             "type": "user-facing", "final_complexity": "Moderate",
             "specification_route": "compact", "risk_profile": "low", "ship_order": 2,
             "dependencies": {"hard": ["01-foo"], "soft": []}},
        ],
    }
    interaction = "# Interaction Contract\n\n## No Cross-Feature Protocol\n"

    return {
        "docs/plans/plans.json": json.dumps(
            {"plans": [{"slug": "acme", "description": "Acme", "relates_to": []}]},
            indent=2),
        "docs/plans/acme/plan.json": json.dumps(plan_json, indent=2),
        "docs/plans/acme/architecture-selection.json": selection_json,
        "docs/plans/acme/architecture-input.md": architecture_input,
        "docs/plans/acme/feature-plan.md": feature_plan,
        "docs/plans/acme/threat-model.md": threat_model,
        "docs/plans/acme/interaction-contract.md": interaction,
        "docs/plans/acme/features/01-foo.md": (
            "# 01-foo — Foo\n\n**Specification route:** explicit\n\n"
            "## Scope\n- Admin invites.\n"
        ),
        "docs/plans/acme/features/02-bar.md": (
            "# 02-bar — Bar\n\n**Specification route:** compact\n\n"
            "## Scope\n- List invites.\n"
        ),
        "docs/plans/acme/specs/01-foo/ce-spec.md": spec_foo,
        "docs/plans/acme/specs/01-foo/tasks.json": json.dumps(tasks_foo, indent=2),
        "docs/plans/acme/specs/02-bar/ce-spec.md": spec_bar,
        "docs/plans/acme/specs/02-bar/tasks.json": json.dumps(tasks_bar, indent=2),
        "src/foo.py": "def invite():\n    return True\n",
        "src/bar.py": "def list_invites():\n    return []\n",
    }


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def run_scan(repo: Path, *extra: str) -> tuple[int, dict]:
    """Run drift_scan --json over `repo`; return (exit_code, parsed_json)."""
    proc = subprocess.run(
        [sys.executable, str(DRIFT_SCAN), "--repo", str(repo), "--json", *extra],
        capture_output=True, text=True, timeout=180)
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = {"_raw_stdout": proc.stdout, "_stderr": proc.stderr}
    return proc.returncode, data


def hard_codes(data: dict) -> list[str]:
    return [f["code"] for f in data.get("hard", [])]


def advisory_codes(data: dict) -> list[str]:
    return [f["code"] for f in data.get("advisory", [])]


class DriftScanBase(unittest.TestCase):
    def make_repo(self, files: dict[str, str]) -> Path:
        d = Path(tempfile.mkdtemp(prefix="drift-test-"))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        write_tree(d, files)
        return d

    def mutate(self, **changes) -> dict[str, str]:
        """A deep copy of the clean fixture with per-file overrides applied.
        Pass path->content to add/replace; use `_remove` for a list of paths."""
        files = copy.deepcopy(clean_fixture())
        remove = changes.pop("_remove", [])
        for path in remove:
            files.pop(path, None)
        files.update(changes)
        return files


# --- clean baseline ---------------------------------------------------------

class TestClean(DriftScanBase):
    def test_clean_fixture_passes_worktree(self):
        repo = self.make_repo(clean_fixture())
        code, data = run_scan(repo, "--worktree")
        self.assertEqual(code, 0, data)
        self.assertEqual(data["status"], "pass", data)
        self.assertEqual(data["hard"], [], data)
        self.assertEqual(data["advisory"], [], data)
        self.assertEqual(data["plans_scanned"], 1)
        self.assertEqual(data["specs_scanned"], 2)

    def test_no_plans_registered_is_pass(self):
        repo = self.make_repo({"README.md": "# empty\n"})
        code, data = run_scan(repo, "--worktree")
        self.assertEqual(code, 0, data)
        self.assertEqual(data["status"], "pass")
        self.assertTrue(any("no docs/plans" in n for n in data["notes"]), data)


# --- hard finding classes (each mutation-tested red) ------------------------

class TestHardClasses(DriftScanBase):
    def _assert_hard(self, files, code_name, needle):
        repo = self.make_repo(files)
        code, data = run_scan(repo, "--worktree")
        self.assertEqual(code, 1, data)
        self.assertEqual(data["status"], "drift", data)
        self.assertIn(code_name, hard_codes(data), data)
        finding = next(f for f in data["hard"] if f["code"] == code_name)
        self.assertIn(needle, finding["message"], finding)
        return data, finding

    def test_plan_lint_fail_is_boundary_lock_drift(self):
        # A plan.json-claimed feature file goes missing -> plan-lint H1 FAIL.
        files = self.mutate(_remove=["docs/plans/acme/features/02-bar.md"])
        _data, f = self._assert_hard(files, "plan_lint_fail", "Scope Lock drift")
        self.assertEqual(f["route"], "/core-engineering:ce-plan")
        self.assertEqual(f["lock"], "Scope Lock")

    def test_missing_plan_json_is_hard_drift(self):
        files = self.mutate(_remove=["docs/plans/acme/plan.json"])
        _data, f = self._assert_hard(
            files,
            "plan_lint_fail",
            "plan-lint could not evaluate",
        )
        self.assertEqual(f["route"], "/core-engineering:ce-plan")
        self.assertNotIn("minimal", f["message"].lower())

    def test_spec_lint_fail_is_spec_lock_drift(self):
        # A task verifies a TC that does not exist -> spec-lint H1 FAIL.
        bad = json.loads(clean_fixture()["docs/plans/acme/specs/01-foo/tasks.json"])
        bad["tasks"][0]["verifies"] = ["TC-9"]
        files = self.mutate(**{
            "docs/plans/acme/specs/01-foo/tasks.json": json.dumps(bad, indent=2)})
        _data, f = self._assert_hard(files, "spec_lint_fail", "Scope Lock drift")
        self.assertEqual(f["route"], "/core-engineering:ce-spec")

    def test_h5_disarmed_when_obligation_declared_but_gate_off(self):
        # tasks.feature_id drifts from the plan id -> spec-lint's H5 auto-lookup
        # misses the obligation and reports `disarmed`, though the threat-model
        # still assigns TZ-001 to 01-foo.
        drifted = json.loads(clean_fixture()["docs/plans/acme/specs/01-foo/tasks.json"])
        drifted["feature_id"] = "01-foo-renamed"
        files = self.mutate(**{
            "docs/plans/acme/specs/01-foo/tasks.json": json.dumps(drifted, indent=2)})
        _data, f = self._assert_hard(
            files, "h5_disarmed", "threat-model coverage disarmed — H5 no longer runs for 01-foo")
        self.assertEqual(f["route"], "/core-engineering:ce-spec")

    def test_orphan_spec_dir(self):
        # A spec dir whose id is in no plan.json feature.
        ghost_spec = (
            "# Spec: 99-ghost\n\n## 5. Acceptance Criteria\n\n### AC-1 does a thing\n\n"
            "## 6. Test Cases\n\n### TC-1 (proves AC-1)\n\nmodality: cli\nverification: auto\n\n"
            "## 6b. Tasks\n\n### T-1\n\n## 7. Traceability\n\n"
            "| Task | TC | AC |\n|---|---|---|\n| T-1 | TC-1 | AC-1 |\n")
        ghost_tasks = {"feature_id": "99-ghost",
                       "tasks": [{"id": "T-1", "verifies": ["TC-1"],
                                  "files": ["src/ghost.py"], "status": "done"}]}
        files = self.mutate(**{
            "docs/plans/acme/specs/99-ghost/ce-spec.md": ghost_spec,
            "docs/plans/acme/specs/99-ghost/tasks.json": json.dumps(ghost_tasks, indent=2),
            "src/ghost.py": "x = 1\n"})
        _data, f = self._assert_hard(files, "orphan_spec", "resolves to no feature")
        self.assertEqual(f["route"], "/core-engineering:ce-plan")

    def test_phantom_threat_id(self):
        # A spec cites a [SECURITY: TZ-NNN] the threat-model never defines.
        spec = clean_fixture()["docs/plans/acme/specs/02-bar/ce-spec.md"].replace(
            "### AC-1 Pending invitations are listed",
            "### AC-1 [SECURITY: TZ-777] Pending invitations are listed")
        files = self.mutate(**{"docs/plans/acme/specs/02-bar/ce-spec.md": spec})
        _data, f = self._assert_hard(files, "phantom_threat_id", "TZ-777")
        self.assertEqual(f["route"], "/core-engineering:ce-spec")

    def test_registry_break_entry_without_dir(self):
        reg = {"plans": [{"slug": "acme"}, {"slug": "extra"}]}
        files = self.mutate(**{"docs/plans/plans.json": json.dumps(reg, indent=2)})
        _data, f = self._assert_hard(files, "registry_break", "extra")
        self.assertIn("does not exist", f["message"])

    def test_registry_break_dir_without_entry(self):
        files = self.mutate(**{"docs/plans/orphanplan/plan.json": "{}\n"})
        _data, f = self._assert_hard(files, "registry_break", "unregistered")


# --- advisory classes (never change the exit code) --------------------------

class TestAdvisoryClasses(DriftScanBase):
    def test_surface_residue_is_advisory(self):
        # A deprecate+removed_by surface whose removing feature is done, yet the
        # surface string still appears elsewhere in the repo.
        fp = (clean_fixture()["docs/plans/acme/feature-plan.md"]
              + "\n## Surface-Removal Closure\n\n"
              "| Surface | Break-class | continuity |\n|---|---|---|\n"
              "| /old/invite | contract-break | deprecate:2 releases,removed_by:02-bar |\n")
        files = self.mutate(**{
            "docs/plans/acme/feature-plan.md": fp,
            "src/legacy.py": "ROUTE = '/old/invite'\n"})
        repo = self.make_repo(files)
        code, data = run_scan(repo, "--worktree")
        self.assertEqual(code, 0, data)  # advisory never changes the exit code
        self.assertIn("surface_residue", advisory_codes(data), data)
        f = next(x for x in data["advisory"] if x["code"] == "surface_residue")
        self.assertIn("src/legacy.py", f["message"])
        self.assertIn("Scope Lock drift (advisory)", f["message"])

    def test_surface_residue_skipped_when_feature_not_done(self):
        # Same residue, but the removing feature's tasks are NOT done -> no
        # advisory (removal not yet due).
        undone = json.loads(clean_fixture()["docs/plans/acme/specs/02-bar/tasks.json"])
        undone["tasks"][0]["status"] = "todo"
        fp = (clean_fixture()["docs/plans/acme/feature-plan.md"]
              + "\n## Surface-Removal Closure\n\n"
              "| Surface | Break-class | continuity |\n|---|---|---|\n"
              "| /old/invite | contract-break | deprecate:2 releases,removed_by:02-bar |\n")
        files = self.mutate(**{
            "docs/plans/acme/feature-plan.md": fp,
            "docs/plans/acme/specs/02-bar/tasks.json": json.dumps(undone, indent=2),
            "src/legacy.py": "ROUTE = '/old/invite'\n"})
        repo = self.make_repo(files)
        code, data = run_scan(repo, "--worktree")
        self.assertEqual(code, 0, data)
        self.assertNotIn("surface_residue", advisory_codes(data), data)

    def test_claimed_file_missing_is_advisory(self):
        bad = json.loads(clean_fixture()["docs/plans/acme/specs/01-foo/tasks.json"])
        bad["tasks"][0]["files"] = ["src/gone.py"]
        files = self.mutate(**{
            "docs/plans/acme/specs/01-foo/tasks.json": json.dumps(bad, indent=2)})
        repo = self.make_repo(files)
        code, data = run_scan(repo, "--worktree")
        self.assertEqual(code, 0, data)
        self.assertIn("claimed_file_missing", advisory_codes(data), data)
        f = next(x for x in data["advisory"] if x["code"] == "claimed_file_missing")
        self.assertIn("src/gone.py", f["message"])
        self.assertIn("Scope Lock drift (advisory)", f["message"])


# --- --advisory-only + exit contract ----------------------------------------

class TestExitContract(DriftScanBase):
    def test_advisory_only_forces_exit_zero_but_reports_hard(self):
        files = self.mutate(_remove=["docs/plans/acme/features/02-bar.md"])
        repo = self.make_repo(files)
        code, data = run_scan(repo, "--worktree", "--advisory-only")
        self.assertEqual(code, 0, data)
        self.assertTrue(data["advisory_only"])
        self.assertIn("plan_lint_fail", hard_codes(data), data)  # still reported

    def test_missing_repo_is_error_exit_2(self):
        code, data = run_scan(Path("/no/such/repo/xyz"), "--worktree")
        self.assertEqual(code, 2, data)
        self.assertEqual(data.get("status"), "error")

    def test_bad_plans_json_is_error_exit_2(self):
        files = self.mutate(**{"docs/plans/plans.json": "{ not json"})
        repo = self.make_repo(files)
        code, data = run_scan(repo, "--worktree")
        self.assertEqual(code, 2, data)

    def test_missing_lint_script_is_error_exit_2(self):
        repo = self.make_repo(clean_fixture())
        proc = subprocess.run(
            [sys.executable, str(DRIFT_SCAN), "--repo", str(repo), "--worktree",
             "--json", "--plan-lint", "/no/such/plan-lint.py"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)


# --- committed-state judging (git materialization) --------------------------

@unittest.skipIf(shutil.which("git") is None, "git not available")
class TestCommittedState(DriftScanBase):
    def _git(self, repo: Path, *args: str):
        env = dict(os.environ,
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        proc = subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def test_head_mode_ignores_uncommitted_break(self):
        repo = self.make_repo(clean_fixture())
        self._git(repo, "init", "-q")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-q", "-m", "clean plan")

        # Default (HEAD) mode over the clean commit -> PASS.
        code, data = run_scan(repo)
        self.assertEqual(code, 0, data)
        self.assertIsNotNone(data["head_sha"])
        self.assertFalse(data["worktree"])

        # Break a plan file in the WORKING TREE only (do not commit).
        (repo / "docs/plans/acme/features/02-bar.md").unlink()

        # HEAD mode still PASSES (judges committed state, not the dirty tree)...
        code, data = run_scan(repo)
        self.assertEqual(code, 0, data)
        # ...while --worktree SEES the uncommitted break.
        code_wt, data_wt = run_scan(repo, "--worktree")
        self.assertEqual(code_wt, 1, data_wt)
        self.assertIn("plan_lint_fail", hard_codes(data_wt))

        # Once committed, HEAD mode goes red too.
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-q", "-m", "break plan")
        code2, data2 = run_scan(repo)
        self.assertEqual(code2, 1, data2)
        self.assertIn("plan_lint_fail", hard_codes(data2))


if __name__ == "__main__":
    unittest.main()
