#!/usr/bin/env python3
"""sca-guard.py — known-vulnerability scan of pinned dependency manifests.

Queries the OSV.dev advisory database for every exactly-pinned dependency it
can parse from the repo's manifests. Deterministic in what it scans and how it
degrades; the only non-determinism is the advisory database itself.

Privacy: the ONLY data that leaves the machine is package coordinates —
ecosystem + name + version — sent to https://api.osv.dev. No file contents,
no repo identity. `--offline` (or any network failure) degrades LOUDLY with
exit 2: could-not-run is never a silent pass.

Parsed manifests (v1 scope, documented in the skill's Honest Limitations):
  * requirements*.txt and requirements/*.txt — `name==version` pins (PyPI)
  * package-lock.json — v2/v3 `packages` and v1 `dependencies` (npm)
  * package.json — dependencies/devDependencies with EXACT versions only;
    range specifiers (^ ~ > < * ||) are reported as skipped-unpinned

Exit codes: 0 = scanned clean · 1 = at least one known-vulnerable pin ·
2 = could not run (offline/network/parse-nothing errors are loud, never pass).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import merge_disposition  # noqa: E402  (dir-local forked ledger reader)

DEFAULT_OSV_URL = "https://api.osv.dev/v1/querybatch"
BATCH_SIZE = 100
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build"}
RANGE_CHARS = ("^", "~", ">", "<", "*", "||", " - ")


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def iter_files(repo: Path, names: tuple[str, ...]):
    for path in sorted(repo.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and any(path.match(pattern) for pattern in names):
            yield path


def parse_requirements(path: Path, repo: Path) -> tuple[list[dict], list[str]]:
    pins, skipped = [], []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("#", 1)[0].split(";", 1)[0].strip()
        if not line or line.startswith(("-", "--")):
            continue
        if "==" not in line:
            skipped.append(f"{path.relative_to(repo)}: {line} (not an exact pin)")
            continue
        name, _, version = line.partition("==")
        name = name.split("[", 1)[0].strip()
        version = version.strip()
        if name and version:
            pins.append({"ecosystem": "PyPI", "name": name, "version": version,
                         "manifest": str(path.relative_to(repo))})
    return pins, skipped


def parse_package_lock(path: Path, repo: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    pins: list[dict] = []
    rel_path = str(path.relative_to(repo))
    packages = data.get("packages")
    if isinstance(packages, dict):  # lockfile v2/v3
        for key, meta in packages.items():
            if not key or not isinstance(meta, dict):
                continue
            name = key.rsplit("node_modules/", 1)[-1]
            version = meta.get("version")
            if name and isinstance(version, str) and version:
                pins.append({"ecosystem": "npm", "name": name, "version": version,
                             "manifest": rel_path})
    else:  # lockfile v1
        def walk(deps: dict) -> None:
            for name, meta in deps.items():
                if not isinstance(meta, dict):
                    continue
                version = meta.get("version")
                if isinstance(version, str) and version:
                    pins.append({"ecosystem": "npm", "name": name, "version": version,
                                 "manifest": rel_path})
                child = meta.get("dependencies")
                if isinstance(child, dict):
                    walk(child)
        deps = data.get("dependencies")
        if isinstance(deps, dict):
            walk(deps)
    return pins


def parse_package_json(path: Path, repo: Path) -> tuple[list[dict], list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return [], []
    pins, skipped = [], []
    rel_path = str(path.relative_to(repo))
    for section in ("dependencies", "devDependencies"):
        deps = data.get(section)
        if not isinstance(deps, dict):
            continue
        for name, version in deps.items():
            if not isinstance(version, str) or not version:
                continue
            if any(ch in version for ch in RANGE_CHARS) or version[0] in "^~":
                skipped.append(f"{rel_path}: {name}@{version} (range, not a pin)")
                continue
            pins.append({"ecosystem": "npm", "name": name, "version": version,
                         "manifest": rel_path})
    return pins, skipped


def collect_pins(repo: Path) -> tuple[list[dict], list[str]]:
    pins: list[dict] = []
    skipped: list[str] = []
    for path in iter_files(repo, ("requirements*.txt", "requirements/*.txt")):
        found, missed = parse_requirements(path, repo)
        pins.extend(found)
        skipped.extend(missed)
    lock_dirs = set()
    for path in iter_files(repo, ("package-lock.json",)):
        pins.extend(parse_package_lock(path, repo))
        lock_dirs.add(path.parent)
    for path in iter_files(repo, ("package.json",)):
        if path.parent in lock_dirs:
            continue  # the lockfile is the better source for the same tree
        found, missed = parse_package_json(path, repo)
        pins.extend(found)
        skipped.extend(missed)
    unique: dict[tuple, dict] = {}
    for pin in pins:
        key = (pin["ecosystem"], pin["name"], pin["version"])
        if key in unique:
            manifests = unique[key].setdefault("manifests", [unique[key].pop("manifest")]) \
                if "manifest" in unique[key] else unique[key]["manifests"]
            if pin["manifest"] not in manifests:
                manifests.append(pin["manifest"])
        else:
            unique[key] = dict(pin)
    out = []
    for pin in unique.values():
        if "manifest" in pin:
            pin["manifests"] = [pin.pop("manifest")]
        out.append(pin)
    return out, skipped


def query_osv(pins: list[dict], url: str, timeout: float) -> list[list[str]]:
    vulns_per_pin: list[list[str]] = []
    for start in range(0, len(pins), BATCH_SIZE):
        batch = pins[start:start + BATCH_SIZE]
        payload = json.dumps({"queries": [
            {"package": {"name": p["name"], "ecosystem": p["ecosystem"]},
             "version": p["version"]}
            for p in batch
        ]}).encode("utf-8")
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        results = body.get("results")
        if not isinstance(results, list) or len(results) != len(batch):
            raise ValueError("OSV response shape unexpected (results length mismatch)")
        for result in results:
            vulns = result.get("vulns") if isinstance(result, dict) else None
            ids = [v.get("id") for v in vulns if isinstance(v, dict) and v.get("id")] \
                if isinstance(vulns, list) else []
            vulns_per_pin.append(ids)
    return vulns_per_pin


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan pinned dependencies against the OSV.dev advisory database.")
    parser.add_argument("--repo", default=".", help="repository root to scan")
    parser.add_argument("--offline", action="store_true",
                        help="do not touch the network; degrade loudly (exit 2)")
    parser.add_argument("--osv-url", default=DEFAULT_OSV_URL,
                        help="OSV querybatch endpoint (tests may point this locally)")
    parser.add_argument("--timeout", type=float, default=20.0, help="per-request timeout")
    parser.add_argument("--today", help="override today for disposition expiry (YYYY-MM-DD; tests)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        eprint(f"sca-guard: ERROR — repo not found: {repo}")
        return 2
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        eprint(f"sca-guard: ERROR — bad --today {args.today!r}")
        return 2
    pins, skipped = collect_pins(repo)
    if not pins:
        result = {"schema_version": 1, "status": "pass", "packages_scanned": 0,
                  "findings": [], "hard_failures": [], "skipped_unpinned": skipped,
                  "note": "no exactly-pinned dependencies found to scan"}
        print(json.dumps(result, indent=2) if args.json
              else "sca-guard: no exactly-pinned dependencies found to scan "
                   f"({len(skipped)} unpinned skipped).")
        return 0

    if args.offline:
        eprint(f"sca-guard: DEGRADED — offline mode: {len(pins)} pinned package(s) "
               "were NOT checked against OSV. This is not a pass.")
        return 2
    try:
        vulns_per_pin = query_osv(pins, args.osv_url, args.timeout)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        eprint(f"sca-guard: DEGRADED — OSV query failed ({exc.__class__.__name__}: {exc}). "
               f"{len(pins)} pinned package(s) were NOT checked. This is not a pass.")
        return 2

    raw_findings = []
    for pin, ids in zip(pins, vulns_per_pin):
        if ids:
            raw_findings.append({**pin, "vulns": ids})
    # Consult the disposition ledger AS COMMITTED at head (this repo IS the committed
    # {head_tree} when run as a merge-bar gate): a consciously-accepted advisory moves to
    # `accepted` — shown, counted, never silently dropped — so it stops re-alarming every
    # PR without hiding it. Absent ledger -> no dispositions -> identical to prior behavior.
    entries, ledger_err = merge_disposition.read_ledger_file(repo / merge_disposition.LEDGER_RELPATH)
    findings, accepted = merge_disposition.partition(raw_findings, entries, "sca-guard", today)
    # `hard_failures` carries the SAME human-evidence line shape the other gate
    # scripts emit, so a consuming merge-runner renders the advisory ids and
    # package names — never a bare "FAIL (no detail)". Empty on a clean scan.
    hard_failures = [
        f"{f['ecosystem']}:{f['name']}=={f['version']} is advisory-listed "
        f"[{', '.join(f['vulns'])}] ({', '.join(f.get('manifests', []))})"
        for f in findings
    ]
    result = {
        "schema_version": 1,
        "status": "fail" if findings else "pass",
        "packages_scanned": len(pins),
        "findings": findings,
        "accepted": accepted,
        "hard_failures": hard_failures,
        "skipped_unpinned": skipped,
    }
    if ledger_err:
        result["ledger_warning"] = ledger_err
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"sca-guard: scanned {len(pins)} pinned package(s); "
              f"{len(findings)} with known advisories; {len(accepted)} accepted via ledger; "
              f"{len(skipped)} unpinned skipped.")
        for f in findings:
            print(f"  ✗ {f['ecosystem']}:{f['name']}=={f['version']} "
                  f"[{', '.join(f['vulns'])}] ({', '.join(f['manifests'])})")
        for a in accepted:
            print(f"  ○ accepted [{a['disposition_id']}] {a['ecosystem']}:{a['name']}=={a['version']}")
        if ledger_err:
            eprint(f"sca-guard: ledger warning — {ledger_err}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
