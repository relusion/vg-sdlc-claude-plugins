"""Tests for scripts/eval_check.py, the offline eval-corpus validator."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "eval_check.py"


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


class EvalCheck(unittest.TestCase):
    def test_this_repo_eval_corpus_passes(self):
        import json
        res = run()
        self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
        self.assertIn("eval-check: OK", res.stdout)
        catalog = json.loads((REPO / "evals" / "scenarios.json").read_text(encoding="utf-8"))
        self.assertIn(f"{len(catalog['scenarios'])} scenario(s)", res.stdout)

    def test_duplicate_scenario_id_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            data["scenarios"].append(dict(data["scenarios"][0]))
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("duplicate scenario id", res.stderr)

    def test_full_profile_scenario_requires_artifact_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            del data["scenarios"][3]["artifact_checks"]
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("full-profile scenarios must include artifact_checks", res.stderr)

    def test_required_citation_scenario_must_pin_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            del data["scenarios"][0]["output_checks"]["required_citations"]
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("must pin expected files with required_citations", res.stderr)

    def test_brittle_output_anchor_fails_catalog_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            data["scenarios"][0]["output_checks"]["required_substrings"].append("x" * 161)
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("prefer smaller deterministic anchors", res.stderr)

    def test_missing_expected_fixture_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            (repo / "evals/fixtures/minimal-service/auth.py").unlink()
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("expected fixture file missing", res.stderr)
            self.assertIn("auth.py", res.stderr)

    def test_output_check_failure_is_attributed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "runs"
            out.mkdir()
            (out / "EVAL-003.md").write_text(
                "Affected components\n- app.py:1 guessed impact\n",
                encoding="utf-8",
            )
            res = run("--outputs-dir", str(out))
            self.assertEqual(res.returncode, 1)
            self.assertIn("EVAL-003", res.stderr)
            self.assertIn("should not contain file:line citations", res.stderr)

    def test_required_citation_file_failure_is_attributed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "runs"
            out.mkdir()
            (out / "EVAL-001.md").write_text(
                "RateLimiter login 429 app.py:1 auth.py:2 checks/auth_check.py:\n",
                encoding="utf-8",
            )
            res = run("--outputs-dir", str(out))
            self.assertEqual(res.returncode, 1)
            self.assertIn("EVAL-001", res.stderr)
            self.assertIn("missing citation for checks/auth_check.py", res.stderr)

    def test_partial_output_check_can_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "runs"
            out.mkdir()
            (out / "EVAL-003.md").write_text(
                "**Not analyzable yet** — the description is too thin to ground an impact analysis.\n",
                encoding="utf-8",
            )
            res = run("--outputs-dir", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("1 output(s) graded", res.stdout)

    def test_failed_run_metadata_is_reported_before_grading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "runs"
            out.mkdir()
            (out / "EVAL-003.md").write_text(
                "Error: Exceeded USD budget (0.25)\n",
                encoding="utf-8",
            )
            (out / "metadata.json").write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "id": "EVAL-003",
                    "status": "failed",
                    "returncode": 1,
                    "failure_kind": "budget-exceeded",
                    "failure_message": "Error: Exceeded USD budget (0.25)"
                }]
            }), encoding="utf-8")
            res = run("--outputs-dir", str(out))
            self.assertEqual(res.returncode, 1)
            self.assertIn("run failed before output grading", res.stderr)
            self.assertIn("budget-exceeded", res.stderr)
            self.assertNotIn("output missing required text", res.stderr)

    def test_artifact_json_field_failure_is_attributed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "runs"
            work = out / "work" / "EVAL-007"
            work.mkdir(parents=True)
            (out / "EVAL-007.md").write_text(
                "CR-1 High confirmed security actor_id owner_id service.py: IDOR\n",
                encoding="utf-8",
            )
            (out / "metadata.json").write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "id": "EVAL-007",
                    "status": "pass",
                    "work_dir": str(work)
                }]
            }), encoding="utf-8")
            (work / "review-summary.json").write_text(json.dumps({
                "status": "passed",
                "findings_total": 0,
                "blocking_high": 0,
                "by_severity": {"high": {"confirmed": 0}},
                "by_lens": {"security": 0},
                "findings": [{
                    "id": "CR-1",
                    "lens": "security",
                    "severity": "high",
                    "confidence": "confirmed",
                    "file": "service.py:8",
                    "observation": "actor_id owner_id IDOR"
                }]
            }), encoding="utf-8")
            (work / "code-review.md").write_text(
                "CR-1 High · confirmed service.py:8-10 missing ownership check\n",
                encoding="utf-8",
            )
            res = run("--outputs-dir", str(out))
            self.assertEqual(res.returncode, 1)
            self.assertIn("review-summary.json", res.stderr)
            self.assertIn("blocking_high", res.stderr)

    def test_artifact_spec_lint_failure_is_attributed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "runs"
            spec_dir = (
                out
                / "work"
                / "EVAL-005"
                / "docs"
                / "plans"
                / "team-invitations"
                / "specs"
                / "01-invite-user"
            )
            spec_dir.mkdir(parents=True)
            (out / "EVAL-005.md").write_text(
                "Wrote spec.md and tasks.json with [SECURITY: TZ-001].\n",
                encoding="utf-8",
            )
            (out / "metadata.json").write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "id": "EVAL-005",
                    "status": "pass",
                    "work_dir": str(out / "work" / "EVAL-005")
                }]
            }), encoding="utf-8")
            (spec_dir / "spec.md").write_text(
                "### AC-\n### TC-\n### T-\n"
                "[SECURITY: TZ-001]\n[CONTRACT: IC-001]\nTraceability Matrix\n",
                encoding="utf-8",
            )
            (spec_dir / "tasks.json").write_text(json.dumps({
                "feature_id": "01-invite-user",
                "spec_revision": 1,
                "tasks": [
                    {"id": "T-1", "verifies": ["TC-1"], "status": "todo"},
                    {"id": "T-2", "verifies": ["TC-2"], "status": "todo"},
                    {"id": "T-3", "verifies": ["TC-3"], "status": "todo"}
                ]
            }), encoding="utf-8")
            res = run("--outputs-dir", str(out))
            self.assertEqual(res.returncode, 1)
            self.assertIn("spec_lint failed", res.stderr)
            self.assertIn("artifact", res.stderr)

    def test_artifact_path_glob_checks_can_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "runs"
            work = out / "work" / "EVAL-008"
            report_dir = work / "docs" / "infra-reviews"
            evidence_dir = report_dir / "evidence" / "2099-01-01-full-repo"
            evidence_dir.mkdir(parents=True)
            (out / "EVAL-008.md").write_text(
                "Findings: 3. Scanners: degraded. evidence written for "
                "Dockerfile:3, k8s/deployment.yaml:17, and terraform/main.tf:8. "
                "Edit withheld.\n",
                encoding="utf-8",
            )
            (out / "metadata.json").write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "id": "EVAL-008",
                    "status": "pass",
                    "work_dir": str(work)
                }]
            }), encoding="utf-8")
            (report_dir / "2099-01-01-full-repo.md").write_text(
                "Scanners used:\nMissing (degraded)\n"
                "P-OPEN-INGRESS terraform/main.tf:8\n"
                "P-LATEST k8s/deployment.yaml:17\n"
                "P-NO-USER Dockerfile\n",
                encoding="utf-8",
            )
            (report_dir / "2099-01-01-full-repo.summary.json").write_text(json.dumps({
                "status": "pass",
                "blocking_hard": 0,
                "formats_detected": {"terraform": 1, "k8s": 1, "dockerfile": 1},
                "secrets_redacted_count": 0,
                "states": {"manifest-read": 3},
                "counts": {"medium": 3}
            }), encoding="utf-8")
            (evidence_dir / "floor-output.json").write_text(json.dumps({
                "status": "pass",
                "supported_files": 3,
                "formats_detected": {"dockerfile": 1, "k8s": 1, "terraform": 1},
                "hard_failures": [],
                "secrets_redacted_count": 0,
                "files_scanned_capped": False,
                "findings": [
                    {"check": "P-NO-USER", "file": "Dockerfile"},
                    {"check": "P-LATEST", "file": "k8s/deployment.yaml"},
                    {"check": "P-OPEN-INGRESS", "file": "terraform/main.tf"}
                ]
            }), encoding="utf-8")
            (evidence_dir / "F-1.txt").write_text(
                "terraform/main.tf cidr_blocks 0.0.0.0/0\n",
                encoding="utf-8",
            )
            (evidence_dir / "F-2_F-4_F-5_F-6.txt").write_text(
                "k8s/deployment.yaml example/orders-api:latest securityContext\n",
                encoding="utf-8",
            )
            (evidence_dir / "F-3_F-8.txt").write_text(
                "Dockerfile COPY . . no USER\n",
                encoding="utf-8",
            )
            res = run("--outputs-dir", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("1 output(s) graded", res.stdout)

    def test_artifact_file_forbidden_substring_failure_is_attributed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "runs"
            work = out / "work" / "EVAL-010"
            checks = work / "checks"
            checks.mkdir(parents=True)
            (out / "EVAL-010.md").write_text(
                "patch-eligible C2 C6 durable noun persistence "
                "/ce-plan Nothing was written to disk\n",
                encoding="utf-8",
            )
            (out / "metadata.json").write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "id": "EVAL-010",
                    "status": "pass",
                    "work_dir": str(work)
                }]
            }), encoding="utf-8")
            (work / "schema.sql").write_text(
                "CREATE TABLE accounts (\n  status TEXT NOT NULL,\n  preference TEXT\n);\n",
                encoding="utf-8",
            )
            (work / "accounts.py").write_text(
                "def account_summary(row: dict) -> str:\n"
                "    return f\"{row['email']} ({row['status']})\"\n",
                encoding="utf-8",
            )
            (checks / "accounts_check.py").write_text(
                "from accounts import account_summary\n"
                "def test_account_summary_includes_email_and_status():\n"
                "    assert account_summary({'email': 'a@example.com', 'status': 'active'})\n",
                encoding="utf-8",
            )
            res = run("--outputs-dir", str(out))
            self.assertEqual(res.returncode, 1)
            self.assertIn("schema.sql", res.stderr)
            self.assertIn("contains forbidden text 'preference'", res.stderr)


class GoldenGates(unittest.TestCase):
    """The deterministic replay gates over frozen evals/golden/ artifacts."""

    def test_golden_gate_count_is_at_least_five(self):
        import re
        res = run()
        self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
        m = re.search(r"(\d+) golden gate\(s\)", res.stdout)
        self.assertIsNotNone(m, res.stdout)
        self.assertGreaterEqual(int(m.group(1)), 5, res.stdout)

    def test_broken_golden_plan_json_fails_plan_lint_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            plan = repo / "evals" / "golden" / "EVAL-004" / "plan.json"
            data = json.loads(plan.read_text())
            # H4: point 02's hard dependency at a feature that does not exist.
            data["features"][1]["dependencies"]["hard"][0]["id"] = "99-does-not-exist"
            plan.write_text(json.dumps(data, indent=2), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("plan_lint failed", res.stderr)
            self.assertIn("99-does-not-exist", res.stderr)

    def test_dropped_blocking_high_key_fails_json_fields_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            summary = repo / "evals" / "golden" / "EVAL-007" / "review-summary.json"
            data = json.loads(summary.read_text())
            del data["blocking_high"]
            summary.write_text(json.dumps(data, indent=2), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("EVAL-007", res.stderr)
            self.assertIn("blocking_high", res.stderr)

    def test_dropped_eligibility_clause_fails_json_fields_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            elig = repo / "evals" / "golden" / "EVAL-009" / "eligibility.json"
            data = json.loads(elig.read_text())
            del data["clauses"]["C7_no_open_unknown"]
            elig.write_text(json.dumps(data, indent=2), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("EVAL-009", res.stderr)
            self.assertIn("C7_no_open_unknown", res.stderr)

    def test_mutated_infra_summary_status_fails_json_fields_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            summary = repo / "evals" / "golden" / "EVAL-008" / "infra-summary.json"
            data = json.loads(summary.read_text())
            data["status"] = "fail"
            summary.write_text(json.dumps(data, indent=2), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("EVAL-008", res.stderr)
            self.assertIn("status", res.stderr)

    def test_unknown_gate_key_fails_catalog_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            for s in data["scenarios"]:
                if s["id"] == "EVAL-004":
                    s["gate_checks"][0]["bogus"] = True
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("unknown key", res.stderr)


class CoverageRatchet(unittest.TestCase):
    def _load_allowlist(self, repo):
        import json
        path = repo / "evals" / "coverage-allowlist.json"
        return path, json.loads(path.read_text(encoding="utf-8"))

    def test_uncovered_skill_without_waiver_fails(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            path, data = self._load_allowlist(repo)
            data["waivers"] = [w for w in data["waivers"] if w["skill"] != "ce-brief"]
            path.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("ce-brief has no eval scenario and no waiver", res.stderr)

    def test_expired_waiver_fails(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            path, data = self._load_allowlist(repo)
            for w in data["waivers"]:
                if w["skill"] == "ce-brief":
                    w["expires"] = "2020-01-01"
            path.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("expired 2020-01-01", res.stderr)

    def test_stale_waiver_for_covered_skill_fails(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            path, data = self._load_allowlist(repo)
            data["waivers"].append({"skill": "ce-ask", "reason": "x", "expires": "2027-01-01"})
            path.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("waiver for ce-ask is stale", res.stderr)

    def test_offschedule_waiver_expiry_fails(self):
        # A live waiver whose expiry is not one of the burndown_schedule tiers
        # is off-schedule — the staggered ratchet rejects a fresh single date.
        import json
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            path, data = self._load_allowlist(repo)
            for w in data["waivers"]:
                if w["skill"] == "ce-brief":
                    w["expires"] = "2028-06-30"
            path.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("not a scheduled burn-down tier", res.stderr)

    def test_tier_over_cap_fails(self):
        # Dropping a tier's max_waivers below its live-waiver count trips the
        # anti-cliff cap: coverage may not pile onto a single date.
        import json
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            path, data = self._load_allowlist(repo)
            for tier in data["burndown_schedule"]:
                if tier["date"] == "2026-11-30":
                    tier["max_waivers"] = 1
            path.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("over its max_waivers cap of 1", res.stderr)

    def test_missing_schedule_with_waivers_fails(self):
        # A waiver list with no burndown_schedule is a regression to a cliff.
        import json
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            path, data = self._load_allowlist(repo)
            del data["burndown_schedule"]
            path.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("burndown_schedule must be a non-empty list", res.stderr)

    def test_duplicate_schedule_date_fails(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            path, data = self._load_allowlist(repo)
            data["burndown_schedule"].append(
                {"date": "2026-09-30", "unblocker": "dupe", "max_waivers": 8}
            )
            path.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("is duplicated", res.stderr)


if __name__ == "__main__":
    unittest.main()
