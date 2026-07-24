"""WS6-T4 — plan-lint wired as a write-time gate in /core-engineering:ce-plan + /core-engineering:ce-auto-build kickoff.

Behaviour of plan-lint.py itself is covered by test_plan_lint.py; this suite locks
the *wiring* so a future edit cannot silently unhook the gate or let a fork drift:

  * the fork entry is registered with every consumer copy, byte-identical;
  * ce-plan validates exact scratch bytes before Final Plan Approval, publishes
    them unchanged, then reruns plan-lint as a post-publication drift check;
  * ce-auto-build Stage 0 plan-lints the resolved plan before any spawn;
  * ce-plan's Honest Limitations no longer claims dependency direction is unproven.
"""

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "plugins/core-engineering/fork-manifest.json"

CANONICAL = "plugins/core-engineering/skills/ce-plan-audit/scripts/plan-lint.py"
PLAN_COPY = "plugins/core-engineering/skills/ce-plan/scripts/plan-lint.py"
AUTOBUILD_COPY = "plugins/core-engineering/skills/ce-auto-build/scripts/plan-lint.py"
ARCHITECTURE_COPY = "plugins/core-engineering/skills/ce-architecture/scripts/plan-lint.py"
SPEC_COPY = "plugins/core-engineering/skills/ce-spec/scripts/plan-lint.py"
IMPLEMENT_COPY = "plugins/core-engineering/skills/ce-implement/scripts/plan-lint.py"
REVIEW_COPY = "plugins/core-engineering/skills/ce-review/scripts/plan-lint.py"
VERIFY_COPY = "plugins/core-engineering/skills/ce-verify/scripts/plan-lint.py"
RELEASE_COPY = "plugins/core-engineering/skills/ce-ship-release/scripts/plan-lint.py"

SELECTION_CANONICAL = (
    "plugins/core-engineering/skills/ce-plan-audit/scripts/architecture-selection-lint.py"
)
SELECTION_COPIES = [
    "plugins/core-engineering/skills/ce-architecture/scripts/architecture-selection-lint.py",
    "plugins/core-engineering/skills/ce-plan/scripts/architecture-selection-lint.py",
    "plugins/core-engineering/skills/ce-auto-build/scripts/architecture-selection-lint.py",
    "plugins/core-engineering/skills/ce-spec/scripts/architecture-selection-lint.py",
    "plugins/core-engineering/skills/ce-implement/scripts/architecture-selection-lint.py",
    "plugins/core-engineering/skills/ce-review/scripts/architecture-selection-lint.py",
    "plugins/core-engineering/skills/ce-verify/scripts/architecture-selection-lint.py",
    "plugins/core-engineering/skills/ce-ship-release/scripts/architecture-selection-lint.py",
]

PLAN_STAGE = REPO / "plugins/core-engineering/skills/ce-plan/stage-8-9-write.md"
PLAN_SKILL = REPO / "plugins/core-engineering/skills/ce-plan/SKILL.md"
AUTOBUILD_STAGE0 = REPO / "plugins/core-engineering/skills/ce-auto-build/stage-0-kickoff.md"
VERIFY_STAGE0 = REPO / "plugins/core-engineering/skills/ce-verify/stage-0-1-load-check.md"
RELEASE_STAGES = REPO / "plugins/core-engineering/skills/ce-ship-release/stages.md"

PLAN_LINT_COMMAND = 'scripts/plan-lint.py"'
REMOVED_DIRECTION_FLAG = "--require-architecture-direction"


