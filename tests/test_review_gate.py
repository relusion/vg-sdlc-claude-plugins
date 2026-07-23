"""Behavioral contract tests for current, provenance-bound review evidence."""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-review/scripts/review-gate.py"
HELPER = (
    REPO
    / "plugins/core-engineering/skills/ce-review/scripts/architecture_context.py"
)
AUTO_COPY = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/review-gate.py"
AUTO_HELPER = (
    REPO
    / "plugins/core-engineering/skills/ce-auto-build/scripts/architecture_context.py"
)
FORK_MANIFEST = REPO / "plugins/core-engineering/fork-manifest.json"

_helper_spec = importlib.util.spec_from_file_location("review_context_test", HELPER)
ac = importlib.util.module_from_spec(_helper_spec)
assert _helper_spec.loader is not None
_helper_spec.loader.exec_module(ac)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Review Test",
            "-c",
            "user.email=review@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _markdown(context: dict) -> str:
    return (
        "# Spec\n\n"
        "## AC-1 behavior\n\n"
        "## TC-1 (proves AC-1)\n"
        "modality: cli\nverification: auto\n\n"
        "## Architecture Context\n\n"
        "```json architecture-context\n"
        + json.dumps(context, indent=2, sort_keys=True)
        + "\n```\n"
    )


