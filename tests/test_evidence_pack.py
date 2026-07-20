"""Fixture tests for retro/ship-release's evidence-pack.py — the pack composer.

Asserts the seven sections populate or gap-list, that the guard-log chain head is
recorded and a tampered chain fails the pack's verify field LOUDLY, that model
identity flags a below-policy-tier run, that the finding-disposition register
splits active from expired accepted risk (an absent ledger is NOT a gap; an
expired or unreadable one IS), that --out writes pack.json plus sha256-stamped
verbatim artifact copies, and the exit-code / clobber contract.
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/core-engineering/skills/ce-retro/scripts/evidence-pack.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, timeout=60,
    )


def build_guard_log(path: Path, entries: list) -> None:
    """Write a valid hash-chained guard log — the exact algorithm guard_log.py's
    append_entry uses (prev = sha256 of the previous RAW line; genesis prev="")."""
    lines, prev = [], ""
    for e in entries:
        e = dict(e)
        e["prev"] = hashlib.sha256(prev.encode("utf-8")).hexdigest() if prev else ""
        line = json.dumps(e, sort_keys=True)
        lines.append(line)
        prev = line
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


ACTIVE_DISPOSITION = {
    "id": "SEC-2026-07-fixture-key", "gate": "secrets-guard",
    "match": {"path_glob": "tests/fixtures/**", "type": "AWS access key id"},
    "reason": "test fixture credential, not a live secret",
    "accepted_by": "alice", "date": "2026-07-01", "expires": "2999-01-01",
}
EXPIRED_DISPOSITION = {
    "id": "SCA-2026-01-lapsed", "gate": "sca-guard",
    "match": {"package": "pypi:requests", "version": "2.0.0"},
    "reason": "upgrade blocked on a vendor pin",
    "accepted_by": "bob", "date": "2026-01-01", "expires": "2026-02-01",
}


def write_ledger(root: Path, dispositions: list, *, schema_version: int = 1) -> Path:
    """Write .merge-bar/dispositions.json at the repo root above the plan, where
    evidence-pack's find_up() discovers it (the guard-log resolution pattern)."""
    d = root / ".merge-bar"
    d.mkdir(exist_ok=True)
    path = d / "dispositions.json"
    path.write_text(json.dumps(
        {"schema_version": schema_version, "dispositions": dispositions}))
    return path


def disposition_gaps(pack: dict) -> list:
    return [g for g in pack["gaps"] if "disposition" in g.lower()]


