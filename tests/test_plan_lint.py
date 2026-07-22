"""Tests for skills/ce-plan-audit/scripts/plan-lint.py.

Covers the pre-existing hard invariants at a smoke level (H1/H5/H6 still fire,
happy path still passes) and, in depth, the three checks WS6-T3 adds:

  H7  every plan.json `bridges[].replaced_by` resolves to an in-plan feature with
      a strictly-LATER ship_order (dangling / backward / self / missing target),
      and stays DORMANT when no feature carries a `bridges` array (a hard check
      reads plan.json + the filesystem, never markdown);
  H8  a multi-feature plan carries BOTH `threat-model.md` and
      `interaction-contract.md` on disk, each present and non-empty (present or
      attested-negative), and the check is SKIPPED for a single-feature plan.json;
  A10 Durable-State Closure reciprocals and A11 Surface-Removal Closure continuity
      are dispositioned — advisory (markdown-derived), never touching the exit code.

It also covers H9 architecture-disposition/convergence structure and the A12
legacy-compatibility advisory.

The suite also pins the exit-0/1/2 contract end-to-end via the CLI.
"""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-plan-audit/scripts/plan-lint.py"

_spec = importlib.util.spec_from_file_location("plan_lint_mod", SCRIPT)
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)


# --- Golden-shaped three-feature plan (all H1–H9 green, no advisories) ---------

ARCHITECTURE_DISPOSITION = {
    "decision": "required",
    "triggers": ["cross-feature-durable-or-async-flow"],
    "rationale": "Cross-feature durable state shapes the delivery cut.",
    "decided_by": "human",
    "convergence": {
        "status": "converged",
        "iteration_count": 1,
        "summary": "The architecture shaping pass confirmed the candidate cut.",
        "decision_refs": [],
    },
}

GOLDEN_MANIFEST = {
    "project_slug": "smoke",
    "status": "planned",
    "architecture_disposition": ARCHITECTURE_DISPOSITION,
    "features": [
        {
            "id": "01-auth", "title": "Auth", "type": "foundation",
            "final_complexity": "Moderate", "risk_profile": "low", "ship_order": 1,
            "file": "features/01-auth.md",
            "dependencies": {"hard": [], "soft": []},
            "bridges": [{"type": "exit", "description": "temp page",
                         "replaces": "history surface", "replaced_by": "03-history"}],
        },
        {
            "id": "02-orders", "title": "Orders", "type": "user-facing",
            "final_complexity": "Complex", "risk_profile": "medium", "ship_order": 2,
            "file": "features/02-orders.md",
            "dependencies": {"hard": [{"id": "01-auth"}], "soft": []},
        },
        {
            "id": "03-history", "title": "History", "type": "user-facing",
            "final_complexity": "Simple", "risk_profile": "low", "ship_order": 3,
            "file": "features/03-history.md",
            "dependencies": {"hard": [{"id": "02-orders"}], "soft": []},
        },
    ],
}

FEATURE_PLAN_MD = """# Plan smoke
01-auth 02-orders 03-history

| Noun | Access-mode | Data-class | revisit | amend | retire | retain | export | erase |
|---|---|---|---|---|---|---|---|---|
| order | user-owned-mutable | operational | owned-by:02-orders | owned-by:02-orders | excluded:immutable log | owned-by:02-orders | owned-by:03-history | excluded:legal hold |

| Surface | Break-class | continuity |
|---|---|---|
| /v1/orders | contract-break | deprecate:2 releases,removed_by:03-history |
"""

THREAT_MODEL_MD = "## No Security Surface\nattested negative.\n"
INTERACTION_CONTRACT_MD = "## No Cross-Feature Protocol\nattested negative.\n"


