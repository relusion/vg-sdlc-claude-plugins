"""Fixture tests for idea-score's score-lint.py — the Verdict-Honesty gate.

Locks in H8's buy-back guard across BOTH disqualification paths: a breached knockout
floor (Gates says DISQUALIFIED) and a FIRED binary kill-condition (an affirmative `DEAD`
in the Gates section). The latter used to slip through — H8 keyed only on the DISQUALIFIED
token, so a DEAD-but-Pursue artifact passed clean. These fixtures assert the fired kill now
blocks Pursue, while the `DEAD if any true` rubric phrasing and a `not DEAD` status do not
false-positive, and a fired kill paired with Drop still passes (the gate bars only Pursue).
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/product-discovery/skills/ce-idea-score/scripts/score-lint.py"

# A valid Scorecard + Kill-Condition + Weighted Verdict that passes H1–H7. Feasibility and
# Distribution are >= 4 so no knockout floor is breached — H8 is then the only gate that can
# fire, isolating the binary-kill behavior under test.
SCORECARD = """## Scorecard
| Axis | Score | Evidence |
|---|---|---|
| Market demand | 7 | confirmed |
| Distribution | 6 | suspected |
| Feasibility | 7 | confirmed |
| Differentiation | 5 | suspected |
| Defensibility | 3 | suspected |
| Revenue potential | 6 | confirmed |
| Timing | 7 | confirmed |
"""

TAIL = """
## Kill-Condition
DEAD IF fewer than 3 of 20 cold-outreach target buyers take a paid pilot call within two weeks.

## Weighted Verdict
Weights: Distribution 0.20, Feasibility 0.18, Market demand 0.17, Timing 0.15, Revenue potential 0.13, Differentiation 0.10, Defensibility 0.07
Vector: 7/6/7/5/3/6/7
Composite: 6.1
The weighting is an opinionated profile, not a fact; read the vector, not just the number.
"""


def artifact(gates_body: str, recommendation: str) -> str:
    return (
        SCORECARD
        + "\n## Gates\n"
        + gates_body.rstrip()
        + "\n"
        + TAIL
        + "\n## Recommendation\n"
        + recommendation
        + "\n"
    )


def lint(md: str):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(md)
        path = f.name
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), path],
        capture_output=True, text=True, timeout=30,
    )
    Path(path).unlink(missing_ok=True)
    return proc


FLOOR_PASS = "- Knockout floors: Feasibility 7, Distribution 6 -> PASS (neither <= 3)."


class H8BinaryKill(unittest.TestCase):
    def test_fired_binary_kill_with_pursue_fails(self):
        gates = (
            FLOOR_PASS
            + "\n- Binary kill-conditions (DEAD if any true): depends on an exclusive"
            " dataset the team cannot get -- DEAD."
        )
        proc = lint(artifact(gates, "Pursue"))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("H8", proc.stdout)

    def test_fired_binary_kill_with_pursue_with_changes_fails(self):
        gates = FLOOR_PASS + "\n- Binary kill-conditions: regulated license blocker -- DEAD."
        proc = lint(artifact(gates, "Pursue-with-changes"))
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("H8", proc.stdout)

    def test_rubric_phrasing_only_with_pursue_passes(self):
        # "(DEAD if any true)" is the rubric, not a fired result — must not false-positive.
        gates = (
            FLOOR_PASS
            + "\n- Binary kill-conditions (DEAD if any true): none fired -- no"
            " regulated-license, capital, or exclusive-data blocker."
        )
        proc = lint(artifact(gates, "Pursue"))
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_explicit_not_dead_with_pursue_passes(self):
        gates = FLOOR_PASS + "\n- Binary kill-conditions: regulated license not DEAD; capital not DEAD."
        proc = lint(artifact(gates, "Pursue"))
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_fired_binary_kill_with_drop_passes(self):
        # The gate bars only Pursue / Pursue-with-changes; a fired kill SHOULD be Drop.
        gates = FLOOR_PASS + "\n- Binary kill-conditions: exclusive dataset unobtainable -- DEAD."
        proc = lint(artifact(gates, "Drop"))
        self.assertEqual(proc.returncode, 0, proc.stdout)


class H8KnockoutFloor(unittest.TestCase):
    def test_breached_floor_disqualified_with_pursue_fails(self):
        # Feasibility 2 breaches the floor; Gates says DISQUALIFIED; Pursue must fail (H4 and H8).
        scorecard = SCORECARD.replace("| Feasibility | 7 |", "| Feasibility | 2 |")
        gates = "- Knockout floors: Feasibility 2 <= 3 -> DISQUALIFIED."
        md = (
            scorecard + "\n## Gates\n" + gates + "\n" + TAIL
            + "\n## Recommendation\nPursue\n"
        )
        proc = lint(md)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("H8", proc.stdout)


if __name__ == "__main__":
    unittest.main()
