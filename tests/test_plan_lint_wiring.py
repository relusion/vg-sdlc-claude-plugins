"""WS6-T4 — plan-lint wired as a write-time gate in /ce-plan + /ce-auto-build kickoff.

Behaviour of plan-lint.py itself is covered by test_plan_lint.py; this suite locks
the *wiring* so a future edit cannot silently unhook the gate or let a fork drift:

  * the fork entry is registered with the canonical + both copies, byte-identical;
  * ce-plan Stage 9 invokes plan-lint over the written dir with exit-code disposition,
    and runs it BEFORE the resume scratch is deleted (a FAIL must stay resumable);
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

PLAN_STAGE = REPO / "plugins/core-engineering/skills/ce-plan/stage-8-9-write.md"
PLAN_SKILL = REPO / "plugins/core-engineering/skills/ce-plan/SKILL.md"
AUTOBUILD_STAGE0 = REPO / "plugins/core-engineering/skills/ce-auto-build/stage-0-kickoff.md"

INVOCATION = 'scripts/plan-lint.py" docs/plans/<slug> --json'


class PlanLintForkRegistration(unittest.TestCase):
    def _entry(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        return next((f for f in data["forks"] if f.get("canonical") == CANONICAL), None)

    def test_fork_entry_registered_with_both_copies(self):
        entry = self._entry()
        self.assertIsNotNone(
            entry, "plan-lint.py fork must be registered in fork-manifest.json"
        )
        self.assertIn(PLAN_COPY, entry["copies"])
        self.assertIn(AUTOBUILD_COPY, entry["copies"])

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


class PlanWriteTimeGateWiring(unittest.TestCase):
    def test_stage9_invokes_plan_lint_over_written_dir(self):
        self.assertIn(INVOCATION, PLAN_STAGE.read_text(encoding="utf-8"))

    def test_stage9_states_exit_code_disposition(self):
        text = PLAN_STAGE.read_text(encoding="utf-8")
        for needle in ("exit 0", "exit 1", "exit 2",
                       "N/A — single-feature minimal plan"):
            self.assertIn(needle, text,
                          f"Stage 9 gate must state disposition: {needle!r}")

    def test_stage9_gate_runs_before_scratch_deletion(self):
        # A FAIL keeps the run resumable: the lint must run BEFORE the
        # "Delete the gate-checkpoint scratch on success" step, never after.
        text = PLAN_STAGE.read_text(encoding="utf-8")
        self.assertLess(
            text.index("plan-lint.py"),
            text.index("Delete the gate-checkpoint scratch on success"),
        )

    def test_honest_limitation_no_longer_claims_direction_unproven(self):
        text = PLAN_SKILL.read_text(encoding="utf-8")
        self.assertNotIn("Dependency direction is not machine-proven", text)
        self.assertIn("plan-lint.py", text)


class AutoBuildKickoffWiring(unittest.TestCase):
    def test_stage0_plan_lints_before_spawn(self):
        text = AUTOBUILD_STAGE0.read_text(encoding="utf-8")
        self.assertIn(INVOCATION, text)
        self.assertIn("before any spawn", text)

    def test_stage0_states_exit_code_disposition(self):
        text = AUTOBUILD_STAGE0.read_text(encoding="utf-8")
        for needle in ("exit 0", "exit 1", "exit 2"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
