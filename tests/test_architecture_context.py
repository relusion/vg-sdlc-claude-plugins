"""Behavioral tests for downstream architecture provenance and freshness."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO
    / "plugins/core-engineering/skills/ce-spec/scripts/architecture_context.py"
)

_spec = importlib.util.spec_from_file_location("architecture_context_mod", SCRIPT)
ac = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ac)


def mapping(feature_id: str = "01-feature") -> dict:
    return {
        "feature_id": feature_id,
        "mapping_scope": "cross-feature",
        "direction_realization_ids": ["DR-001"],
        "driver_ids": ["DRV-001"],
        "actor_ids": ["A-001"],
        "context_relationship_ids": ["CR-001"],
        "component_ids": ["C-002", "C-001", "C-001"],
        "relationship_ids": ["R-001"],
        "deployment_node_ids": ["N-001"],
        "deployment_ids": ["DP-001"],
        "deployment_connection_ids": ["DC-001"],
        "data_ids": ["DATA-001"],
        "integration_ids": ["IF-001"],
        "dynamic_scenario_ids": ["DS-001"],
        "trust_boundary_ids": ["TB-001"],
        "security_realization_ids": ["SR-001"],
        "contract_realization_ids": ["CTR-001"],
        "transition_ids": ["TR-001"],
        "quality_ids": ["QA-001"],
        "operation_ids": ["OP-001"],
        "decision_ids": ["D-001"],
        "open_question_ids": [],
        "risk_ids": ["AR-001"],
        "gap_ids": ["GAP-001"],
        "evidence_state": "inferred",
        "evidence": ["docs/plans/demo/features/01-feature.md"],
    }


def write_full_plan(root: Path, decision: str = "not-required") -> Path:
    plan_dir = root / "docs/plans/demo"
    (plan_dir / "features").mkdir(parents=True)
    (plan_dir / "features/01-feature.md").write_text(
        "# Feature\n", encoding="utf-8"
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
                        "id": "01-feature",
                        "file": "features/01-feature.md",
                    }
                ],
                "architecture_disposition": {
                    "decision": decision,
                    "rationale": f"architecture is {decision} for this fixture",
                    "triggers": [],
                    "decided_by": "human",
                    "convergence": {
                        "status": (
                            "converged"
                            if decision == "required"
                            else "not-applicable"
                        ),
                        "iteration_count": 0,
                        "summary": "fixture convergence",
                        "decision_refs": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return plan_dir


def markdown_with_context(context: dict) -> str:
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


class MappingContract(unittest.TestCase):
    def test_v2_mapping_is_projected_into_exact_consumer_categories(self):
        row = mapping()
        manifest = {"schema_version": 2, "feature_mappings": [row]}
        exact = ac.feature_mapping(manifest, "01-feature")
        self.assertIs(exact, row)
        self.assertEqual(
            ac.mapped_ids(row),
            {
                "drivers": ["DRV-001"],
                "actors": ["A-001"],
                "components": ["C-001", "C-002"],
                "relationships": ["CR-001", "R-001"],
                "deployments": ["DC-001", "DP-001", "N-001"],
                "data": ["DATA-001"],
                "flows": ["IF-001"],
                "dynamic": ["DS-001"],
                "transitions": ["TR-001"],
                "security": ["SR-001", "TB-001"],
                "contracts": ["CTR-001"],
                "quality": ["QA-001"],
                "operations": ["OP-001"],
                "decisions": ["D-001", "DR-001"],
                "questions": [],
                "risks": ["AR-001"],
                "gaps": ["GAP-001"],
            },
        )

    def test_v1_and_missing_canonical_v2_fields_are_rejected(self):
        with self.assertRaisesRegex(ac.ContextError, "schema_version 2"):
            ac.feature_mapping(
                {"schema_version": 1, "feature_mappings": [mapping()]},
                "01-feature",
            )
        row = mapping()
        del row["driver_ids"]
        with self.assertRaisesRegex(ac.ContextError, "driver_ids"):
            ac.mapped_ids(row)

    def test_context_schema_v1_has_an_explicit_migration_failure(self):
        legacy = {
            "schema_version": 1,
            "mode": "not-required",
            "package_path": None,
            "plan_revision": 1,
            "architecture_revision": None,
            "package_receipt_sha256": None,
            "feature_mapping_sha256": None,
            "mapped_ids": {key: [] for key in ac.MAPPING_KEYS},
            "reason": "legacy fixture",
        }
        errors = ac.validate_context_shape(legacy)
        self.assertTrue(any("schema_version must be 2" in item for item in errors))
        self.assertTrue(any("plan_contract_sha256" in item for item in errors))


class ContextDerivation(unittest.TestCase):
    def test_package_context_uses_verified_producer_receipt_and_mapping_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_full_plan(root, "required")
            architecture_dir = plan_dir / "architecture"
            architecture_dir.mkdir()
            row = mapping()
            receipt = "a" * 64
            (architecture_dir / "architecture.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "project_slug": "demo",
                        "architecture_revision": 4,
                        "source_plan_revision": 1,
                        "feature_mappings": [row],
                        "approval": {"receipt_sha256": receipt},
                    }
                ),
                encoding="utf-8",
            )
            context = ac.derive_context(
                plan_dir,
                "01-feature",
                repo_root=root,
                lint_package=False,
            )
        self.assertEqual(context["mode"], "package")
        self.assertEqual(context["package_path"], "docs/plans/demo/architecture")
        self.assertEqual(context["plan_revision"], 1)
        self.assertEqual(context["architecture_revision"], 4)
        self.assertEqual(context["package_receipt_sha256"], receipt)
        self.assertEqual(context["feature_mapping_sha256"], ac.object_sha256(row))

    def test_consumer_lint_identity_must_exactly_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_full_plan(root, "required")
            architecture_dir = plan_dir / "architecture"
            architecture_dir.mkdir()
            receipt = "a" * 64
            (architecture_dir / "architecture.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "project_slug": "demo",
                        "architecture_revision": 1,
                        "source_plan_revision": 1,
                        "feature_mappings": [mapping()],
                        "approval": {"receipt_sha256": receipt},
                    }
                ),
                encoding="utf-8",
            )
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "architecture-lint.py").write_text(
                "import json\n"
                "print(json.dumps({'status':'pass',"
                "'architecture_schema_version':2,'project_slug':'demo',"
                "'architecture_revision':1,'source_plan_revision':1,"
                f"'package_receipt_sha256':'{'b' * 64}'}}))\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ac.ContextError, "package identity"):
                ac.derive_context(
                    plan_dir,
                    "01-feature",
                    repo_root=root,
                    script_dir=scripts,
                )

    def test_every_no_package_outcome_is_typed_and_has_empty_mapping(self):
        for decision, expected in (
            ("not-required", "not-required"),
            ("recommended", "recommended-absent"),
            ("waived", "waived"),
        ):
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                context = ac.derive_context(
                    write_full_plan(root, decision),
                    "01-feature",
                    repo_root=root,
                )
                self.assertEqual(context["mode"], expected)
                self.assertTrue(all(not ids for ids in context["mapped_ids"].values()))
                self.assertIsNone(context["package_receipt_sha256"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / "docs/plans/demo"
            plan_dir.mkdir(parents=True)
            (plan_dir / "feature-plan.md").write_text("# Minimal\n", encoding="utf-8")
            context = ac.derive_context(
                plan_dir,
                "01-feature",
                repo_root=root,
                plan_mode="single-feature-minimal",
            )
            self.assertEqual(context["mode"], "single-feature-minimal")
            self.assertIsNone(context["plan_revision"])

    def test_required_absent_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ac.ContextError, "required.*absent"):
                ac.derive_context(
                    write_full_plan(root, "required"),
                    "01-feature",
                    repo_root=root,
                )

    def test_no_package_context_binds_full_direction_and_plan_authorities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_full_plan(root, "recommended")
            adr = root / "docs/decisions/ADR-001.md"
            adr.parent.mkdir(parents=True)
            adr.write_text(
                "# ADR-001\n\nStatus: accepted\n", encoding="utf-8"
            )
            plan_path = plan_dir / "plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["architecture_disposition"]["convergence"]["decision_refs"] = [
                "docs/decisions/ADR-001.md"
            ]
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            before = ac.derive_context(
                plan_dir, "01-feature", repo_root=root
            )

            feature = plan_dir / "features/01-feature.md"
            feature.write_text("# Materially changed feature\n", encoding="utf-8")
            after_feature = ac.derive_context(
                plan_dir, "01-feature", repo_root=root
            )
            self.assertNotEqual(
                before["plan_contract_sha256"],
                after_feature["plan_contract_sha256"],
            )

            adr.write_text(
                "# ADR-001\n\nStatus: accepted\n\nRevised boundary.\n",
                encoding="utf-8",
            )
            after_adr = ac.derive_context(
                plan_dir, "01-feature", repo_root=root
            )
            self.assertNotEqual(
                after_feature["plan_contract_sha256"],
                after_adr["plan_contract_sha256"],
            )

            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["architecture_disposition"]["triggers"] = [
                "shared-data-ownership-or-migration"
            ]
            plan["architecture_disposition"]["convergence"][
                "summary"
            ] = "materially revised direction"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            after_plan = ac.derive_context(
                plan_dir, "01-feature", repo_root=root
            )
            self.assertNotEqual(
                after_adr["plan_contract_sha256"],
                after_plan["plan_contract_sha256"],
            )

            (plan_dir / "architecture-selection.json").write_text(
                json.dumps({"schema_version": 2, "fixture": "reselected"}),
                encoding="utf-8",
            )
            after_selection = ac.derive_context(
                plan_dir, "01-feature", repo_root=root
            )
            self.assertNotEqual(
                after_plan["plan_contract_sha256"],
                after_selection["plan_contract_sha256"],
            )

    def test_minimal_context_binds_authority_and_rejects_mixed_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = root / "docs/plans/demo"
            spec_dir = plan_dir / "specs/01-feature"
            spec_dir.mkdir(parents=True)
            feature_plan = plan_dir / "feature-plan.md"
            feature_plan.write_text("# Minimal one\n", encoding="utf-8")
            context = ac.derive_context(
                plan_dir,
                "01-feature",
                repo_root=root,
                plan_mode="single-feature-minimal",
            )
            tasks = {
                "feature_id": "01-feature",
                "spec_revision": 1,
                "architecture_context": context,
                "tasks": [
                    {
                        "id": "T-1",
                        "files": ["src/feature.py"],
                        "verifies": ["TC-1"],
                    }
                ],
            }
            feature_plan.write_text(
                "# Materially changed minimal authority\n", encoding="utf-8"
            )
            hard, _ = ac.validate_spec_context(
                spec_text=markdown_with_context(context),
                tasks=tasks,
                spec_dir=spec_dir,
                repo_root=root,
            )
            self.assertTrue(any("stale or mismatched" in item for item in hard))

            (plan_dir / "architecture").mkdir()
            hard, _ = ac.validate_spec_context(
                spec_text=markdown_with_context(context),
                tasks=tasks,
                spec_dir=spec_dir,
                repo_root=root,
            )
            self.assertTrue(
                any("forbidden full-plan/architecture" in item for item in hard)
            )


class PersistedParityAndBinding(unittest.TestCase):
    def test_markdown_tasks_parity_and_current_plan_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_full_plan(root)
            context = ac.derive_context(
                plan_dir, "01-feature", repo_root=root
            )
            spec_dir = plan_dir / "specs/01-feature"
            spec_dir.mkdir(parents=True)
            tasks = {
                "feature_id": "01-feature",
                "spec_revision": 1,
                "architecture_context": context,
                "tasks": [
                    {"id": "T-1", "files": ["src/feature.py"], "verifies": ["TC-1"]}
                ],
            }
            spec_text = markdown_with_context(context)
            hard, parsed = ac.validate_spec_context(
                spec_text=spec_text,
                tasks=tasks,
                spec_dir=spec_dir,
                repo_root=root,
            )
            self.assertEqual(hard, [])
            self.assertEqual(parsed, context)

            plan = json.loads((plan_dir / "plan.json").read_text(encoding="utf-8"))
            plan["plan_revision"] = 2
            (plan_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
            hard, _ = ac.validate_spec_context(
                spec_text=spec_text,
                tasks=tasks,
                spec_dir=spec_dir,
                repo_root=root,
            )
            self.assertTrue(any("stale or mismatched" in item for item in hard))

    def test_binding_changes_when_declared_implementation_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_full_plan(root)
            context = ac.derive_context(plan_dir, "01-feature", repo_root=root)
            spec_dir = plan_dir / "specs/01-feature"
            spec_dir.mkdir(parents=True)
            source = root / "src/feature.py"
            source.parent.mkdir()
            source.write_text("value = 1\n", encoding="utf-8")
            tasks = {
                "feature_id": "01-feature",
                "spec_revision": 1,
                "architecture_context": context,
                "tasks": [
                    {"id": "T-1", "files": ["src/feature.py"], "verifies": ["TC-1"]}
                ],
            }
            (spec_dir / "ce-spec.md").write_text(
                markdown_with_context(context), encoding="utf-8"
            )
            (spec_dir / "tasks.json").write_text(
                json.dumps(tasks), encoding="utf-8"
            )
            before = ac.review_binding(spec_dir, repo_root=root)
            source.write_text("value = 2\n", encoding="utf-8")
            after = ac.review_binding(spec_dir, repo_root=root)
        self.assertNotEqual(
            before["implementation_files_sha256"],
            after["implementation_files_sha256"],
        )
        self.assertIsNone(before["commit_sha"])

    def test_binding_changes_when_undeclared_repository_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_full_plan(root)
            context = ac.derive_context(plan_dir, "01-feature", repo_root=root)
            spec_dir = plan_dir / "specs/01-feature"
            spec_dir.mkdir(parents=True)
            source = root / "src/feature.py"
            source.parent.mkdir()
            source.write_text("value = 1\n", encoding="utf-8")
            tasks = {
                "feature_id": "01-feature",
                "spec_revision": 1,
                "architecture_context": context,
                "tasks": [
                    {
                        "id": "T-1",
                        "files": ["src/feature.py"],
                        "verifies": ["TC-1"],
                    }
                ],
            }
            (spec_dir / "ce-spec.md").write_text(
                markdown_with_context(context), encoding="utf-8"
            )
            (spec_dir / "tasks.json").write_text(
                json.dumps(tasks), encoding="utf-8"
            )
            before = ac.review_binding(spec_dir, repo_root=root)
            (root / "src/unbound.py").write_text(
                "security_boundary = 'changed'\n", encoding="utf-8"
            )
            after = ac.review_binding(spec_dir, repo_root=root)
        self.assertEqual(
            before["implementation_files_sha256"],
            after["implementation_files_sha256"],
        )
        self.assertNotEqual(
            before["repository_state_sha256"],
            after["repository_state_sha256"],
        )

    def test_only_canonical_post_binding_evidence_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_dir = write_full_plan(root)
            context = ac.derive_context(plan_dir, "01-feature", repo_root=root)
            spec_dir = plan_dir / "specs/01-feature"
            spec_dir.mkdir(parents=True)
            source = root / "src/feature.py"
            source.parent.mkdir()
            source.write_text("value = 1\n", encoding="utf-8")
            tasks = {
                "feature_id": "01-feature",
                "spec_revision": 1,
                "architecture_context": context,
                "tasks": [
                    {
                        "id": "T-1",
                        "files": ["src/feature.py"],
                        "verifies": ["TC-1"],
                    }
                ],
            }
            (spec_dir / "ce-spec.md").write_text(
                markdown_with_context(context), encoding="utf-8"
            )
            (spec_dir / "tasks.json").write_text(
                json.dumps(tasks), encoding="utf-8"
            )
            before = ac.review_binding(spec_dir, repo_root=root)

            (spec_dir / "review-summary.json").write_text(
                "{}\n", encoding="utf-8"
            )
            (spec_dir / "code-review.md").write_text(
                "# Review\n", encoding="utf-8"
            )
            (plan_dir / ".metrics.jsonl").write_text("{}\n", encoding="utf-8")
            (plan_dir / "STATUS.md").write_text("# Status\n", encoding="utf-8")
            (plan_dir / "code-review.md").write_text(
                "# Plan review\n", encoding="utf-8"
            )
            run_dir = plan_dir / "ce-auto-build"
            run_dir.mkdir()
            (run_dir / "state.json").write_text("{}\n", encoding="utf-8")
            evidence_dir = plan_dir / "evidence"
            evidence_dir.mkdir()
            (evidence_dir / "CR-1.txt").write_text(
                "review trace\n", encoding="utf-8"
            )
            feature_evidence = spec_dir / "evidence"
            feature_evidence.mkdir()
            (feature_evidence / "CR-2.txt").write_text(
                "feature review trace\n", encoding="utf-8"
            )
            after_evidence = ac.review_binding(spec_dir, repo_root=root)
            self.assertEqual(
                before["repository_state_sha256"],
                after_evidence["repository_state_sha256"],
            )

            application_path = root / "src/ce-auto-build/runtime.py"
            application_path.parent.mkdir()
            application_path.write_text("changed = True\n", encoding="utf-8")
            after_application = ac.review_binding(spec_dir, repo_root=root)
            self.assertNotEqual(
                after_evidence["repository_state_sha256"],
                after_application["repository_state_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
