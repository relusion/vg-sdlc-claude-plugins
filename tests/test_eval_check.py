"""Tests for scripts/eval_check.py, the offline eval-corpus validator."""

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "eval_check.py"
sys.path.insert(0, str(REPO / "scripts"))

import eval_check  # noqa: E402


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


def git_state(repo: Path) -> dict:
    def out(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    branch = subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "--quiet", "--short", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip() or None
    local_config = out("config", "--local", "--list", "--null")
    changed = {
        path for path in out("diff", "--name-only", "-z", "HEAD").split("\0") if path
    }
    changed.update(
        path
        for path in out("ls-files", "--others", "--exclude-standard", "-z").split("\0")
        if path
    )
    ignored_files_sha256 = {}
    ignored_paths = (
        path
        for path in out(
            "ls-files", "--others", "--ignored", "--exclude-standard", "-z"
        ).split("\0")
        if path
    )
    for relative_path in ignored_paths:
        if any(
            part in eval_check.IGNORED_STATE_EXCLUDED_DIRS
            for part in Path(relative_path).parts
        ):
            continue
        path = repo / relative_path
        digest = hashlib.sha256()
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(b"file\0")
            digest.update(path.read_bytes())
        else:
            continue
        ignored_files_sha256[relative_path] = digest.hexdigest()
    return {
        "head": out("rev-parse", "HEAD").strip(),
        "branch": branch,
        "refs": sorted(
            line
            for line in out("for-each-ref", "--format=%(objectname) %(refname)").splitlines()
            if line
        ),
        "worktrees": [
            line for line in out("worktree", "list", "--porcelain").splitlines() if line
        ],
        "local_config_sha256": hashlib.sha256(local_config.encode("utf-8")).hexdigest(),
        "changed_paths": sorted(changed),
        "ignored_files_sha256": dict(sorted(ignored_files_sha256.items())),
    }


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

    def test_spec_workflow_scenarios_require_canonical_ce_spec_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            scenario = next(s for s in data["scenarios"] if s["id"] == "EVAL-005")
            scenario["output_checks"]["required_substrings"][0] = "spec.md"
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("uses legacy spec.md", res.stderr)
            self.assertIn("canonical ce-spec.md", res.stderr)

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

    def test_scenario_timeout_must_be_a_positive_integer(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            data["scenarios"][0]["timeout_seconds"] = 0
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("timeout_seconds must be a positive integer", res.stderr)

    def test_scripted_turn_requires_context_anchor_and_scenario_scoped_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            data["scenarios"][0]["scripted_turns"] = [{
                "event_id": "wrong-event",
                "answer": "Proceed",
                "required_previous_output": [],
            }]
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("event_id must start with EVAL-001-", res.stderr)
            self.assertIn("must contain at least one gate/context anchor", res.stderr)

    def test_scripted_turn_rejects_unknown_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            data["scenarios"][0]["scripted_turns"] = [{
                "event_id": "EVAL-001-D01",
                "answer": "Proceed",
                "required_previous_output": ["Gate 1 of"],
                "invented": True,
            }]
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("scripted_turns.0 has unknown key(s): invented", res.stderr)

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

    def test_output_substring_checks_can_opt_into_case_insensitive_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            checks = data["scenarios"][2]["output_checks"]
            checks["required_substrings"] = []
            checks["required_substrings_case_insensitive"] = [
                "Not analyzable yet",
                "too thin to ground",
            ]
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            out = Path(tmp) / "runs"
            out.mkdir()
            (out / "EVAL-003.md").write_text(
                "NOT ANALYZABLE YET — TOO THIN TO GROUND\n",
                encoding="utf-8",
            )
            res = run("--root", str(repo), "--outputs-dir", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)

    def test_output_identifiers_remain_case_sensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            scenarios = repo / "evals" / "scenarios.json"
            data = json.loads(scenarios.read_text())
            data["scenarios"][2]["output_checks"] = {
                "required_substrings": ["WEBHOOK_TOKEN"]
            }
            scenarios.write_text(json.dumps(data), encoding="utf-8")
            out = Path(tmp) / "runs"
            out.mkdir()
            (out / "EVAL-003.md").write_text("webhook_token\n", encoding="utf-8")
            res = run("--root", str(repo), "--outputs-dir", str(out))
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing required text 'WEBHOOK_TOKEN'", res.stderr)

    def test_patch_red_evidence_does_not_match_word_fragment(self):
        catalog = json.loads((REPO / "evals" / "scenarios.json").read_text())
        checks = next(
            scenario["output_checks"]
            for scenario in catalog["scenarios"]
            if scenario["id"] == "EVAL-009"
        )
        text = (
            "Gate 1 of 1 Patch acceptance required Green command/result: pass "
            "Accept /core-engineering:ce-plan"
        )
        errors = eval_check.grade_one_output("EVAL-009", text, checks)
        self.assertTrue(any("Red command/result:" in error for error in errors))

    def test_ce_go_scenario_pins_direct_only_route_and_zero_writes(self):
        catalog = json.loads((REPO / "evals" / "scenarios.json").read_text())
        scenario = next(
            item for item in catalog["scenarios"] if item["id"] == "EVAL-019"
        )
        self.assertNotIn("ce-patch", scenario["prompt"])
        self.assertIn(
            "Routing to /core-engineering:ce-patch",
            scenario["output_checks"]["required_substrings"],
        )
        self.assertEqual(scenario["git_checks"]["changed_paths_exact"], [])
        for key in (
            "head_unchanged",
            "branch_unchanged",
            "refs_unchanged",
            "worktrees_unchanged",
            "local_config_unchanged",
        ):
            self.assertIs(scenario["git_checks"][key], True)

        passing = (
            "Gate 1 of 1 — confirm the route\n"
            "Routing to /core-engineering:ce-patch because this is a bounded typo fix.\n"
            "Proceed | Pick another | Abort\n"
        )
        self.assertEqual(
            eval_check.grade_one_output(
                "EVAL-019", passing, scenario["output_checks"]
            ),
            [],
        )
        wrong_route = passing.replace("ce-patch", "ce-plan")
        self.assertTrue(
            any(
                "Routing to /core-engineering:ce-patch" in error
                for error in eval_check.grade_one_output(
                    "EVAL-019", wrong_route, scenario["output_checks"]
                )
            )
        )

    def test_ce_architecture_scenario_stops_at_scope_gate_without_publication(self):
        catalog = json.loads((REPO / "evals/scenarios.json").read_text())
        scenario = next(
            item for item in catalog["scenarios"] if item["id"] == "EVAL-020"
        )
        required = scenario["output_checks"]["required_substrings"]
        self.assertIn("Scope Confirmation", required)
        self.assertIn("Proceed with this evidence set", required)
        self.assertIn(
            "Architecture written:",
            scenario["output_checks"]["forbidden_substrings"],
        )
        self.assertEqual(
            scenario["artifact_checks"],
            [{
                "type": "path_absent",
                "path": "docs/plans/team-invitations-rbac/architecture",
            }],
        )
        self.assertEqual(
            set(scenario["git_checks"]["allowed_changed_path_globs"]),
            {
                ".claude/ce-write-scope.json",
                ".claude/ce-write-scope.session.json",
                ".claude/ce-guard-log.jsonl",
            },
        )

    def test_eval017_retry_sentinel_is_unconditional(self):
        path = (
            REPO / "evals/fixtures/auto-build-three-feature/checks/export_check.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"))
        test_fn = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "test_export_csv_matches_golden"
        )
        final = test_fn.body[-1]
        self.assertIsInstance(final, ast.Expr)
        self.assertIsInstance(final.value, ast.Call)
        self.assertIsInstance(final.value.func, ast.Attribute)
        self.assertEqual(final.value.func.attr, "fail")
        self.assertIn(
            "EVAL-017_RETRY_SENTINEL",
            ast.literal_eval(final.value.args[0]),
        )

    def test_eval017_sentinel_activates_when_feature_spec_exists(self):
        class SentinelFailure(Exception):
            pass

        class Mark:
            @staticmethod
            def skipif(condition, reason):
                def decorate(fn):
                    fn.eval_skip = bool(condition)
                    fn.eval_skip_reason = reason
                    return fn
                return decorate

        fake_pytest = types.SimpleNamespace(
            mark=Mark(),
            fail=lambda message: (_ for _ in ()).throw(SentinelFailure(message)),
        )
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixture"
            shutil.copytree(REPO / "evals/fixtures/auto-build-three-feature", fixture)
            export_check = fixture / "checks/export_check.py"
            old_pytest = sys.modules.get("pytest")
            old_snippets = sys.modules.get("snippets")
            sys.modules["pytest"] = fake_pytest
            sys.path.insert(0, str(fixture))

            def load(name):
                sys.modules.pop("snippets", None)
                spec = importlib.util.spec_from_file_location(name, export_check)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module

            try:
                dormant = load("export_check_dormant")
                self.assertTrue(dormant.test_export_csv_matches_golden.eval_skip)

                spec_dir = (
                    fixture
                    / "docs/plans/snippet-vault/specs/03-export-snippets"
                )
                spec_dir.mkdir(parents=True)
                (spec_dir / "ce-spec.md").write_text("# active\n", encoding="utf-8")
                missing = load("export_check_missing")
                self.assertFalse(missing.test_export_csv_matches_golden.eval_skip)
                with self.assertRaisesRegex(AssertionError, "started without export_csv"):
                    missing.test_export_csv_matches_golden()

                with (fixture / "snippets.py").open("a", encoding="utf-8") as stream:
                    stream.write(
                        "\ndef add_snippet(store, *, title, body, language):\n"
                        "    item = Snippet(store._next_id, title, body, language)\n"
                        "    store._next_id += 1\n"
                        "    store.snippets.append(item)\n"
                        "    return item\n"
                        "\ndef export_csv(store):\n"
                        "    return 'id,title\\n' + ''.join(\n"
                        "        f'{item.id},{item.title}\\n' for item in store.snippets\n"
                        "    )\n"
                    )
                correct = load("export_check_correct")
                with self.assertRaisesRegex(SentinelFailure, "EVAL-017_RETRY_SENTINEL"):
                    correct.test_export_csv_matches_golden()
            finally:
                sys.path.remove(str(fixture))
                if old_pytest is None:
                    sys.modules.pop("pytest", None)
                else:
                    sys.modules["pytest"] = old_pytest
                if old_snippets is None:
                    sys.modules.pop("snippets", None)
                else:
                    sys.modules["snippets"] = old_snippets

    def test_jsonl_records_correlate_and_count_repair_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            repair = {
                "event": "repair-attempt",
                "feature": "03-export-snippets",
                "attempt": 1,
                "outcome": "gates-fail",
                "evidence": "EVAL-017_RETRY_SENTINEL",
            }
            path.write_text(
                json.dumps({"event": "park", "feature": "02-share-snippet"})
                + "\n" + json.dumps(repair) + "\n",
                encoding="utf-8",
            )
            check = {
                "type": "jsonl_records",
                "where": {"event": "repair-attempt", "feature": "03-export-snippets"},
                "equals": {"attempt": 1, "outcome": "gates-fail"},
                "contains": {"evidence": ["EVAL-017_RETRY_SENTINEL"]},
                "count": 1,
            }
            self.assertEqual(
                eval_check.grade_artifact_target(
                    REPO, "EVAL-017", check, "jsonl_records", path
                ),
                [],
            )
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(repair) + "\n")
            errors = eval_check.grade_artifact_target(
                REPO, "EVAL-017", check, "jsonl_records", path
            )
            self.assertTrue(any("matched 2" in error for error in errors))

    def test_git_checks_reject_post_run_untracked_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "runs"
            work = out / "work" / "EVAL-010"
            shutil.copytree(REPO / "evals/fixtures/schema-change-service", work)
            (work / ".gitignore").write_text(".claude/\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(work), "init", "--quiet"], check=True)
            subprocess.run(["git", "-C", str(work), "add", "--all"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(work),
                    "-c", "user.name=Eval", "-c", "user.email=eval@example.invalid",
                    "commit", "--quiet", "--no-gpg-sign", "-m", "baseline",
                ],
                check=True,
            )
            snapshot = git_state(work)
            out.mkdir(exist_ok=True)
            (out / "EVAL-010.md").write_text(
                "E1 E5 schema /core-engineering:ce-plan\nWorking tree: no patch edit\n",
                encoding="utf-8",
            )
            (out / "metadata.json").write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "id": "EVAL-010",
                    "status": "pass",
                    "work_dir": str(work),
                    "git_state": {"before": snapshot, "after": snapshot},
                }],
            }), encoding="utf-8")

            ignored = work / ".claude" / "unexpected-policy.md"
            ignored.parent.mkdir()
            ignored.write_text("unexpected = true\n", encoding="utf-8")
            ignored_res = run("--outputs-dir", str(out))
            self.assertEqual(ignored_res.returncode, 1)
            self.assertIn("changed after the runner captured", ignored_res.stderr)
            self.assertIn(".claude/unexpected-policy.md", ignored_res.stderr)
            ignored.unlink()
            ignored.parent.rmdir()

            subprocess.run(["git", "-C", str(work), "tag", "unexpected-tag"], check=True)
            tagged = run("--outputs-dir", str(out))
            self.assertEqual(tagged.returncode, 1)
            self.assertIn("Git refs changed", tagged.stderr)

            subprocess.run(
                ["git", "-C", str(work), "config", "eval.unexpected", "true"],
                check=True,
            )
            configured = run("--outputs-dir", str(out))
            self.assertEqual(configured.returncode, 1)
            self.assertIn("local Git config changed", configured.stderr)

            (work / "rogue.py").write_text("unexpected = True\n", encoding="utf-8")

            res = run("--outputs-dir", str(out))
            self.assertEqual(res.returncode, 1)
            self.assertIn("changed after the runner captured", res.stderr)
            self.assertIn("expected exactly []", res.stderr)

            subprocess.run(["git", "-C", str(work), "add", "rogue.py"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(work),
                    "-c", "user.name=Eval", "-c", "user.email=eval@example.invalid",
                    "commit", "--quiet", "--no-gpg-sign", "-m", "unauthorized",
                ],
                check=True,
            )
            committed = run("--outputs-dir", str(out))
            self.assertEqual(committed.returncode, 1)
            self.assertIn("Git HEAD changed", committed.stderr)
            self.assertIn("Git refs changed", committed.stderr)

    def test_git_checks_include_relevant_ignored_file_deltas_but_skip_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "runs"
            work = out / "work" / "EVAL-010"
            shutil.copytree(REPO / "evals/fixtures/schema-change-service", work)
            (work / ".gitignore").write_text(
                ".claude/\n.pytest_cache/\nnode_modules/\nbuild/\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(work), "init", "--quiet"], check=True)
            subprocess.run(["git", "-C", str(work), "add", "--all"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(work),
                    "-c", "user.name=Eval", "-c", "user.email=eval@example.invalid",
                    "commit", "--quiet", "--no-gpg-sign", "-m", "baseline",
                ],
                check=True,
            )

            ignored = work / ".claude"
            ignored.mkdir()
            (ignored / "modified-policy.md").write_text("before\n", encoding="utf-8")
            (ignored / "removed-policy.md").write_text("before\n", encoding="utf-8")
            before = git_state(work)

            (ignored / "unexpected-policy.md").write_text("added\n", encoding="utf-8")
            (ignored / "modified-policy.md").write_text("after\n", encoding="utf-8")
            (ignored / "removed-policy.md").unlink()
            for relative in (
                ".pytest_cache/state.json",
                "node_modules/example/index.js",
                "build/generated.txt",
            ):
                path = work / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("ephemeral\n", encoding="utf-8")
            after = git_state(work)

            out.mkdir(exist_ok=True)
            (out / "EVAL-010.md").write_text(
                "E1 E5 schema /core-engineering:ce-plan\nWorking tree: no patch edit\n",
                encoding="utf-8",
            )
            (out / "metadata.json").write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "id": "EVAL-010",
                    "status": "pass",
                    "work_dir": str(work),
                    "git_state": {"before": before, "after": after},
                }],
            }), encoding="utf-8")

            res = run("--outputs-dir", str(out))
            self.assertEqual(res.returncode, 1)
            self.assertNotIn("changed after the runner captured", res.stderr)
            self.assertIn(
                "final changed paths ['.claude/modified-policy.md', "
                "'.claude/removed-policy.md', '.claude/unexpected-policy.md']",
                res.stderr,
            )
            self.assertNotIn(".pytest_cache", res.stderr)
            self.assertNotIn("node_modules", res.stderr)
            self.assertNotIn("build/generated.txt", res.stderr)

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

    def test_require_all_outputs_uses_metadata_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "runs"
            out.mkdir()
            (out / "metadata.json").write_text(json.dumps({
                "schema_version": 1,
                "records": [{"id": "EVAL-003", "status": "pass"}],
            }), encoding="utf-8")
            (out / "EVAL-003.md").write_text(
                "Not analyzable yet — too thin to ground\n", encoding="utf-8"
            )
            selected = run("--outputs-dir", str(out), "--require-all-outputs")
            self.assertEqual(selected.returncode, 0, selected.stderr)

            (out / "EVAL-003.md").unlink()
            missing = run("--outputs-dir", str(out), "--require-all-outputs")
            self.assertEqual(missing.returncode, 1)
            self.assertIn("EVAL-003: missing output file", missing.stderr)

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
                "Wrote ce-spec.md and tasks.json with [SECURITY: TZ-001].\n",
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
            (spec_dir / "ce-spec.md").write_text(
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

    def test_artifact_architecture_lint_failure_is_attributed(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "repo"
            shutil.copytree(REPO / "evals/golden/EVAL-020", work)
            arch_dir = (
                work
                / "docs/plans/team-invitations-rbac/architecture"
            )
            manifest_path = arch_dir / "architecture.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["relationships"][0]["to"] = "C-999"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            errors = eval_check.grade_artifact_target(
                REPO,
                "EVAL-020",
                {"type": "architecture_lint", "path": "unused"},
                "architecture_lint",
                arch_dir,
                artifact_repo_root=work,
            )
            self.assertTrue(
                any("architecture_lint failed" in error for error in errors),
                errors,
            )
            self.assertTrue(any("C-999" in error for error in errors), errors)

    def test_path_absent_artifact_check_catches_premature_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "docs/plans/demo/architecture"
            check = {"type": "path_absent", "path": "docs/plans/demo/architecture"}
            self.assertEqual(
                eval_check.grade_artifact_target(
                    REPO, "EVAL-020", check, "path_absent", target
                ),
                [],
            )
            target.mkdir(parents=True)
            errors = eval_check.grade_artifact_target(
                REPO, "EVAL-020", check, "path_absent", target
            )
            self.assertTrue(any("before human approval" in error for error in errors))

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
                "/core-engineering:ce-plan Nothing was written to disk\n",
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

    def test_golden_gate_count_is_at_least_six(self):
        import re
        res = run()
        self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
        m = re.search(r"(\d+) golden gate\(s\)", res.stdout)
        self.assertIsNotNone(m, res.stdout)
        self.assertGreaterEqual(int(m.group(1)), 6, res.stdout)

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

    def test_dangling_golden_architecture_endpoint_fails_architecture_lint_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            manifest_path = (
                repo
                / "evals/golden/EVAL-020/docs/plans/team-invitations-rbac/"
                "architecture/architecture.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["relationships"][0]["to"] = "C-999"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("architecture_lint failed", res.stderr)
            self.assertIn("C-999", res.stderr)

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

    def test_dropped_patch_candidate_file_fails_json_fields_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_eval_repo(Path(tmp))
            candidate = repo / "evals" / "golden" / "EVAL-009" / "express.json"
            data = json.loads(candidate.read_text())
            data["files"].pop()
            candidate.write_text(json.dumps(data, indent=2), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("EVAL-009", res.stderr)
            self.assertIn("files.1", res.stderr)

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