class PlanLintForkRegistration(unittest.TestCase):
    def _entry(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        return next((f for f in data["forks"] if f.get("canonical") == CANONICAL), None)

    def test_fork_entry_registered_with_all_consumers(self):
        entry = self._entry()
        self.assertIsNotNone(
            entry, "plan-lint.py fork must be registered in fork-manifest.json"
        )
        self.assertIn(PLAN_COPY, entry["copies"])
        self.assertIn(AUTOBUILD_COPY, entry["copies"])
        self.assertIn(ARCHITECTURE_COPY, entry["copies"])
        self.assertIn(SPEC_COPY, entry["copies"])
        self.assertIn(IMPLEMENT_COPY, entry["copies"])
        self.assertIn(REVIEW_COPY, entry["copies"])
        self.assertIn(VERIFY_COPY, entry["copies"])
        self.assertIn(RELEASE_COPY, entry["copies"])

    def test_copies_are_byte_identical_to_canonical(self):
        canon = (REPO / CANONICAL).read_bytes()
        self.assertEqual(
            (REPO / PLAN_COPY).read_bytes(), canon,
            "ce-plan plan-lint copy drifted from canonical",
        )
        self.assertEqual(
            (REPO / AUTOBUILD_COPY).read_bytes(), canon,
            "ce-auto-build plan-lint copy drifted from canonical",
        )
        self.assertEqual(
            (REPO / ARCHITECTURE_COPY).read_bytes(), canon,
            "ce-architecture plan-lint copy drifted from canonical",
        )
        self.assertEqual(
            (REPO / SPEC_COPY).read_bytes(), canon,
            "ce-spec plan-lint copy drifted from canonical",
        )
        self.assertEqual(
            (REPO / IMPLEMENT_COPY).read_bytes(), canon,
            "ce-implement plan-lint copy drifted from canonical",
        )
        self.assertEqual(
            (REPO / REVIEW_COPY).read_bytes(), canon,
            "ce-review plan-lint copy drifted from canonical",
        )
        self.assertEqual(
            (REPO / VERIFY_COPY).read_bytes(), canon,
            "ce-verify plan-lint copy drifted from canonical",
        )
        self.assertEqual(
            (REPO / RELEASE_COPY).read_bytes(), canon,
            "ce-ship-release plan-lint copy drifted from canonical",
        )

    def test_selection_lint_registered_for_every_plan_lint_consumer(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        entry = next(
            (
                fork
                for fork in data["forks"]
                if fork.get("canonical") == SELECTION_CANONICAL
            ),
            None,
        )
        self.assertIsNotNone(
            entry,
            "architecture-selection-lint.py must be registered in fork-manifest.json",
        )
        self.assertEqual(entry["copies"], SELECTION_COPIES)

    def test_selection_lint_copies_are_byte_identical(self):
        canonical = (REPO / SELECTION_CANONICAL).read_bytes()
        for copy in SELECTION_COPIES:
            with self.subTest(copy=copy):
                self.assertEqual((REPO / copy).read_bytes(), canonical)

    def test_plan_lint_loads_only_its_colocated_selection_validator(self):
        canonical = (REPO / CANONICAL).read_text(encoding="utf-8")
        self.assertIn(
            'Path(__file__).with_name("architecture-selection-lint.py")', canonical
        )
        self.assertNotIn("skills/ce-plan-audit", canonical)


class PlanWriteTimeGateWiring(unittest.TestCase):
    def test_stage8_lints_scratch_before_approval_and_stage9_rechecks_publication(self):
        text = PLAN_STAGE.read_text(encoding="utf-8")
        scratch = text.index("docs/plans/.plan-candidate-<slug>-<run-id>")
        first_lint = text.index(PLAN_LINT_COMMAND, scratch)
        approval = text.index("## 8.3 Final Plan Approval")
        publication = text.index("## 9. Publish the approved bytes")
        second_lint = text.index("post-publication runs", publication)
        self.assertLess(scratch, first_lint)
        self.assertLess(first_lint, approval)
        self.assertLess(approval, publication)
        self.assertLess(publication, second_lint)
        self.assertNotIn(REMOVED_DIRECTION_FLAG, text)
        self.assertIn("docs/plans/<slug>", text[publication:])
        self.assertGreaterEqual(text.count(PLAN_LINT_COMMAND), 2)

    def test_stage9_states_exit_code_disposition(self):
        text = PLAN_STAGE.read_text(encoding="utf-8")
        for needle in ("exit 0", "exit 1", "exit 2", "non-waivable"):
            self.assertIn(needle, text,
                          f"Stage 9 gate must state disposition: {needle!r}")

    def test_validation_runs_before_candidate_scratch_deletion(self):
        # A FAIL keeps the run inspectable: validation and publication checks
        # precede deletion of the exact candidate.
        text = PLAN_STAGE.read_text(encoding="utf-8")
        self.assertLess(
            text.index("plan-lint.py"),
            text.index("Delete only the exact candidate scratch"),
        )

    def test_honest_limitation_no_longer_claims_direction_unproven(self):
        text = PLAN_SKILL.read_text(encoding="utf-8")
        self.assertNotIn("Dependency direction is not machine-proven", text)
        self.assertIn("plan-lint.py", text)


class AutoBuildKickoffWiring(unittest.TestCase):
    def test_stage0_plan_lints_before_spawn(self):
        text = AUTOBUILD_STAGE0.read_text(encoding="utf-8")
        lint = text.index(PLAN_LINT_COMMAND)
        self.assertIn("docs/plans/<slug>", text[lint:])
        self.assertNotIn(REMOVED_DIRECTION_FLAG, text)
        self.assertIn("before any spawn", text)

    def test_stage0_states_exit_code_disposition(self):
        text = AUTOBUILD_STAGE0.read_text(encoding="utf-8")
        for needle in ("exit 0", "exit 1", "exit 2"):
            self.assertIn(needle, text)


class AssuranceEntryPreflightWiring(unittest.TestCase):
    def _assert_current_authority_preflight(self, text, before):
        selection = text.index("scripts/architecture-selection-lint.py")
        plan = text.index("scripts/plan-lint.py", selection)
        consumer = text.index(before, plan)
        self.assertLess(selection, plan)
        self.assertLess(plan, consumer)
        self.assertNotIn("--require-current-schema", text[selection:plan])
        self.assertNotIn(REMOVED_DIRECTION_FLAG, text[plan:consumer])
        self.assertIn("--json", text[plan:consumer])
        for needle in ("exit 0", "Exit 1", "exit 2"):
            self.assertIn(needle, text[selection:consumer])
        self.assertIn("current", text[selection:consumer].lower())

    def test_verify_rejects_non_current_authority_before_feature_state(self):
        self._assert_current_authority_preflight(
            VERIFY_STAGE0.read_text(encoding="utf-8"),
            "### 0.3 Derive Feature State",
        )

    def test_release_rejects_non_current_authority_before_feature_gates(self):
        self._assert_current_authority_preflight(
            RELEASE_STAGES.read_text(encoding="utf-8"),
            "For each in-range feature",
        )


if __name__ == "__main__":
    unittest.main()