def build_plan(root: Path, manifest: dict, *,
               feature_plan: str | None = FEATURE_PLAN_MD,
               threat_model: str | None = THREAT_MODEL_MD,
               interaction_contract: str | None = INTERACTION_CONTRACT_MD) -> Path:
    """Lay out a plan dir; return it. `None` for a doc file omits it entirely."""
    plan_dir = root / "docs/plans/smoke"
    (plan_dir / "features").mkdir(parents=True)
    (plan_dir / "plan.json").write_text(json.dumps(manifest), encoding="utf-8")
    for f in manifest["features"]:
        rel = f.get("file")
        if isinstance(rel, str) and rel:
            (plan_dir / rel).write_text(
                f"## {f['id']}\n\n### Structured Metadata\n\n```yaml\nid: {f['id']}\n```\n",
                encoding="utf-8",
            )
    if feature_plan is not None:
        (plan_dir / "feature-plan.md").write_text(feature_plan, encoding="utf-8")
    if threat_model is not None:
        (plan_dir / "threat-model.md").write_text(threat_model, encoding="utf-8")
    if interaction_contract is not None:
        (plan_dir / "interaction-contract.md").write_text(interaction_contract, encoding="utf-8")
    return plan_dir


def lint(plan_dir: Path):
    """Run the checks in-process; return (hard, advisory)."""
    manifest, pdir = pl.load(plan_dir / "plan.json")
    registry = pl.load_registry(pdir)
    return pl.run_checks(manifest, pdir, registry)


def has(items, prefix):
    return [i for i in items if i.startswith(prefix)]


class GoldenAndRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_happy_path_clean(self):
        pdir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST))
        hard, advisory = lint(pdir)
        self.assertEqual(hard, [], f"golden plan should have no hard failures: {hard}")
        self.assertEqual(advisory, [], f"golden plan should have no advisories: {advisory}")

    def test_h5_backward_hard_dep_still_fires(self):
        # Regression guard: an existing invariant is untouched by the new checks.
        m = copy.deepcopy(GOLDEN_MANIFEST)
        m["features"][0]["dependencies"]["hard"] = [{"id": "03-history"}]  # 01 depends on later 03
        pdir = build_plan(self.root, m)
        hard, _ = lint(pdir)
        self.assertTrue(has(hard, "H5"), hard)

    def test_h1_missing_file_still_fires(self):
        m = copy.deepcopy(GOLDEN_MANIFEST)
        del m["features"][1]["file"]
        pdir = build_plan(self.root, m)
        hard, _ = lint(pdir)
        self.assertTrue(has(hard, "H1"), hard)


class BridgeResolutionH7(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _lint_with_bridge(self, bridge):
        m = copy.deepcopy(GOLDEN_MANIFEST)
        m["features"][0]["bridges"] = [bridge]
        return lint(build_plan(self.root, m))

    def test_dangling_replaced_by(self):
        hard, _ = self._lint_with_bridge(
            {"type": "exit", "description": "x", "replaces": "y", "replaced_by": "99-nope"})
        self.assertTrue(has(hard, "H7"), hard)
        self.assertIn("does not resolve", " ".join(hard))

    def test_backward_ship_order(self):
        # 02-orders (ship 2) bridged by 01-auth (ship 1) — not strictly later.
        m = copy.deepcopy(GOLDEN_MANIFEST)
        del m["features"][0]["bridges"]
        m["features"][1]["bridges"] = [
            {"type": "exit", "description": "x", "replaces": "y", "replaced_by": "01-auth"}]
        hard, _ = lint(build_plan(self.root, m))
        self.assertTrue(has(hard, "H7"), hard)
        self.assertIn("not strictly later", " ".join(hard))

    def test_self_replacement(self):
        hard, _ = self._lint_with_bridge(
            {"type": "exit", "description": "x", "replaces": "y", "replaced_by": "01-auth"})
        self.assertTrue(has(hard, "H7"), hard)
        self.assertIn("itself", " ".join(hard))

    def test_missing_replaced_by(self):
        hard, _ = self._lint_with_bridge({"type": "exit", "description": "x", "replaces": "y"})
        self.assertTrue(has(hard, "H7"), hard)
        self.assertIn("no `replaced_by`", " ".join(hard))

    def test_valid_bridge_passes(self):
        hard, _ = self._lint_with_bridge(
            {"type": "exit", "description": "x", "replaces": "y", "replaced_by": "03-history"})
        self.assertEqual(has(hard, "H7"), [], hard)

    def test_dormant_without_bridges(self):
        m = copy.deepcopy(GOLDEN_MANIFEST)
        del m["features"][0]["bridges"]  # no feature carries a bridges array
        hard, _ = lint(build_plan(self.root, m))
        self.assertEqual(has(hard, "H7"), [], hard)

    def test_cross_plan_target_not_hard_failed(self):
        # A qualified `<slug>/<id>` target is outside the in-plan ship-order check.
        hard, _ = self._lint_with_bridge(
            {"type": "exit", "description": "x", "replaces": "y", "replaced_by": "other/09-x"})
        self.assertEqual(has(hard, "H7"), [], hard)


class ReprojectionPresenceH8(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_threat_model(self):
        pdir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST), threat_model=None)
        hard, _ = lint(pdir)
        self.assertTrue(any("threat-model.md" in h for h in has(hard, "H8")), hard)

    def test_missing_interaction_contract(self):
        pdir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST), interaction_contract=None)
        hard, _ = lint(pdir)
        self.assertTrue(any("interaction-contract.md" in h for h in has(hard, "H8")), hard)

    def test_empty_file_is_a_silent_omission(self):
        pdir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST), threat_model="   \n")
        hard, _ = lint(pdir)
        self.assertTrue(any("empty" in h for h in has(hard, "H8")), hard)

    def test_attested_negative_satisfies(self):
        # The golden files ARE attested negatives — no H8.
        pdir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST))
        hard, _ = lint(pdir)
        self.assertEqual(has(hard, "H8"), [], hard)

    def test_single_feature_plan_skips_h8(self):
        m = copy.deepcopy(GOLDEN_MANIFEST)
        m["features"] = [m["features"][0]]
        del m["features"][0]["bridges"]  # its bridge targeted a now-absent feature
        pdir = build_plan(self.root, m, threat_model=None, interaction_contract=None)
        hard, _ = lint(pdir)
        self.assertEqual(has(hard, "H8"), [], hard)


