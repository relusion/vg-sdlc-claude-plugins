#!/usr/bin/env python3
"""
evidence-pack.py — compose ONE auditor-consumable evidence pack for a plan.

One command, one pack: this composes a per-merge / per-release evidence bundle
from everything the pipeline already recorded — the audit-export compilation,
the raw metrics stream, the hash-chained guard log, the merge-bar verdict, human
attestations, model identity, and dismissal records — into a single structured
`pack.json` plus verbatim, sha256-stamped copies of every cited artifact.

It is COMPILATION, not attestation, and not a verdict: it gathers and hashes what
exists, renders no compliance or conformity judgment, and reports every absence
honestly (gaps[]) rather than silently zeroing it. It reuses audit-export.py's
machinery by invoking the sibling script and embedding its JSON, so the two stay
in lockstep instead of re-deriving each other's numbers.

Sections (each populated or gap-listed):
  1. event_log         — the embedded audit-export compilation + the raw
                         .metrics.jsonl (preserved verbatim, sha256'd).
  2. guard_decisions   — the guard log: guard_log.py --verify result (INTERNAL
                         consistency only) PLUS the chain head (last-line sha256
                         + entry count). The chain head is anti-tamper evidence
                         only once THIS pack is retained off the writable tree by
                         an independent party and a later log is diffed against
                         it; --verify alone does not detect a re-chained edit or
                         a wholesale re-genesis (see honest_limitations).
  3. gate_verdicts     — the gate_runner.py merge verdict (policy sha256, base/
                         head SHAs, change class) when supplied, plus the
                         in-loop gate pass/fail tallies from the metrics stream.
  4. human_attestations— verification-report.md (presence + verdict extract),
                         the auto-build end-review run reports, and the
                         attestation-telemetry rollup (confirm/override/edit/loop).
  5. model_identity    — per-stage model ids from the metrics stream with
                         below-policy-tier flags (model-policy.json tier_patterns);
                         a hook-less run records model=null, never a guessed tier.
  6. dismissal_records — per-feature suppressed / blocking-high counts from each
                         review-summary.json (end-review accepted findings live in
                         the verbatim-preserved run report, not machine-parsed).
  7. finding_dispositions
                       — the merge-bar accepted-risk register
                         (.merge-bar/dispositions.json): every consciously-accepted
                         gate finding, split active vs expired, each with the human
                         who accepted it and when it lapses. A gate suppresses an
                         accepted finding; this section is why that suppression is
                         never invisible to an auditor. An expired entry re-alarms
                         through its gate and is reported here AND in gaps[].

Usage:
    python3 evidence-pack.py <plan-dir>                     # JSON to stdout
    python3 evidence-pack.py <plan-dir> --out DIR           # write DIR/pack.json + copies
        [--guard-log FILE]        # default <repo>/.claude/ce-guard-log.jsonl if present
        [--merge-verdict FILE]    # gate_runner.py --json output (merge-verdict.json)
        [--repo-evidence FILE]    # scripts/enterprise_evidence.py --json inventory
        [--dispositions FILE]     # default <repo>/.merge-bar/dispositions.json if present
    The dated convention is docs/plans/<slug>/evidence-pack/<date>/pack.json —
    dated, never overwritten.

Exit codes:
    0  pack produced (even with gaps or a broken guard chain — both surfaced IN it)
    1  plan dir invalid (no plan.json and no specs/), or --out would clobber a source
    2  unexpected internal error (could-not-run; never impersonates a FAIL)

Stdlib-only by design (the portability guarantee): no Claude Code, no network.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_disposition  # noqa: E402  (dir-local forked ledger reader)

SCHEMA_VERSION = 1

# Lines in verification-report.md that read as a rendered verdict — extracted as
# a convenience (the verbatim copy + sha256 is the authoritative record).
VERDICT_LINE_RE = re.compile(
    r"\b(PASS|FAIL|FAILED|BLOCKED|VERDICT|ACCEPT|ACCEPTED|REJECT|REGRESS|"
    r"GO/NO-GO|NO-GO|GO\b)", re.IGNORECASE)
MAX_VERDICT_LINES = 60

HONEST_LIMITATIONS = [
    "Evidence COMPILATION, not an attestation and not a verdict: this pack "
    "gathers and hashes what the pipeline recorded; it renders no compliance or "
    "conformity judgment. A human or external process reads it.",
    "Tamper-EVIDENT, never tamper-PROOF, and only against an EXTERNAL anchor: "
    "guard_log.py --verify proves ONLY that the guard log is internally "
    "self-consistent on disk. Because the chain is an unkeyed public sha256 over "
    "the prior line, an actor with write access can edit/delete/reorder a line "
    "and recompute every downstream prev, or re-genesis the whole file, and "
    "--verify still returns 0 (it catches only accidental damage and a naive "
    "tamperer who does NOT re-chain; an empty or single-line file also passes). "
    "guard_decisions.tamper_evident here means 'internal chain self-consistent', "
    "NOT 'history un-forged'. The recorded chain_head (last-line sha256 + entry "
    "count) has anti-tamper value ONLY once this pack is archived off the "
    "agent-writable tree at generation time (git-committed, archived by CI, or "
    "delivered to the auditor) and a later log is diffed against that retained "
    "{chain_head, entry_count}; a chain_head left on the same writable disk "
    "anchors nothing. The append-only external sink (retained prior pack) is the "
    "future hardening; until it runs, treat --verify as corruption-evidence.",
    "Model identity is best-effort: only gate and attestation metrics lines "
    "carry a model id, and a hook-less run records model=null "
    "(surfaced as null_count, never a guessed tier). Below-tier flags depend on "
    "model-policy.json being locatable; when it is not, models are listed "
    "unflagged and the gap is recorded.",
    "Markdown artifacts (verification-report.md, the end-review run reports) are "
    "preserved verbatim with their sha256 and only lightly excerpted; their "
    "prose — including end-review accepted findings — is not re-judged here.",
    "The finding-disposition register is a HUMAN-AUTHORED file, reported as found "
    "and never re-judged: this pack does not verify that the named accepted_by "
    "actually approved the entry, nor that the accepted finding was real. What "
    "constrains it lives outside the pack — .merge-bar/** is in the merge policy's "
    "class_rules, so editing the ledger escalates to two-human review, and "
    "disposition-lint fails CI on an expired or malformed entry. An absent ledger "
    "means 'nothing accepted', which is reported as present:false, not as a gap.",
    "Completeness equals pipeline completeness: a source absent on disk is "
    "reported in gaps[], never silently zeroed. Verbatim copies are written only "
    "under --out; stdout mode records sha256 references without copying.",
    "Embedded audit-export and merge-verdict JSON are carried as their producing "
    "tools emitted them; this pack does not re-derive their numbers.",
]


# --- small stdlib helpers ------------------------------------------------------

def sha256_file(path: Path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return "sha256:" + h.hexdigest()
    except OSError:
        return None


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None


def find_up(start: Path, *relparts):
    """Walk parents of `start` for the first `parent/<relparts>` that exists.

    Locates plugin-tree siblings (hooks/guard_log.py, model-policy.json) from
    both the canonical ce-retro copy and the ce-ship-release fork, which share
    the plugins/core-engineering/skills/<skill>/scripts/ ancestry. Returns None
    when not found (for example, in a standalone script copy) so the caller can
    degrade honestly instead of crashing.
    """
    try:
        start = start.resolve()
    except OSError:
        return None
    for parent in start.parents:
        cand = parent.joinpath(*relparts)
        if cand.exists():
            return cand
    return None


# --- artifact manifest ---------------------------------------------------------

def add_artifact(artifacts: list, role: str, path, *, external: bool = False):
    """Register a cited artifact: presence + sha256 now, verbatim copy under --out.

    Returns the entry dict so a section can embed its {present, sha256} keys.
    """
    p = Path(path)
    present = p.is_file()
    entry = {
        "role": role,
        "path": str(path),
        "external": external,
        "present": present,
        "sha256": sha256_file(p) if present else None,
        "copied_to": None,
    }
    artifacts.append(entry)
    return entry


def copy_artifacts(artifacts: list, out_dir: Path, plan_dir: Path, gaps: list):
    """Copy every present artifact verbatim under out_dir/artifacts/, recording
    the destination on each entry. Plan-internal files keep their relative path;
    external files land under artifacts/external/ namespaced by role."""
    plan_r = plan_dir.resolve()
    for entry in artifacts:
        if not entry["present"]:
            continue
        src = Path(entry["path"]).resolve()
        rel = None
        if not entry["external"]:
            try:
                rel = src.relative_to(plan_r)
            except ValueError:
                rel = None
        if rel is not None:
            dest = out_dir / "artifacts" / rel
        else:
            safe = f"{entry['role']}__{src.name}"
            dest = out_dir / "artifacts" / "external" / safe
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            entry["copied_to"] = str(dest.relative_to(out_dir))
        except OSError as exc:
            gaps.append(f"could not copy {entry['role']} ({entry['path']}): "
                        f"{type(exc).__name__}")


# --- section 1: event log ------------------------------------------------------

def run_audit_export(plan_dir: Path, gaps: list) -> dict:
    """Invoke the sibling audit-export.py and embed its JSON (the reuse seam).

    INVARIANT — a release pack is NEVER windowed. No --since/--until is passed, so
    the embedded compilation is always the full stream. A pack whose event log
    covered only a sprint would be a dishonest record-keeping artifact, whatever an
    Art-12 reader assumed. Test: test_embedded_compilation_is_never_windowed.
    """
    sibling = Path(__file__).resolve().with_name("audit-export.py")
    if not sibling.is_file():
        gaps.append("audit-export.py not found beside evidence-pack.py — event "
                    "log compilation unavailable (embedded audit summary absent)")
        return {"present": False, "reason": "sibling audit-export.py missing"}
    try:
        res = subprocess.run(
            [sys.executable, str(sibling), str(plan_dir)],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        gaps.append(f"audit-export.py failed to run: {type(exc).__name__}")
        return {"present": False, "reason": f"run error: {type(exc).__name__}"}
    if res.returncode != 0:
        gaps.append(f"audit-export.py exited {res.returncode} — event log "
                    f"compilation unavailable")
        return {"present": False, "returncode": res.returncode,
                "stderr": res.stderr.strip()[:400]}
    try:
        return {"present": True, "compilation": json.loads(res.stdout)}
    except json.JSONDecodeError:
        gaps.append("audit-export.py stdout was not valid JSON")
        return {"present": False, "reason": "unparseable audit-export stdout"}


# --- section 2: guard decisions (tamper-evident chain) -------------------------

def guard_section(guard_log: Path, gaps: list) -> dict:
    """Chain head + guard_log.py --verify result.

    verify.valid / tamper_evident report INTERNAL chain consistency only — a
    re-chained edit or a wholesale re-genesis by a write-capable agent still
    passes. The chain_head recorded here is an anchor only once this pack is
    retained off the writable tree and a later log is compared against it (see
    HONEST_LIMITATIONS); on its own it is not an out-of-band guarantee."""
    out = {
        "present": guard_log.is_file(),
        "path": str(guard_log),
        "sha256": None,
        "entry_count": 0,
        "chain_head": None,       # sha256 of last raw line; anchors ONLY vs. a retained prior pack
        "last_ts": None,
        "verify": {"ran": False, "valid": None, "returncode": None, "message": None},
        "tamper_evident": False,
    }
    if not out["present"]:
        gaps.append(f"guard log absent at {guard_log} — no hash-chained guard "
                    f"decisions to bind (a plan built without the guards, or a "
                    f"different repo root)")
        return out

    out["sha256"] = sha256_file(guard_log)
    try:
        raw_lines = [ln for ln in guard_log.read_text(
            encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    except OSError:
        gaps.append(f"guard log at {guard_log} present but unreadable")
        return out
    out["entry_count"] = len(raw_lines)
    if raw_lines:
        last = raw_lines[-1]
        out["chain_head"] = "sha256:" + hashlib.sha256(
            last.encode("utf-8")).hexdigest()
        try:
            out["last_ts"] = json.loads(last).get("ts")
        except (json.JSONDecodeError, AttributeError):
            out["last_ts"] = None

    verifier = find_up(Path(__file__), "hooks", "guard_log.py")
    if verifier is None:
        gaps.append("guard_log.py verifier not locatable beside the pack script "
                    "— chain head recorded, but --verify not run (chain integrity "
                    "unconfirmed by this pack)")
        return out
    try:
        res = subprocess.run(
            [sys.executable, str(verifier), "--verify", str(guard_log)],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        gaps.append(f"guard_log.py --verify failed to run: {type(exc).__name__}")
        return out
    valid = res.returncode == 0
    out["verify"] = {
        "ran": True,
        "valid": valid,
        "returncode": res.returncode,
        "message": (res.stdout.strip() or res.stderr.strip())[:400],
    }
    out["tamper_evident"] = valid
    if not valid:
        gaps.append("GUARD LOG CHAIN BROKEN — guard_log.py --verify returned "
                    f"{res.returncode}: {out['verify']['message']}. A logged "
                    f"guard decision was edited, deleted, or reordered.")
    return out


# --- section 3: gate verdicts --------------------------------------------------

def gate_verdicts_section(merge_verdict: Path, audit_json: dict,
                          gaps: list) -> dict:
    out = {
        "merge_verdict": {"present": False},
        "in_loop_gates": {"pass": 0, "fail": 0},
    }
    # In-loop gate tallies come free from the embedded audit-export metrics.
    metrics = _audit_metrics(audit_json)
    if isinstance(metrics.get("gates"), dict):
        out["in_loop_gates"] = {
            "pass": metrics["gates"].get("pass", 0),
            "fail": metrics["gates"].get("fail", 0),
        }

    if merge_verdict is None:
        return out
    mv = {"present": merge_verdict.is_file(), "path": str(merge_verdict),
          "sha256": None}
    if not mv["present"]:
        gaps.append(f"--merge-verdict {merge_verdict} not found — no merge-bar "
                    f"verdict to bind (per-merge packs point this at the CI verdict)")
        out["merge_verdict"] = mv
        return out
    mv["sha256"] = sha256_file(merge_verdict)
    parsed = load_json(merge_verdict)
    if not isinstance(parsed, dict):
        mv["unreadable"] = True
        gaps.append(f"{merge_verdict} present but not valid JSON")
        out["merge_verdict"] = mv
        return out
    mv["status"] = parsed.get("status")
    mv["change_class"] = parsed.get("change_class")
    mv["base_sha"] = parsed.get("base_sha")
    mv["head_sha"] = parsed.get("head_sha")
    policy = parsed.get("policy")
    if isinstance(policy, dict):
        mv["policy_sha256"] = policy.get("sha256")
        mv["policy_shipped_default"] = policy.get("shipped_default")
    if parsed.get("status") == "error":
        gaps.append("merge verdict records status=error — the bar could not run "
                    "(carried verbatim; not a pass)")
    out["merge_verdict"] = mv
    return out


# --- section 4: human attestations ---------------------------------------------

def human_attestations_section(plan_dir: Path, audit_json: dict,
                               artifacts: list, gaps: list) -> dict:
    out = {"verification_report": {"present": False},
           "end_review_reports": [],
           "attestation_telemetry": {}}

    vr = plan_dir / "verification-report.md"
    entry = add_artifact(artifacts, "verification-report", vr)
    vr_out = {"present": entry["present"], "sha256": entry["sha256"],
              "path": str(vr), "verdict_lines": []}
    if entry["present"]:
        try:
            for line in vr.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if s and VERDICT_LINE_RE.search(s):
                    vr_out["verdict_lines"].append(s[:200])
                    if len(vr_out["verdict_lines"]) >= MAX_VERDICT_LINES:
                        break
        except OSError:
            gaps.append("verification-report.md present but unreadable")
    else:
        gaps.append("no verification-report.md — /core-engineering:ce-verify has not produced a "
                    "cross-feature acceptance record for this plan")
    out["verification_report"] = vr_out

    # End-review records: the auto-build run reports carry the human's accepted
    # degradations / overrides. Preserved verbatim; prose not machine-parsed.
    run_dir = plan_dir / "ce-auto-build"
    reports = sorted(run_dir.glob("*-run.md")) if run_dir.is_dir() else []
    for rp in reports:
        entry = add_artifact(artifacts, "end-review-run-report", rp)
        out["end_review_reports"].append(
            {"name": rp.name, "sha256": entry["sha256"]})
    if not reports:
        gaps.append("no auto-build run report — either an interactive build or "
                    "auto-build has not run (end-review attestations unavailable)")

    # Attestation telemetry (WS3-T7 rollup) straight from audit-export.
    metrics = _audit_metrics(audit_json)
    att = metrics.get("attestations")
    if isinstance(att, dict):
        out["attestation_telemetry"] = att
    else:
        gaps.append("no attestation telemetry in the metrics stream (interactive "
                    "HITL gates emitted no attestation lines, or no metrics)")
    return out


# --- section 5: model identity -------------------------------------------------

def _classify_model(model, tier_patterns):
    """(tier, below_strong) for a model id against tier_patterns.

    tier is the matched policy tier, 'unattested' when the id matches no pattern,
    or 'no-policy' when tier_patterns is unavailable. below_strong is True only
    for a confidently-matched non-'strong' tier."""
    if tier_patterns is None:
        return "no-policy", False
    low = str(model).lower()
    for tier, needles in tier_patterns.items():
        if not isinstance(needles, list):
            continue
        for n in needles:
            if isinstance(n, str) and n.lower() in low:
                return tier, (tier != "strong")
    return "unattested", False


def model_identity_section(plan_dir: Path, gaps: list) -> dict:
    """Per-stage model ids from gate/attestation metrics lines + tier flags."""
    out = {
        "by_stage": [],            # [{stage, model, tier, below_tier, count}]
        "below_tier": [],          # stages that ran below the 'strong' policy tier
        "unattested": [],          # a non-null model matching no tier pattern
        "null_count": 0,           # gate/attestation lines with no model id
        "policy_located": False,
    }
    policy_path = find_up(Path(__file__), "model-policy.json")
    tier_patterns = None
    if policy_path is not None:
        pol = load_json(policy_path)
        if isinstance(pol, dict) and isinstance(pol.get("tier_patterns"), dict):
            tier_patterns = {k: v for k, v in pol["tier_patterns"].items()
                             if not k.startswith("_")}
            out["policy_located"] = True
    if tier_patterns is None:
        gaps.append("model-policy.json tier_patterns not locatable — model ids "
                    "listed unflagged (below-tier attestation unavailable)")

    metrics_path = plan_dir / ".metrics.jsonl"
    if not metrics_path.is_file():
        gaps.append("no .metrics.jsonl — model identity unavailable")
        return out
    counts: dict = {}
    try:
        raw = metrics_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        gaps.append(".metrics.jsonl present but unreadable — model identity absent")
        return out
    for line in raw:
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict) or ev.get("event") not in ("gate", "attestation"):
            continue
        stage = str(ev.get("stage") or "unknown")
        model = ev.get("model")
        if model in (None, "", "null"):
            out["null_count"] += 1
            key = (stage, None)
        else:
            key = (stage, str(model))
        counts[key] = counts.get(key, 0) + 1
    for (stage, model), n in sorted(counts.items(), key=lambda kv: (kv[0][0],
                                                                    str(kv[0][1]))):
        if model is None:
            out["by_stage"].append({"stage": stage, "model": None,
                                    "tier": "null", "below_tier": False,
                                    "count": n})
            continue
        tier, below = _classify_model(model, tier_patterns)
        row = {"stage": stage, "model": model, "tier": tier,
               "below_tier": below, "count": n}
        out["by_stage"].append(row)
        if below:
            out["below_tier"].append({"stage": stage, "model": model, "tier": tier})
        elif tier == "unattested":
            out["unattested"].append({"stage": stage, "model": model})
    if out["below_tier"]:
        gaps.append(f"{len(out['below_tier'])} stage(s) ran BELOW the 'strong' "
                    f"policy tier — accepted degradations, surfaced for the "
                    f"end-review (see model_identity.below_tier)")
    return out


# --- section 6: dismissal records ----------------------------------------------

def dismissal_section(audit_json: dict) -> dict:
    out = {"by_feature": [], "total_suppressed": 0, "total_blocking_high": 0,
           "note": "per-feature review-summary.json counts; end-review accepted "
                   "findings live in the verbatim-preserved run report, not "
                   "machine-parsed here"}
    comp = audit_json.get("compilation") if isinstance(audit_json, dict) else None
    features = comp.get("features") if isinstance(comp, dict) else None
    for f in (features or []):
        if not isinstance(f, dict):
            continue
        review = f.get("review") or {}
        if not review.get("present"):
            continue
        supp = review.get("suppressed", 0) or 0
        bh = review.get("blocking_high", 0) or 0
        out["by_feature"].append({
            "id": f.get("id"),
            "suppressed": supp,
            "blocking_high": bh,
            "findings_total": review.get("findings_total"),
        })
        out["total_suppressed"] += supp
        out["total_blocking_high"] += bh
    return out


# --- section 7: finding dispositions (the accepted-risk register) ---------------

DISPOSITION_NOTE = (
    "the merge-bar accepted-risk register. An advisory gate SUPPRESSES a matched "
    "active finding rather than re-alarming on every PR; this section is the record "
    "of what was accepted, by whom, and until when — so a suppressed finding is "
    "never invisible. An expired entry suppresses nothing (its finding re-alarms) "
    "and fails disposition-lint; it is listed here and in gaps[]."
)


def _disposition_view(entry: dict) -> dict:
    """The auditor-facing projection of one ledger entry. A secrets-guard `match`
    keys on file + finding TYPE only, never a secret value, so it is safe to embed."""
    return {
        "id": entry.get("id"),
        "gate": entry.get("gate"),
        "match": entry.get("match"),
        "reason": entry.get("reason"),
        "accepted_by": entry.get("accepted_by"),
        "date": entry.get("date"),
        "expires": entry.get("expires"),
    }


def disposition_section(ledger_path: Path, today, gaps: list, artifacts: list,
                        *, explicit: bool = False) -> dict:
    """Render .merge-bar/dispositions.json as active vs expired accepted risk.

    A DISCOVERED-absent ledger is the healthy default (most repos accept nothing) —
    reported as present:false and deliberately NOT a gap. An EXPLICITLY named one
    (--dispositions) that is missing IS a gap, like --merge-verdict / --repo-evidence:
    an operator asked for a register and got none, so "nothing accepted" is unproven,
    not established. An unreadable or schema-invalid ledger is likewise a gap — the
    pack cannot tell "nothing accepted" from "the register is broken", and never guesses.
    """
    entry = add_artifact(artifacts, "disposition-ledger", ledger_path)
    out = {
        "present": entry["present"],
        "path": str(ledger_path),
        "sha256": entry["sha256"],
        "schema_version": merge_disposition.SCHEMA_VERSION,
        "known_gates": list(merge_disposition.KNOWN_GATES),
        "counts": {"total": 0, "active": 0, "expired": 0},
        "active": [],
        "expired": [],
        "note": DISPOSITION_NOTE,
    }
    if not entry["present"]:
        if explicit:
            gaps.append(f"--dispositions {ledger_path} not found (or not a file) — "
                        f"the named accepted-risk register is missing, so "
                        f"'nothing accepted' is unproven, not established")
        return out

    entries, err = merge_disposition.read_ledger_file(ledger_path)
    if err:
        out["unreadable"] = True
        gaps.append(f"disposition ledger ({ledger_path}) present but unusable — {err}; "
                    f"accepted risk cannot be evidenced from a broken register")
        return out

    # validate() reports an expired `expires` as an error — correct: an expired
    # disposition is a lapsed acceptance, and CI's disposition-lint fails on it.
    # Carry each message through verbatim rather than re-wording it here.
    for message in merge_disposition.validate(entries, today):
        gaps.append(f"disposition ledger: {message}")

    for item in entries:
        if not isinstance(item, dict):
            continue  # already reported by validate()
        bucket = "active" if merge_disposition.is_active(item, today) else "expired"
        out[bucket].append(_disposition_view(item))
    out["counts"] = {
        "total": len(out["active"]) + len(out["expired"]),
        "active": len(out["active"]),
        "expired": len(out["expired"]),
    }
    return out


# --- shared accessors ----------------------------------------------------------

def _audit_metrics(audit_json: dict) -> dict:
    comp = audit_json.get("compilation") if isinstance(audit_json, dict) else None
    metrics = comp.get("metrics") if isinstance(comp, dict) else None
    return metrics if isinstance(metrics, dict) else {}


# --- --out safety --------------------------------------------------------------

def out_would_clobber_source(out_dir: Path, plan_dir: Path) -> bool:
    """True if writing the pack into out_dir would land on a source location.

    Refuses plan_dir root and anything at/under specs/ — but ALLOWS the dated
    evidence-pack/<date>/ convention inside plan_dir and any path outside it.
    """
    try:
        out_r = out_dir.resolve()
        plan_r = plan_dir.resolve()
    except OSError:
        return False
    if out_r == plan_r:
        return True
    specs_r = plan_r / "specs"
    if out_r == specs_r or specs_r in out_r.parents:
        return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Compose one auditor-consumable evidence pack for a plan")
    ap.add_argument("plan_dir", help="docs/plans/<slug> directory")
    ap.add_argument("--out", help="write DIR/pack.json + verbatim artifact copies")
    ap.add_argument("--guard-log",
                    help="hash-chained guard log (default: <repo>/.claude/"
                         "ce-guard-log.jsonl beside the plan, if present)")
    ap.add_argument("--merge-verdict", help="gate_runner.py --json verdict file")
    ap.add_argument("--repo-evidence",
                    help="scripts/enterprise_evidence.py --json inventory file")
    ap.add_argument("--dispositions",
                    help="merge-bar finding-disposition ledger (default: <repo>/"
                         ".merge-bar/dispositions.json beside the plan, if present)")
    args = ap.parse_args(argv)

    plan_dir = Path(args.plan_dir)
    plan = load_json(plan_dir / "plan.json")
    if not isinstance(plan, dict) and not (plan_dir / "specs").is_dir():
        print(f"evidence-pack: {plan_dir} has no plan.json and no specs/ — "
              f"nothing to compile", file=sys.stderr)
        return 1

    out_dir = Path(args.out) if args.out else None
    if out_dir is not None and out_would_clobber_source(out_dir, plan_dir):
        print(f"evidence-pack: refusing --out {out_dir} — it would write onto a "
              f"source location (plan root or specs/). Use the dated "
              f"evidence-pack/<date>/ convention.", file=sys.stderr)
        return 1
    if out_dir is not None and (out_dir.exists() or out_dir.is_symlink()):
        print(f"evidence-pack: refusing --out {out_dir} — the target already "
              f"exists. Choose a new dated directory; evidence packs are "
              f"never overwritten.", file=sys.stderr)
        return 1

    gaps: list = []
    artifacts: list = []

    # Section 1 — event log (embedded audit-export + raw metrics artifact).
    audit_json = run_audit_export(plan_dir, gaps)
    metrics_path = plan_dir / ".metrics.jsonl"
    metrics_entry = add_artifact(artifacts, "metrics-jsonl", metrics_path)
    if not metrics_entry["present"]:
        gaps.append("no .metrics.jsonl to preserve (best-effort stream never "
                    "emitted, or an interactive-only run)")
    event_log = {
        "audit_export": audit_json,
        "metrics_jsonl": {"present": metrics_entry["present"],
                          "path": str(metrics_path),
                          "sha256": metrics_entry["sha256"]},
    }

    # Section 2 — guard decisions.
    if args.guard_log:
        guard_log = Path(args.guard_log)
    else:
        repo = find_up(plan_dir, ".claude", "ce-guard-log.jsonl")
        guard_log = repo if repo is not None else (
            plan_dir / ".claude" / "ce-guard-log.jsonl")
    guard = guard_section(guard_log, gaps)
    add_artifact(artifacts, "guard-log", guard_log)

    # Section 3 — gate verdicts.
    merge_verdict = Path(args.merge_verdict) if args.merge_verdict else None
    gate_verdicts = gate_verdicts_section(merge_verdict, audit_json, gaps)
    if merge_verdict is not None:
        add_artifact(artifacts, "merge-verdict", merge_verdict, external=True)

    # Section 4 — human attestations.
    human = human_attestations_section(plan_dir, audit_json, artifacts, gaps)

    # Section 5 — model identity.
    model_identity = model_identity_section(plan_dir, gaps)

    # Section 6 — dismissal records.
    dismissals = dismissal_section(audit_json)

    # Section 7 — finding dispositions (the accepted-risk register).
    # Resolved like the guard log: an explicit path wins, else the repo-root ledger
    # found by walking up from the plan, else the (absent) conventional location.
    if args.dispositions:
        ledger_path = Path(args.dispositions)
    else:
        found = find_up(plan_dir, ".merge-bar", "dispositions.json")
        ledger_path = found if found is not None else (
            plan_dir / ".merge-bar" / "dispositions.json")
    dispositions = disposition_section(
        ledger_path, datetime.now(timezone.utc).date(), gaps, artifacts,
        explicit=bool(args.dispositions))

    # Optional repo-level supply-chain evidence (referenced, not re-implemented).
    repo_evidence = {"present": False}
    if args.repo_evidence:
        rep = Path(args.repo_evidence)
        entry = add_artifact(artifacts, "repo-evidence", rep, external=True)
        repo_evidence = {"present": entry["present"], "path": str(rep),
                         "sha256": entry["sha256"]}
        if entry["present"]:
            parsed = load_json(rep)
            if isinstance(parsed, dict):
                repo_evidence["inventory"] = parsed
            else:
                repo_evidence["unreadable"] = True
                gaps.append(f"--repo-evidence {rep} present but not valid JSON")
        else:
            gaps.append(f"--repo-evidence {rep} not found")

    pack = {
        "schema_version": SCHEMA_VERSION,
        "tool": "core-engineering evidence-pack",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan_dir": str(plan_dir),
        "plan_slug": plan_dir.name,
        "sections": {
            "event_log": event_log,
            "guard_decisions": guard,
            "gate_verdicts": gate_verdicts,
            "human_attestations": human,
            "model_identity": model_identity,
            "dismissal_records": dismissals,
            "finding_dispositions": dispositions,
        },
        "repo_evidence": repo_evidence,
        "artifacts": artifacts,
        "gaps": gaps,
        "honest_limitations": HONEST_LIMITATIONS,
    }

    if out_dir is not None:
        # audit-export written as a first-class dated artifact beside the pack.
        if audit_json.get("present"):
            ae_path = out_dir / "artifacts" / "audit-export.json"
            try:
                ae_path.parent.mkdir(parents=True, exist_ok=True)
                ae_path.write_text(
                    json.dumps(audit_json["compilation"], indent=2) + "\n",
                    encoding="utf-8")
            except OSError as exc:
                gaps.append(f"could not write embedded audit-export.json: "
                            f"{type(exc).__name__}")
        copy_artifacts(artifacts, out_dir, plan_dir, gaps)
        pack_path = out_dir / "pack.json"
        try:
            pack_path.parent.mkdir(parents=True, exist_ok=True)
            pack_path.write_text(json.dumps(pack, indent=2) + "\n",
                                 encoding="utf-8")
        except OSError as exc:
            print(f"evidence-pack: could not write {pack_path}: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        print(f"evidence-pack: wrote {pack_path} "
              f"({sum(1 for a in artifacts if a['copied_to'])} artifact copies, "
              f"{len(gaps)} gap(s))")
    else:
        print(json.dumps(pack, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — could-not-run must exit 2, never 1
        print(f"evidence-pack: unexpected error: {type(e).__name__}: {e}",
              file=sys.stderr)
        sys.exit(2)
