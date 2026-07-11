"""Tests for auto-build's run-state.py — the deterministic run-state owner.

Covers the init schema, the status-lattice transitions (legal / illegal /
optional-stage skips / diagnose detours / fail-from-anywhere), the counter
mechanics (consecutive-park bump + done-reset, retry cap → exit 1), the
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


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=30,
    )


def make_plan(root: Path, name="plan") -> Path:
    plan = root / name
    plan.mkdir(parents=True)
    return plan


def init(plan: Path, *, budget=None, retry_cap=3, park_cap=3, spawn_caps=None,
         date=DATE):
    args = ["init", "--plan-dir", str(plan), "--date", date,
            "--retry-cap", str(retry_cap), "--park-cap", str(park_cap)]
    if budget is not None:
        args += ["--budget", str(budget)]
    for name, val in (spawn_caps or {}).items():
        args += ["--spawn-cap", f"{name}={val}"]
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
            res = init(plan, budget=1000, retry_cap=2, park_cap=4,
                       spawn_caps={"spec": 50, "implement": 80})
            self.assertEqual(res.returncode, 0, res.stderr)
            st = state_of(plan)
            self.assertEqual(st["schema_version"], 1)
            self.assertEqual(st["slug"], "plan")
            self.assertEqual(st["date"], DATE)
            self.assertEqual(st["bounds"], {
                "budget": 1000, "retry_cap": 2, "park_cap": 4,
                "spawn_caps": {"spec": 50, "implement": 80}})
            self.assertEqual(st["counters"],
                             {"consecutive_parks": 0, "budget_spent": 0})
            self.assertEqual(st["retry_counts"], {})
            self.assertEqual(st["features"], {})

    def test_reinit_refuses_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            self.assertEqual(init(plan).returncode, 0)
            res = init(plan)
            self.assertEqual(res.returncode, 2)
            self.assertIn("already initialized", res.stdout)

    def test_force_reinit_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            self.assertEqual(init(plan, park_cap=1).returncode, 0)
            res = run("init", "--plan-dir", str(plan), "--date", DATE,
                      "--park-cap", "9", "--force")
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(state_of(plan)["bounds"]["park_cap"], 9)

    def test_init_bad_plan_dir_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            res = run("init", "--plan-dir", str(missing), "--date", DATE)
            self.assertEqual(res.returncode, 2)
            self.assertIn("not an existing directory", res.stdout)

    def test_bad_spawn_cap_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(Path(tmp))
            res = run("init", "--plan-dir", str(plan), "--date", DATE,
                      "--spawn-cap", "spec=notint")
            self.assertEqual(res.returncode, 2)


class Advance(unittest.TestCase):
    def _init(self, tmp):
        plan = make_plan(Path(tmp))
        init(plan)
        return plan

    def test_forward_lattice_is_legal(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            for gate in ["specced", "challenged", "implementing",
                         "verifying", "reviewed", "done"]:
                res = run("advance", "01-a", gate, "--plan-dir", str(plan))
                self.assertEqual(res.returncode, 0, f"{gate}: {res.stdout}")
            self.assertEqual(state_of(plan)["features"]["01-a"]["status"], "done")

    def test_optional_stages_may_be_skipped(self):
        # Challenger off (skip challenged) and review off (skip reviewed).
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            self.assertEqual(run("advance", "01-a", "specced",
                                 "--plan-dir", str(plan)).returncode, 0)
            self.assertEqual(run("advance", "01-a", "implementing",
                                 "--plan-dir", str(plan)).returncode, 0)
            self.assertEqual(run("advance", "01-a", "verifying",
                                 "--plan-dir", str(plan)).returncode, 0)
            self.assertEqual(run("advance", "01-a", "done",
                                 "--plan-dir", str(plan)).returncode, 0)

    def test_backward_transition_is_illegal(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            run("advance", "01-a", "reviewed", "--plan-dir", str(plan))
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

    def test_advance_to_parked_via_advance_is_illegal(self):
        # parked has its own subcommand (it bumps the park counter); advancing
        # to it must be refused so the counter can never be bypassed.
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            res = run("advance", "01-a", "parked", "--plan-dir", str(plan))
            self.assertEqual(res.returncode, 2)

    def test_diagnose_detour(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            for gate in ["specced", "implementing", "verifying"]:
                run("advance", "01-a", gate, "--plan-dir", str(plan))
            # verifying → diagnosing (failed verify gate under diagnose mode)
            self.assertEqual(run("advance", "01-a", "diagnosing",
                                 "--plan-dir", str(plan)).returncode, 0)
            # diagnosing → implementing (a bug: targeted re-implement)
            self.assertEqual(run("advance", "01-a", "implementing",
                                 "--plan-dir", str(plan)).returncode, 0)
            # diagnosing is illegal from implementing (only verify/review reach it)
            run("advance", "01-a", "verifying", "--plan-dir", str(plan))
            self.assertEqual(run("advance", "01-a", "implementing",
                                 "--plan-dir", str(plan)).returncode, 2)

    def test_fail_from_any_live_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
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
            run("advance", "03-c", "done", "--plan-dir", str(plan))
            self.assertEqual(state_of(plan)["counters"]["consecutive_parks"], 0)

    def test_advance_metrics_line_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            run("advance", "01-a", "verifying", "--plan-dir", str(plan))
            line = metrics_of(plan)[-1]
            self.assertEqual(line, {
                "ts": DATE, "stage": "auto-build", "plan": "plan",
                "feature": "01-a", "event": "gate", "gate": "pass",
                "escalation_type": None, "detail": "advance:verifying",
                "est": {"tokens": 0}})

    def test_done_emits_stage_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            run("advance", "01-a", "done", "--plan-dir", str(plan))
            line = metrics_of(plan)[-1]
            self.assertEqual(line["event"], "stage-complete")
            self.assertIsNone(line["gate"])

    def test_escalation_flag_emits_escalation_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._init(tmp)
            for gate in ["specced", "implementing", "verifying"]:
                run("advance", "01-a", gate, "--plan-dir", str(plan))
            run("advance", "01-a", "diagnosing", "--plan-dir", str(plan))
            res = run("advance", "01-a", "implementing", "--plan-dir", str(plan),
                      "--escalation", "/ce-implement", "--detail", "diagnose:bug")
            self.assertEqual(res.returncode, 0)
            line = metrics_of(plan)[-1]
            self.assertEqual(line["event"], "escalation")
            self.assertEqual(line["escalation_type"], "/ce-implement")
            self.assertEqual(line["detail"], "diagnose:bug")

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