@unittest.skipUnless(shutil.which("git"), "review provenance tests require git")
class ReviewGate(unittest.TestCase):
    def make_repo(self, tmp: str) -> tuple[Path, Path, Path]:
        root = Path(tmp)
        plan_dir = root / "docs/plans/demo"
        spec_dir = plan_dir / "specs/04-checkout"
        (plan_dir / "features").mkdir(parents=True)
        spec_dir.mkdir(parents=True)
        (plan_dir / "features/04-checkout.md").write_text(
            "# Checkout\n", encoding="utf-8"
        )
        (plan_dir / "architecture-selection.json").write_text(
            json.dumps({"schema_version": 2, "fixture": True}),
            encoding="utf-8",
        )
        (plan_dir / "plan.json").write_text(
            json.dumps(
                {
                    "project_slug": "demo",
                    "plan_revision": 1,
                    "features": [
                        {
                            "id": "04-checkout",
                            "file": "features/04-checkout.md",
                        }
                    ],
                    "architecture_disposition": {
                        "decision": "not-required",
                        "rationale": "bounded feature-local fixture",
                        "triggers": [],
                        "decided_by": "human",
                        "convergence": {
                            "status": "not-applicable",
                            "iteration_count": 0,
                            "summary": "fixture convergence",
                            "decision_refs": [],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        context = ac.derive_context(
            plan_dir, "04-checkout", repo_root=root
        )
        source = root / "src/checkout.py"
        source.parent.mkdir()
        source.write_text("total = 1\n", encoding="utf-8")
        (root / "src/shared.py").write_text(
            "shared_boundary = 'reviewed'\n", encoding="utf-8"
        )
        tasks = {
            "feature_id": "04-checkout",
            "spec_revision": 3,
            "architecture_context": context,
            "tasks": [
                {
                    "id": "T-1",
                    "files": ["src/checkout.py"],
                    "verifies": ["TC-1"],
                }
            ],
        }
        (spec_dir / "ce-spec.md").write_text(
            _markdown(context), encoding="utf-8"
        )
        (spec_dir / "tasks.json").write_text(
            json.dumps(tasks), encoding="utf-8"
        )
        subprocess.run(
            ["git", "-C", str(root), "init", "-q", "-b", "main"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        _git(root, "add", "-A")
        _git(root, "commit", "-m", "reviewed implementation")
        return root, plan_dir, spec_dir

    def summary(self, root: Path, plan_dir: Path, spec_dir: Path) -> dict:
        return {
            "schema_version": 2,
            "status": "pass",
            "feature_id": "04-checkout",
            "plan_slug": "demo",
            "spec_revision": 3,
            "binding": ac.review_binding(
                spec_dir,
                repo_root=root,
                plan_dir=plan_dir,
                feature_id="04-checkout",
            ),
            "blocking_high": 0,
            "blocking_route": None,
            "findings_total": 0,
            "findings": [],
        }

    def run_case(
        self,
        transform=None,
        *,
        write_summary: bool = True,
        commit_summary: bool = False,
        mutate_after_review=None,
        extra: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root, plan_dir, spec_dir = self.make_repo(tmp)
            summary = self.summary(root, plan_dir, spec_dir)
            if transform is not None:
                transform(summary)
            if write_summary:
                (spec_dir / "review-summary.json").write_text(
                    json.dumps(summary), encoding="utf-8"
                )
            if commit_summary:
                _git(root, "add", str(spec_dir / "review-summary.json"))
                _git(root, "commit", "-m", "record review evidence")
            if mutate_after_review is not None:
                mutate_after_review(root, plan_dir, spec_dir)
            return subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(spec_dir),
                    "--repo-root",
                    str(root),
                    "--plan-dir",
                    str(plan_dir),
                    "--feature",
                    "04-checkout",
                    "--json",
                    *extra,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

    def test_clean_summary_passes_and_allows_unrelated_fields(self):
        result = self.run_case(
            lambda data: data.update(
                {"future_extension": {"compatible": True}}
            )
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        verdict = json.loads(result.stdout)
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["binding_status"], "current")

    def test_review_artifact_only_descendant_commit_remains_valid(self):
        result = self.run_case(commit_summary=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["binding_status"], "current")

    def test_declared_implementation_mutation_after_review_is_stale(self):
        def mutate_and_commit(root, _plan, _spec):
            source = root / "src/checkout.py"
            source.write_text("total = 2\n", encoding="utf-8")
            _git(root, "add", "src/checkout.py")
            _git(root, "commit", "-m", "post-review implementation change")

        result = self.run_case(
            mutate_after_review=mutate_and_commit
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(
            "implementation_files_sha256", json.loads(result.stdout)["message"]
        )

    def test_undeclared_post_review_mutation_is_stale(self):
        def mutate_and_commit(root, _plan, _spec):
            source = root / "src/unbound.py"
            source.write_text(
                "security_boundary = 'changed'\n", encoding="utf-8"
            )
            _git(root, "add", "src/unbound.py")
            _git(root, "commit", "-m", "post-review unbound change")

        result = self.run_case(mutate_after_review=mutate_and_commit)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(
            "repository_state_sha256", json.loads(result.stdout)["message"]
        )

    def test_undeclared_post_review_deletion_is_stale(self):
        def delete_and_commit(root, _plan, _spec):
            source = root / "src/shared.py"
            source.unlink()
            _git(root, "add", "-A")
            _git(root, "commit", "-m", "post-review unbound deletion")

        result = self.run_case(mutate_after_review=delete_and_commit)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(
            "repository_state_sha256", json.loads(result.stdout)["message"]
        )

    def test_undeclared_post_review_mode_change_is_stale(self):
        def make_executable_and_commit(root, _plan, _spec):
            source = root / "src/shared.py"
            source.chmod(0o755)
            _git(root, "add", "src/shared.py")
            _git(root, "commit", "-m", "post-review unbound mode change")

        result = self.run_case(mutate_after_review=make_executable_and_commit)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(
            "repository_state_sha256", json.loads(result.stdout)["message"]
        )

    def test_missing_or_empty_task_file_scope_is_an_integrity_error(self):
        for label, replacement in (("missing", None), ("empty", [])):
            def mutate(_root, _plan, spec_dir, value=replacement):
                path = spec_dir / "tasks.json"
                tasks = json.loads(path.read_text(encoding="utf-8"))
                if value is None:
                    tasks["tasks"][0].pop("files")
                else:
                    tasks["tasks"][0]["files"] = value
                path.write_text(json.dumps(tasks), encoding="utf-8")

            with self.subTest(case=label):
                result = self.run_case(mutate_after_review=mutate)
                self.assertEqual(
                    result.returncode, 2, result.stdout + result.stderr
                )
                self.assertIn("non-empty files list", json.loads(result.stdout)["message"])

    def test_blocked_summary_returns_finding(self):
        def blocked(data):
            findings = [
                {
                    "id": f"CR-{index}",
                    "lens": "correctness",
                    "severity": "high",
                    "confidence": "confirmed",
                }
                for index in range(1, 4)
            ]
            data.update(
                {
                    "status": "blocked",
                    "blocking_high": 3,
                    "blocking_route": "implement",
                    "findings_total": len(findings),
                    "findings": findings,
                }
            )

        result = self.run_case(blocked)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        verdict = json.loads(result.stdout)
        self.assertEqual(verdict["status"], "fail")
        self.assertEqual(verdict["blocking_high"], 3)
        self.assertIn("3 unresolved", verdict["hard_failures"][0])
        self.assertEqual(verdict["blocking_route"], "implement")

    def test_plan_conflict_route_is_validated_and_returned(self):
        def conflict(data):
            data.update(
                {
                    "status": "blocked",
                    "blocking_high": 1,
                    "blocking_route": "plan-conflict",
                    "findings_total": 1,
                    "findings": [
                        {
                            "id": "CR-1",
                            "lens": "security",
                            "severity": "high",
                            "confidence": "confirmed",
                            "observation": (
                                "plan_conflict: undocumented public boundary"
                            ),
                            "suggested_escalation": "/core-engineering:ce-plan",
                        }
                    ],
                }
            )

        result = self.run_case(conflict, extra=("--require-blocking-route",))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["blocking_route"], "plan-conflict"
        )

    def test_automation_rejects_missing_or_discarded_plan_conflict_route(self):
        def conflict_with(route, false_pass=False):
            def mutate(data):
                data.update(
                    {
                        "status": "pass" if false_pass else "blocked",
                        "blocking_high": 0 if false_pass else 1,
                        "findings_total": 1,
                        "findings": [
                            {
                                "id": "CR-1",
                                "lens": "security",
                                "severity": "high",
                                "confidence": "confirmed",
                                "observation": "plan_conflict: stale projection",
                                "suggested_escalation": "/core-engineering:ce-plan",
                            }
                        ],
                    }
                )
                if route is not ...:
                    data["blocking_route"] = route
                else:
                    data.pop("blocking_route", None)

            return mutate

        cases = {
            "missing": conflict_with(...),
            "null": conflict_with(None),
            "implement": conflict_with("implement"),
            "false-pass": conflict_with(None, True),
        }
        for label, transform in cases.items():
            with self.subTest(case=label):
                result = self.run_case(
                    transform, extra=("--require-blocking-route",)
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(
                    "plan_conflict", json.loads(result.stdout)["message"]
                )

    def test_confirmed_security_high_cannot_be_laundered_as_clean_count(self):
        def false_clean(data):
            data.update(
                {
                    "status": "pass",
                    "blocking_high": 0,
                    "blocking_route": None,
                    "findings_total": 1,
                    "findings": [
                        {
                            "id": "CR-1",
                            "lens": "security",
                            "severity": "high",
                            "confidence": "confirmed",
                            "observation": "reachable authorization bypass",
                            "suggested_escalation":
                                "/core-engineering:ce-implement",
                        }
                    ],
                }
            )

        result = self.run_case(
            false_clean, extra=("--require-blocking-route",)
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(
            "expected 1 from confirmed correctness/security High",
            json.loads(result.stdout)["message"],
        )

    def test_finding_severity_contract_cannot_be_weakened(self):
        cases = {
            "performance-high": {
                "id": "CR-1",
                "lens": "performance",
                "severity": "high",
                "confidence": "suspected",
            },
            "tagged-medium": {
                "id": "CR-1",
                "lens": "maintainability",
                "severity": "medium",
                "confidence": "confirmed",
            },
        }
        for label, finding in cases.items():
            with self.subTest(case=label):
                result = self.run_case(
                    lambda data, row=finding: data.update(
                        findings_total=1, findings=[row]
                    )
                )
                self.assertEqual(result.returncode, 2)

    def test_identity_and_binding_fields_are_mandatory(self):
        transforms = {
            "schema": lambda d: d.update(schema_version=1),
            "feature": lambda d: d.update(feature_id="other"),
            "plan": lambda d: d.update(plan_slug="other"),
            "revision": lambda d: d.update(spec_revision=4),
            "binding": lambda d: d["binding"].pop("plan_sha256"),
        }
        for label, transform in transforms.items():
            with self.subTest(case=label):
                result = self.run_case(transform)
                self.assertEqual(result.returncode, 2)

    def test_status_and_count_must_agree(self):
        for status, blocking, expected in (
            ("blocked", 0, "expected 'pass'"),
            ("pass", 1, "expected 'blocked'"),
        ):
            with self.subTest(status=status, blocking=blocking):
                result = self.run_case(
                    lambda data, s=status, b=blocking: data.update(
                        status=s, blocking_high=b
                    )
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, json.loads(result.stdout)["message"])

    def test_blocking_high_must_be_a_nonnegative_integer(self):
        for blocking in (-1, True, "1", None):
            with self.subTest(blocking=blocking):
                result = self.run_case(
                    lambda data, value=blocking: data.update(
                        blocking_high=value
                    )
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(
                    "non-negative integer", json.loads(result.stdout)["message"]
                )

    def test_missing_file_stays_a_could_not_run_error(self):
        result = self.run_case(write_summary=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing", json.loads(result.stdout)["message"])


class ReviewGateFork(unittest.TestCase):
    def test_auto_build_copies_are_registered_and_identical(self):
        manifest = json.loads(FORK_MANIFEST.read_text(encoding="utf-8"))
        gate_entry = next(
            item
            for item in manifest["forks"]
            if item["canonical"].endswith("ce-review/scripts/review-gate.py")
        )
        self.assertIn(
            "plugins/core-engineering/skills/ce-auto-build/scripts/review-gate.py",
            gate_entry["copies"],
        )
        context_entry = next(
            item
            for item in manifest["forks"]
            if item["canonical"].endswith("ce-spec/scripts/architecture_context.py")
        )
        self.assertIn(
            "plugins/core-engineering/skills/ce-auto-build/scripts/architecture_context.py",
            context_entry["copies"],
        )
        self.assertEqual(SCRIPT.read_bytes(), AUTO_COPY.read_bytes())
        self.assertEqual(HELPER.read_bytes(), AUTO_HELPER.read_bytes())


if __name__ == "__main__":
    unittest.main()
