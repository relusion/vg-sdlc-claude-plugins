#!/usr/bin/env python3
"""Compile repository-level SDLC metrics into JSON and optional HTML.

This is a read-only projection over artifacts the framework already writes:
plan metrics streams, review summaries, verification files, auto-build reports,
and eval-run metadata. It is a dashboard input, not an attestation and not a
quality verdict. Missing or unreadable artifacts are reported as gaps instead of
being silently ignored.

Usage:
    python3 scripts/metrics_report.py --json
    python3 scripts/metrics_report.py --out /tmp/metrics.json
    python3 scripts/metrics_report.py --html /tmp/metrics.html
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# --- windowing (--since / --until), mirroring audit-export.py -----------------
#
# Only the stream-derived `metrics` blocks can be honestly filtered by date. The
# review / verification / auto-build / eval blocks are current on-disk state.
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WINDOWED_BLOCKS = ("metrics", "plans.items[].metrics")
AS_OF_NOW_BLOCKS = ("reviews", "verification_files", "auto_build_reports", "evals",
                    "plans.metrics_coverage", "plans.items[].feature_count")
WINDOWING_NOTE = (
    "Only the blocks in windowed_blocks reflect --since/--until. Everything in "
    "as_of_now_blocks is current on-disk state at generated_at_utc and is NOT "
    "filtered — narrating one as windowed is a fabrication. A plan whose stream "
    "has no in-window activity still appears with windowed zeros; a missing "
    "stream is explicitly no data, not zero."
)
WINDOW_LIMITATIONS = (
    "Day granularity: bounds are INCLUSIVE and compared as YYYY-MM-DD. The stream's "
    "ts has no time component, so same-day events are unordered and two adjacent "
    "windows sharing an endpoint both count that day.",
)


def parse_iso_date(raw):
    """A metrics `ts` -> date, or None when absent/unparseable (date-only stream)."""
    if not isinstance(raw, str):
        return None
    head = raw[:10]
    if not ISO_DATE_RE.match(head):
        return None
    try:
        return date.fromisoformat(head)
    except ValueError:
        return None


def in_window(ev_date, since, until) -> bool:
    if since is not None and ev_date < since:
        return False
    if until is not None and ev_date > until:
        return False
    return True

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
METRICS_EVENT_SCHEMA_VERSION = 2
METRICS_EVENT_STAGES = {
    "plan", "spec", "implement", "verify", "review", "debug", "release",
    "document", "auto-build", "patch",
}
METRICS_EVENT_TYPES = {
    "stage-complete", "gate", "escalation", "park", "retry",
    "circuit-break", "attestation", "run-terminal",
}
TERMINAL_OUTCOMES = {
    "completed", "failed", "aborted", "parked", "escalated",
    "could-not-run",
}
ATTESTATION_ACTIONS = {"confirm", "override", "edit", "loop"}


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def load_json(path: Path, gaps: list[str], label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        gaps.append(f"{label}: missing {rel(path.parent, path)}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        gaps.append(f"{label}: unreadable JSON at {path}: {exc}")
    return None


def empty_metrics() -> dict:
    return {
        "lines_total": 0,
        "lines_unparseable": 0,
        "lines_invalid_schema": 0,
        "event_schema": {
            "current_version": METRICS_EVENT_SCHEMA_VERSION,
            "legacy_unversioned": 0,
            "version_1": 0,
            "version_2": 0,
            "unsupported": 0,
        },
        "field_coverage": {
            "valid_events": 0,
            "run_id": 0,
            "terminal_outcome": 0,
            "duration_ms": 0,
            "model": 0,
            "claude_cli_version": 0,
            "plugin_version": 0,
        },
        "events_by_type": {},
        "terminal_outcomes": {},
        "gates": {"pass": 0, "fail": 0},
        "escalations_by_type": {},
        "parks": 0,
        "retries": 0,
        "circuit_breaks": 0,
    }


def merge_count(dst: dict, key, amount: int = 1) -> None:
    dst[key] = dst.get(key, 0) + amount


def validate_metrics_event(event: dict) -> tuple[str, list[str]]:
    """Classify and validate one ce-retro metrics event.

    The original stream contract was unversioned. Treat absent or explicit v1
    as legacy and retain its permissive reader behavior. Version 2 is strict so
    malformed new telemetry cannot silently influence the report. Unknown
    versions are parseable but unsupported.
    """
    version = event.get("schema_version")
    if version is None:
        return "legacy_unversioned", []
    if isinstance(version, int) and not isinstance(version, bool) and version == 1:
        return "version_1", []
    if (not isinstance(version, int) or isinstance(version, bool)
            or version != METRICS_EVENT_SCHEMA_VERSION):
        return "unsupported", [
            f"unsupported schema_version {version!r}; expected "
            f"{METRICS_EVENT_SCHEMA_VERSION}, 1, or an unversioned legacy event"
        ]

    errors: list[str] = []
    required = ("ts", "stage", "plan", "feature", "event")
    for field in required:
        if field not in event:
            errors.append(f"missing required field {field!r}")

    if "ts" in event and parse_iso_date(event.get("ts")) is None:
        errors.append("ts must begin with a valid YYYY-MM-DD date")
    if event.get("stage") not in METRICS_EVENT_STAGES:
        errors.append(f"stage must be one of {sorted(METRICS_EVENT_STAGES)!r}")
    plan = event.get("plan")
    if not isinstance(plan, str) or not plan.strip():
        errors.append("plan must be a non-empty string")
    feature = event.get("feature")
    if feature is not None and (not isinstance(feature, str) or not feature.strip()):
        errors.append("feature must be null or a non-empty string")

    event_type = event.get("event")
    if event_type not in METRICS_EVENT_TYPES:
        errors.append(f"event must be one of {sorted(METRICS_EVENT_TYPES)!r}")
    if event_type == "gate" and event.get("gate") not in ("pass", "fail"):
        errors.append("a gate event requires gate='pass' or gate='fail'")
    if event_type == "attestation":
        gate = event.get("gate")
        if not isinstance(gate, str) or not gate.strip():
            errors.append("an attestation event requires a non-empty gate name")
        gate_index = event.get("gate_index")
        locator = (re.fullmatch(r"([1-9]\d*) of ([1-9]\d*)", gate_index)
                   if isinstance(gate_index, str) else None)
        if locator is None or int(locator.group(1)) > int(locator.group(2)):
            errors.append("an attestation event requires gate_index='N of M'")
        if event.get("action") not in ATTESTATION_ACTIONS:
            errors.append(
                f"an attestation event action must be one of "
                f"{sorted(ATTESTATION_ACTIONS)!r}"
            )
        if not isinstance(event.get("basis_shown"), bool):
            errors.append("an attestation event requires boolean basis_shown")

    outcome = event.get("outcome")
    if event_type == "run-terminal":
        if outcome not in TERMINAL_OUTCOMES:
            errors.append(
                f"a run-terminal event outcome must be one of "
                f"{sorted(TERMINAL_OUTCOMES)!r}"
            )
    elif outcome is not None:
        errors.append("outcome is only valid on a run-terminal event")

    run_id = event.get("run_id")
    if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
        errors.append("run_id must be null, absent, or a non-empty string")
    duration_ms = event.get("duration_ms")
    if duration_ms is not None and (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or duration_ms < 0):
        errors.append("duration_ms must be a non-negative integer")
    for field in ("model", "claude_cli_version", "plugin_version"):
        value = event.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{field} must be null, absent, or a non-empty string")

    estimate = event.get("est")
    if estimate is not None and not isinstance(estimate, dict):
        errors.append("est must be an object when present")
    return "version_2", errors


def record_field_coverage(out: dict, event: dict) -> None:
    coverage = out["field_coverage"]
    coverage["valid_events"] += 1
    for field in ("run_id", "model", "claude_cli_version", "plugin_version"):
        if isinstance(event.get(field), str) and event[field].strip():
            coverage[field] += 1
    if (isinstance(event.get("duration_ms"), int)
            and not isinstance(event.get("duration_ms"), bool)
            and event["duration_ms"] >= 0):
        coverage["duration_ms"] += 1
    if event.get("event") == "run-terminal" and event.get("outcome") in TERMINAL_OUTCOMES:
        coverage["terminal_outcome"] += 1


def parse_metrics_file(path: Path, root: Path, gaps: list[str],
                       since=None, until=None) -> dict:
    out = empty_metrics()
    windowed = since is not None or until is not None
    if windowed:
        out["windowed"] = True
        out["window_lines"] = {"in_window": 0, "out_of_window": 0, "undated": 0}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        gaps.append(f"{rel(root, path)}: cannot read metrics stream: {exc}")
        return out

    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        out["lines_total"] += 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            out["lines_unparseable"] += 1
            continue
        if not isinstance(event, dict):
            out["lines_unparseable"] += 1
            continue

        if windowed:
            ev_date = parse_iso_date(event.get("ts"))
            if ev_date is None:
                out["window_lines"]["undated"] += 1
                continue  # counted, never silently dropped
            if not in_window(ev_date, since, until):
                out["window_lines"]["out_of_window"] += 1
                continue
            out["window_lines"]["in_window"] += 1

        schema_bucket, schema_errors = validate_metrics_event(event)
        out["event_schema"][schema_bucket] += 1
        if schema_errors:
            out["lines_invalid_schema"] += 1
            gaps.append(
                f"{rel(root, path)}:{lineno}: invalid metrics event schema: "
                + "; ".join(schema_errors)
            )
            continue
        record_field_coverage(out, event)

        event_type = str(event.get("event") or "unknown")
        merge_count(out["events_by_type"], event_type)
        gate = event.get("gate")
        if event_type == "gate" and gate in ("pass", "fail"):
            out["gates"][gate] += 1
        elif event_type == "escalation":
            escalation_type = str(event.get("escalation_type") or "unknown")
            merge_count(out["escalations_by_type"], escalation_type)
        elif event_type == "park":
            out["parks"] += 1
        elif event_type == "retry":
            out["retries"] += 1
        elif event_type == "circuit-break":
            out["circuit_breaks"] += 1
        elif event_type == "run-terminal":
            merge_count(out["terminal_outcomes"], str(event["outcome"]))

        if event_type == "unknown":
            gaps.append(f"{rel(root, path)}:{lineno}: metrics event missing event type")

    if out["lines_unparseable"]:
        gaps.append(
            f"{rel(root, path)}: {out['lines_unparseable']} unparseable metrics line(s)"
        )
    if windowed and out["window_lines"]["undated"]:
        gaps.append(
            f"{rel(root, path)}: {out['window_lines']['undated']} line(s) have a "
            f"missing/unparseable ts — excluded from the window (counted, not "
            f"skipped silently)"
        )
    return out


def add_metrics(total: dict, item: dict) -> None:
    total["lines_total"] += item["lines_total"]
    total["lines_unparseable"] += item["lines_unparseable"]
    total["lines_invalid_schema"] += item["lines_invalid_schema"]
    total["gates"]["pass"] += item["gates"]["pass"]
    total["gates"]["fail"] += item["gates"]["fail"]
    total["parks"] += item["parks"]
    total["retries"] += item["retries"]
    total["circuit_breaks"] += item["circuit_breaks"]
    for key, value in item["events_by_type"].items():
        merge_count(total["events_by_type"], key, value)
    for key, value in item["terminal_outcomes"].items():
        merge_count(total["terminal_outcomes"], key, value)
    for key, value in item["escalations_by_type"].items():
        merge_count(total["escalations_by_type"], key, value)
    for key in ("legacy_unversioned", "version_1", "version_2", "unsupported"):
        total["event_schema"][key] += item["event_schema"][key]
    for key, value in item["field_coverage"].items():
        total["field_coverage"][key] += value


def review_counts(summary: dict) -> dict:
    out = {"findings_total": 0, "blocking_high": 0, "by_severity": {}}
    if isinstance(summary.get("findings_total"), int):
        out["findings_total"] = summary["findings_total"]
    if isinstance(summary.get("blocking_high"), int):
        out["blocking_high"] = summary["blocking_high"]

    by_severity = summary.get("by_severity")
    if isinstance(by_severity, dict):
        for severity, value in by_severity.items():
            if isinstance(value, int):
                out["by_severity"][str(severity)] = value
            elif isinstance(value, dict):
                out["by_severity"][str(severity)] = sum(
                    v for v in value.values() if isinstance(v, int)
                )
    return out


def merge_review_counts(total: dict, item: dict) -> None:
    total["findings_total"] += item["findings_total"]
    total["blocking_high"] += item["blocking_high"]
    for severity, count in item["by_severity"].items():
        merge_count(total["by_severity"], severity, count)


def discover_plans(root: Path) -> list[Path]:
    plans_root = root / "docs" / "plans"
    if not plans_root.is_dir():
        return []
    return sorted(p for p in plans_root.iterdir() if p.is_dir())


def collect_plan(root: Path, plan_dir: Path, gaps: list[str],
                 since=None, until=None) -> dict:
    plan_json = plan_dir / "plan.json"
    plan_data = load_json(plan_json, gaps, rel(root, plan_json)) if plan_json.is_file() else None
    features = plan_data.get("features") if isinstance(plan_data, dict) else []
    if plan_json.is_file() and not isinstance(plan_data, dict):
        gaps.append(f"{rel(root, plan_json)}: top-level JSON is not an object")

    metrics_path = plan_dir / ".metrics.jsonl"
    metrics_present = metrics_path.is_file()
    if metrics_present:
        metrics = parse_metrics_file(metrics_path, root, gaps, since, until)
    else:
        metrics = empty_metrics()
        gaps.append(
            f"{rel(root, metrics_path)}: missing metrics stream — stream-derived "
            "values are no data, not complete zeros"
        )

    reviews = {
        "files": 0,
        "unreadable": 0,
        "findings_total": 0,
        "blocking_high": 0,
        "by_severity": {},
    }
    for review_path in sorted(plan_dir.rglob("review-summary.json")):
        reviews["files"] += 1
        parsed = load_json(review_path, gaps, rel(root, review_path))
        if not isinstance(parsed, dict):
            reviews["unreadable"] += 1
            continue
        merge_review_counts(reviews, review_counts(parsed))

    verifications = sorted(plan_dir.rglob("verification.md"))
    run_report_dir = plan_dir / "ce-auto-build"
    if not run_report_dir.is_dir():
        run_report_dir = plan_dir / "auto-build"  # legacy pre-canonical path
    run_reports = sorted(run_report_dir.glob("*-run.md")) if run_report_dir.is_dir() else []

    return {
        "slug": plan_dir.name,
        "path": rel(root, plan_dir),
        "status": plan_data.get("status") if isinstance(plan_data, dict) else None,
        "feature_count": len(features) if isinstance(features, list) else 0,
        "metrics_present": metrics_present,
        "metrics": metrics,
        "reviews": reviews,
        "verification_files": len(verifications),
        "auto_build_reports": len(run_reports),
    }


def collect_evals(root: Path, gaps: list[str]) -> dict:
    runs_root = root / "evals" / "runs"
    out = {
        "run_dirs": 0,
        "metadata_files": 0,
        "dry_runs": 0,
        "records_total": 0,
        "by_status": {},
        "by_profile": {},
        "by_failure_kind": {},
        "records": [],
    }
    if not runs_root.is_dir():
        return out

    for metadata_path in sorted(runs_root.glob("*/metadata.json")):
        out["metadata_files"] += 1
        out["run_dirs"] += 1
        metadata = load_json(metadata_path, gaps, rel(root, metadata_path))
        if not isinstance(metadata, dict):
            continue
        if metadata.get("dry_run") is True:
            out["dry_runs"] += 1
        records = metadata.get("records")
        if not isinstance(records, list):
            gaps.append(f"{rel(root, metadata_path)}: records is not a list")
            continue
        for record in records:
            if not isinstance(record, dict):
                gaps.append(f"{rel(root, metadata_path)}: non-object eval record")
                continue
            out["records_total"] += 1
            status = str(record.get("status") or "unknown")
            profile = str(record.get("profile") or "unknown")
            merge_count(out["by_status"], status)
            merge_count(out["by_profile"], profile)
            if record.get("failure_kind"):
                merge_count(out["by_failure_kind"], str(record["failure_kind"]))
            out["records"].append({
                "id": record.get("id"),
                "profile": record.get("profile"),
                "status": record.get("status"),
                "failure_kind": record.get("failure_kind"),
                "run": metadata_path.parent.name,
            })
    return out


def collect_report(root: Path, since=None, until=None) -> dict:
    gaps: list[str] = []
    plans = [collect_plan(root, plan, gaps, since, until)
             for plan in discover_plans(root)]

    metrics_total = empty_metrics()
    reviews_total = {
        "files": 0,
        "unreadable": 0,
        "findings_total": 0,
        "blocking_high": 0,
        "by_severity": {},
    }
    verification_files = 0
    auto_build_reports = 0
    for plan in plans:
        add_metrics(metrics_total, plan["metrics"])
        reviews_total["files"] += plan["reviews"]["files"]
        reviews_total["unreadable"] += plan["reviews"]["unreadable"]
        merge_review_counts(reviews_total, plan["reviews"])
        verification_files += plan["verification_files"]
        auto_build_reports += plan["auto_build_reports"]

    windowed = since is not None or until is not None
    if windowed:
        # add_metrics() sums only the typed counters, so roll the per-plan line
        # census up here — the rollup must state its own reach.
        metrics_total["windowed"] = True
        rollup = {"in_window": 0, "out_of_window": 0, "undated": 0}
        for plan in plans:
            wl = plan["metrics"].get("window_lines") or {}
            for key in rollup:
                rollup[key] += wl.get(key, 0)
        metrics_total["window_lines"] = rollup

    evals = collect_evals(root, gaps)
    plans_with_metrics = sum(1 for p in plans if p["metrics_present"])
    metrics_coverage = {
        "plans_expected": len(plans),
        "plans_with_stream": plans_with_metrics,
        "plans_missing_stream": len(plans) - plans_with_metrics,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "core-engineering metrics-report",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "plans": {
            "count": len(plans),
            "with_metrics": plans_with_metrics,
            "without_metrics": metrics_coverage["plans_missing_stream"],
            "metrics_coverage": metrics_coverage,
            "with_reviews": sum(1 for p in plans if p["reviews"]["files"]),
            "items": plans,
        },
        "metrics": metrics_total,
        "reviews": reviews_total,
        "verifications": {"files": verification_files},
        "auto_build": {"run_reports": auto_build_reports},
        "evals": evals,
        "gaps": gaps,
        "honest_limitations": [
            "Repository-level projection, not a delivery-quality verdict.",
            "Metrics streams are best-effort and producer-owned; missing lines are reported as gaps.",
            "Markdown artifacts are counted by presence and are not semantically re-graded here.",
        ],
    }
    if windowed:
        report["window"] = {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "applied": True,
            "granularity": "day",
            "bounds_inclusive": True,
            "stream_lines": metrics_total["window_lines"],
            "limitations": list(WINDOW_LIMITATIONS),
        }
        report["windowing"] = {
            "windowed_blocks": list(WINDOWED_BLOCKS),
            "as_of_now_blocks": list(AS_OF_NOW_BLOCKS),
            "note": WINDOWING_NOTE,
        }
    return report


def render_html(report: dict) -> str:
    def esc(value) -> str:
        return html.escape(str(value))

    plan_rows = "\n".join(
        "<tr>"
        f"<td>{esc(p['slug'])}</td>"
        f"<td>{esc(p.get('status') or '')}</td>"
        f"<td>{esc(p['feature_count'])}</td>"
        f"<td>{'present' if p['metrics_present'] else '<strong>missing</strong>'}</td>"
        f"<td>{esc(p['metrics']['lines_total']) if p['metrics_present'] else 'no data'}</td>"
        f"<td>{esc(p['reviews']['blocking_high'])}</td>"
        f"<td>{esc(p['verification_files'])}</td>"
        "</tr>"
        for p in report["plans"]["items"]
    )
    gaps = "".join(f"<li>{esc(gap)}</li>" for gap in report["gaps"]) or "<li>None</li>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Core Engineering Metrics</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #17202a; }}
    table {{ border-collapse: collapse; width: 100%; margin-block: 1rem; }}
    th, td {{ border: 1px solid #d5d8dc; padding: 0.45rem 0.6rem; text-align: left; }}
    th {{ background: #f4f6f7; }}
    code {{ background: #f4f6f7; padding: 0.1rem 0.25rem; }}
  </style>
</head>
<body>
  <h1>Core Engineering Metrics</h1>
  <p>Generated at <code>{esc(report['generated_at_utc'])}</code>.</p>
  <h2>Summary</h2>
  <ul>
    <li>Plans: {esc(report['plans']['count'])}</li>
    <li>Metrics stream coverage: {esc(report['plans']['metrics_coverage']['plans_with_stream'])}/{esc(report['plans']['metrics_coverage']['plans_expected'])} present; {esc(report['plans']['metrics_coverage']['plans_missing_stream'])} missing</li>
    <li>Metric lines: {esc(report['metrics']['lines_total'])}</li>
    <li>Review findings: {esc(report['reviews']['findings_total'])}</li>
    <li>Blocking high findings: {esc(report['reviews']['blocking_high'])}</li>
    <li>Eval records: {esc(report['evals']['records_total'])}</li>
  </ul>
  <h2>Plans</h2>
  <table>
    <thead><tr><th>Plan</th><th>Status</th><th>Features</th><th>Metrics stream</th><th>Metric lines</th><th>Blocking high</th><th>Verifications</th></tr></thead>
    <tbody>{plan_rows}</tbody>
  </table>
  <h2>Gaps</h2>
  <ul>{gaps}</ul>
</body>
</html>
"""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile repository-level SDLC metrics")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="repository root")
    parser.add_argument("--json", action="store_true",
                        help="print JSON to stdout (default unless --out is used)")
    parser.add_argument("--out", help="write JSON report to FILE")
    parser.add_argument("--html", help="write a standalone HTML report to FILE")
    parser.add_argument("--fail-on-gaps", action="store_true",
                        help="exit 1 when the report contains gaps")
    parser.add_argument("--since", metavar="YYYY-MM-DD",
                        help="window the metrics streams: events on/after this date "
                             "(inclusive). Review/verification/eval blocks stay as-of-now.")
    parser.add_argument("--until", metavar="YYYY-MM-DD",
                        help="window the metrics streams: events on/before this date "
                             "(inclusive)")
    args = parser.parse_args(argv)

    since = until = None
    for name in ("since", "until"):
        raw = getattr(args, name)
        if raw is None:
            continue
        parsed = parse_iso_date(raw)
        if parsed is None:
            print(f"metrics-report: --{name} must be YYYY-MM-DD (got {raw!r})",
                  file=sys.stderr)
            return 2
        if name == "since":
            since = parsed
        else:
            until = parsed
    if since is not None and until is not None and since > until:
        print(f"metrics-report: --since {since} is after --until {until} — an empty "
              f"window is a usage error, not an empty report", file=sys.stderr)
        return 2

    try:
        root = Path(args.root).resolve()
        report = collect_report(root, since, until)
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if args.out:
            write_text(Path(args.out), rendered + "\n")
        if args.html:
            write_text(Path(args.html), render_html(report))
        if args.json or not args.out:
            print(rendered)
        return 1 if args.fail_on_gaps and report["gaps"] else 0
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(f"metrics-report: unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
