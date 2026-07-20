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
                    "plans.items[].feature_count")
WINDOWING_NOTE = (
    "Only the blocks in windowed_blocks reflect --since/--until. Everything in "
    "as_of_now_blocks is current on-disk state at generated_at_utc and is NOT "
    "filtered — narrating one as windowed is a fabrication. A plan with no "
    "in-window activity still appears, with windowed zeros."
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
        "events_by_type": {},
        "gates": {"pass": 0, "fail": 0},
        "escalations_by_type": {},
        "parks": 0,
        "retries": 0,
        "circuit_breaks": 0,
    }


def merge_count(dst: dict, key, amount: int = 1) -> None:
    dst[key] = dst.get(key, 0) + amount


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
    total["gates"]["pass"] += item["gates"]["pass"]
    total["gates"]["fail"] += item["gates"]["fail"]
    total["parks"] += item["parks"]
    total["retries"] += item["retries"]
    total["circuit_breaks"] += item["circuit_breaks"]
    for key, value in item["events_by_type"].items():
        merge_count(total["events_by_type"], key, value)
    for key, value in item["escalations_by_type"].items():
        merge_count(total["escalations_by_type"], key, value)


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
    metrics = (parse_metrics_file(metrics_path, root, gaps, since, until)
               if metrics_path.is_file() else empty_metrics())

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
        "metrics_present": metrics_path.is_file(),
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
    report = {
        "schema_version": SCHEMA_VERSION,
        "tool": "core-engineering metrics-report",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "plans": {
            "count": len(plans),
            "with_metrics": sum(1 for p in plans if p["metrics_present"]),
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
        f"<td>{esc(p['metrics']['lines_total'])}</td>"
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
    <li>Metric lines: {esc(report['metrics']['lines_total'])}</li>
    <li>Review findings: {esc(report['reviews']['findings_total'])}</li>
    <li>Blocking high findings: {esc(report['reviews']['blocking_high'])}</li>
    <li>Eval records: {esc(report['evals']['records_total'])}</li>
  </ul>
  <h2>Plans</h2>
  <table>
    <thead><tr><th>Plan</th><th>Status</th><th>Features</th><th>Metric lines</th><th>Blocking high</th><th>Verifications</th></tr></thead>
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