class ArchitectureDispositionH9(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _lint_posture(self, posture):
        manifest = copy.deepcopy(GOLDEN_MANIFEST)
        manifest["architecture_disposition"] = posture
        case_root = Path(tempfile.mkdtemp(dir=self.root))
        return lint(build_plan(case_root, manifest))

    def test_valid_required_posture_passes(self):
        hard, advisory = self._lint_posture(copy.deepcopy(ARCHITECTURE_DISPOSITION))
        self.assertEqual(has(hard, "H9"), [], hard)
        self.assertEqual(has(advisory, "A12"), [], advisory)

    def test_legacy_absence_is_advisory_only(self):
        manifest = copy.deepcopy(GOLDEN_MANIFEST)
        del manifest["architecture_disposition"]
        hard, advisory = lint(build_plan(self.root, manifest))
        self.assertEqual(has(hard, "H9"), [], hard)
        self.assertTrue(has(advisory, "A12"), advisory)

    def test_malformed_present_posture_is_hard_failure(self):
        hard, _ = self._lint_posture("required")
        self.assertTrue(has(hard, "H9"), hard)

    def test_required_needs_convergence_iteration_and_trigger(self):
        posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
        posture["triggers"] = []
        posture["convergence"]["status"] = "deferred"
        posture["convergence"]["iteration_count"] = 0
        hard, _ = self._lint_posture(posture)
        joined = " ".join(has(hard, "H9"))
        self.assertIn("status `converged`", joined)
        self.assertIn("iteration_count >= 1", joined)
        self.assertIn("at least one trigger", joined)

    def test_recommended_allows_converged_or_deferred_but_needs_trigger(self):
        for state in ("converged", "deferred"):
            with self.subTest(state=state):
                posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
                posture["decision"] = "recommended"
                posture["triggers"] = ["team-policy-recommendation"]
                posture["convergence"]["status"] = state
                posture["convergence"]["iteration_count"] = 1 if state == "converged" else 0
                hard, _ = self._lint_posture(posture)
                self.assertEqual(has(hard, "H9"), [], hard)

        posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
        posture["decision"] = "recommended"
        posture["triggers"] = []
        posture["convergence"]["status"] = "waived"
        hard, _ = self._lint_posture(posture)
        joined = " ".join(has(hard, "H9"))
        self.assertIn("`converged` or `deferred`", joined)
        self.assertIn("at least one trigger", joined)

    def test_recommended_iteration_semantics(self):
        posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
        posture["decision"] = "recommended"
        posture["triggers"] = ["planned-reuse-recommendation"]
        posture["convergence"]["status"] = "converged"
        posture["convergence"]["iteration_count"] = 0
        hard, _ = self._lint_posture(posture)
        self.assertIn("iteration_count >= 1", " ".join(has(hard, "H9")))

        posture["convergence"]["status"] = "deferred"
        posture["convergence"]["iteration_count"] = 1
        hard, _ = self._lint_posture(posture)
        self.assertIn("iteration_count 0", " ".join(has(hard, "H9")))

    def test_not_required_needs_na_zero_iterations_and_no_triggers(self):
        posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
        posture["decision"] = "not-required"
        posture["triggers"] = []
        posture["convergence"]["status"] = "not-applicable"
        posture["convergence"]["iteration_count"] = 0
        hard, _ = self._lint_posture(posture)
        self.assertEqual(has(hard, "H9"), [], hard)

        posture["triggers"] = ["unexpected-boundary"]
        posture["convergence"]["status"] = "converged"
        posture["convergence"]["iteration_count"] = 1
        hard, _ = self._lint_posture(posture)
        joined = " ".join(has(hard, "H9"))
        self.assertIn("`not-applicable`", joined)
        self.assertIn("iteration_count 0", joined)
        self.assertIn("empty triggers", joined)

    def test_waiver_needs_trigger_and_explicit_human_evidence(self):
        posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
        posture["decision"] = "waived"
        posture["convergence"]["status"] = "waived"
        hard, _ = self._lint_posture(posture)
        self.assertEqual(has(hard, "H9"), [], hard)

        posture["triggers"] = []
        posture["rationale"] = ""
        posture["decided_by"] = "agent"
        posture["convergence"]["summary"] = ""
        hard, _ = self._lint_posture(posture)
        joined = " ".join(has(hard, "H9"))
        self.assertIn("rationale", joined)
        self.assertIn("decided_by", joined)
        self.assertIn("summary", joined)
        self.assertIn("at least one trigger", joined)

    def test_waiver_requires_a_recorded_iteration(self):
        posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
        posture["decision"] = "waived"
        posture["convergence"]["status"] = "waived"
        posture["convergence"]["iteration_count"] = 0
        hard, _ = self._lint_posture(posture)
        self.assertIn("iteration_count >= 1", " ".join(has(hard, "H9")))

    def test_unknown_and_duplicate_triggers_are_hard_failures(self):
        posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
        posture["triggers"] = [
            "cross-feature-durable-or-async-flow",
            "bogus-trigger",
            "cross-feature-durable-or-async-flow",
        ]
        hard, _ = self._lint_posture(posture)
        joined = " ".join(has(hard, "H9"))
        self.assertIn("unknown trigger(s): bogus-trigger", joined)
        self.assertIn("duplicate trigger(s)", joined)

    def test_decision_rejects_trigger_from_the_other_taxonomy(self):
        posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
        posture["triggers"] = ["team-policy-recommendation"]
        hard, _ = self._lint_posture(posture)
        self.assertIn("only required architecture trigger", " ".join(has(hard, "H9")))

        posture["decision"] = "recommended"
        posture["triggers"] = ["shared-data-ownership-or-migration"]
        hard, _ = self._lint_posture(posture)
        self.assertIn("only recommendation trigger", " ".join(has(hard, "H9")))

    def test_required_posture_cannot_use_light_plan_tier(self):
        manifest = copy.deepcopy(GOLDEN_MANIFEST)
        manifest["plan_tier"] = "light"
        hard, _ = lint(build_plan(self.root, manifest))
        self.assertIn("incompatible with `plan_tier: light`", " ".join(has(hard, "H9")))

    def test_present_plan_tier_uses_known_vocabulary(self):
        for tier in ("minimal", []):
            with self.subTest(tier=tier):
                manifest = copy.deepcopy(GOLDEN_MANIFEST)
                manifest["plan_tier"] = tier
                case_root = Path(tempfile.mkdtemp(dir=self.root))
                hard, _ = lint(build_plan(case_root, manifest))
                self.assertIn(
                    "must be `standard` or `light`", " ".join(has(hard, "H9"))
                )

    def test_leaf_types_and_unknown_keys_are_hard_failures(self):
        posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
        posture["unexpected"] = True
        posture["triggers"] = [""]
        posture["convergence"]["iteration_count"] = True
        posture["convergence"]["decision_refs"] = [7]
        hard, _ = self._lint_posture(posture)
        joined = " ".join(has(hard, "H9"))
        self.assertIn("unknown key", joined)
        self.assertIn("triggers", joined)
        self.assertIn("integer >= 0", joined)
        self.assertIn("decision_refs", joined)

class ClosureAdvisoriesA10A11(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _lint_fp(self, feature_plan):
        return lint(build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST), feature_plan=feature_plan))

    def test_empty_reciprocal_cell(self):
        fp = FEATURE_PLAN_MD.replace(
            "| owned-by:02-orders | owned-by:02-orders | excluded:immutable log",
            "|  | owned-by:02-orders | excluded:immutable log")
        hard, advisory = self._lint_fp(fp)
        self.assertEqual(hard, [], "A10 is advisory, must not hard-fail")
        self.assertTrue(any("revisit" in a for a in has(advisory, "A10")), advisory)

    def test_unrecognized_disposition_and_dangling_owner(self):
        fp = FEATURE_PLAN_MD.replace("owned-by:03-history", "owned-by:77-ghost")\
                            .replace("excluded:legal hold", "maybe-later")
        _, advisory = self._lint_fp(fp)
        text = " ".join(has(advisory, "A10"))
        self.assertIn("does not resolve", text)      # dangling owned-by:77-ghost
        self.assertIn("not a recognized disposition", text)  # bare "maybe-later"

    def test_all_dispositioned_no_a10(self):
        _, advisory = self._lint_fp(FEATURE_PLAN_MD)
        self.assertEqual(has(advisory, "A10"), [], advisory)

    def test_surface_continuity_empty_and_bad(self):
        fp = FEATURE_PLAN_MD.replace(
            "| /v1/orders | contract-break | deprecate:2 releases,removed_by:03-history |",
            "| /v1/orders | contract-break |  |\n| /v1/legacy | internal-only | someday |")
        hard, advisory = self._lint_fp(fp)
        self.assertEqual(hard, [], "A11 is advisory, must not hard-fail")
        text = " ".join(has(advisory, "A11"))
        self.assertIn("undispositioned", text)
        self.assertIn("not a recognized disposition", text)

    def test_greenfield_no_surface_table_no_a11(self):
        # Drop the Surface-Removal table entirely (greenfield records N/A).
        fp = FEATURE_PLAN_MD.split("| Surface")[0]
        _, advisory = self._lint_fp(fp)
        self.assertEqual(has(advisory, "A11"), [], advisory)


class ExitCodeContract(unittest.TestCase):
    """End-to-end exit codes via the CLI (the caller gates on these)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, plan_dir):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(plan_dir), "--json"],
            capture_output=True, text=True)

    def test_pass_exit_0(self):
        pdir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST))
        r = self._run(pdir)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "pass")

    def test_hard_fail_exit_1(self):
        pdir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST), threat_model=None)
        r = self._run(pdir)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "fail")

    def test_advisory_only_exit_0(self):
        fp = FEATURE_PLAN_MD.replace("owned-by:03-history", "bogus")
        pdir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST), feature_plan=fp)
        r = self._run(pdir)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["status"], "pass")
        self.assertTrue(out["advisory"])

    def test_unparseable_exit_2(self):
        pdir = self.root / "docs/plans/broken"
        pdir.mkdir(parents=True)
        (pdir / "plan.json").write_text("{not json", encoding="utf-8")
        r = self._run(pdir)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "error")


if __name__ == "__main__":
    unittest.main()
