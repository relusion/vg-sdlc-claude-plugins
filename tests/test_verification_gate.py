"""Behavioral tests for the release-consumable verification receipt."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO
    / "plugins/core-engineering/skills/ce-verify/scripts/verification-gate.py"
)
RELEASE_COPY = (
    REPO
    / "plugins/core-engineering/skills/ce-ship-release/scripts/verification-gate.py"
)
FORK_MANIFEST = REPO / "plugins/core-engineering/fork-manifest.json"


def load_gate_module():
    spec = importlib.util.spec_from_file_location("verification_gate_under_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load verification gate: {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Verification Test",
            "-c",
            "user.email=verification@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def report(*, verified: str = "yes", accepted: str = "yes") -> str:
    return (
        "# Verification Report: demo\n\n"
        "> Status: verified\n\n"
        "## Per-Feature Status  *(derived roll-up)*\n\n"
        "| Feature | Implemented | Journeys pass | Criteria ok | Accepted | Verified |\n"
        "|---|---|---|---|---|---|\n"
        f"| 01-core | yes | 1-of-1 | 2-of-2 | {accepted} | {verified} |\n\n"
        "## Open Issues\n\n"
        "None.\n"
    )


@unittest.skipUnless(shutil.which("git"), "verification provenance tests require git")
class VerificationGate(unittest.TestCase):
    def make_repo(
        self,
        tmp: str,
        *,
        verified: str = "yes",
        accepted: str = "yes",
        task_status: str = "done",
    ) -> tuple[Path, Path]:
        root = Path(tmp)
        plan = root / "docs/plans/demo"
        spec = plan / "specs/01-core"
        (plan / "features").mkdir(parents=True)
        spec.mkdir(parents=True)
        (root / "src").mkdir()
        (root / "src/core.py").write_text("VALUE = 1\n", encoding="utf-8")
        (plan / "features/01-core.md").write_text(
            "# Core feature\n", encoding="utf-8"
        )
        (plan / "plan.json").write_text(
            json.dumps(
                {
                    "project_slug": "demo",
                    "plan_revision": 3,
                    "features": [
                        {
                            "id": "01-core",
                            "file": "features/01-core.md",
                            "ship_order": 1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (spec / "ce-spec.md").write_text(
            "# Core specification\n", encoding="utf-8"
        )
        (spec / "tasks.json").write_text(
            json.dumps(
                {
                    "feature_id": "01-core",
                    "spec_revision": 2,
                    "tasks": [
                        {
                            "id": "T-1",
                            "status": task_status,
                            "files": ["src/core.py"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (spec / "verification.md").write_text(
            "# Implementation verification\n\nTests passed.\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", str(root), "init", "-q", "-b", "main"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        git(root, "add", "-A")
        git(root, "commit", "-m", "implemented feature")
        (plan / "verification-report.md").write_text(
            report(verified=verified, accepted=accepted),
            encoding="utf-8",
        )
        return root, plan

    def run_gate(
        self,
        command: str,
        root: Path,
        plan: Path,
        *extra: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                command,
                str(plan),
                "--repo-root",
                str(root),
                "--json",
                *extra,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def create(self, root: Path, plan: Path) -> dict:
        result = self.run_gate("create", root, plan)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_create_and_current_check_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan = self.make_repo(tmp)
            created = self.create(root, plan)
            self.assertEqual(created["status"], "created")
            summary = json.loads(
                (plan / "verification-summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["schema_version"], 1)
            self.assertEqual(summary["plan_revision"], 3)
            self.assertEqual(summary["verification_report"]["path"], "verification-report.md")
            self.assertEqual(summary["features"][0]["feature_id"], "01-core")
            self.assertEqual(summary["features"][0]["implementation_status"], "implemented")
            self.assertEqual(summary["features"][0]["verdict"], "verified")
            self.assertEqual(summary["features"][0]["acceptance"], "accepted")

            checked = self.run_gate(
                "check", root, plan, "--feature", "01-core", "--evaluated-commit", "HEAD"
            )
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            verdict = json.loads(checked.stdout)
            self.assertEqual(verdict["status"], "pass")
            self.assertEqual(verdict["binding_status"], "current")

    def test_interrupted_atomic_write_preserves_previous_receipt_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan = self.make_repo(tmp)
            self.create(root, plan)
            summary = plan / "verification-summary.json"
            previous = summary.read_bytes()
            gate = load_gate_module()

            with mock.patch.object(
                gate.os, "fsync", side_effect=OSError("simulated write failure")
            ):
                code, result = gate.create_summary(
                    plan,
                    repo_root=root,
                    output=summary,
                    evaluated_commit="HEAD",
                )

            self.assertEqual(code, 2, result)
            self.assertIn("simulated write failure", result["message"])
            self.assertEqual(summary.read_bytes(), previous)
            self.assertEqual(
                list(plan.glob(".verification-summary.json.*.tmp")), []
            )

    def test_destination_symlink_race_does_not_overwrite_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan = self.make_repo(tmp)
            summary = plan / "verification-summary.json"
            victim = root / "victim.txt"
            victim.write_text("do not overwrite\n", encoding="utf-8")
            gate = load_gate_module()
            real_replace = os.replace

            def race_destination(source, destination):
                summary.symlink_to(victim)
                real_replace(source, destination)

            with mock.patch.object(gate.os, "replace", side_effect=race_destination):
                code, result = gate.create_summary(
                    plan,
                    repo_root=root,
                    output=summary,
                    evaluated_commit="HEAD",
                )

            self.assertEqual(code, 0, result)
            self.assertFalse(summary.is_symlink())
            self.assertEqual(victim.read_text(encoding="utf-8"), "do not overwrite\n")
            self.assertEqual(
                list(plan.glob(".verification-summary.json.*.tmp")), []
            )

    @unittest.skipUnless(os.name == "posix", "byte-path regression requires POSIX")
    def test_non_utf8_git_filename_is_structured_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan = self.make_repo(tmp)
            bad_name = os.fsencode(root) + b"/invalid-utf8-\xff.txt"
            descriptor = os.open(
                bad_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            try:
                os.write(descriptor, b"untracked\n")
            finally:
                os.close(descriptor)

            created = self.run_gate("create", root, plan)

            self.assertEqual(created.returncode, 2, created.stdout + created.stderr)
            result = json.loads(created.stdout)
            self.assertEqual(result["status"], "error")
            self.assertIn("file listing failed", result["message"])
            self.assertNotIn("Traceback", created.stderr)

    def test_evidence_only_descendant_commit_remains_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan = self.make_repo(tmp)
            self.create(root, plan)
            git(root, "add", str(plan / "verification-report.md"))
            git(root, "add", str(plan / "verification-summary.json"))
            git(root, "commit", "-m", "record verification evidence")

            checked = self.run_gate("check", root, plan, "--feature", "01-core")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            verdict = json.loads(checked.stdout)
            self.assertNotEqual(
                verdict["recorded_evaluated_commit"], verdict["evaluated_commit"]
            )

    def test_current_nonpassing_verdict_is_exit_one(self):
        cases = (
            ("partial (0-of-1)", "yes", "verification verdict is partial"),
            ("no", "yes", "verification verdict is failed"),
            ("yes", "Reject", "acceptance is rejected"),
            ("yes", "Defer", "acceptance is deferred"),
        )
        for verified, accepted, expected in cases:
            with self.subTest(verified=verified, accepted=accepted):
                with tempfile.TemporaryDirectory() as tmp:
                    root, plan = self.make_repo(
                        tmp, verified=verified, accepted=accepted
                    )
                    self.create(root, plan)
                    checked = self.run_gate(
                        "check", root, plan, "--feature", "01-core"
                    )
                    self.assertEqual(
                        checked.returncode, 1, checked.stdout + checked.stderr
                    )
                    verdict = json.loads(checked.stdout)
                    self.assertEqual(verdict["status"], "fail")
                    self.assertIn(expected, " ".join(verdict["hard_failures"]))

    def test_incomplete_implementation_is_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan = self.make_repo(tmp, task_status="in-progress")
            self.create(root, plan)
            checked = self.run_gate("check", root, plan, "--feature", "01-core")
            self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
            self.assertIn(
                "implementation is not complete",
                " ".join(json.loads(checked.stdout)["hard_failures"]),
            )

    def test_mutated_bound_inputs_are_stale(self):
        mutations = {
            "source": lambda root, plan: (root / "src/core.py").write_text(
                "VALUE = 2\n", encoding="utf-8"
            ),
            "plan": lambda root, plan: (plan / "plan.json").write_text(
                (plan / "plan.json")
                .read_text(encoding="utf-8")
                .replace('"plan_revision": 3', '"plan_revision": 4'),
                encoding="utf-8",
            ),
            "feature": lambda root, plan: (plan / "features/01-core.md").write_text(
                "# Changed feature\n", encoding="utf-8"
            ),
            "spec": lambda root, plan: (plan / "specs/01-core/ce-spec.md").write_text(
                "# Changed spec\n", encoding="utf-8"
            ),
            "tasks": lambda root, plan: (plan / "specs/01-core/tasks.json").write_text(
                (plan / "specs/01-core/tasks.json")
                .read_text(encoding="utf-8")
                .replace('"spec_revision": 2', '"spec_revision": 3'),
                encoding="utf-8",
            ),
            "implementation verification": lambda root, plan: (
                plan / "specs/01-core/verification.md"
            ).write_text("# Changed evidence\n", encoding="utf-8"),
            "report": lambda root, plan: (plan / "verification-report.md").write_text(
                report().replace("## Open Issues", "## Notes\n\nChanged.\n\n## Open Issues"),
                encoding="utf-8",
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmp:
                    root, plan = self.make_repo(tmp)
                    self.create(root, plan)
                    mutate(root, plan)
                    checked = self.run_gate(
                        "check", root, plan, "--feature", "01-core"
                    )
                    self.assertEqual(
                        checked.returncode, 2, checked.stdout + checked.stderr
                    )
                    self.assertIn(
                        "stale or mismatched", json.loads(checked.stdout)["message"]
                    )

    def test_missing_malformed_and_uncovered_summary_are_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan = self.make_repo(tmp)
            missing = self.run_gate("check", root, plan, "--feature", "01-core")
            self.assertEqual(missing.returncode, 2)

            (plan / "verification-summary.json").write_text(
                "{not json", encoding="utf-8"
            )
            malformed = self.run_gate("check", root, plan, "--feature", "01-core")
            self.assertEqual(malformed.returncode, 2)
            self.assertIn("not valid", json.loads(malformed.stdout)["message"])

            self.create(root, plan)
            uncovered = self.run_gate(
                "check", root, plan, "--feature", "02-missing"
            )
            self.assertEqual(uncovered.returncode, 2)
            self.assertIn("does not cover", json.loads(uncovered.stdout)["message"])

    def test_peer_review_evidence_does_not_stale_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan = self.make_repo(tmp)
            self.create(root, plan)
            spec = plan / "specs/01-core"
            (spec / "review-summary.json").write_text("{}\n", encoding="utf-8")
            (spec / "code-review.md").write_text("# Review\n", encoding="utf-8")
            (plan / "review-learnings.md").write_text(
                "# Review learnings\n", encoding="utf-8"
            )

            checked = self.run_gate("check", root, plan, "--feature", "01-core")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_worktree_must_materialize_the_evaluated_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan = self.make_repo(tmp)
            verified_commit = git(root, "rev-parse", "HEAD")
            self.create(root, plan)
            git(root, "add", str(plan / "verification-report.md"))
            git(root, "add", str(plan / "verification-summary.json"))
            git(root, "commit", "-m", "record verification evidence")

            (root / "src/core.py").write_text("VALUE = 999\n", encoding="utf-8")
            git(root, "add", "src/core.py")
            git(root, "commit", "-m", "unverified source change")
            evaluated_head = git(root, "rev-parse", "HEAD")

            # Make the index/worktree look like the verified commit while HEAD
            # still contains the unverified implementation.
            git(root, "checkout", verified_commit, "--", "src/core.py")
            checked = self.run_gate(
                "check",
                root,
                plan,
                "--feature",
                "01-core",
                "--evaluated-commit",
                evaluated_head,
            )
            self.assertEqual(checked.returncode, 2, checked.stdout + checked.stderr)
            self.assertIn(
                "worktree does not materialize evaluated commit",
                json.loads(checked.stdout)["message"],
            )

    def test_nonancestor_evaluated_commit_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, plan = self.make_repo(tmp)
            self.create(root, plan)
            recorded_branch = git(root, "rev-parse", "HEAD")
            git(root, "checkout", "--orphan", "other")
            git(root, "rm", "-rf", ".")
            (root / "other.txt").write_text("other\n", encoding="utf-8")
            git(root, "add", "other.txt")
            git(root, "commit", "-m", "unrelated history")
            # Restore the verification evidence without changing its recorded
            # commit, then prove the requested head is not its descendant.
            git(root, "checkout", recorded_branch, "--", "docs", "src")
            checked = self.run_gate("check", root, plan, "--feature", "01-core")
            self.assertEqual(checked.returncode, 2, checked.stdout + checked.stderr)
            self.assertIn("not an ancestor", json.loads(checked.stdout)["message"])


class VerificationGateFork(unittest.TestCase):
    def test_release_copy_is_registered_and_identical(self):
        manifest = json.loads(FORK_MANIFEST.read_text(encoding="utf-8"))
        entry = next(
            item
            for item in manifest["forks"]
            if item["canonical"].endswith("ce-verify/scripts/verification-gate.py")
        )
        self.assertIn(
            "plugins/core-engineering/skills/ce-ship-release/scripts/verification-gate.py",
            entry["copies"],
        )
        self.assertEqual(SCRIPT.read_bytes(), RELEASE_COPY.read_bytes())


if __name__ == "__main__":
    unittest.main()
