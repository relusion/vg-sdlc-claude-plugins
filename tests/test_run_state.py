"""Tests for auto-build's run-state.py — the deterministic run-state owner.

Covers the init schema, the fixed status-lattice transitions (legal / illegal /
bounded review repair / fail-from-anywhere), the counter
mechanics (consecutive-park bump + done-reset, failure-attempt cap → exit 1), the
provisional ledger, budget accrual, the circuit-breaker exit-code verdicts, and
the canonical .metrics.jsonl line schema — asserting the documented behavior is
reproduced purely via exit codes. A final integration test proves status-board
reads run-state's overlay from the canonical ce-auto-build/ path.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/run-state.py"
BOARD = REPO / "plugins/core-engineering/skills/ce-auto-build/scripts/status-board.py"
DATE = "2026-07-04"
BASELINE = "a" * 40
FEATURES = ("01-a", "02-b", "03-c")


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=30,
    )


def make_plan(root: Path, name="plan") -> Path:
    plan = root / name
    plan.mkdir(parents=True)
    return plan


def init(plan: Path, *, budget=1000, retry_cap=3, park_cap=3,
         date=DATE, baseline=BASELINE, features=FEATURES):
    args = ["init", "--plan-dir", str(plan), "--date", date,
            "--baseline", baseline,
            "--budget", str(budget), "--retry-cap", str(retry_cap),
            "--park-cap", str(park_cap)]
    for feature in features:
        args.extend(["--feature", feature])
    return run(*args)


def state_of(plan: Path, date=DATE) -> dict:
    return json.loads((plan / "ce-auto-build" / f"{date}-state.json").read_text())


def metrics_of(plan: Path) -> list:
    p = plan / ".metrics.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def ledger_of(plan: Path, date=DATE) -> list:
    p = plan / "ce-auto-build" / f"{date}-ledger.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


class Init(unittest.TestCase):
    def test_init_writes_schema_and_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            res = init(plan, budget=1000, retry_cap=2, park_cap=4)
            self.assertEqual(res.returncode, 0, res.stderr)
            st = state_of(plan)
            self.assertEqual(st["schema_version"], 2)
            self.assertEqual(st["slug"], "plan")
            self.assertEqual(st["date"], DATE)
            self.assertEqual(st["baseline"], BASELINE)
            self.assertEqual(st["selected_features"], list(FEATURES))
            self.assertEqual(st["bounds"], {
                "budget": 1000, "retry_cap": 2, "park_cap": 4})
            self.assertEqual(st["counters"],
                             {"consecutive_parks": 0, "budget_spent": 0})
            self.assertEqual(st["retry_counts"], {})
            self.assertEqual(st["features"], {})

    def test_reinit_refuses_and_has_no_force_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            self.assertEqual(init(plan, park_cap=1).returncode, 0)
            res = init(plan)
            self.assertEqual(res.returncode, 2)
            self.assertIn("already initialized", res.stdout)
            forced = run("init", "--plan-dir", str(plan), "--date", DATE,
                         "--baseline", BASELINE, "--feature", "01-a",
                         "--budget", "1000", "--retry-cap", "3",
                         "--park-cap", "9", "--force")
            self.assertEqual(forced.returncode, 2)
            self.assertEqual(state_of(plan)["bounds"]["park_cap"], 1)

    def test_init_bad_plan_dir_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            res = run("init", "--plan-dir", str(missing), "--date", DATE,
                      "--baseline", BASELINE, "--feature", "01-a",
                      "--budget", "1000")
            self.assertEqual(res.returncode, 2)
            self.assertIn("not an existing directory", res.stdout)

    def test_budget_is_required_and_bounds_must_be_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            missing = run("init", "--plan-dir", str(plan), "--date", DATE)
            self.assertEqual(missing.returncode, 2)
            zero = run("init", "--plan-dir", str(plan), "--date", DATE,
                       "--baseline", BASELINE, "--feature", "01-a",
                       "--budget", "0")
            self.assertEqual(zero.returncode, 2)

    def test_init_rejects_bad_baseline_and_duplicate_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            bad_base = init(plan, baseline="HEAD")
            self.assertEqual(bad_base.returncode, 2)
            duplicate = init(plan, features=("01-a", "01-a"))
            self.assertEqual(duplicate.returncode, 2)


class Advance(unittest.TestCase):
    def _init(self, tmp):
        plan = make_plan(Path(tmp))
        init(plan)
        return plan

    def test_forward_lattice_is_legal(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            for gate in ["specced", "implementing", "verifying", "reviewed", "done"]:
                res = run("advance", "01-a", gate, "--plan-dir", str(plan))
                self.assertEqual(res.returncode, 0, f"{gate}: {res.stdout}")
            self.assertEqual(state_of(plan)["features"]["01-a"]["status"], "done")

    def test_fixed_stages_may_not_be_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            self.assertEqual(run("advance", "01-a", "specced",
                                 "--plan-dir", str(plan)).returncode, 0)
            self.assertEqual(run("advance", "01-a", "done",
                                 "--plan-dir", str(plan)).returncode, 2)

    def test_backward_transition_is_illegal(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            for gate in ["specced", "implementing", "verifying", "reviewed"]:
                run("advance", "01-a", gate, "--plan-dir", str(plan))
            res = run("advance", "01-a", "specced", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 2)
            self.assertEqual(json.loads(res.stdout)["error"], "illegal-transition")
            # State unchanged: still reviewed.
            self.assertEqual(state_of(plan)["features"]["01-a"]["status"], "reviewed")

    def test_unknown_gate_is_illegal(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            res = run("advance", "01-a", "bogus", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 2)

    def test_feature_outside_approved_selection_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            state_path = plan / "ce-auto-build" / f"{DATE}-state.json"
            before = state_path.read_bytes()
            res = run("advance", "99-extra", "specced", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 2)
            self.assertEqual(state_path.read_bytes(), before)

    def test_advance_to_parked_via_advance_is_illegal(self):
        # parked has its own subcommand (it bumps the park counter); advancing
        # to it must be refused so the counter can never be bypassed.
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            res = run("advance", "01-a", "parked", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 2)

    def test_confirmed_review_failure_can_return_to_implementation(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            for gate in ["specced", "implementing", "verifying"]:
                run("advance", "01-a", gate, "--plan-dir", str(plan))
            refused = run("advance", "01-a", "implementing",
                          "--plan-dir", str(plan))
            self.assertEqual(refused.returncode, 2)
            self.assertEqual(run("retry", "01-a", "--plan-dir", str(plan)).returncode, 0)
            self.assertEqual(run("advance", "01-a", "implementing",
                                 "--plan-dir", str(plan)).returncode, 0)
            self.assertEqual(state_of(plan)["features"]["01-a"]["status"],
                             "implementing")

    def test_old_retry_authorization_cannot_enable_later_review_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            self.assertEqual(run("retry", "01-a", "--plan-dir", str(plan)).returncode, 0)
            for gate in ["specced", "implementing", "verifying"]:
                run("advance", "01-a", gate, "--plan-dir", str(plan))
            self.assertEqual(run("advance", "01-a", "implementing",
                                 "--plan-dir", str(plan)).returncode, 2)

    def test_fail_from_any_live_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            run("advance", "01-a", "specced", "--plan-dir", str(plan))
            run("advance", "01-a", "implementing", "--plan-dir", str(plan))
            self.assertEqual(run("advance", "01-a", "failed",
                                 "--plan-dir", str(plan)).returncode, 0)
            self.assertEqual(state_of(plan)["features"]["01-a"]["status"], "failed")

    def test_done_resets_consecutive_park_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            run("park", "01-a", "--class", "spec-gap", "--plan-dir", str(plan))
            run("park", "02-b", "--class", "structural", "--plan-dir", str(plan))
            self.assertEqual(state_of(plan)["counters"]["consecutive_parks"], 2)
            for gate in ["specced", "implementing", "verifying", "reviewed", "done"]:
                run("advance", "03-c", gate, "--plan-dir", str(plan))
            self.assertEqual(state_of(plan)["counters"]["consecutive_parks"], 0)

    def test_advance_metrics_line_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            for gate in ["specced", "implementing", "verifying"]:
                run("advance", "01-a", gate, "--plan-dir", str(plan))
            line = metrics_of(plan)[-1]
            self.assertEqual(line, {
                "ts": DATE, "stage": "auto-build", "plan": "plan",
                "feature": "01-a", "event": "gate", "gate": "pass",
                "escalation_type": None, "detail": "advance:verifying",
                "est": {"tokens": 0}})

    def test_done_emits_stage_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            for gate in ["specced", "implementing", "verifying", "reviewed", "done"]:
                run("advance", "01-a", gate, "--plan-dir", str(plan))
            line = metrics_of(plan)[-1]
            self.assertEqual(line["event"], "stage-complete")
            self.assertIsNone(line["gate"])

    def test_removed_advanced_states_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            for state in ("challenged", "diagnosing"):
                res = run("advance", "01-a", state, "--plan-dir", str(plan))
                self.assertEqual(res.returncode, 2)

    def test_tokens_accrue_to_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            run("advance", "01-a", "specced", "--plan-dir", str(plan),
                "--tokens", "120")
            self.assertEqual(state_of(plan)["counters"]["budget_spent"], 120)
            self.assertEqual(metrics_of(plan)[-1]["est"]["tokens"], 120)


class Park(unittest.TestCase):
    def test_park_bumps_counter_and_records_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan)
            res = run("park", "01-a", "--class", "spec-gap", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            st = state_of(plan)
            self.assertEqual(st["counters"]["consecutive_parks"], 1)
            self.assertEqual(st["features"]["01-a"]["status"], "parked")
            self.assertEqual(st["features"]["01-a"]["park_class"], "spec-gap")
            line = metrics_of(plan)[-1]
            self.assertEqual(line["event"], "park")
            self.assertIsNone(line["escalation_type"])
            self.assertEqual(line["detail"], "park:spec-gap")

    def test_park_requires_nonempty_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan)
            res = run("park", "01-a", "--class", "  ", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 2)

    def test_terminal_feature_cannot_be_parked_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan)
            first = run("park", "01-a", "--class", "spec-gap",
                        "--plan-dir", str(plan))
            second = run("park", "01-a", "--class", "structural",
                         "--plan-dir", str(plan))
            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(state_of(plan)["counters"]["consecutive_parks"], 1)


class Retry(unittest.TestCase):
    def test_retry_under_cap_exit_0_at_cap_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan, retry_cap=2)
            r1 = run("retry", "01-a", "--plan-dir", str(plan))
            self.assertEqual(r1.returncode, 0, r1.stderr)
            self.assertEqual(state_of(plan)["retry_counts"]["01-a"], 1)
            r2 = run("retry", "01-a", "--plan-dir", str(plan))
            self.assertEqual(r2.returncode, 1)          # cap reached
            self.assertTrue(json.loads(r2.stdout)["cap_reached"])
            self.assertEqual(state_of(plan)["retry_counts"]["01-a"], 2)
            self.assertEqual(state_of(plan)["features"]["01-a"]["status"], "failed")

    def test_terminal_feature_cannot_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan)
            run("park", "01-a", "--class", "spec-gap", "--plan-dir", str(plan))
            self.assertEqual(run("retry", "01-a", "--plan-dir", str(plan)).returncode, 2)

    def test_retry_metrics_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan, retry_cap=3)
            run("retry", "01-a", "--plan-dir", str(plan))
            line = metrics_of(plan)[-1]
            self.assertEqual(line["event"], "retry")
            self.assertEqual(line["detail"], "retry:1/3")

    def test_retry_counts_are_per_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan, retry_cap=2)
            run("retry", "01-a", "--plan-dir", str(plan))
            run("retry", "02-b", "--plan-dir", str(plan))
            st = state_of(plan)
            self.assertEqual(st["retry_counts"], {"01-a": 1, "02-b": 1})


class BudgetAndLedger(unittest.TestCase):
    def test_budget_add_accumulates(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan, budget=1000)
            run("budget-add", "--tokens", "300", "--plan-dir", str(plan))
            run("budget-add", "--tokens", "150", "--plan-dir", str(plan))
            self.assertEqual(state_of(plan)["counters"]["budget_spent"], 450)

    def test_negative_tokens_are_rejected_without_state_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan)
            commands = [
                ("advance", "01-a", "specced", "--plan-dir", str(plan), "--tokens", "-1"),
                ("park", "01-a", "--class", "gap", "--plan-dir", str(plan), "--tokens", "-1"),
                ("retry", "01-a", "--plan-dir", str(plan), "--tokens", "-1"),
                ("budget-add", "--tokens", "-1", "--plan-dir", str(plan)),
            ]
            for command in commands:
                with self.subTest(command=command[0]):
                    self.assertEqual(run(*command).returncode, 2)
            st = state_of(plan)
            self.assertEqual(st["counters"]["budget_spent"], 0)
            self.assertEqual(st["features"], {})
            self.assertEqual(st["retry_counts"], {})

    def test_ledger_append_marks_provisional(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan)
            entry = {"feature": "01-a", "point": "soft-delete default",
                     "disposition": "assumed"}
            res = run("ledger-append", "--entry", json.dumps(entry),
                      "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            rows = ledger_of(plan)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["provisional"], f"auto-build {DATE}")
            self.assertEqual(rows[0]["feature"], "01-a")
            self.assertEqual(rows[0]["ts"], DATE)

    def test_ledger_append_rejects_non_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan)
            self.assertEqual(run("ledger-append", "--entry", "[1,2]",
                                 "--plan-dir", str(plan)).returncode, 2)
            self.assertEqual(run("ledger-append", "--entry", "{bad",
                                 "--plan-dir", str(plan)).returncode, 2)


class BreakerCheck(unittest.TestCase):
    def test_continue_when_no_bound_tripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan, park_cap=3, budget=1000)
            res = run("breaker-check", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 0)
            self.assertEqual(json.loads(res.stdout)["verdict"], "continue")

    def test_park_cap_trips_breaker(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan, park_cap=2)
            run("park", "01-a", "--class", "spec-gap", "--plan-dir", str(plan))
            self.assertEqual(run("breaker-check", "--plan-dir", str(plan)).returncode, 0)
            run("park", "02-b", "--class", "structural", "--plan-dir", str(plan))
            res = run("breaker-check", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 1)
            verdict = json.loads(res.stdout)
            self.assertEqual(verdict["verdict"], "circuit-break")
            self.assertEqual(verdict["bounds"][0]["bound"], "consecutive-park-cap")

    def test_budget_trips_breaker(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan, budget=500)
            run("budget-add", "--tokens", "600", "--plan-dir", str(plan))
            res = run("breaker-check", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 1)
            self.assertEqual(json.loads(res.stdout)["bounds"][0]["bound"],
                             "budget-exhausted")

    def test_missing_state_is_could_not_evaluate(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))   # never init'd
            res = run("breaker-check", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 2)


class ScriptedCircuitBreakerSequence(unittest.TestCase):
    """The documented sequence reproduced purely via exit codes."""

    def test_init_advance_retry_park_breaker(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            self.assertEqual(init(plan, retry_cap=2, park_cap=2).returncode, 0)

            self.assertEqual(run("advance", "01-a", "specced",
                                 "--plan-dir", str(plan)).returncode, 0)
            # retry×N: the Nth (=cap) retry signals exit 1.
            self.assertEqual(run("retry", "01-a", "--plan-dir", str(plan)).returncode, 0)
            self.assertEqual(run("retry", "01-a", "--plan-dir", str(plan)).returncode, 1)
            # park×M toward the park cap; breaker stays green until reached.
            run("park", "02-b", "--class", "spec-gap", "--plan-dir", str(plan))
            self.assertEqual(run("breaker-check", "--plan-dir", str(plan)).returncode, 0)
            run("park", "03-c", "--class", "structural", "--plan-dir", str(plan))
            # park cap reached → circuit-break, purely by exit code.
            self.assertEqual(run("breaker-check", "--plan-dir", str(plan)).returncode, 1)


class Locating(unittest.TestCase):
    def test_legacy_state_schema_is_refused_instead_of_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan)
            state_path = plan / "ce-auto-build" / f"{DATE}-state.json"
            state = json.loads(state_path.read_text())
            state["schema_version"] = 1
            state_path.write_text(json.dumps(state))
            res = run("breaker-check", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 2)
            self.assertIn("unsupported schema_version", res.stdout)

    def test_newest_state_is_located_by_mtime(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan, date="2026-07-01", park_cap=5)
            init(plan, date="2026-07-02", park_cap=9)
            sd = plan / "ce-auto-build"
            os.utime(sd / "2026-07-01-state.json", (10_000_000, 10_000_000))
            os.utime(sd / "2026-07-02-state.json", (1, 1))
            # Park via the auto-located (mtime-newest) state = the 2026-07-01 one.
            run("park", "01-a", "--class", "spec-gap", "--plan-dir", str(plan))
            older = state_of(plan, "2026-07-01")
            newer = state_of(plan, "2026-07-02")
            self.assertEqual(older["counters"]["consecutive_parks"], 1)
            self.assertEqual(newer["counters"]["consecutive_parks"], 0)

    def test_explicit_state_path_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            init(plan, date="2026-07-01")
            init(plan, date="2026-07-02")
            target = plan / "ce-auto-build" / "2026-07-01-state.json"
            run("park", "01-a", "--class", "spec-gap", "--state", str(target))
            self.assertEqual(json.loads(target.read_text())
                             ["counters"]["consecutive_parks"], 1)


class Cli(unittest.TestCase):
    def test_no_subcommand_exits_2(self):
        # Portability parity: a bare run must exit within the 0/1/2 contract.
        res = run()
        self.assertEqual(res.returncode, 2)
        self.assertNotIn("Traceback", res.stderr)


class StatusBoardIntegration(unittest.TestCase):
    """run-state writes state.json; status-board reads its overlay (canonical path)."""

    def test_status_board_overlays_run_state_park(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            (plan / "plan.json").write_text(json.dumps({
                "features": [{"id": "01-a", "title": "A", "ship_order": 1}]}))
            (plan / "specs" / "01-a").mkdir(parents=True)
            (plan / "specs" / "01-a" / "ce-spec.md").write_text("# spec\n")
            init(plan)
            run("park", "01-a", "--class", "spec-gap", "--plan-dir", str(plan))
            board = subprocess.run(
                [sys.executable, str(BOARD), str(plan)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(board.returncode, 0, board.stderr)
            row = next(l for l in board.stdout.splitlines() if "`01-a`" in l)
            self.assertIn("**parked**", row)
            self.assertIn("per state.json", row)


if __name__ == "__main__":
    unittest.main()
