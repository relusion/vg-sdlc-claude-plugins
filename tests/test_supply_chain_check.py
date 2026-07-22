"""Tests for scripts/supply_chain_check.py, the enterprise hardening drift gate."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "supply_chain_check.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def copy_repo(tmp: Path) -> Path:
    dst = tmp / "repo"
    for sub in (".github", "action", "docs", "evals", "plugins", "scripts", "templates"):
        shutil.copytree(REPO / sub, dst / sub, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


class SupplyChainCheck(unittest.TestCase):
    def test_this_repo_hardening_controls_pass(self):
        res = run()
        self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
        self.assertIn("supply-chain: OK", res.stdout)

    def test_unpinned_workflow_action_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            workflow = repo / ".github" / "workflows" / "plugin-validate.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
                    "actions/checkout@v4",
                    1,
                ),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("not pinned", res.stderr)
            self.assertIn("actions/checkout@v4", res.stderr)

    def test_missing_adversarial_eval_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text(encoding="utf-8"))
            data["scenarios"] = [
                scenario for scenario in data["scenarios"]
                if scenario.get("id") != "EVAL-011"
            ]
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing EVAL-011", res.stderr)

    def test_release_skill_must_surface_supply_chain_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            release = repo / "plugins/core-engineering/skills/ce-ship-release/SKILL.md"
            release.write_text(
                release.read_text(encoding="utf-8").replace("Supply-Chain Evidence", "Evidence"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("Supply-Chain Evidence", res.stderr)

    def test_eval_live_workflow_must_keep_budget_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            workflow = repo / ".github" / "workflows" / "eval-live.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace("--max-budget-usd", "--budget"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("--max-budget-usd", res.stderr)

    def test_eval_live_workflow_preserves_runner_receipt_and_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            workflow = repo / ".github" / "workflows" / "eval-live.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8")
                .replace("summary.json", "receipt.json")
                .replace("timeout-minutes: 225", "timeout-minutes: 90"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("summary.json", res.stderr)
            self.assertIn("timeout-minutes must be at least", res.stderr)

    def test_eval_live_workflow_trigger_allowlist_rejects_extra_triggers(self):
        for trigger in ("pull_request", "push", "workflow_call", "issues"):
            with self.subTest(trigger=trigger), tempfile.TemporaryDirectory() as tmp:
                repo = copy_repo(Path(tmp))
                workflow = repo / ".github" / "workflows" / "eval-live.yml"
                workflow.write_text(
                    workflow.read_text(encoding="utf-8").replace(
                        "on:\n  workflow_dispatch:",
                        f"on:\n  {trigger}:\n  workflow_dispatch:",
                        1,
                    ),
                    encoding="utf-8",
                )
                res = run("--root", str(repo))
                self.assertEqual(res.returncode, 1)
                self.assertIn("triggers must be exactly", res.stderr)
                self.assertIn(trigger, res.stderr)

    def test_eval_live_workflow_trigger_allowlist_requires_both_triggers(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            workflow = repo / ".github" / "workflows" / "eval-live.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    '  schedule:\n    - cron: "17 6 * * 1" # weekly smoke run, Monday 06:17 UTC\n',
                    "",
                    1,
                ),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("triggers must be exactly", res.stderr)
            self.assertIn("workflow_dispatch", res.stderr)

    def test_claude_version_pin_drift_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            workflow = repo / ".github" / "workflows" / "eval-live.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "CLAUDE_VERSION: 2.1.195",
                    "CLAUDE_VERSION: 2.1.133",
                    1,
                ),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("CLAUDE_VERSION pin drift", res.stderr)
            self.assertIn("bump both pins together", res.stderr)

    def test_red_main_canary_cannot_be_silently_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            (repo / ".github" / "workflows" / "main-health-canary.yml").unlink()
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("main-health-canary.yml", res.stderr)

    def test_red_main_canary_must_keep_its_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            canary = repo / ".github" / "workflows" / "main-health-canary.yml"
            canary.write_text(
                canary.read_text(encoding="utf-8").replace("schedule:", "disabled:"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("schedule:", res.stderr)

    def test_red_main_canary_must_keep_watching_eval_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            canary = repo / ".github" / "workflows" / "main-health-canary.yml"
            canary.write_text(
                canary.read_text(encoding="utf-8").replace(" eval-live.yml", ""),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("eval-live.yml", res.stderr)

    def test_release_pin_block_workflow_cannot_be_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            (repo / ".github" / "workflows" / "release-pin-block.yml").unlink()
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("release-pin-block.yml", res.stderr)

    def test_release_pin_block_workflow_must_keep_generating_the_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            workflow = repo / ".github" / "workflows" / "release-pin-block.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "scripts/print_pin_block.py", "scripts/print-notes.sh"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("scripts/print_pin_block.py", res.stderr)

    def test_gitlab_port_cannot_be_silently_ungated(self):
        # check_ci_ports guards the port's load-bearing content: drop the
        # checksum-verify step and the lens must fail (a port that fetches the
        # toolkit but never verifies it would trust a moving target).
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            port = repo / "templates" / "adopter-ci" / "gates.gitlab-ci.yml"
            port.write_text(
                port.read_text(encoding="utf-8").replace("sha256sum -c", "true"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("gates.gitlab-ci.yml", res.stderr)

    def test_azure_port_cannot_be_silently_unshipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            (repo / "templates" / "adopter-ci" / "azure-pipelines-gates.yml").unlink()
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("azure-pipelines-gates.yml", res.stderr)

    def test_composite_action_dir_cannot_be_silently_unshipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            shutil.rmtree(repo / "action")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("no composite actions found under action/", res.stderr)
            self.assertIn("action/merge-bar/action.yml", res.stderr)

    def test_unpinned_uses_inside_composite_action_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            action = repo / "action" / "merge-bar" / "action.yml"
            with action.open("a", encoding="utf-8") as fh:
                fh.write("\n    - uses: actions/setup-python@v5\n")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("not pinned", res.stderr)
            self.assertIn("actions/setup-python@v5", res.stderr)

    def test_action_must_keep_movable_ref_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            action = repo / "action" / "merge-bar" / "action.yml"
            action.write_text(
                action.read_text(encoding="utf-8").replace("^[0-9a-f]{40}$", ".*"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("^[0-9a-f]{40}$", res.stderr)

    def test_action_readme_must_keep_integrity_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            readme = repo / "action" / "merge-bar" / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "integrity, not function", "integrity"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("integrity, not function", res.stderr)

    def test_gates_template_must_keep_routing_to_the_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            template = repo / "templates" / "adopter-ci" / "gates.yml"
            template.write_text(
                template.read_text(encoding="utf-8").replace(
                    "CHECKSUM-PINNED COPY-IN FALLBACK", "OFFLINE COPY"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("CHECKSUM-PINNED COPY-IN FALLBACK", res.stderr)

    def test_selftest_workflow_must_keep_local_action_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            workflow = repo / ".github" / "workflows" / "action-selftest.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "./action/merge-bar", "./action/other"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("./action/merge-bar", res.stderr)

    def test_drift_template_cannot_be_silently_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            (repo / "templates" / "adopter-ci" / "drift.yml").unlink()
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("templates/adopter-ci/drift.yml", res.stderr)

    def test_drift_template_must_keep_movable_ref_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            template = repo / "templates" / "adopter-ci" / "drift.yml"
            template.write_text(
                template.read_text(encoding="utf-8").replace("^[0-9a-f]{40}$", ".*"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("^[0-9a-f]{40}$", res.stderr)

    def test_drift_template_must_keep_checksum_coverage_of_decision_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            template = repo / "templates" / "adopter-ci" / "drift.yml"
            # Drop the scanner from the checksum block + run step: an adopter
            # could no longer verify the file that decides drift.
            template.write_text(
                template.read_text(encoding="utf-8").replace(
                    "scripts/drift_scan.py", "scripts/other_scan.py"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("scripts/drift_scan.py", res.stderr)

    def test_drift_template_must_keep_advisory_only_rollout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            template = repo / "templates" / "adopter-ci" / "drift.yml"
            template.write_text(
                template.read_text(encoding="utf-8").replace("--advisory-only", "--report"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("--advisory-only", res.stderr)

    def test_drift_template_uses_must_stay_sha_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            template = repo / "templates" / "adopter-ci" / "drift.yml"
            template.write_text(
                template.read_text(encoding="utf-8").replace(
                    "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
                    "actions/checkout@v4",
                ),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("not pinned", res.stderr)
            self.assertIn("actions/checkout@v4", res.stderr)

    def test_quality_moat_scripts_must_remain_documented(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            evidence = repo / "scripts" / "enterprise_evidence.py"
            evidence.write_text(
                evidence.read_text(encoding="utf-8").replace("not a signed attestation", "attestation"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("not a signed attestation", res.stderr)


if __name__ == "__main__":
    unittest.main()
