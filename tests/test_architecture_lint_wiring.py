"""Pin ce-architecture routing and ce-spec's optional consumption seams."""

import json
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ARCH = REPO / "plugins/core-engineering/skills/ce-architecture"
SPEC = REPO / "plugins/core-engineering/skills/ce-spec"
IMPLEMENT = REPO / "plugins/core-engineering/skills/ce-implement/SKILL.md"
REVIEW = REPO / "plugins/core-engineering/skills/ce-review/SKILL.md"
PLAN_R = REPO / "plugins/core-engineering/skills/ce-plan/stage-R-revision.md"
PLAN_TEMPLATE = REPO / "plugins/core-engineering/skills/ce-plan/artifact-template.md"
MINIMAL = REPO / "tests/fixtures/single-feature-minimal/docs/plans"


class ArchitectureLintWiring(unittest.TestCase):
    def test_lint_precedes_final_approval_and_publish(self):
        stage = (ARCH / "stage-3-5-review-write.md").read_text(encoding="utf-8")
        lint = stage.index("### 4.2 Run architecture-lint")
        approval = stage.index("### 5.1 Final Architecture Approval")
        publish = stage.index("### 5.2 Publish transactionally")
        self.assertLess(lint, approval)
        self.assertLess(approval, publish)

    def test_all_exit_codes_have_explicit_disposition(self):
        stage = (ARCH / "stage-3-5-review-write.md").read_text(encoding="utf-8")
        self.assertIn("**exit 0:**", stage)
        self.assertIn("**exit 1:**", stage)
        self.assertIn("**exit 2:**", stage)
        self.assertIn("Never call this a lint PASS", stage)

    def test_publish_is_bound_to_reviewed_scratch_and_human_status(self):
        stage = (ARCH / "stage-3-5-review-write.md").read_text(encoding="utf-8")
        self.assertIn("scripts/architecture-publish.py", stage)
        self.assertIn("--publish-status <approved|approved-with-gaps>", stage)
        self.assertIn("Do not edit the scratch package or destination after approval", stage)
        self.assertIn("Markdown bytes must remain identical to review", stage)
        self.assertIn("not crash-atomic", stage)

    def test_gate_pauses_drop_and_reacquire_write_authority(self):
        skill = (ARCH / "SKILL.md").read_text(encoding="utf-8")
        evidence = (ARCH / "stage-0-2-evidence-model.md").read_text(
            encoding="utf-8"
        )
        publish = (ARCH / "stage-3-5-review-write.md").read_text(encoding="utf-8")
        self.assertIn("immediately before yielding at any human\n   gate", skill)
        self.assertIn("reacquire this exact lease", skill)
        self.assertIn("lease-control baseline may remain", skill)
        self.assertIn("Restore the deny-only baseline immediately\nbefore printing", evidence)
        self.assertIn("Restore the deny-only baseline immediately before yielding", publish)
        self.assertIn("reacquire the exact ce-architecture\nlease", publish)

    def test_spec_validates_present_package_and_allows_absence(self):
        stage = (SPEC / "stage-0-1-frame-resolve.md").read_text(encoding="utf-8")
        self.assertIn("scripts/architecture-lint.py", stage)
        self.assertIn("--consumer --json", stage)
        self.assertIn("repository evidence drift", stage)
        self.assertIn("data entities/lifecycle", stage)
        self.assertIn("optional package absent", stage)
        self.assertIn("never silently ignored", stage)

    def test_plan_floor_precedes_single_feature_retirement(self):
        stage = (ARCH / "stage-0-2-evidence-model.md").read_text(encoding="utf-8")
        plan_floor = stage.index("### 0.4 Run the full-plan floor")
        single_feature = stage.index("lint-validated one-feature full plan")
        self.assertLess(plan_floor, single_feature)
        self.assertIn("cannot enter the\n  destructive retirement branch", stage)
        self.assertIn("scripts/architecture-retire.py", stage)
        self.assertIn("--expected-token <reviewed-64-lowercase-sha256>", stage)
        self.assertIn("`removed_paths`, do not claim rollback or completion", stage)

    def test_all_absence_routes_park_on_publish_transaction_state(self):
        architecture = (ARCH / "stage-0-2-evidence-model.md").read_text(
            encoding="utf-8"
        )
        spec = (SPEC / "stage-0-1-frame-resolve.md").read_text(encoding="utf-8")
        plan_revision = PLAN_R.read_text(encoding="utf-8")
        for text in (architecture, spec, plan_revision):
            self.assertIn(".architecture-publish-", text)
            for transaction_kind in ("lock", "stage", "backup", "rejected"):
                self.assertIn(transaction_kind, text)
            self.assertIn("explicit human recovery", text)

        scan = architecture.index("### 0.2 Recover publication transaction state")
        absent_route = architecture.index("lstat-confirmed `architecture` namespace absence")
        self.assertLess(scan, absent_route)
        self.assertIn("never record architecture as absent", spec)
        self.assertIn("never treat their presence as architecture\nabsence", plan_revision)

    def test_minimal_plan_fixture_has_stable_qualified_identity(self):
        registry = json.loads((MINIMAL / "plans.json").read_text(encoding="utf-8"))
        self.assertEqual(len(registry["plans"]), 1)
        slug = registry["plans"][0]["slug"]
        plan_dir = MINIMAL / slug
        plan = (plan_dir / "feature-plan.md").read_text(encoding="utf-8")

        self.assertFalse((plan_dir / "plan.json").exists())
        self.assertFalse((plan_dir / "shared-context.md").exists())
        self.assertFalse((plan_dir / "features").exists())
        self.assertEqual(len(re.findall(r"^## 4\. Single Feature\s*$", plan, re.M)), 1)
        ids = re.findall(r"^Feature ID:\s*(\S+)\s*$", plan, re.M)
        runs = re.findall(
            r"^Run:\s*/core-engineering:ce-spec\s+(\S+)/(\S+)\s*$",
            plan,
            re.M,
        )
        self.assertEqual(ids, ["01-health-check"])
        self.assertEqual(runs, [(slug, ids[0])])
        checkboxes = re.findall(r"^- \[ \] (\S+) — implemented and verified\s*$", plan, re.M)
        self.assertEqual(checkboxes, ids)

    def test_minimal_plan_routes_before_full_plan_floor(self):
        architecture = (ARCH / "stage-0-2-evidence-model.md").read_text(
            encoding="utf-8"
        )
        transaction_scan = architecture.index(".architecture-publish-")
        minimal_route = architecture.index("registry-backed single-feature minimal")
        plan_floor = architecture.index("Run the full-plan floor")
        self.assertLess(transaction_scan, minimal_route)
        self.assertLess(minimal_route, plan_floor)
        self.assertIn("/core-engineering:ce-spec <slug>/<id>", architecture)

    def test_spec_documents_minimal_authority_and_normal_output(self):
        stage = (SPEC / "stage-0-1-frame-resolve.md").read_text(encoding="utf-8")
        skill = (SPEC / "SKILL.md").read_text(encoding="utf-8")
        write = (SPEC / "stage-4-5-tasks-write.md").read_text(encoding="utf-8")
        for text in (stage, skill):
            self.assertIn("plan_mode: single-feature-minimal", text)
            self.assertIn("Feature ID: <id>", text)
            self.assertIn("Run: /core-engineering:ce-spec <slug>/<id>", text)
            self.assertIn("sole plan authority", text)
        self.assertIn("N/A by construction", stage)
        self.assertIn("write the same normal spec outputs", write)
        self.assertIn("no\nledger file", write)

    def test_plan_template_requires_minimal_qualified_run_line(self):
        template = PLAN_TEMPLATE.read_text(encoding="utf-8")
        minimal = template[template.index("## Recommended Minimal Output"):]
        self.assertIn("Feature ID: <id>", minimal)
        self.assertIn(
            "Run: /core-engineering:ce-spec service-health/01-health-check",
            minimal,
        )
        self.assertIn("must agree exactly", minimal)
        self.assertIn("implemented and verified", minimal)

    def test_minimal_plan_handoff_reaches_implement_and_review(self):
        implement = IMPLEMENT.read_text(encoding="utf-8")
        review = REVIEW.read_text(encoding="utf-8")
        for text in (implement, review):
            self.assertIn("single-feature-minimal", text)
            self.assertIn("feature-plan.md", text)
            self.assertIn("N/A by construction", text)
            self.assertIn("/core-engineering:ce-plan", text)
        self.assertIn("sole plan context", implement)
        self.assertIn("ordinary\n  Security and Correctness lenses still run", review)

    def test_implement_reuses_minimal_plan_authority(self):
        implement = IMPLEMENT.read_text(encoding="utf-8")
        self.assertIn("plan_mode: single-feature-minimal", implement)
        self.assertIn("feature-plan.md` as the\n  sole plan context", implement)
        self.assertIn("ce-spec.md` + `tasks.json` remain the implementation authority", implement)
        self.assertIn("mixed shape", implement)
        self.assertIn("match the one checkbox keyed by the exact `Feature ID`", implement)
        self.assertIn("rather than appending or guessing a row", implement)

    def test_validator_is_registered_fork(self):
        manifest = (REPO / "plugins/core-engineering/fork-manifest.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("ce-architecture/scripts/architecture-lint.py", manifest)
        self.assertIn("ce-spec/scripts/architecture-lint.py", manifest)
        self.assertEqual(
            (ARCH / "scripts/architecture-lint.py").read_bytes(),
            (SPEC / "scripts/architecture-lint.py").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
