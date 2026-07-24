"""Tests for scripts/product_layer_check.py, the product-doc drift gate."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "product_layer_check.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def inject_pass_row(bench_path: Path, eval_id: str, date: str = "2026-06-27") -> None:
    """Append a synthetic `pass (DATE)` row to a copied BENCHMARKS table.

    The real table now carries only design-verified rows (the recency ratchet
    degraded the 2026-06-27 batch), so provenance tests mint their own live-pass
    claim rather than lean on the committed doc state. No backticks: the row must
    not trip the doc-link check's repo-path detection.
    """
    text = bench_path.read_text(encoding="utf-8")
    text += (f"\n| {eval_id} | ce-x skill | injected live-pass claim "
             f"| $1.00 | pass ({date}) |\n")
    bench_path.write_text(text, encoding="utf-8")


def copy_repo(tmp: Path) -> Path:
    dst = tmp / "repo"
    # check_doc_links resolves references into templates/, tests/, and evals/,
    # so the copy carries every referenced tree (never the gitignored
    # evals/runs/) to stay faithful to a fresh checkout.
    for sub in (".github", "action", "docs", "plugins", "scripts", "templates", "tests"):
        shutil.copytree(REPO / sub, dst / sub, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "evals", dst / "evals",
                    ignore=shutil.ignore_patterns("__pycache__", "runs"))
    for name in (".gitignore", "README.md", "CLAUDE.md", "CONTRIBUTING.md",
                 "COMMERCIAL.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md", "LICENSE"):
        shutil.copy2(REPO / name, dst / name)
    return dst


def init_git_repo(root: Path) -> str:
    (root / "receipt-anchor.txt").write_text("anchor\n", encoding="utf-8")
    (root / "evals").mkdir(exist_ok=True)
    (root / "evals" / "scenarios.json").write_text(json.dumps({
        "schema_version": 1,
        "scenarios": [
            {"id": "EVAL-901", "skill": "ce-x", "fixture": "receipt-fixture"},
            {"id": "EVAL-902", "skill": "ce-x", "fixture": "receipt-fixture"},
        ],
    }), encoding="utf-8")
    skill_dir = root / "plugins/core-engineering/skills/ce-x"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# ce-x\n", encoding="utf-8")
    fixture_dir = root / "evals/fixtures/receipt-fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "README.md").write_text("fixture\n", encoding="utf-8")
    scripts_dir = root / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    for name in ("eval_run.py", "eval_check.py"):
        (scripts_dir / name).write_text(f"# {name}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
    subprocess.run(
        [
            "git", "-C", str(root),
            "-c", "user.name=Eval", "-c", "user.email=eval@example.invalid",
            "commit", "--quiet", "--no-gpg-sign", "-m", "receipt anchor",
        ],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def commit_all(root: Path, message: str = "commit receipt") -> str:
    """Commit a synthetic result so provenance tests exercise HEAD bytes."""
    subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
    subprocess.run(
        [
            "git", "-C", str(root),
            "-c", "user.name=Eval", "-c", "user.email=eval@example.invalid",
            "commit", "--quiet", "--no-gpg-sign", "-m", message,
        ],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


class ProductLayerCheck(unittest.TestCase):
    def test_this_repo_product_layer_passes(self):
        res = run()
        self.assertEqual(res.returncode, 0, f"stdout={res.stdout}\nstderr={res.stderr}")
        self.assertIn("product-layer: OK", res.stdout)

    def test_usage_matrix_must_cover_every_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            matrix = repo / "docs" / "USAGE-MATRIX.md"
            # Strip every mention (the skill also appears in Default Routes),
            # without minting an unknown namespaced command.
            matrix.write_text(
                matrix.read_text(encoding="utf-8").replace(
                    "/core-engineering:ce-probe-infra", "/probe-infra"
                ),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing shipped skill", res.stderr)
            self.assertIn("/core-engineering:ce-probe-infra", res.stderr)

    def test_readme_must_link_product_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace("docs/GETTING-STARTED.md", "docs/START.md"),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("docs/GETTING-STARTED.md", res.stderr)

    def test_ci_must_run_umbrella_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            workflow = repo / ".github" / "workflows" / "plugin-validate.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "python3 scripts/check.py --no-install-hooks",
                    "python3 scripts/check.py --skip-validation",
                ),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing umbrella validation step", res.stderr)

    def test_runtime_sidecars_must_be_gitignored_and_bootstrapped(self):
        for runtime_entry in (
            ".claude/ce-write-scope.session.json",
            "**/.architecture-frame-change-receipt.json",
        ):
            with self.subTest(runtime_entry=runtime_entry):
                with tempfile.TemporaryDirectory() as tmp:
                    repo = copy_repo(Path(tmp))
                    ignore = repo / ".gitignore"
                    ignore.write_text(
                        ignore.read_text(encoding="utf-8").replace(
                            runtime_entry, ""
                        ),
                        encoding="utf-8",
                    )
                    res = run("--root", str(repo))
                    self.assertEqual(res.returncode, 1)
                    self.assertIn(runtime_entry, res.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            init_skill = (
                repo / "plugins/core-engineering/skills/ce-init/SKILL.md"
            )
            init_skill.write_text(
                init_skill.read_text(encoding="utf-8").replace(
                    "**/.architecture-frame-change-receipt.json", ""
                ),
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn(
                "plugins/core-engineering/skills/ce-init/SKILL.md", res.stderr
            )
            self.assertIn(
                "**/.architecture-frame-change-receipt.json", res.stderr
            )


class Freshness(unittest.TestCase):
    def test_stale_as_of_date_fails(self):
        import re
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            comp = repo / "docs" / "COMPARISON.md"
            text = comp.read_text(encoding="utf-8")
            stale = re.sub(r"as of\s+\*{0,2}\d{4}-\d{2}-\d{2}\*{0,2}", "as of 2025-01-01", text)
            self.assertNotEqual(text, stale, "fixture drift: no as-of date found")
            comp.write_text(stale, encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("days old", res.stderr)


class SupportedSurface(unittest.TestCase):
    def test_comparison_inventory_must_match_shipped_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            comparison = repo / "docs" / "COMPARISON.md"
            text = comparison.read_text(encoding="utf-8")
            changed = text.replace(
                "(32 skills across 2 plugins)", "(33 skills across 2 plugins)"
            )
            self.assertNotEqual(text, changed, "fixture drift: inventory not found")
            comparison.write_text(changed, encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("supported inventory says 33 skills", res.stderr)
            self.assertIn("contains 32 skills", res.stderr)

    def test_retired_delivery_claims_and_duplicate_validator_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            enterprise = repo / "docs" / "ENTERPRISE-HARDENING.md"
            enterprise.write_text(
                enterprise.read_text(encoding="utf-8")
                + "\nrelease/delivery prompts\n"
                + "python3 scripts/check.py --no-install-hooks\n"
                + "python3 scripts/supply_chain_check.py\n",
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("retired surface claim", res.stderr)
            self.assertIn("already delegates to it", res.stderr)

    def test_retired_auto_build_diagnose_mode_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            debug = repo / "plugins/core-engineering/skills/ce-debug/SKILL.md"
            debug.write_text(
                debug.read_text(encoding="utf-8")
                + "\n`/core-engineering:ce-auto-build` invokes debug through its Diagnose Gate.\n",
                encoding="utf-8",
            )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("retired surface claim", res.stderr)
            self.assertIn("Diagnose Gate", res.stderr)


class SupervisionSurface(unittest.TestCase):
    """The mid-flight/unattended orientation surface must not silently vanish."""

    def test_deleting_the_return_mid_flight_recipe_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            recipes = repo / "docs" / "WORKFLOW-RECIPES.md"
            text = recipes.read_text(encoding="utf-8")
            gutted = text.replace("## Recipe 19: Return To A Plan Mid-Flight",
                                  "## Recipe 19: Removed")
            self.assertNotEqual(text, gutted, "fixture drift: Recipe 19 heading not found")
            recipes.write_text(gutted, encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("Return To A Plan Mid-Flight", res.stderr)

    def test_recipes_losing_resume_and_status_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            recipes = repo / "docs" / "WORKFLOW-RECIPES.md"
            text = recipes.read_text(encoding="utf-8")
            gutted = text.replace("--resume", "--continue").replace(
                "STATUS.md", "STATE.md")
            self.assertNotEqual(text, gutted, "fixture drift: supervision needles not found")
            recipes.write_text(gutted, encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("'--resume'", res.stderr)
            self.assertIn("'STATUS.md'", res.stderr)

    def test_readme_must_reference_docs_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            readme = repo / "README.md"
            text = readme.read_text(encoding="utf-8")
            gutted = text.replace("docs/README.md", "docs/INDEX.md")
            self.assertNotEqual(text, gutted, "fixture drift: docs index link not found")
            readme.write_text(gutted, encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("docs/README.md", res.stderr)

    def test_missing_docs_index_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            (repo / "docs" / "README.md").unlink()
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing: docs/README.md", res.stderr)

    def test_autobuild_recipe_must_route_plan_audit(self):
        # ce-plan-audit elsewhere in the file (Recipe 14) must not satisfy the
        # section-scoped check: strip it from Recipe 10's section only.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            recipes = repo / "docs" / "WORKFLOW-RECIPES.md"
            text = recipes.read_text(encoding="utf-8")
            start = text.find("## Recipe 10: Run The Full Spine Autonomously")
            self.assertNotEqual(start, -1, "fixture drift: Recipe 10 heading not found")
            end = text.find("\n## ", start + 1)
            section = text[start:end]
            audit = "/core-engineering:ce-plan-audit"
            self.assertIn(audit, section, "fixture drift: audit step not in Recipe 10")
            gutted = text[:start] + section.replace(
                audit, "/core-engineering:ce-plan"
            ) + text[end:]
            recipes.write_text(gutted, encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("Recipe 10", res.stderr)
            self.assertIn(audit, res.stderr)


class FrontDoorParity(unittest.TestCase):
    """check_front_door_parity: ce-go's routing table and USAGE-MATRIX must
    route to exactly the same skills (excluding ce-go itself)."""

    CE_GO = ("plugins", "core-engineering", "skills", "ce-go", "SKILL.md")
    START = "<!-- routing-table:start -->"
    END = "<!-- routing-table:end -->"

    def _slice_block(self, text):
        start = text.index(self.START) + len(self.START)
        end = text.index(self.END)
        return text[:start], text[start:end], text[end:]

    def test_removing_a_routing_row_fails(self):
        # The Done-when guarantee: drop a skill from ce-go's table and the
        # parity lint must go red for exactly that skill.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            skill = repo.joinpath(*self.CE_GO)
            head, block, tail = self._slice_block(skill.read_text(encoding="utf-8"))
            review = "/core-engineering:ce-review"
            self.assertIn(review, block, "fixture drift: ce-review not routed")
            block = block.replace(review, "/ce_review")  # break the token
            skill.write_text(head + block + tail, encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("routing table missing", res.stderr)
            self.assertIn(review, res.stderr)

    def test_routing_a_skill_not_in_the_matrix_fails(self):
        # The reverse direction: a ce-go route naming a skill the matrix does
        # not route to is stale and must fail.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            skill = repo.joinpath(*self.CE_GO)
            head, block, tail = self._slice_block(skill.read_text(encoding="utf-8"))
            block += "\n| a bogus request | `/core-engineering:ce-bogus` | not a real skill |\n"
            skill.write_text(head + block + tail, encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("not in", res.stderr)
            self.assertIn("/core-engineering:ce-bogus", res.stderr)

    def test_missing_routing_markers_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            skill = repo.joinpath(*self.CE_GO)
            text = skill.read_text(encoding="utf-8").replace(self.START, "<!-- gone -->")
            skill.write_text(text, encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("routing-table markers", res.stderr)


class DocLinkIntegrity(unittest.TestCase):
    """check_doc_links: repo-file references in README + docs must resolve."""

    def test_dangling_markdown_link_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            readme = repo / "README.md"
            with readme.open("a", encoding="utf-8") as fh:
                fh.write("\nSee [the guide](docs/NO-SUCH-GUIDE.md) for details.\n")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("dead markdown link", res.stderr)
            self.assertIn("docs/NO-SUCH-GUIDE.md", res.stderr)

    def test_dangling_backtick_citation_fails(self):
        # The exact incident shape this check exists for: a backtick citation
        # of a doc that was purged (`docs/ROADMAP.md`) with CI none the wiser.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            how = repo / "docs" / "HOW-IT-WORKS.md"
            with how.open("a", encoding="utf-8") as fh:
                fh.write("\nThe roadmap lives in `docs/ROADMAP.md`.\n")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("dead repo path", res.stderr)
            self.assertIn("docs/ROADMAP.md", res.stderr)

    def test_placeholders_and_adopter_paths_do_not_false_positive(self):
        # Placeholders, globs, adopter-side artifact roots, and fenced code
        # blocks are all documented skip rules — none of these may go red.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            started = repo / "docs" / "GETTING-STARTED.md"
            with started.open("a", encoding="utf-8") as fh:
                fh.write(
                    "\nArtifacts land in `docs/plans/<slug>/plan.json` and\n"
                    "`docs/plans/review-policy.md`; hooks glob\n"
                    "`plugins/*/hooks/*.py`. See [the feature file](features/<id>.md).\n"
                    "\n```\nA fenced example may cite `scripts/not-built-yet.py`.\n```\n"
                )
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 0,
                             f"stdout={res.stdout}\nstderr={res.stderr}")

    def test_nested_contributor_docs_are_scanned(self):
        # Contributor references moved below docs/contributing; recursive link
        # checking must cover them just as it covers the public docs root.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            standard = repo / "docs" / "contributing" / "SKILL-AUTHORING.md"
            with standard.open("a", encoding="utf-8") as fh:
                fh.write("\nSee `scripts/not-a-real-check.py`.\n")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("scripts/not-a-real-check.py", res.stderr)


class LeanWorkflowDocs(unittest.TestCase):
    """The concise public route must keep the breaking workflow semantics."""

    def test_canonical_docs_keep_the_adaptive_path_and_final_release_order(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        how = (REPO / "docs" / "HOW-IT-WORKS.md").read_text(encoding="utf-8")
        matrix = (REPO / "docs" / "USAGE-MATRIX.md").read_text(encoding="utf-8")
        recipes = (REPO / "docs" / "WORKFLOW-RECIPES.md").read_text(encoding="utf-8")

        for text in (readme, how, matrix, recipes):
            self.assertIn("compact", text)
            self.assertIn("explicit", text)
            self.assertNotIn("single-feature-minimal", text)

        self.assertIn("optional specialist", readme)
        self.assertIn("Architecture only when load-bearing", how)
        self.assertIn("question / inspect / adjust", how)
        self.assertIn("Independent assurance, one handoff", how)
        self.assertIn("ce-ship-release` is the final workflow", how)

        release = recipes.index("## Recipe 9: Prepare A Release Handoff")
        next_recipe = recipes.index("\n## Recipe 10:", release)
        release_recipe = recipes[release:next_recipe]
        self.assertLess(
            release_recipe.index("/core-engineering:ce-ship-document"),
            release_recipe.index("/core-engineering:ce-ship-release"),
        )
        self.assertLess(
            release_recipe.index("/core-engineering:ce-doc-audit"),
            release_recipe.index("/core-engineering:ce-ship-release"),
        )

    def test_hitl_docs_do_not_gate_clean_deterministic_results(self):
        hitl = (
            REPO / "docs" / "contributing" / "HITL-GATE-STANDARD.md"
        ).read_text(encoding="utf-8")
        self.assertIn("A gate is for a real human decision", hitl)
        self.assertIn("a deterministic validator returned PASS", hitl)
        self.assertIn("inspect or ask a question", hitl)
        self.assertIn("adjust the frame or an option", hitl)


class LiveEvalProvenance(unittest.TestCase):
    def test_ci_summary_top_level_run_id_backs_scenario(self):
        # eval-live's distiller writes one run_id at the summary root and omits
        # it from each scenario. That documented CI shape is a complete receipt.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "evals" / "results").mkdir(parents=True)
            head = init_git_repo(root)
            (root / "docs" / "BENCHMARKS.md").write_text(
                "| EVAL-901 | ce-x | ci receipt | $1.00 | pass (2026-07-20) |\n",
                encoding="utf-8",
            )
            (root / "evals" / "results" / "ci-summary.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "run_id": "20260720-120000Z",
                    "completed_at": "2026-07-20T12:00:00Z",
                    "git_head": head,
                    "source_clean": True,
                    "dry_run": False,
                    "grade_status": "pass",
                    "grade_returncode": 0,
                    "graded_scenarios": ["EVAL-901", "EVAL-902"],
                    "scenarios": [
                        {
                            "id": "EVAL-901",
                            "skill": "ce-x",
                            "status": "pass",
                            "returncode": 0,
                        },
                        {
                            "id": "EVAL-902",
                            "skill": "ce-x",
                            "status": "pass",
                            "returncode": 0,
                        },
                    ],
                }),
                encoding="utf-8",
            )
            commit_all(root)
            scripts = str(REPO / "scripts")
            if scripts not in sys.path:
                sys.path.insert(0, scripts)
            import product_layer_check  # noqa: E402

            errors = []
            product_layer_check.check_live_eval_provenance(root, errors)
            self.assertEqual(errors, [])

            (root / "evals" / "results" / "duplicate-id.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "run_id": "20260720-120000Z",
                    "completed_at": "2026-07-20T12:01:00Z",
                    "dry_run": False,
                    "scenarios": [],
                }),
                encoding="utf-8",
            )
            commit_all(root, "commit duplicate receipt")
            errors = []
            product_layer_check.check_live_eval_provenance(root, errors)
            self.assertEqual(len(errors), 1)
            self.assertIn("unique run_id", errors[0])

    def test_incomplete_or_duplicate_receipt_does_not_back_live_claim(self):
        scripts = str(REPO / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import product_layer_check  # noqa: E402

        invalid_overrides = (
            {"source_clean": False},
            {"git_head": None},
            {"git_head": "f" * 40},
            {"grade_status": "failed", "grade_returncode": 1},
            {"graded_scenarios": []},
        )
        for override in invalid_overrides:
            with self.subTest(override=override), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "docs").mkdir()
                (root / "evals" / "results").mkdir(parents=True)
                head = init_git_repo(root)
                (root / "docs" / "BENCHMARKS.md").write_text(
                    "| EVAL-901 | ce-x | receipt | $1.00 | pass (2026-07-20) |\n",
                    encoding="utf-8",
                )
                summary = {
                    "schema_version": 1,
                    "run_id": "eval-live-123-1",
                    "completed_at": "2026-07-20T12:00:00Z",
                    "git_head": head,
                    "source_clean": True,
                    "dry_run": False,
                    "grade_status": "pass",
                    "grade_returncode": 0,
                    "graded_scenarios": ["EVAL-901"],
                    "scenarios": [{
                        "id": "EVAL-901", "status": "pass", "returncode": 0,
                    }],
                }
                summary.update(override)
                (root / "evals" / "results" / "ci.json").write_text(
                    json.dumps(summary), encoding="utf-8"
                )
                commit_all(root)
                errors = []
                product_layer_check.check_live_eval_provenance(root, errors)
                self.assertEqual(len(errors), 1)
                self.assertIn("promotable live pass", errors[0])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "evals" / "results").mkdir(parents=True)
            head = init_git_repo(root)
            (root / "docs" / "BENCHMARKS.md").write_text(
                "| EVAL-901 | ce-x | receipt | $1.00 | pass (2026-07-20) |\n",
                encoding="utf-8",
            )
            (root / "evals" / "results" / "aggregate.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "completed_at": "2026-07-20T12:00:00Z",
                    "dry_run": False,
                    "scenarios": [
                        {
                            "id": "EVAL-901",
                            "status": "pass",
                            "returncode": 0,
                            "run_id": "reused-local-id",
                            "git_head": head,
                            "source_clean": True,
                            "grade_status": "pass",
                            "grade_returncode": 0,
                            "graded": True,
                        },
                        {
                            "id": "EVAL-902",
                            "status": "failed",
                            "returncode": 1,
                            "run_id": "reused-local-id",
                        },
                    ],
                }),
                encoding="utf-8",
            )
            commit_all(root)
            errors = []
            product_layer_check.check_live_eval_provenance(root, errors)
            self.assertEqual(len(errors), 1)
            self.assertIn("unique run_id", errors[0])

    def test_receipt_commit_must_contain_current_eval_contract(self):
        scripts = str(REPO / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import product_layer_check  # noqa: E402

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "evals" / "results").mkdir(parents=True)
            old_head = init_git_repo(root)
            skill = root / "plugins/core-engineering/skills/ce-x/SKILL.md"
            skill.write_text("# ce-x\nnew contract\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(root),
                    "-c", "user.name=Eval", "-c", "user.email=eval@example.invalid",
                    "commit", "--quiet", "--no-gpg-sign", "-m", "change contract",
                ],
                check=True,
            )
            (root / "docs" / "BENCHMARKS.md").write_text(
                "| EVAL-901 | ce-x | receipt | $1.00 | pass (2026-07-20) |\n",
                encoding="utf-8",
            )
            (root / "evals" / "results" / "old.json").write_text(json.dumps({
                "schema_version": 1,
                "run_id": "old-run",
                "completed_at": "2026-07-20T12:00:00Z",
                "git_head": old_head,
                "source_clean": True,
                "dry_run": False,
                "grade_status": "pass",
                "grade_returncode": 0,
                "graded_scenarios": ["EVAL-901"],
                "scenarios": [{
                    "id": "EVAL-901", "status": "pass", "returncode": 0,
                }],
            }), encoding="utf-8")
            commit_all(root, "commit stale receipt")
            errors = []
            product_layer_check.check_live_eval_provenance(root, errors)
            self.assertEqual(len(errors), 1)
            self.assertIn("promotable live pass", errors[0])

    def test_benchmarks_must_list_every_catalog_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            bench = repo / "docs" / "BENCHMARKS.md"
            text = bench.read_text(encoding="utf-8")
            self.assertIn("| EVAL-018 |", text, "fixture drift: EVAL-018 row missing")
            bench.write_text(text.replace("| EVAL-018 |", "| OMITTED-018 |"),
                             encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("missing catalog scenario", res.stderr)
            self.assertIn("EVAL-018", res.stderr)

    def test_uncited_pass_row_fails(self):
        # A BENCHMARKS 'pass (DATE)' row with no committed results summary is the
        # exact say-do gap the audit found — it must turn CI red. EVAL-901 is in
        # no committed summary, so provenance has nothing to cite.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            inject_pass_row(repo / "docs" / "BENCHMARKS.md", "EVAL-901")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("no committed evals/results", res.stderr)
            self.assertIn("EVAL-901", res.stderr)

    def test_dry_run_summary_does_not_count_as_evidence(self):
        # A summary marked dry_run:true must not back a live-pass claim. EVAL-001
        # IS recorded in the committed summary, so this proves the dry_run guard
        # (not merely an uncited id) is what fails the row.
        with tempfile.TemporaryDirectory() as tmp:
            repo = copy_repo(Path(tmp))
            inject_pass_row(repo / "docs" / "BENCHMARKS.md", "EVAL-001")
            for summary in (repo / "evals" / "results").glob("*.json"):
                data = json.loads(summary.read_text(encoding="utf-8"))
                data["dry_run"] = True
                summary.write_text(json.dumps(data), encoding="utf-8")
            res = run("--root", str(repo))
            self.assertEqual(res.returncode, 1)
            self.assertIn("no committed evals/results", res.stderr)
            self.assertIn("EVAL-001", res.stderr)


class BenchmarkRecency(unittest.TestCase):
    """check_benchmark_recency: a BENCHMARKS `pass (DATE)` row must degrade to
    design-verified once its skill (or fixture) changes after the cited run —
    judged from committed git history, failing loud on a shallow clone."""

    @classmethod
    def setUpClass(cls):
        scripts = str(REPO / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import product_layer_check  # noqa: E402 — sibling import for direct call
        cls.mod = product_layer_check

    SKILL_MD = ("plugins", "core-engineering", "skills", "ce-ask", "SKILL.md")
    FIXTURE = ("evals", "fixtures", "minimal-service", "app.py")

    def _git(self, repo, *args, date=None):
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        })
        if date:
            env["GIT_AUTHOR_DATE"] = f"{date}T12:00:00"
            env["GIT_COMMITTER_DATE"] = f"{date}T12:00:00"
        subprocess.run(["git", "-C", str(repo), *args], check=True,
                       capture_output=True, text=True, env=env)

    def _scaffold(self, base, run_date="2026-06-27", live=True):
        repo = Path(base) / "repo"
        (repo / "docs").mkdir(parents=True)
        repo.joinpath(*self.SKILL_MD).parent.mkdir(parents=True)
        repo.joinpath(*self.FIXTURE).parent.mkdir(parents=True)
        result = f"pass ({run_date})" if live else "design-verified, not live-run"
        (repo / "docs" / "BENCHMARKS.md").write_text(
            "| Scenario | Skill | Proves | Budget | Live result |\n"
            "|---|---|---:|---:|---|\n"
            f"| EVAL-001 | ce-ask | grounded answer | $1.00 | {result} |\n",
            encoding="utf-8")
        (repo / "evals" / "scenarios.json").write_text(json.dumps(
            {"schema_version": 1, "scenarios": [
                {"id": "EVAL-001", "skill": "ce-ask", "fixture": "minimal-service"}]}),
            encoding="utf-8")
        repo.joinpath(*self.SKILL_MD).write_text("skill body\n", encoding="utf-8")
        repo.joinpath(*self.FIXTURE).write_text("x = 1\n", encoding="utf-8")
        return repo

    def _init(self, repo, date):
        self._git(repo, "init", "-q")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-q", "-m", "baseline", date=date)

    def _recency(self, repo):
        errors = []
        self.mod.check_benchmark_recency(Path(repo), errors)
        return errors

    def test_untouched_skill_stays_green(self):
        # Skill last committed 2026-06-20, cited run 2026-06-27 → not stale.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._scaffold(tmp, run_date="2026-06-27")
            self._init(repo, "2026-06-20")
            self.assertEqual(self._recency(repo), [])

    def test_fresh_row_stays_valid(self):
        # A run dated after the skill's last change is a live, current claim.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._scaffold(tmp, run_date="2026-07-10")
            self._init(repo, "2026-07-01")
            self.assertEqual(self._recency(repo), [])

    def test_skill_changed_after_run_goes_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._scaffold(tmp, run_date="2026-06-27")
            self._init(repo, "2026-06-20")
            repo.joinpath(*self.SKILL_MD).write_text("edited body\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-q", "-m", "edit skill", date="2026-07-01")
            errors = self._recency(repo)
            self.assertTrue(any("changed after its cited run" in e for e in errors), errors)
            self.assertTrue(any("EVAL-001" in e for e in errors), errors)

    def test_fixture_change_alone_invalidates_the_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._scaffold(tmp, run_date="2026-06-27")
            self._init(repo, "2026-06-20")
            repo.joinpath(*self.FIXTURE).write_text("x = 2\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-q", "-m", "edit fixture", date="2026-07-02")
            errors = self._recency(repo)
            self.assertTrue(any("changed after its cited run" in e for e in errors), errors)

    def test_shallow_clone_fails_loud_not_green(self):
        # A depth-1 clone hides history, so recency must refuse to pass silently.
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._scaffold(tmp, run_date="2026-06-27")
            self._init(repo, "2026-06-20")
            repo.joinpath(*self.SKILL_MD).write_text("second\n", encoding="utf-8")
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-q", "-m", "c2", date="2026-06-21")
            self._git(Path(tmp), "clone", "-q", "--depth", "1",
                      f"file://{repo}", "clone")
            errors = self._recency(Path(tmp) / "clone")
            self.assertTrue(any("shallow" in e.lower() for e in errors), errors)

    def test_non_git_tree_is_skipped_not_failed(self):
        # An exported tarball / copied fixture has no history to consult; the
        # ratchet skips it rather than reddening (only CI's shallow case fails).
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._scaffold(tmp, run_date="2026-06-27")  # never git-init'd
            self.assertEqual(self._recency(repo), [])

    def test_no_pass_rows_returns_green_without_touching_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._scaffold(tmp, live=False)  # only design-verified rows
            self.assertEqual(self._recency(repo), [])


if __name__ == "__main__":
    unittest.main()
