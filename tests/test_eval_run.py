"""Tests for scripts/eval_run.py, the Claude Code eval runner wrapper."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "eval_run.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def copy_eval_repo(tmp: Path) -> Path:
    dst = tmp / "repo"
    for sub in ("scripts", "plugins", "evals"):
        shutil.copytree(REPO / sub, dst / sub, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


class EvalRun(unittest.TestCase):
    def test_dry_run_single_scenario_writes_metadata_without_model_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            res = run("--scenario", "EVAL-003", "--out-dir", str(out))
            self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
            self.assertIn("would run", res.stdout)
            self.assertNotIn("--bare", res.stdout)
            self.assertNotIn("--max-budget-usd None", res.stdout)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertTrue(metadata["dry_run"])
            self.assertFalse(metadata["bare"])
            self.assertEqual(metadata["grade_status"], "not-run")
            self.assertIsNone(metadata["grade_returncode"])
            self.assertEqual(metadata["graded_scenarios"], [])
            self.assertIsInstance(metadata["source_clean"], bool)
            self.assertIn(len(metadata["git_head"]), (40, 64))
            self.assertNotEqual(metadata["run_id"], out.name)
            self.assertTrue(metadata["started_at"].endswith("Z"))
            self.assertTrue(metadata["completed_at"].endswith("Z"))
            self.assertEqual(metadata["claude_cli"], {
                "binary": "claude",
                "status": "unavailable",
                "version": None,
                "reason": "not-probed-dry-run",
            })
            self.assertEqual(len(metadata["plugin_manifests"]), 1)
            self.assertEqual(metadata["plugin_manifests"][0]["source"], "--plugin-dir")
            self.assertEqual(metadata["plugin_manifests"][0]["name"], "core-engineering")
            self.assertEqual(
                metadata["plugin_manifests"][0]["version"],
                json.loads(
                    (REPO / "plugins/core-engineering/.claude-plugin/plugin.json").read_text()
                )["version"],
            )
            self.assertEqual(metadata["plugin_manifests"][0]["status"], "resolved")
            self.assertEqual(metadata["records"][0]["id"], "EVAL-003")
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual(summary["run_id"], metadata["run_id"])
            self.assertEqual(summary["claude_cli"], metadata["claude_cli"])
            self.assertEqual(summary["plugin_manifests"], metadata["plugin_manifests"])
            self.assertEqual(summary["scenarios"], [{
                "id": "EVAL-003", "skill": "ce-impact", "status": "planned",
            }])
            self.assertTrue((out / "work" / "EVAL-003" / "README.md").is_file())
            self.assertFalse((out / "EVAL-003.md").exists())

    def test_bare_opt_in_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            res = run("--scenario", "EVAL-003", "--bare", "--out-dir", str(out))
            self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
            self.assertIn("--bare", res.stdout)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertTrue(metadata["bare"])
            self.assertIn("--bare", metadata["records"][0]["claude_command"])

    def test_requires_selection(self):
        res = run()
        self.assertEqual(res.returncode, 2)
        self.assertIn("choose --scenario", res.stderr)

    def test_execute_requires_budget_before_calling_claude(self):
        res = run("--scenario", "EVAL-003", "--execute", "--claude-bin", "definitely-not-claude")
        self.assertEqual(res.returncode, 2)
        self.assertIn("--execute requires --max-budget-usd", res.stderr)

    def test_execute_refuses_below_recommended_budget(self):
        res = run(
            "--scenario",
            "EVAL-008",
            "--execute",
            "--max-budget-usd",
            "1",
            "--claude-bin",
            "definitely-not-claude",
        )
        self.assertEqual(res.returncode, 2)
        self.assertIn("below the selected scenario recommendation", res.stderr)
        self.assertIn("--max-budget-usd 3", res.stderr)

    def test_profile_smoke_selects_read_only_smoke_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            res = run("--profile", "smoke", "--out-dir", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(
                [record["id"] for record in metadata["records"]],
                [
                    "EVAL-001", "EVAL-002", "EVAL-003", "EVAL-011", "EVAL-012",
                    "EVAL-018", "EVAL-019",
                ],
            )
            self.assertTrue(all(record["profile"] == "smoke" for record in metadata["records"]))

    def test_profile_benchmark_selects_cross_stack_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            res = run("--profile", "benchmark", "--out-dir", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(
                [record["id"] for record in metadata["records"]],
                ["EVAL-013", "EVAL-014", "EVAL-015"],
            )
            self.assertTrue(all(record["profile"] == "benchmark" for record in metadata["records"]))
            self.assertTrue((out / "work" / "EVAL-013" / "src" / "api" / "routes.ts").is_file())

    def test_unknown_scenario_fails_cleanly(self):
        res = run("--scenario", "EVAL-999")
        self.assertEqual(res.returncode, 2)
        self.assertIn("unknown scenario id", res.stderr)

    def test_fixture_copy_is_replaced_between_dry_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            res1 = run("--scenario", "EVAL-003", "--out-dir", str(out))
            self.assertEqual(res1.returncode, 0, res1.stderr)
            marker = out / "work" / "EVAL-003" / "marker.txt"
            marker.write_text("stale")
            res2 = run("--scenario", "EVAL-003", "--out-dir", str(out))
            self.assertEqual(res2.returncode, 0, res2.stderr)
            self.assertFalse(marker.exists())

    def test_live_fixture_is_a_clean_git_worktree_before_claude_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            fake = root / "fake-claude"
            fake.write_text(
                "#!/bin/sh\n"
                "test \"$(git rev-parse --show-toplevel)\" = \"$PWD\" || exit 20\n"
                "test -z \"$(git status --porcelain --untracked-files=all)\" || exit 21\n"
                "git log -1 --format='%an <%ae>'\n"
            )
            fake.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{root}:{env.get('PATH', '')}"
            env["GIT_DIR"] = str(root / "wrong-git-dir")
            env["GIT_WORK_TREE"] = str(root / "wrong-work-tree")
            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--scenario",
                    "EVAL-003",
                    "--execute",
                    "--max-budget-usd",
                    "1.00",
                    "--claude-bin",
                    "fake-claude",
                    "--skip-check",
                    "--out-dir",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
            output = (out / "EVAL-003.md").read_text()
            self.assertIn("Claude Code Eval <claude-code-eval@example.invalid>", output)
            state = json.loads((out / "metadata.json").read_text())["records"][0]["git_state"]
            self.assertEqual(state["before"], state["after"])
            self.assertEqual(state["after"]["changed_paths"], [])
            self.assertEqual(state["after"]["ignored_files_sha256"], {})
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(metadata["grade_status"], "not-run")

    def test_live_receipt_records_actual_cli_and_loaded_plugin_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            fake = root / "fake-claude"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"--version\" ]; then\n"
                "  printf '%s\\n' '9.9.9 (Claude Code)'\n"
                "  exit 0\n"
                "fi\n"
                "printf '%s\\n' 'Not analyzable yet — too thin to ground'\n"
            )
            fake.chmod(0o755)
            res = run(
                "--scenario", "EVAL-003",
                "--execute",
                "--max-budget-usd", "1.00",
                "--claude-bin", str(fake),
                "--skip-check",
                "--out-dir", str(out),
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(metadata["claude_cli"], {
                "binary": str(fake),
                "status": "resolved",
                "version": "9.9.9 (Claude Code)",
                "reason": None,
            })
            self.assertEqual(metadata["plugin_manifests"][0]["status"], "resolved")
            self.assertEqual(metadata["plugin_manifests"][0]["name"], "core-engineering")
            self.assertEqual(
                json.loads((out / "summary.json").read_text())["claude_cli"],
                metadata["claude_cli"],
            )

    def test_scripted_turn_verifies_context_and_records_decision_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_eval_repo(Path(tmp))
            scenarios = root / "evals/scenarios.json"
            data = json.loads(scenarios.read_text(encoding="utf-8"))
            scenario = next(s for s in data["scenarios"] if s["id"] == "EVAL-003")
            scenario["scripted_turns"] = [{
                "event_id": "EVAL-003-D01",
                "answer": "Proceed with the supplied project facts, then stop at the next gate.",
                "required_previous_output": [
                    "Gate 1 of 2",
                    "Intent and Scope",
                ],
            }]
            scenarios.write_text(json.dumps(data), encoding="utf-8")

            out = Path(tmp) / "run"
            fake = Path(tmp) / "fake-claude"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"--version\" ]; then echo '9.9.9'; exit 0; fi\n"
                "resume=0\n"
                "for arg in \"$@\"; do [ \"$arg\" = \"--resume\" ] && resume=1; done\n"
                "if [ \"$resume\" -eq 1 ]; then\n"
                "  printf '%s\\n' '{\"result\":\"Gate 2 of 2 — Architecture Direction Selection\",\"session_id\":\"sess-scripted\",\"total_cost_usd\":0.1}'\n"
                "else\n"
                "  printf '%s\\n' '{\"result\":\"Gate 1 of 2 — Intent and Scope\",\"session_id\":\"sess-scripted\",\"total_cost_usd\":0.1}'\n"
                "fi\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)

            res = run(
                "--root", str(root),
                "--scenario", "EVAL-003",
                "--execute",
                "--max-budget-usd", "1.00",
                "--claude-bin", str(fake),
                "--skip-check",
                "--out-dir", str(out),
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            output = (out / "EVAL-003.md").read_text(encoding="utf-8")
            self.assertIn("Gate 1 of 2 — Intent and Scope", output)
            self.assertIn("Scripted decision event EVAL-003-D01", output)
            self.assertIn("Gate 2 of 2 — Architecture Direction Selection", output)

            record = json.loads((out / "metadata.json").read_text())["records"][0]
            self.assertEqual(record["status"], "pass")
            self.assertEqual(record["reported_cost_usd"], 0.2)
            self.assertEqual(len(record["claude_commands"]), 2)
            self.assertNotIn("--no-session-persistence", record["claude_commands"][0])
            self.assertIn("--resume", record["claude_commands"][1])
            second = record["claude_commands"][1]
            self.assertEqual(second[second.index("--max-budget-usd") + 1], "0.9")
            self.assertEqual(
                record["scripted_decisions"][0]["event_id"],
                "EVAL-003-D01",
            )
            self.assertEqual(len(record["scripted_decisions"][0]["context_sha256"]), 64)
            self.assertEqual(len(record["scripted_decisions"][0]["answer_sha256"]), 64)

    def test_scripted_turn_refuses_answer_when_gate_context_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_eval_repo(Path(tmp))
            scenarios = root / "evals/scenarios.json"
            data = json.loads(scenarios.read_text(encoding="utf-8"))
            scenario = next(s for s in data["scenarios"] if s["id"] == "EVAL-003")
            scenario["scripted_turns"] = [{
                "event_id": "EVAL-003-D01",
                "answer": "Proceed",
                "required_previous_output": ["Gate N of M — Missing"],
            }]
            scenarios.write_text(json.dumps(data), encoding="utf-8")

            out = Path(tmp) / "run"
            fake = Path(tmp) / "fake-claude"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"--version\" ]; then echo '9.9.9'; exit 0; fi\n"
                "printf '%s\\n' '{\"result\":\"A different gate\",\"session_id\":\"sess-scripted\",\"total_cost_usd\":0.1}'\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            res = run(
                "--root", str(root),
                "--scenario", "EVAL-003",
                "--execute",
                "--max-budget-usd", "1.00",
                "--claude-bin", str(fake),
                "--skip-check",
                "--out-dir", str(out),
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("refused to send decision event", res.stderr)
            record = json.loads((out / "metadata.json").read_text())["records"][0]
            self.assertEqual(record["failure_kind"], "scripted-context-mismatch")
            self.assertEqual(len(record["claude_commands"]), 1)

    def test_live_receipt_labels_unavailable_cli_version_without_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            fake = root / "fake-claude"
            fake.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"--version\" ]; then exit 17; fi\n"
                "printf '%s\\n' 'Not analyzable yet — too thin to ground'\n"
            )
            fake.chmod(0o755)
            res = run(
                "--scenario", "EVAL-003",
                "--execute",
                "--max-budget-usd", "1.00",
                "--claude-bin", str(fake),
                "--skip-check",
                "--out-dir", str(out),
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            provenance = json.loads((out / "metadata.json").read_text())["claude_cli"]
            self.assertEqual(provenance["status"], "unavailable")
            self.assertIsNone(provenance["version"])
            self.assertEqual(provenance["reason"], "version-probe-exited-17")

    def test_receipt_labels_missing_plugin_manifest_without_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            (repo / "plugins/core-engineering/.claude-plugin/plugin.json").unlink()
            out = Path(tmp) / "run"
            res = run(
                "--root", str(repo),
                "--scenario", "EVAL-003",
                "--out-dir", str(out),
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            manifest = json.loads(
                (out / "metadata.json").read_text(encoding="utf-8")
            )["plugin_manifests"][0]
            self.assertEqual(manifest["status"], "unavailable")
            self.assertIsNone(manifest["name"])
            self.assertIsNone(manifest["version"])
            self.assertEqual(manifest["reason"], "manifest-missing")

    def test_deterministic_grade_is_recorded_in_live_receipt(self):
        for output, expected_code, expected_grade in (
            ("Not analyzable yet — too thin to ground\n", 0, "pass"),
            ("unsupported claim\n", 1, "failed"),
        ):
            with self.subTest(expected_grade=expected_grade), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                out = root / "run"
                fake = root / "fake-claude"
                fake.write_text(f"#!/bin/sh\nprintf '%s' {output!r}\n")
                fake.chmod(0o755)
                res = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--scenario", "EVAL-003",
                        "--execute",
                        "--max-budget-usd", "1.00",
                        "--claude-bin", str(fake),
                        "--out-dir", str(out),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(res.returncode, expected_code, res.stdout + res.stderr)
                metadata = json.loads((out / "metadata.json").read_text())
                self.assertEqual(metadata["records"][0]["status"], "pass")
                self.assertEqual(metadata["grade_status"], expected_grade)
                self.assertEqual(metadata["grade_returncode"], expected_code)
                self.assertEqual(
                    metadata["graded_scenarios"],
                    ["EVAL-003"] if expected_code == 0 else [],
                )
                summary = json.loads((out / "summary.json").read_text())
                self.assertEqual(summary["grade_status"], expected_grade)
                self.assertEqual(summary["grade_returncode"], expected_code)
                self.assertEqual(summary["scenarios"][0]["returncode"], 0)

    def test_live_run_refuses_to_overwrite_nonempty_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "existing-run"
            out.mkdir()
            marker = out / "receipt.json"
            marker.write_text("preserve me", encoding="utf-8")
            fake = root / "fake-claude"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            res = run(
                "--scenario", "EVAL-003",
                "--execute",
                "--max-budget-usd", "1.00",
                "--claude-bin", str(fake),
                "--skip-check",
                "--out-dir", str(out),
            )
            self.assertEqual(res.returncode, 2)
            self.assertIn("must be new or empty", res.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me")

    def test_unignored_in_repo_output_makes_receipt_unpromotable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_eval_repo(Path(tmp))
            fake = root / "fake-claude"
            fake.write_text(
                "#!/bin/sh\nprintf '%s\\n' 'Not analyzable yet — too thin to ground'\n"
            )
            fake.chmod(0o755)
            subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True)
            subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(root),
                    "-c", "user.name=Eval", "-c", "user.email=eval@example.invalid",
                    "commit", "--quiet", "--no-gpg-sign", "-m", "baseline",
                ],
                check=True,
            )
            out = root / "unignored-run"
            res = run(
                "--root", str(root),
                "--scenario", "EVAL-003",
                "--execute",
                "--max-budget-usd", "1.00",
                "--claude-bin", str(fake),
                "--out-dir", str(out),
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertFalse(metadata["source_clean"])
            self.assertEqual(metadata["grade_status"], "pass")

    def test_bad_fixture_in_catalog_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            data["scenarios"][0]["fixture"] = "missing-fixture"
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo), "--scenario", "EVAL-001")
            self.assertEqual(res.returncode, 2)
            self.assertIn("fixture not found", res.stderr)

    def test_budget_exceeded_failure_is_labeled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            fake = root / "fake-claude"
            fake.write_text("#!/bin/sh\necho 'Error: Exceeded USD budget (0.25)'\nexit 1\n")
            fake.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{root}:{env.get('PATH', '')}"
            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--scenario",
                    "EVAL-003",
                    "--execute",
                    "--max-budget-usd",
                    "0.25",
                    "--allow-low-budget",
                    "--claude-bin",
                    "fake-claude",
                    "--out-dir",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("budget exceeded", res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(metadata["records"][0]["failure_kind"], "budget-exceeded")
            self.assertIn("Exceeded USD budget", metadata["records"][0]["failure_message"])

    def test_auth_failure_is_labeled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            fake = root / "fake-claude"
            fake.write_text("#!/bin/sh\necho 'Not logged in · Please run /login'\nexit 1\n")
            fake.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{root}:{env.get('PATH', '')}"
            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--scenario",
                    "EVAL-003",
                    "--execute",
                    "--max-budget-usd",
                    "1.00",
                    "--bare",
                    "--claude-bin",
                    "fake-claude",
                    "--out-dir",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("authentication failed", res.stderr)
            self.assertIn("without --bare", res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(metadata["records"][0]["failure_kind"], "auth-error")
            self.assertIn("Not logged in", metadata["records"][0]["failure_message"])

    def test_timeout_preserves_failure_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            fake = root / "fake-claude"
            fake.write_text("#!/bin/sh\necho started\nsleep 2\necho too-late\n")
            fake.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{root}:{env.get('PATH', '')}"
            res = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--scenario",
                    "EVAL-003",
                    "--execute",
                    "--max-budget-usd",
                    "1.00",
                    "--claude-bin",
                    "fake-claude",
                    "--timeout",
                    "1",
                    "--out-dir",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("timed out after 1 seconds", res.stderr)
            metadata = json.loads((out / "metadata.json").read_text())
            record = metadata["records"][0]
            self.assertEqual(record["failure_kind"], "timeout")
            self.assertEqual(record["timeout_seconds"], 1)
            self.assertEqual((out / "EVAL-003.md").read_text().strip(), "started")


if __name__ == "__main__":
    unittest.main()