def make_fixture(root: Path) -> tuple:
    """Return (plan_dir, guard_log, merge_verdict) inside root."""
    plan = root / "demo-plan"
    (plan / "specs" / "01-core").mkdir(parents=True)
    (plan / "ce-auto-build").mkdir(parents=True)
    (plan / "plan.json").write_text(json.dumps({"features": [
        {"id": "01-core", "title": "Core", "ship_order": 1,
         "final_complexity": "Moderate"},
    ]}))
    s1 = plan / "specs" / "01-core"
    (s1 / "ce-spec.md").write_text(
        "# spec\n### TC-1  (proves AC-1) — modality: http · verification: auto\n")
    (s1 / "tasks.json").write_text(json.dumps(
        {"feature_id": "01-core",
         "tasks": [{"id": "T0", "status": "done"}]}))
    (s1 / "verification.md").write_text("# verified\n")
    # review summary drives the dismissal_records section
    (s1 / "review-summary.json").write_text(json.dumps(
        {"blocking_high": 1, "findings_total": 4, "suppressed": 2}))

    # metrics: gate + attestation lines carry model ids; one below-tier (haiku),
    # one strong (opus), one unattested (sonnet), one null-model gate.
    (plan / ".metrics.jsonl").write_text("\n".join([
        json.dumps({"ts": "2026-07-04", "stage": "implement", "plan": "demo-plan",
                    "feature": "01-core", "event": "gate", "gate": "pass",
                    "detail": "test-guard: T0", "model": "claude-opus-4-8"}),
        json.dumps({"ts": "2026-07-04", "stage": "review", "plan": "demo-plan",
                    "feature": "01-core", "event": "gate", "gate": "fail",
                    "detail": "blocking_high:1", "model": "claude-haiku-4"}),
        json.dumps({"ts": "2026-07-04", "stage": "spec", "plan": "demo-plan",
                    "feature": "01-core", "event": "gate", "gate": "pass",
                    "detail": "spec-lint", "model": "claude-sonnet-4"}),
        json.dumps({"ts": "2026-07-04", "stage": "verify", "plan": "demo-plan",
                    "feature": "01-core", "event": "gate", "gate": "pass",
                    "detail": "no-model-here"}),
        json.dumps({"ts": "2026-07-04", "stage": "implement", "plan": "demo-plan",
                    "feature": "01-core", "event": "attestation",
                    "gate": "manual-verdict", "gate_index": "1 of 2",
                    "action": "confirm", "basis_shown": True,
                    "model": "claude-opus-4-8"}),
        json.dumps({"ts": "2026-07-04", "stage": "implement", "plan": "demo-plan",
                    "feature": "01-core", "event": "attestation",
                    "gate": "manual-verdict", "gate_index": "1 of 2",
                    "action": "override", "basis_shown": True,
                    "model": "claude-opus-4-8"}),
    ]) + "\n")

    (plan / "verification-report.md").write_text(
        "# Verification Report\n\n"
        "| Journey | Verdict |\n|---|---|\n"
        "| J1 checkout | PASS |\n"
        "| J2 refund | FAIL — regression in totals |\n\n"
        "Overall: NO-GO until J2 is fixed.\n")
    (plan / "ce-auto-build" / "2026-07-04-run.md").write_text(
        "# Run report\nDegradations: review ran on haiku (accepted).\n")

    # guard log OUTSIDE plan_dir (repo-level .claude), passed via --guard-log
    claude = root / ".claude"
    claude.mkdir()
    guard_log = claude / "ce-guard-log.jsonl"
    build_guard_log(guard_log, [
        {"ts": "2026-07-04T10:00:00+00:00", "guard": "git-guard",
         "decision": "deny", "reason": "force-push blocked", "session_id": "s1",
         "tool": "Bash", "hook_event": "PreToolUse", "payload_sha256": "a" * 64},
        {"ts": "2026-07-04T10:01:00+00:00", "guard": "write-scope-guard",
         "decision": "ask", "reason": "out-of-lease write", "session_id": "s1",
         "tool": "Write", "hook_event": "PreToolUse", "payload_sha256": "b" * 64},
        {"ts": "2026-07-04T10:02:00+00:00", "guard": "env-guard",
         "decision": "allow", "reason": "clean env", "session_id": "s1",
         "tool": "Bash", "hook_event": "PreToolUse", "payload_sha256": "c" * 64},
    ])

    merge_verdict = root / "merge-verdict.json"
    merge_verdict.write_text(json.dumps({
        "status": "pass", "schema_version": 1, "change_class": "standard",
        "base_sha": "d" * 40, "head_sha": "e" * 40, "repo": str(plan),
        "policy": {"path": "merge-policy.json", "sha256": "f" * 64,
                   "shipped_default": True},
        "gates": [], "hard_failures": [], "advisory": [],
    }))
    return plan, guard_log, merge_verdict


