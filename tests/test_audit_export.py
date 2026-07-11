"""Fixture tests for retro's audit-export.py — the evidence compiler.

Asserts feature evidence derivation, honest gap reporting, the
count-don't-skip rule for unparseable metrics lines, and the exit-code
contract.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-retro/scripts/audit-export.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=30,
    )


def make_fixture(root: Path) -> Path:
    plan = root / "demo-plan"
    (plan / "specs" / "01-core").mkdir(parents=True)
    (plan / "specs" / "02-api").mkdir(parents=True)
    (plan / "auto-build").mkdir()
    (plan / "plan.json").write_text(json.dumps({"features": [
        {"id": "01-core", "title": "Core", "ship_order": 1,
         "final_complexity": "Moderate"},
        {"id": "02-api", "title": "API", "ship_order": 2,
         "final_complexity": "Simple"},
    ]}))
    s1 = plan / "specs" / "01-core"
    # ce-spec.md is the canonical name; its TC headings carry verification tags
    (s1 / "ce-spec.md").write_text(
        "# spec\n\n"
        "## 4. Test Cases\n\n"
        "### TC-1  (proves AC-1) — modality: http · verification: auto\n"
        "- Expected: 200\n\n"
        "### TC-2  (proves AC-1) — modality: browser · "
        "verification: manual:harness-gap\n"
        "- Expected: renders\n\n"
        "### TC-3  (proves AC-2) — modality: manual · "
        "verification: manual:judgment\n"
        "- Reason: aesthetic taste — never manual:judgment in prose here\n")
    (s1 / "tasks.json").write_text(json.dumps(
        {"feature_id": "01-core",
         "tasks": [{"id": "T0", "status": "done"}, {"id": "T1", "status": "done"}]}))
    (s1 / "verification.md").write_text("# verified\n")
    (s1 / "review-summary.json").write_text(json.dumps(
        {"blocking_high": 0, "findings_total": 3, "suppressed": 1}))
    # per-feature (auto-build) diagnosis lives under specs/<id>/
    (s1 / "diagnosis.md").write_text("# DX-1 per-feature\n")
    s2 = plan / "specs" / "02-api"
    # 02-api: spec present but NO TC verification tags -> testability zero (honest)
    (s2 / "spec.md").write_text("# spec\n")
    (s2 / "tasks.json").write_text(json.dumps(
        {"feature_id": "02-api", "tasks": [{"id": "T0", "status": "done"}]}))
    # 02-api: all tasks done, NO verification.md -> must surface as a gap
    (plan / ".metrics.jsonl").write_text("\n".join([
        json.dumps({"ts": "2026-06-11", "stage": "spec", "plan": "demo-plan",
                    "feature": "01-core", "event": "stage-complete",
                    "gate": None, "escalation_type": None, "detail": "",
                    "est": {"tokens": 100}}),
        json.dumps({"ts": "2026-06-11", "stage": "implement", "plan": "demo-plan",
                    "feature": "01-core", "event": "gate", "gate": "pass",
                    "escalation_type": None, "detail": "test-guard: 0",
                    "est": {"tokens": 0}}),
        json.dumps({"ts": "2026-06-11", "stage": "implement", "plan": "demo-plan",
                    "feature": "01-core", "event": "retry",
                    "escalation_type": None, "detail": "re-attempt T1",
                    "est": {"tokens": 0}}),
        json.dumps({"ts": "2026-06-11", "stage": "spec", "plan": "demo-plan",
                    "feature": "02-api", "event": "escalation", "gate": None,
                    "escalation_type": "/ce-plan", "detail": "boundary conflict",
                    "est": {"tokens": 0}}),
        "{this line is not json",
        json.dumps(["not", "an", "object"]),
    ]) + "\n")
    (plan / "auto-build" / "2026-06-11-run.md").write_text("# run\n")
    (plan / "shared-context.md").write_text("# ctx\n")
    # plan-root diagnosis.md is /ce-debug's INTERACTIVE (cumulative) output
    (plan / "diagnosis.md").write_text("# DX-1 plan-root\n")
    return plan


class Export(unittest.TestCase):
    def test_compiles_evidence_and_reports_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_fixture(Path(tmp))
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)

            self.assertEqual(doc["schema_version"], 1)
            self.assertEqual(doc["plan"]["feature_count"], 2)
            self.assertEqual(doc["plan"]["ship_order"], ["01-core", "02-api"])

            f1 = next(f for f in doc["features"] if f["id"] == "01-core")
            self.assertTrue(f1["verification_present"])
            self.assertEqual(f1["tasks"], {"present": True, "total": 2, "done": 2})
            self.assertEqual(f1["review"]["blocking_high"], 0)
            self.assertEqual(f1["review"]["suppressed"], 1)

            # both diagnosis locations reported: plan-root (interactive) at the
            # top level, per-feature (auto-build) under the feature's evidence
            self.assertTrue(doc["diagnosis_present"])
            self.assertTrue(f1["diagnosis_present"])

            # honest gaps: 02-api all-done-but-unverified, and the bad lines
            self.assertTrue(any("02-api" in g and "verification.md" in g
                                for g in doc["gaps"]), doc["gaps"])
            self.assertEqual(doc["metrics"]["lines_total"], 6)
            self.assertEqual(doc["metrics"]["lines_unparseable"], 2)
            self.assertEqual(doc["metrics"]["gates"]["pass"], 1)
            self.assertEqual(doc["metrics"]["retries"], 1)
            self.assertEqual(doc["metrics"]["retries_by_feature"], {"01-core": 1})
            self.assertEqual(len(doc["metrics"]["escalations"]), 1)
            self.assertEqual(doc["metrics"]["escalations"][0]["escalation_type"],
                             "/ce-plan")
            self.assertEqual(doc["run_reports"], ["2026-06-11-run.md"])
            self.assertTrue(doc["decisions_ledger"]["shared_context_present"])
            self.assertTrue(doc["honest_limitations"])  # the contract, in-band

            # criteria-testability rate: 01-core's TC tags parsed from the
            # heading line only (the prose "manual:judgment" is never counted);
            # 02-api's untagged spec contributes zero (honest "no data")
            self.assertEqual(f1["testability"],
                             {"total": 3, "auto": 1, "harness_gap": 1,
                              "judgment": 1})
            self.assertEqual(doc["testability"],
                             {"total": 3, "auto": 1, "harness_gap": 1,
                              "judgment": 1})
            f2 = next(f for f in doc["features"] if f["id"] == "02-api")
            self.assertEqual(f2["testability"]["total"], 0)

            # complexity-vs-actual drift: planned final_complexity joined with
            # built signals (task count + retry events per feature)
            drift = {d["id"]: d for d in doc["complexity_drift"]}
            self.assertEqual(drift["01-core"], {
                "id": "01-core", "final_complexity": "Moderate",
                "task_count": 2, "retries": 1})
            self.assertEqual(drift["02-api"], {
                "id": "02-api", "final_complexity": "Simple",
                "task_count": 1, "retries": 0})

    def test_out_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_fixture(Path(tmp))
            out = Path(tmp) / "audit-export" / "2026-06-11-audit-export.json"
            res = run(str(plan), "--out", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(out.is_file())
            json.loads(out.read_text())  # valid JSON on disk

    def test_empty_dir_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run(tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("nothing to export", res.stderr)

    def test_out_refuses_to_clobber_plan_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_fixture(Path(tmp))
            before = (plan / "plan.json").read_text()
            res = run(str(plan), "--out", str(plan / "plan.json"))
            self.assertEqual(res.returncode, 1)
            self.assertIn("refusing", res.stderr)
            self.assertEqual((plan / "plan.json").read_text(), before)  # untouched

    def test_out_refuses_inside_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_fixture(Path(tmp))
            res = run(str(plan), "--out", str(plan / "specs" / "x.json"))
            self.assertEqual(res.returncode, 1)

    def test_out_allows_dated_convention(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_fixture(Path(tmp))
            out = plan / "audit-export" / "2026-06-11-audit-export.json"
            res = run(str(plan), "--out", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertTrue(out.is_file())

    def test_traversal_id_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evil").mkdir()
            (root / "evil" / "spec.md").write_text("x")
            plan = root / "p"
            plan.mkdir()
            (plan / "plan.json").write_text(json.dumps(
                {"features": [{"id": "../../evil", "title": "X", "ship_order": 1}]}))
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)
            f = doc["features"][0]
            self.assertTrue(f.get("invalid_id"))
            self.assertFalse(f["spec_present"])  # never read from outside the plan

    def test_multiple_eligibility_is_a_gap_not_silent_pick(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "p"
            (plan / "specs" / "00-a").mkdir(parents=True)
            (plan / "specs" / "00-b").mkdir(parents=True)
            (plan / "specs" / "00-a" / "eligibility.json").write_text('{"m":"a"}')
            (plan / "specs" / "00-b" / "eligibility.json").write_text('{"m":"b"}')
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)
            self.assertTrue(doc["patch_lane"]["present"])
            self.assertTrue(any("multiple eligibility" in g for g in doc["gaps"]))

    def test_non_utf8_plan_json_exits_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "p"
            (plan / "specs").mkdir(parents=True)  # specs/ present -> still exports
            (plan / "plan.json").write_bytes(b"\xff\xfe bad")
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertNotIn("Traceback", res.stderr)
            doc = json.loads(res.stdout)
            self.assertFalse(doc["plan"]["present"])

    def test_attestation_rollup(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "p"
            (plan / "specs").mkdir(parents=True)  # specs/ present -> exports
            (plan / ".metrics.jsonl").write_text("\n".join([
                json.dumps({"ts": "2026-07-04", "stage": "implement",
                            "plan": "p", "feature": "01-x", "event": "attestation",
                            "gate": "Manual verdict", "gate_index": "2 of 3",
                            "action": "confirm", "basis_shown": True,
                            "detail": "accepted"}),
                json.dumps({"ts": "2026-07-04", "stage": "implement",
                            "plan": "p", "feature": "01-x", "event": "attestation",
                            "gate": "Manual verdict", "gate_index": "2 of 3",
                            "action": "loop", "basis_shown": True, "detail": ""}),
                json.dumps({"ts": "2026-07-04", "stage": "implement",
                            "plan": "p", "feature": "01-x", "event": "attestation",
                            "gate": "Manual verdict", "gate_index": "2 of 3",
                            "action": "override", "basis_shown": True,
                            "detail": "changed the call"}),
                json.dumps({"ts": "2026-07-04", "stage": "review",
                            "plan": "p", "feature": None, "event": "attestation",
                            "gate": "End review", "gate_index": "1 of 1",
                            "action": "edit", "basis_shown": False, "detail": ""}),
                # unrecognized action: gate still surfaces, no typed counter moves
                json.dumps({"ts": "2026-07-04", "stage": "review",
                            "plan": "p", "feature": None, "event": "attestation",
                            "gate": "End review", "gate_index": "1 of 1",
                            "action": "bogus", "basis_shown": True, "detail": ""}),
            ]) + "\n")
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            metrics = json.loads(res.stdout)["metrics"]
            att = metrics["attestations"]
            self.assertEqual(att["confirms"], 1)
            self.assertEqual(att["overrides"], 1)
            self.assertEqual(att["edits"], 1)
            self.assertEqual(att["loops"], 1)
            self.assertEqual(att["by_gate"]["Manual verdict"],
                             {"confirm": 1, "override": 1, "edit": 0, "loop": 1})
            self.assertEqual(att["by_gate"]["End review"]["edit"], 1)
            # the unrecognized-action line surfaced its gate but moved no counter
            self.assertIn("End review", att["by_gate"])
            self.assertEqual(sum(att["by_gate"]["End review"].values()), 1)
            # generic events_by_type still counts every attestation line (5)
            self.assertEqual(metrics["events_by_type"]["attestation"], 5)

    def test_testability_anchors_to_tc_heading_and_reads_legacy_spec_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "p"
            (plan / "specs" / "01-x").mkdir(parents=True)
            (plan / "plan.json").write_text(json.dumps(
                {"features": [{"id": "01-x", "title": "X", "ship_order": 1}]}))
            # legacy spec.md; prose lines that mention verification tags must
            # NOT be counted — only the TC heading lines are
            (plan / "specs" / "01-x" / "spec.md").write_text(
                "# spec\n\n"
                "Tag each case auto or manual:harness-gap, never "
                "manual:judgment.  (prose — not a heading)\n\n"
                "### TC-1 (proves AC-1) — modality: cli · verification: auto\n"
                "### TC-2 (proves AC-1) — modality: http · verification: auto\n")
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)
            self.assertEqual(doc["testability"],
                             {"total": 2, "auto": 2, "harness_gap": 0,
                              "judgment": 0})

    def test_complexity_drift_null_when_feature_unplanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "p"
            (plan / "specs" / "01-x").mkdir(parents=True)
            # feature with no final_complexity, no tasks, no retries
            (plan / "plan.json").write_text(json.dumps(
                {"features": [{"id": "01-x", "title": "X", "ship_order": 1}]}))
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)
            self.assertEqual(doc["complexity_drift"], [{
                "id": "01-x", "final_complexity": None,
                "task_count": 0, "retries": 0}])

    def test_unstamped_evidence_on_nongit_fixture(self):
        # The plain fixture has done tasks with no evidence stamp and no git repo:
        # every done task rolls up as unstamped, never a false fresh/stale.
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_fixture(Path(tmp))
            doc = json.loads(run(str(plan)).stdout)
            f1 = next(f for f in doc["features"] if f["id"] == "01-core")
            self.assertEqual(f1["evidence"],
                             {"stamped": 0, "fresh": 0, "stale": 0, "unstamped": 2})
            self.assertEqual(doc["evidence"]["stale"], 0)
            self.assertEqual(doc["evidence"]["unstamped"], 3)  # 2 + 1 across features

    def test_evidence_flips_to_stale_after_rewind(self):
        # A git-backed plan: stamp a done task to a real commit (fresh), then rewind
        # HEAD past it — audit-export must roll the feature up as stale and gap it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
            plan = root / "docs" / "plans" / "demo"
            (plan / "specs" / "01-core").mkdir(parents=True)
            (plan / "plan.json").write_text(json.dumps({"features": [
                {"id": "01-core", "title": "Core", "ship_order": 1}]}))
            # seed + feature commit
            (root / "seed").write_text("s")
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "seed"], check=True)
            (root / "f.txt").write_text("x")
            subprocess.run(["git", "-C", str(root), "add", "f.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "feat"], check=True)
            c1 = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
            # tasks.json stamped to the feature commit — but NOT committed (untracked),
            # so the later `git reset --hard` leaves it in place.
            (plan / "specs" / "01-core" / "tasks.json").write_text(json.dumps(
                {"feature_id": "01-core", "tasks": [
                    {"id": "T-1", "status": "done",
                     "completed_at": "2026-07-04T00:00:00Z", "commit_sha": c1,
                     "test_run_digest": None}]}))

            doc = json.loads(run(str(plan)).stdout)
            f1 = next(f for f in doc["features"] if f["id"] == "01-core")
            self.assertEqual(f1["evidence"],
                             {"stamped": 1, "fresh": 1, "stale": 0, "unstamped": 0})

            subprocess.run(["git", "-C", str(root), "reset", "--hard", "HEAD~1", "-q"],
                           check=True)
            doc2 = json.loads(run(str(plan)).stdout)
            f1b = next(f for f in doc2["features"] if f["id"] == "01-core")
            self.assertEqual(f1b["evidence"]["stale"], 1)
            self.assertEqual(f1b["evidence"]["fresh"], 0)
            self.assertEqual(doc2["evidence"]["stale"], 1)
            self.assertTrue(any("01-core" in g and "STALE" in g for g in doc2["gaps"]),
                            doc2["gaps"])

    def test_specs_without_plan_json_still_exports_with_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "p"
            (plan / "specs" / "00-x").mkdir(parents=True)
            res = run(str(plan))
            self.assertEqual(res.returncode, 0, res.stderr)
            doc = json.loads(res.stdout)
            self.assertFalse(doc["plan"]["present"])
            self.assertTrue(any("plan.json missing" in g for g in doc["gaps"]))
            # no diagnosis anywhere -> plan-root field honestly reports absent
            self.assertFalse(doc["diagnosis_present"])


def make_windowed_fixture(root: Path) -> Path:
    """A plan whose stream straddles a window boundary, plus one undated line.

    June: 1 retry + 1 gate pass.  2026-07-01 (the boundary day): 1 gate fail.
    July: 1 park + 1 attestation. Undated: 1 park with no ts at all.
    """
    plan = root / "win-plan"
    (plan / "specs" / "01-core").mkdir(parents=True)
    (plan / "plan.json").write_text(json.dumps({"features": [
        {"id": "01-core", "title": "Core", "ship_order": 1,
         "final_complexity": "Moderate"}]}))
    s1 = plan / "specs" / "01-core"
    (s1 / "ce-spec.md").write_text(
        "# spec\n### TC-1  (proves AC-1) — modality: http · verification: auto\n")
    (s1 / "tasks.json").write_text(json.dumps(
        {"feature_id": "01-core", "tasks": [{"id": "T0", "status": "done"}]}))
    (s1 / "verification.md").write_text("# verified\n")
    (plan / ".metrics.jsonl").write_text("\n".join([
        json.dumps({"ts": "2026-06-11", "stage": "implement", "plan": "win-plan",
                    "feature": "01-core", "event": "retry", "detail": "old"}),
        json.dumps({"ts": "2026-06-11", "stage": "implement", "plan": "win-plan",
                    "feature": "01-core", "event": "gate", "gate": "pass"}),
        json.dumps({"ts": "2026-07-01", "stage": "review", "plan": "win-plan",
                    "feature": "01-core", "event": "gate", "gate": "fail"}),
        json.dumps({"ts": "2026-07-04", "stage": "implement", "plan": "win-plan",
                    "feature": "01-core", "event": "park", "detail": "new"}),
        json.dumps({"ts": "2026-07-04", "stage": "implement", "plan": "win-plan",
                    "feature": "01-core", "event": "attestation",
                    "gate": "manual-verdict", "gate_index": "1 of 2",
                    "action": "confirm", "basis_shown": True}),
        json.dumps({"stage": "implement", "plan": "win-plan", "event": "park",
                    "detail": "no ts at all"}),
    ]) + "\n")
    return plan


class Windowing(unittest.TestCase):
    """--since / --until filter ONLY the dated stream. Every other block is
    current on-disk state and must never be rendered as windowed."""

    def export(self, plan, *args):
        res = run(str(plan), *args)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)

    def test_no_window_output_has_no_window_keys(self):
        """Backward compatibility: no flags => ts is never read, no key appears."""
        with tempfile.TemporaryDirectory() as tmp:
            doc = self.export(make_windowed_fixture(Path(tmp)))
            self.assertNotIn("window", doc)
            self.assertNotIn("windowing", doc)
            self.assertNotIn("windowed", doc["metrics"])
            self.assertNotIn("window_lines", doc["metrics"])
            self.assertEqual(doc["metrics"]["parks"], 2)  # incl. the undated one
            self.assertEqual(doc["metrics"]["retries"], 1)

    def test_since_filters_stream_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_windowed_fixture(Path(tmp))
            full = self.export(plan)
            win = self.export(plan, "--since", "2026-07-01")
            # stream tallies move...
            self.assertEqual(win["metrics"]["retries"], 0)   # June retry excluded
            self.assertEqual(win["metrics"]["parks"], 1)     # undated excluded
            self.assertEqual(win["metrics"]["gates"], {"pass": 0, "fail": 1})
            self.assertEqual(win["metrics"]["attestations"]["confirms"], 1)
            # ...static artifact blocks do not.
            for block in ("testability", "evidence", "features", "plan"):
                self.assertEqual(win[block], full[block], f"{block} must be as-of-now")

    def test_since_boundary_day_is_inclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            win = self.export(make_windowed_fixture(Path(tmp)), "--since", "2026-07-01")
            self.assertEqual(win["metrics"]["gates"]["fail"], 1)

    def test_until_boundary_day_is_inclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            win = self.export(make_windowed_fixture(Path(tmp)), "--until", "2026-06-11")
            self.assertEqual(win["metrics"]["retries"], 1)
            self.assertEqual(win["metrics"]["gates"], {"pass": 1, "fail": 0})

    def test_window_and_windowing_manifest_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_windowed_fixture(Path(tmp))
            win = self.export(plan, "--since", "2026-07-01", "--until", "2026-07-31")
            self.assertTrue(win["window"]["applied"])
            self.assertTrue(win["window"]["bounds_inclusive"])
            self.assertEqual(win["window"]["granularity"], "day")
            self.assertEqual(win["window"]["since"], "2026-07-01")
            self.assertEqual(win["window"]["until"], "2026-07-31")
            self.assertTrue(win["metrics"]["windowed"])
            self.assertEqual(win["windowing"]["windowed_blocks"], ["metrics"])
            # the manifest is what stops a narrator claiming a static number moved
            for block in ("testability", "evidence", "complexity_drift", "features"):
                self.assertIn(block, win["windowing"]["as_of_now_blocks"])
            self.assertEqual(win["window"]["stream_lines"],
                             {"in_window": 3, "out_of_window": 2, "undated": 1})

    def test_complexity_drift_retries_stay_full_stream_under_window(self):
        """A windowed retry count joined to a lifetime task count would make drift
        SHRINK as the window narrows. The row stays lifetime, and the manifest says so."""
        with tempfile.TemporaryDirectory() as tmp:
            win = self.export(make_windowed_fixture(Path(tmp)), "--since", "2026-07-01")
            self.assertEqual(win["metrics"]["retries"], 0)              # windowed
            self.assertEqual(win["complexity_drift"][0]["retries"], 1)  # lifetime
            self.assertIn("complexity_drift", win["windowing"]["as_of_now_blocks"])

    def test_undated_line_excluded_counted_and_gapped(self):
        with tempfile.TemporaryDirectory() as tmp:
            win = self.export(make_windowed_fixture(Path(tmp)), "--since", "2026-07-01")
            self.assertEqual(win["window"]["stream_lines"]["undated"], 1)
            self.assertTrue(any("missing/unparseable ts" in g for g in win["gaps"]),
                            "an undated line must be counted AND gapped")

    def test_malformed_since_exits_2_with_no_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run(str(make_windowed_fixture(Path(tmp))), "--since", "07-01-2026")
            self.assertEqual(res.returncode, 2)
            self.assertEqual(res.stdout.strip(), "")

    def test_inverted_range_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run(str(make_windowed_fixture(Path(tmp))),
                      "--since", "2026-08-01", "--until", "2026-07-01")
            self.assertEqual(res.returncode, 2)
            self.assertEqual(res.stdout.strip(), "")

    def test_ts_with_time_component_is_truncated_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_windowed_fixture(Path(tmp))
            with open(plan / ".metrics.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": "2026-07-05T10:00:00Z", "stage": "verify",
                                     "plan": "win-plan", "event": "park"}) + "\n")
            win = self.export(plan, "--since", "2026-07-01")
            self.assertEqual(win["metrics"]["parks"], 2)  # the July park + this one
            self.assertEqual(win["window"]["stream_lines"]["undated"], 1)


if __name__ == "__main__":
    unittest.main()
