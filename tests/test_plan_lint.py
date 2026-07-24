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

It also covers H9 current plan authority and architecture convergence, plus
H10's exact current-schema architecture-selection binding.

The suite also pins the exit-0/1/2 contract end-to-end via the CLI.
"""

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-plan-audit/scripts/plan-lint.py"
SELECTION_SCRIPT = (
    REPO
    / "plugins/core-engineering/skills/ce-plan-audit/scripts/architecture-selection-lint.py"
)
SELECTION_TEST_SUPPORT = REPO / "tests/test_architecture_selection_lint.py"

_spec = importlib.util.spec_from_file_location("plan_lint_mod", SCRIPT)
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

_selection_spec = importlib.util.spec_from_file_location(
    "architecture_selection_lint_for_plan_tests", SELECTION_SCRIPT
)
sl = importlib.util.module_from_spec(_selection_spec)
_selection_spec.loader.exec_module(sl)

_selection_support_spec = importlib.util.spec_from_file_location(
    "architecture_selection_test_support", SELECTION_TEST_SUPPORT
)
selection_support = importlib.util.module_from_spec(_selection_support_spec)
_selection_support_spec.loader.exec_module(selection_support)


# --- Current three-feature plan (H1–H11 green) -------------------------------

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
    "plan_revision": 1,
    "plan_tier": "standard",
    "architecture_disposition": ARCHITECTURE_DISPOSITION,
    "relates_to": [],
    "features": [
        {
            "id": "01-auth", "title": "Auth", "type": "foundation",
            "specification_route": "explicit",
            "final_complexity": "Moderate", "risk_profile": "low", "ship_order": 1,
            "file": "features/01-auth.md",
            "dependencies": {"hard": [], "soft": []},
            "bridges": [{"type": "exit", "description": "temp page",
                         "replaces": "history surface", "replaced_by": "03-history"}],
        },
        {
            "id": "02-orders", "title": "Orders", "type": "user-facing",
            "specification_route": "explicit",
            "final_complexity": "Complex", "risk_profile": "medium", "ship_order": 2,
            "file": "features/02-orders.md",
            "dependencies": {"hard": [{"id": "01-auth"}], "soft": []},
        },
        {
            "id": "03-history", "title": "History", "type": "user-facing",
            "specification_route": "compact",
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
               interaction_contract: str | None = INTERACTION_CONTRACT_MD,
               bind_direction: bool = True) -> Path:
    """Lay out a plan dir; return it. `None` for a doc file omits it entirely."""
    plan_dir = root / "docs/plans/smoke"
    (plan_dir / "features").mkdir(parents=True)
    (plan_dir / "plan.json").write_text(json.dumps(manifest), encoding="utf-8")
    for f in manifest["features"]:
        rel = f.get("file")
        if isinstance(rel, str) and rel:
            (plan_dir / rel).write_text(
                f"## {f['id']}\n\n"
                f"**Specification route:** "
                f"{f.get('specification_route', 'explicit')}\n\n"
                f"### Structured Metadata\n\n```yaml\nid: {f['id']}\n```\n",
                encoding="utf-8",
            )
    if feature_plan is not None:
        (plan_dir / "feature-plan.md").write_text(feature_plan, encoding="utf-8")
    if threat_model is not None:
        (plan_dir / "threat-model.md").write_text(threat_model, encoding="utf-8")
    if interaction_contract is not None:
        (plan_dir / "interaction-contract.md").write_text(interaction_contract, encoding="utf-8")
    posture = manifest.get("architecture_disposition")
    if (
        bind_direction
        and isinstance(posture, dict)
        and "direction" not in posture
    ):
        attach_valid_direction(plan_dir)
    return plan_dir


def lint(plan_dir: Path):
    """Run the checks in-process; return (hard, advisory)."""
    manifest, pdir = pl.load(plan_dir / "plan.json")
    registry = pl.load_registry(pdir)
    return pl.run_checks(manifest, pdir, registry)


def attach_valid_direction(plan_dir: Path) -> dict:
    """Write a valid selected artifact and bind it into plan.json."""
    repo_root = plan_dir.parent.parent.parent
    source = plan_dir / "feature-plan.md"
    source_rel = source.relative_to(repo_root).as_posix()
    sources = [
        {
            "path": source_rel,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "kind": "planning-input",
        }
    ]
    weights = (0.25, 0.20, 0.15, 0.15, 0.15, 0.10)
    criteria = [
        {"id": cid, "weight": weight, "basis": f"Confirmed priority for {cid}."}
        for cid, weight in zip(sl.CRITERIA, weights)
    ]
    constraints = [
        {
            "id": "HC01",
            "statement": "Keep the plan scope unchanged.",
            "basis": "Approved plan intent.",
            "authority": "Plan owner.",
        }
    ]
    option = {
        "option_id": "A01",
        "title": "Selected direction",
        "summary": "One coherent direction for the smoke plan.",
        "responsibilities_and_boundaries": ["Application boundary."],
        "runtime_and_deployment": ["One runtime."],
        "data_ownership": ["Application-owned state."],
        "integrations_and_failure": ["Explicit failure response."],
        "trust_residency_and_security": ["Existing trust boundary retained."],
        "quality_tactics": ["Observable validation path."],
        "migration_and_evolution": ["Reversible migration."],
        "capability_implications": ["Covers the approved capability map."],
        "assumptions": ["Repository evidence remains current."],
        "irreversible_commitments": ["None before cutover."],
        "constraint_verdicts": [
            {"constraint_id": "HC01", "verdict": "pass", "basis": "Scope retained."}
        ],
        "scores": [
            {
                "criterion_id": cid,
                "score": 4,
                "basis": f"Selected direction fit against {cid}.",
                "evidence_state": "recorded",
                "evidence": [source_rel],
            }
            for cid in sl.CRITERIA
        ],
        "weighted_score": 4,
        "confidence": "high",
        "option_sha256": "",
    }
    option["option_sha256"] = sl.option_hash(option)
    comparator = copy.deepcopy(option)
    comparator["option_id"] = "A02"
    comparator["title"] = "Comparator direction"
    comparator["summary"] = "A genuine but lower-fit direction for the smoke plan."
    for score in comparator["scores"]:
        score["score"] = 3
    comparator["weighted_score"] = 3
    comparator["option_sha256"] = sl.option_hash(comparator)
    options = [option, comparator]
    option_set_sha256 = sl.option_set_hash(options, [])
    evaluation_frame = {
        "project_intent": "Validate the smoke plan without widening scope.",
        "non_goals": ["Replace the existing runtime."],
        "decision_owner": {
            "identity_or_role": "Smoke Architecture Owner",
            "authority_basis": (
                "The repository test plan assigns solution-direction approval "
                "to the Smoke Architecture Owner."
            ),
        },
        "architecture_applicability": "required",
        "driver_screen": [
            {
                "id": driver_id,
                "verdict": "positive" if index == 0 else "negative",
                "basis": f"Recorded basis for {driver_id}.",
                "evidence": [source_rel],
            }
            for index, driver_id in enumerate(sl.DRIVER_IDS)
        ],
        "accepted_decisions": [],
        "material_gaps": [],
        "capabilities": [
            {
                "id": "C01",
                "outcome": "The smoke workflow produces its recorded outcome.",
                "actors": ["operator"],
                "data": ["plan state"],
                "integrations": ["existing application"],
                "observable": "The validation target is visible.",
            }
        ],
        "journeys": [
            {
                "id": "J01",
                "outcome": "The operator completes the workflow.",
                "actors": ["operator"],
                "capability_refs": ["C01"],
                "steps": ["Invoke and observe the planned capability."],
                "observable": "The expected result is recorded.",
            }
        ],
        "quality_attribute_scenarios": [
            {
                "id": "QA01",
                "attribute": "operability",
                "stimulus": "The workflow is invoked.",
                "environment": "normal operation",
                "response": "Expose a deterministic validation result.",
                "target": "one explicit result",
                "priority": "must",
                "evidence": [source_rel],
            }
        ],
    }
    selection = {
        "schema_version": 2,
        "project_slug": "smoke",
        "exploration_id": f"AEX-{option_set_sha256[:12]}",
        "source_capability_revision": 1,
        "source_exploration_attempt": 1,
        "source_input_sha256": "0" * 64,
        "evaluation_frame": evaluation_frame,
        "blocking_decision": None,
        "sources": sources,
        "evidence_fingerprint": sl.canonical_sha256(sources),
        "criteria": criteria,
        "hard_constraints": constraints,
        "options": options,
        "eliminated_options": [],
        "option_set_sha256": option_set_sha256,
        "recommendation": {
            "option_id": "A01",
            "confidence": "high",
            "sensitivity": "stable",
            "sensitivity_witness": None,
            "basis": "A01 remains the leader across the tested ranges.",
        },
        "selection": {
            "status": "direction-selected",
            "option_id": "A01",
            "option_sha256": option["option_sha256"],
            "decided_by": "human",
            "approved_by": "Smoke Architecture Owner",
            "rationale": "Human selected the viable direction.",
        },
        "next_owner": "ce-plan",
    }
    selection["source_input_sha256"] = sl.source_input_hash(selection)
    report = plan_dir / "architecture-options.md"
    report.write_text(
        selection_support.render_options_report(selection),
        encoding="utf-8",
    )
    selection["architecture_options_report"] = {
        "schema_version": 1,
        "status": "present",
        "path": "architecture-options.md",
        "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "reason": None,
    }
    artifact = plan_dir / "architecture-selection.json"
    artifact.write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
    manifest = json.loads((plan_dir / "plan.json").read_text(encoding="utf-8"))
    manifest["architecture_disposition"]["direction"] = {
        "status": "direction-selected",
        "artifact": "architecture-selection.json",
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "exploration_id": selection["exploration_id"],
        "selected_option_id": "A01",
        "selected_option_sha256": option["option_sha256"],
        "decided_by": "human",
        "summary": "Human-selected architecture direction A01.",
    }
    (plan_dir / "plan.json").write_text(json.dumps(manifest), encoding="utf-8")
    return selection


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
        self.assertEqual(advisory, [])

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


class SpecificationRouteH11(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_manifest_authority_and_single_matching_projection_pass(self):
        pdir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST))
        hard, _ = lint(pdir)
        self.assertEqual(has(hard, "H11"), [], hard)

    def test_missing_or_unknown_manifest_route_fails(self):
        for case, value in (("missing", None), ("unknown", "auto")):
            with self.subTest(case=case):
                case_root = self.root / case
                manifest = copy.deepcopy(GOLDEN_MANIFEST)
                if value is None:
                    manifest["features"][0].pop("specification_route")
                else:
                    manifest["features"][0]["specification_route"] = value
                hard, _ = lint(build_plan(case_root, manifest))
                self.assertTrue(has(hard, "H11"), hard)

    def test_missing_duplicate_or_mismatched_projection_fails(self):
        for case in ("missing", "duplicate", "mismatch"):
            with self.subTest(case=case):
                case_root = self.root / case
                pdir = build_plan(case_root, copy.deepcopy(GOLDEN_MANIFEST))
                feature = pdir / "features/01-auth.md"
                text = feature.read_text(encoding="utf-8")
                if case == "missing":
                    text = text.replace("**Specification route:** explicit\n\n", "")
                elif case == "duplicate":
                    text += "\n**Specification route:** explicit\n"
                else:
                    text = text.replace(
                        "**Specification route:** explicit",
                        "**Specification route:** compact",
                    )
                feature.write_text(text, encoding="utf-8")
                hard, _ = lint(pdir)
                self.assertTrue(has(hard, "H11"), hard)

    def test_complex_feature_cannot_take_compact_route(self):
        manifest = copy.deepcopy(GOLDEN_MANIFEST)
        manifest["features"][1]["specification_route"] = "compact"
        pdir = build_plan(self.root, manifest)
        feature = pdir / manifest["features"][1]["file"]
        feature.write_text(
            feature.read_text(encoding="utf-8").replace(
                "**Specification route:** explicit",
                "**Specification route:** compact",
            ),
            encoding="utf-8",
        )

        hard, _ = lint(pdir)

        self.assertTrue(has(hard, "H11"), hard)
        self.assertTrue(
            any("`final_complexity` is `Complex`" in item for item in hard),
            hard,
        )


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
        self.assertEqual(advisory, [])

    def test_missing_architecture_disposition_is_hard_failure(self):
        manifest = copy.deepcopy(GOLDEN_MANIFEST)
        del manifest["architecture_disposition"]
        hard, advisory = lint(build_plan(self.root, manifest))
        self.assertTrue(
            any("requires `architecture_disposition`" in item for item in has(hard, "H9")),
            hard,
        )
        self.assertEqual(advisory, [])

    def test_current_plan_authority_fields_are_required(self):
        cases = {
            "project_slug": "`project_slug` must be a non-empty string",
            "status": "`status` must equal `planned`",
            "plan_revision": "`plan_revision` must be an integer >= 1",
            "plan_tier": "`plan_tier` must be `standard` or `light`",
            "relates_to": "`relates_to` must be a list of non-empty plan slugs",
        }
        for field, diagnostic in cases.items():
            with self.subTest(field=field):
                manifest = copy.deepcopy(GOLDEN_MANIFEST)
                del manifest[field]
                case_root = Path(tempfile.mkdtemp(dir=self.root))
                hard, _ = lint(build_plan(case_root, manifest))
                self.assertIn(diagnostic, " ".join(has(hard, "H9")))

    def test_current_plan_authority_field_types_are_strict(self):
        cases = (
            ("project_slug", "", "`project_slug`"),
            ("status", "draft", "`status`"),
            ("plan_revision", True, "`plan_revision`"),
            ("plan_revision", 0, "`plan_revision`"),
            ("plan_tier", "minimal", "`plan_tier`"),
            ("relates_to", ["other", ""], "`relates_to`"),
            ("relates_to", ["other", "other"], "duplicate"),
        )
        for field, value, diagnostic in cases:
            with self.subTest(field=field, value=value):
                manifest = copy.deepcopy(GOLDEN_MANIFEST)
                manifest[field] = value
                case_root = Path(tempfile.mkdtemp(dir=self.root))
                hard, _ = lint(build_plan(case_root, manifest))
                self.assertIn(diagnostic, " ".join(has(hard, "H9")))

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
        self.assertIn("convergence.status", joined)
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

    def test_retired_waiver_is_rejected_as_unknown(self):
        posture = copy.deepcopy(ARCHITECTURE_DISPOSITION)
        posture["decision"] = "waived"
        posture["convergence"]["status"] = "waived"
        hard, _ = self._lint_posture(posture)
        joined = " ".join(has(hard, "H9"))
        self.assertIn("architecture_disposition.decision", joined)
        self.assertIn("architecture_disposition.convergence.status", joined)
        self.assertNotIn("'waived'", str(sorted(pl.ARCHITECTURE_DECISIONS)))
        self.assertNotIn("'waived'", str(sorted(pl.ARCHITECTURE_CONVERGENCE_STATES)))

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

    def test_plan_tier_uses_known_vocabulary(self):
        for tier in ("minimal", [], None):
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


class ArchitectureDirectionH10(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _plan_with_direction(self):
        plan_dir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST))
        selection = json.loads(
            (plan_dir / "architecture-selection.json").read_text(encoding="utf-8")
        )
        return plan_dir, selection

    @staticmethod
    def _manifest(plan_dir: Path) -> dict:
        return json.loads((plan_dir / "plan.json").read_text(encoding="utf-8"))

    @staticmethod
    def _write_manifest(plan_dir: Path, manifest: dict) -> None:
        (plan_dir / "plan.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_valid_current_direction_binding_passes(self):
        plan_dir, _ = self._plan_with_direction()
        hard, advisory = lint(plan_dir)
        self.assertEqual(has(hard, "H10"), [], hard)
        self.assertEqual(advisory, [])

    def test_every_plan_lint_rejects_legacy_selection_schema(self):
        plan_dir, _ = self._plan_with_direction()
        artifact = plan_dir / "architecture-selection.json"
        selection = json.loads(artifact.read_text(encoding="utf-8"))
        selection["schema_version"] = 1
        selection.pop("architecture_options_report")
        artifact.write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
        manifest = self._manifest(plan_dir)
        manifest["architecture_disposition"]["direction"]["artifact_sha256"] = (
            hashlib.sha256(artifact.read_bytes()).hexdigest()
        )
        self._write_manifest(plan_dir, manifest)

        hard, _ = lint(plan_dir)
        self.assertTrue(
            any(
                "schema_version must equal 2" in item
                for item in has(hard, "H10")
            ),
            hard,
        )

    def test_missing_direction_is_always_a_hard_failure(self):
        plan_dir = build_plan(
            self.root,
            copy.deepcopy(GOLDEN_MANIFEST),
            bind_direction=False,
        )
        hard, advisory = lint(plan_dir)
        self.assertTrue(
            any("missing key(s): direction" in item for item in has(hard, "H9")),
            hard,
        )
        self.assertTrue(
            any("current plan authority requires" in item for item in has(hard, "H10")),
            hard,
        )
        self.assertEqual(advisory, [])

    def test_summary_artifact_hash_is_byte_exact(self):
        plan_dir, _ = self._plan_with_direction()
        manifest = self._manifest(plan_dir)
        manifest["architecture_disposition"]["direction"]["artifact_sha256"] = "0" * 64
        self._write_manifest(plan_dir, manifest)
        hard, _ = lint(plan_dir)
        self.assertIn("does not match architecture-selection.json", " ".join(has(hard, "H10")))

    def test_summary_cross_checks_exploration_and_selected_option(self):
        plan_dir, _ = self._plan_with_direction()
        manifest = self._manifest(plan_dir)
        direction = manifest["architecture_disposition"]["direction"]
        direction["exploration_id"] = "AEX-other"
        direction["selected_option_id"] = "A02"
        direction["selected_option_sha256"] = "f" * 64
        self._write_manifest(plan_dir, manifest)
        hard, _ = lint(plan_dir)
        joined = " ".join(has(hard, "H10"))
        self.assertIn("exploration_id", joined)
        self.assertIn("selected_option_id", joined)
        self.assertIn("selected_option_sha256", joined)

    def test_selection_lint_failures_are_promoted_to_h10(self):
        plan_dir, _ = self._plan_with_direction()
        (plan_dir / "feature-plan.md").write_text("source drift\n", encoding="utf-8")
        hard, _ = lint(plan_dir)
        joined = " ".join(has(hard, "H10"))
        self.assertIn("architecture-selection.json", joined)
        self.assertIn("is stale", joined)

    def test_direction_status_matches_applicability_semantics(self):
        plan_dir, _ = self._plan_with_direction()
        manifest = self._manifest(plan_dir)
        posture = manifest["architecture_disposition"]
        posture["decision"] = "not-required"
        posture["triggers"] = []
        posture["convergence"]["status"] = "not-applicable"
        posture["convergence"]["iteration_count"] = 0
        self._write_manifest(plan_dir, manifest)
        hard, _ = lint(plan_dir)
        self.assertIn(
            "decision `not-required` requires direction status",
            " ".join(has(hard, "H10")),
        )

    def test_retired_adopted_existing_direction_is_rejected(self):
        plan_dir, _ = self._plan_with_direction()
        manifest = self._manifest(plan_dir)
        manifest["architecture_disposition"]["direction"]["status"] = "adopted-existing"
        self._write_manifest(plan_dir, manifest)
        hard, _ = lint(plan_dir)
        joined = " ".join(has(hard, "H10"))
        self.assertIn("direction.status", joined)
        self.assertNotIn(
            "adopted-existing",
            str(sorted(pl.ARCHITECTURE_DIRECTION_STATUSES)),
        )

    def test_retired_waiver_cannot_preserve_a_selected_direction(self):
        plan_dir, _ = self._plan_with_direction()
        manifest = self._manifest(plan_dir)
        posture = manifest["architecture_disposition"]
        posture["decision"] = "waived"
        posture["convergence"]["status"] = "waived"
        self._write_manifest(plan_dir, manifest)
        hard, _ = lint(plan_dir)
        joined = " ".join(has(hard, "H9"))
        self.assertIn("architecture_disposition.decision", joined)
        self.assertIn("architecture_disposition.convergence.status", joined)

    def test_selection_artifact_must_not_be_a_symlink(self):
        plan_dir, _ = self._plan_with_direction()
        artifact = plan_dir / "architecture-selection.json"
        target = plan_dir / "selection-target.json"
        target.write_bytes(artifact.read_bytes())
        artifact.unlink()
        artifact.symlink_to(target.name)
        hard, _ = lint(plan_dir)
        self.assertIn("regular non-symlink", " ".join(has(hard, "H10")))


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

    def _run(self, plan_dir, *extra):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(plan_dir), "--json", *extra],
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

    def test_missing_direction_is_hard_failure_without_a_mode_flag(self):
        pdir = build_plan(
            self.root,
            copy.deepcopy(GOLDEN_MANIFEST),
            bind_direction=False,
        )
        r = self._run(pdir)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["status"], "fail")
        self.assertTrue(any(item.startswith("H10") for item in out["hard_failures"]))

    def test_removed_legacy_strictness_flag_is_rejected(self):
        pdir = build_plan(self.root, copy.deepcopy(GOLDEN_MANIFEST))
        r = self._run(pdir, "--require-architecture-direction")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("unrecognized arguments", r.stderr)


if __name__ == "__main__":
    unittest.main()