class EvidencePack(unittest.TestCase):
    def test_all_sections_populated(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, guard_log, mv = make_fixture(Path(tmp))
            res = run(str(plan), "--guard-log", str(guard_log),
                      "--merge-verdict", str(mv))
            self.assertEqual(res.returncode, 0, res.stderr)
            pack = json.loads(res.stdout)
            self.assertEqual(pack["schema_version"], 1)
            sec = pack["sections"]

            # 1. event log — embedded audit-export compilation + raw metrics ref
            self.assertTrue(sec["event_log"]["audit_export"]["present"])
            self.assertEqual(
                sec["event_log"]["audit_export"]["compilation"]["plan_slug"],
                "demo-plan")
            self.assertTrue(sec["event_log"]["metrics_jsonl"]["present"])
            self.assertTrue(
                sec["event_log"]["metrics_jsonl"]["sha256"].startswith("sha256:"))

            # 2. guard decisions — chain head + verify valid
            g = sec["guard_decisions"]
            self.assertTrue(g["present"])
            self.assertEqual(g["entry_count"], 3)
            self.assertTrue(g["chain_head"].startswith("sha256:"))
            self.assertTrue(g["verify"]["ran"])
            self.assertTrue(g["verify"]["valid"])
            self.assertTrue(g["tamper_evident"])

            # 3. gate verdicts — policy hash + SHAs + in-loop tallies
            mvv = sec["gate_verdicts"]["merge_verdict"]
            self.assertTrue(mvv["present"])
            self.assertEqual(mvv["status"], "pass")
            self.assertEqual(mvv["change_class"], "standard")
            self.assertEqual(mvv["policy_sha256"], "f" * 64)
            self.assertEqual(mvv["base_sha"], "d" * 40)
            self.assertEqual(sec["gate_verdicts"]["in_loop_gates"],
                             {"pass": 3, "fail": 1})

            # 4. human attestations — verdict extract + run report + telemetry
            hum = sec["human_attestations"]
            self.assertTrue(hum["verification_report"]["present"])
            self.assertTrue(any("NO-GO" in ln for ln in
                                hum["verification_report"]["verdict_lines"]))
            self.assertEqual(len(hum["end_review_reports"]), 1)
            att = hum["attestation_telemetry"]
            self.assertEqual(att["confirms"], 1)
            self.assertEqual(att["overrides"], 1)
            self.assertIn("manual-verdict", att["by_gate"])

            # 5. model identity — below-tier + unattested + null
            mi = sec["model_identity"]
            self.assertTrue(mi["policy_located"])
            self.assertTrue(any(r["model"] == "claude-haiku-4" and r["below_tier"]
                                for r in mi["by_stage"]))
            self.assertTrue(any(b["model"] == "claude-haiku-4"
                                for b in mi["below_tier"]))
            self.assertTrue(any(u["model"] == "claude-sonnet-4"
                                for u in mi["unattested"]))
            self.assertEqual(mi["null_count"], 1)

            # 6. dismissal records — per-feature suppressed / blocking-high
            dr = sec["dismissal_records"]
            self.assertEqual(dr["total_suppressed"], 2)
            self.assertEqual(dr["total_blocking_high"], 1)
            self.assertEqual(dr["by_feature"][0]["id"], "01-core")

            # 7. finding dispositions — no ledger in this fixture, and that is
            # the healthy default, never a gap (see DispositionSection below).
            fd = sec["finding_dispositions"]
            self.assertFalse(fd["present"])
            self.assertEqual(fd["counts"]["total"], 0)

            # honest limitations carried in-band (the contract)
            self.assertTrue(pack["honest_limitations"])
            self.assertTrue(any("tamper-PROOF" in h
                                for h in pack["honest_limitations"]))

    def test_tampered_guard_log_fails_verify_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, guard_log, mv = make_fixture(Path(tmp))
            # edit a MIDDLE line's payload — breaks the chain from that point
            lines = guard_log.read_text().splitlines()
            obj = json.loads(lines[1])
            obj["reason"] = "TAMPERED — decision rewritten after the fact"
            lines[1] = json.dumps(obj, sort_keys=True)
            guard_log.write_text("\n".join(lines) + "\n")

            res = run(str(plan), "--guard-log", str(guard_log))
            self.assertEqual(res.returncode, 0, res.stderr)  # pack still produced
            pack = json.loads(res.stdout)
            g = pack["sections"]["guard_decisions"]
            self.assertTrue(g["verify"]["ran"])
            self.assertFalse(g["verify"]["valid"])       # loudly false
            self.assertFalse(g["tamper_evident"])
            self.assertTrue(any("CHAIN BROKEN" in gap for gap in pack["gaps"]),
                            pack["gaps"])

    def test_out_writes_pack_and_sha256_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, guard_log, mv = make_fixture(Path(tmp))
            out = plan / "evidence-pack" / "2026-07-04"
            res = run(str(plan), "--guard-log", str(guard_log),
                      "--merge-verdict", str(mv), "--out", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            pack = json.loads((out / "pack.json").read_text())
            # every present artifact carries a sha256 and a verbatim copy
            present = [a for a in pack["artifacts"] if a["present"]]
            self.assertTrue(present)
            for a in present:
                self.assertTrue(a["sha256"].startswith("sha256:"))
                self.assertIsNotNone(a["copied_to"], a["role"])
                copied = out / a["copied_to"]
                self.assertTrue(copied.is_file(), a["role"])
                # copy is byte-verbatim: recompute sha256 and compare
                h = "sha256:" + hashlib.sha256(copied.read_bytes()).hexdigest()
                self.assertEqual(h, a["sha256"], a["role"])
            # the embedded audit-export is written as a first-class artifact
            self.assertTrue((out / "artifacts" / "audit-export.json").is_file())

    def test_out_refuses_to_clobber_plan_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, guard_log, mv = make_fixture(Path(tmp))
            res = run(str(plan), "--out", str(plan))
            self.assertEqual(res.returncode, 1)
            self.assertIn("refusing", res.stderr)

    def test_out_refuses_inside_specs(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, guard_log, mv = make_fixture(Path(tmp))
            res = run(str(plan), "--out", str(plan / "specs" / "01-core"))
            self.assertEqual(res.returncode, 1)

    def test_out_refuses_to_overwrite_existing_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, guard_log, mv = make_fixture(Path(tmp))
            out = plan / "evidence-pack" / "2026-07-04"
            first = run(str(plan), "--guard-log", str(guard_log),
                        "--merge-verdict", str(mv), "--out", str(out))
            self.assertEqual(first.returncode, 0, first.stderr)
            original = (out / "pack.json").read_bytes()

            second = run(str(plan), "--guard-log", str(guard_log),
                         "--merge-verdict", str(mv), "--out", str(out))
            self.assertEqual(second.returncode, 1)
            self.assertIn("target already exists", second.stderr)
            self.assertEqual((out / "pack.json").read_bytes(), original)

    def test_empty_dir_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = run(tmp)
            self.assertEqual(res.returncode, 1)
            self.assertIn("nothing to compile", res.stderr)

    def test_missing_guard_log_is_a_gap_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, guard_log, mv = make_fixture(Path(tmp))
            res = run(str(plan), "--guard-log", str(Path(tmp) / "nope.jsonl"))
            self.assertEqual(res.returncode, 0, res.stderr)
            pack = json.loads(res.stdout)
            self.assertFalse(pack["sections"]["guard_decisions"]["present"])
            self.assertTrue(any("guard log absent" in g for g in pack["gaps"]))

    def test_repo_evidence_embedded(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, guard_log, mv = make_fixture(Path(tmp))
            rep = Path(tmp) / "enterprise-evidence.json"
            rep.write_text(json.dumps({"tool": "enterprise-evidence",
                                       "evidence": {"sbom": []}}))
            res = run(str(plan), "--guard-log", str(guard_log),
                      "--repo-evidence", str(rep))
            self.assertEqual(res.returncode, 0, res.stderr)
            pack = json.loads(res.stdout)
            self.assertTrue(pack["repo_evidence"]["present"])
            self.assertEqual(pack["repo_evidence"]["inventory"]["tool"],
                             "enterprise-evidence")

    def test_missing_merge_verdict_is_a_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, guard_log, mv = make_fixture(Path(tmp))
            res = run(str(plan), "--guard-log", str(guard_log),
                      "--merge-verdict", str(Path(tmp) / "absent.json"))
            self.assertEqual(res.returncode, 0, res.stderr)
            pack = json.loads(res.stdout)
            self.assertFalse(
                pack["sections"]["gate_verdicts"]["merge_verdict"]["present"])
            self.assertTrue(any("merge-verdict" in g for g in pack["gaps"]))


class DispositionSection(unittest.TestCase):
    """Section 7 — the merge-bar accepted-risk register.

    A gate SUPPRESSES an accepted finding; the pack is what keeps that suppression
    visible to an auditor. So: an absent ledger means 'nothing accepted' and must
    never be a gap; an expired or broken one must be loud.
    """

    def pack_for(self, tmp: Path, *extra):
        plan, guard_log, _mv = make_fixture(tmp)
        res = run(str(plan), "--guard-log", str(guard_log), *extra)
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)

    def test_absent_ledger_is_present_false_and_not_a_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.pack_for(Path(tmp))
            fd = pack["sections"]["finding_dispositions"]
            self.assertFalse(fd["present"])
            self.assertEqual(fd["counts"], {"total": 0, "active": 0, "expired": 0})
            self.assertEqual(disposition_gaps(pack), [])

    def test_active_and_expired_are_split_and_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_ledger(Path(tmp), [ACTIVE_DISPOSITION, EXPIRED_DISPOSITION])
            fd = self.pack_for(Path(tmp))["sections"]["finding_dispositions"]
            self.assertTrue(fd["present"])
            self.assertEqual(fd["counts"], {"total": 2, "active": 1, "expired": 1})
            self.assertEqual([e["id"] for e in fd["active"]],
                             ["SEC-2026-07-fixture-key"])
            self.assertEqual([e["id"] for e in fd["expired"]], ["SCA-2026-01-lapsed"])
            # the auditor-facing projection carries who accepted it and until when
            active = fd["active"][0]
            self.assertEqual(active["accepted_by"], "alice")
            self.assertEqual(active["gate"], "secrets-guard")
            self.assertEqual(active["expires"], "2999-01-01")
            self.assertIn("path_glob", active["match"])
            self.assertTrue(fd["sha256"].startswith("sha256:"))

    def test_expired_disposition_gaps_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_ledger(Path(tmp), [EXPIRED_DISPOSITION])
            pack = self.pack_for(Path(tmp))
            gaps = disposition_gaps(pack)
            self.assertTrue(gaps, "an expired disposition must surface in gaps[]")
            self.assertTrue(any("expired" in g for g in gaps))
            # it is still RENDERED — a lapsed acceptance is evidence, not a deletion
            fd = pack["sections"]["finding_dispositions"]
            self.assertEqual(fd["counts"]["expired"], 1)
            self.assertEqual(fd["expired"][0]["accepted_by"], "bob")

    def test_active_only_ledger_has_no_disposition_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_ledger(Path(tmp), [ACTIVE_DISPOSITION])
            pack = self.pack_for(Path(tmp))
            self.assertEqual(disposition_gaps(pack), [])

    def test_invalid_ledger_gaps_and_still_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / ".merge-bar"
            d.mkdir()
            (d / "dispositions.json").write_text("{ not json")
            pack = self.pack_for(Path(tmp))  # asserts returncode 0 internally
            fd = pack["sections"]["finding_dispositions"]
            self.assertTrue(fd["present"])
            self.assertTrue(fd["unreadable"])
            self.assertTrue(any("unusable" in g for g in disposition_gaps(pack)))

    def test_wrong_schema_version_is_a_gap_not_silent_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_ledger(Path(tmp), [ACTIVE_DISPOSITION], schema_version=99)
            pack = self.pack_for(Path(tmp))
            self.assertTrue(pack["sections"]["finding_dispositions"]["unreadable"])
            self.assertTrue(any("schema_version" in g
                                for g in disposition_gaps(pack)))

    def test_malformed_entry_gaps_and_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_ledger(Path(tmp), [{"id": "BAD", "gate": "unknown-gate",
                                      "match": {}, "reason": "", "accepted_by": "",
                                      "date": "nope", "expires": "soon"}])
            pack = self.pack_for(Path(tmp))
            fd = pack["sections"]["finding_dispositions"]
            self.assertTrue(disposition_gaps(pack))
            # an unparseable `expires` never counts as active
            self.assertEqual(fd["counts"]["active"], 0)
            self.assertEqual(fd["counts"]["expired"], 1)

    def test_explicit_missing_ledger_is_a_gap(self):
        """An operator who NAMES a register and gets none must not read the pack
        as 'nothing accepted'. Mirrors --merge-verdict / --repo-evidence, which
        both gap on a named-but-absent file. Discovery-absent stays silent."""
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "typo-dispositions.json"
            pack = self.pack_for(Path(tmp), "--dispositions", str(missing))
            fd = pack["sections"]["finding_dispositions"]
            self.assertFalse(fd["present"])
            gaps = disposition_gaps(pack)
            self.assertTrue(gaps, "a named-but-absent ledger must gap")
            self.assertTrue(any("unproven" in g for g in gaps))

    def test_explicit_directory_ledger_is_a_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            a_dir = Path(tmp) / "not-a-file"
            a_dir.mkdir()
            pack = self.pack_for(Path(tmp), "--dispositions", str(a_dir))
            self.assertFalse(pack["sections"]["finding_dispositions"]["present"])
            self.assertTrue(disposition_gaps(pack))

    def test_explicit_flag_overrides_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_ledger(Path(tmp), [EXPIRED_DISPOSITION])  # discoverable one
            elsewhere = Path(tmp) / "other-dispositions.json"
            elsewhere.write_text(json.dumps(
                {"schema_version": 1, "dispositions": [ACTIVE_DISPOSITION]}))
            fd = self.pack_for(Path(tmp), "--dispositions", str(elsewhere))[
                "sections"]["finding_dispositions"]
            self.assertEqual(fd["counts"], {"total": 1, "active": 1, "expired": 0})

    def test_ledger_is_sha256_stamped_and_copied_under_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = write_ledger(root, [ACTIVE_DISPOSITION])
            plan, guard_log, _mv = make_fixture(root)
            out = root / "pack-out"
            res = run(str(plan), "--guard-log", str(guard_log), "--out", str(out))
            self.assertEqual(res.returncode, 0, res.stderr)
            pack = json.loads((out / "pack.json").read_text())
            entry = next(a for a in pack["artifacts"]
                         if a["role"] == "disposition-ledger")
            self.assertTrue(entry["present"])
            self.assertEqual(entry["sha256"],
                             pack["sections"]["finding_dispositions"]["sha256"])
            copied = out / entry["copied_to"]
            self.assertTrue(copied.is_file())
            self.assertEqual(copied.read_text(), ledger.read_text())

    def test_embedded_compilation_is_never_windowed(self):
        """A release/compliance pack must be the FULL stream. run_audit_export
        passes no --since/--until, so the embedded compilation carries no window.
        Guards against a future edit wiring the flags through."""
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.pack_for(Path(tmp))
            comp = pack["sections"]["event_log"]["audit_export"]["compilation"]
            self.assertNotIn("window", comp)
            self.assertNotIn("windowing", comp)
            self.assertNotIn("windowed", comp["metrics"])

    def test_honest_limitation_names_the_register_as_human_authored(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.pack_for(Path(tmp))
            self.assertTrue(any("HUMAN-AUTHORED" in h
                                for h in pack["honest_limitations"]))


if __name__ == "__main__":
    unittest.main()
