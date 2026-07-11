#!/usr/bin/env python3
"""merge_disposition.py — the shared reader for the merge-bar finding-disposition ledger.

An advisory merge-bar gate (secrets-guard, sca-guard) re-alarms the SAME finding on
every PR until it is fixed — the documented "cries wolf" failure. The disposition
ledger is the accepted-risk register that lets a consciously-accepted finding stop
failing the gate WITHOUT hiding it: a matched finding is moved to an `accepted` list
(shown, counted, with its disposition id), never silently dropped. This is also what
makes promoting an advisory gate to `required_integrity_gates` tenable — accepted
findings no longer block every PR forever.

This module is a pure library: it loads and validates `.merge-bar/dispositions.json`
and partitions a gate's findings against it. Detection stays in the consuming gate;
the CLI validator is disposition-lint.py. Its readers are the two advisory gates
(secrets-guard, sca-guard), that lint, and evidence-pack.py — which renders the ledger
as the pack's accepted-risk register, so an accepted finding is visible to an auditor
rather than merely absent from a gate's output. It is deliberately forked (canonical
here, byte-identical copies beside every reader) so each reads one schema with no
share-by-reference — see plugins/core-engineering/fork-manifest.json.

A disposition entry (in the top-level `dispositions` array):
  {"id": "SEC-2026-07-fixture-key",         # unique, stable, human-authored
   "gate": "secrets-guard" | "sca-guard",   # which gate it dispositions
   "match": {...},                          # gate-specific selector (see below)
   "reason": "test fixture credential, not a live secret",
   "accepted_by": "alice",                  # the human who accepted the risk
   "date": "2026-07-09",                    # when it was accepted
   "expires": "2026-10-09"}                 # a disposition DEFERS, never forgets

`match` shapes:
  secrets-guard: {"file": "<repo-relative path>", "type"?: "<finding type>"}
                 or {"path_glob": "tests/fixtures/**", "type"?: "<finding type>"}
  sca-guard:     {"package": "<ecosystem>:<name>", "version"?: "<v>", "advisory"?: "<id>"}

An EXPIRED disposition never suppresses (the finding re-alarms) and disposition-lint
fails on it — the expiry is self-enforcing through the consuming gate and the lint.

Privacy: a secrets-guard match keys on file + finding TYPE only, never a secret value,
so the ledger stays safe to commit. Stdlib-only (portability guarantee).

Exit codes (run as a script it is a no-op): 0 — it exposes functions, no CLI.
"""
from __future__ import annotations

import fnmatch
import json
from datetime import date

SCHEMA_VERSION = 1
KNOWN_GATES = ("secrets-guard", "sca-guard")
LEDGER_RELPATH = ".merge-bar/dispositions.json"


def parse_ledger(text: str) -> tuple[list[dict], str | None]:
    """Parse ledger JSON text -> (entries, error). Empty/whitespace text -> ([], None)
    (an absent ledger is not an error). A malformed ledger returns ([], message) so the
    caller decides whether to fail — a gate treats it as 'no suppressions', the lint
    fails on it."""
    if not text or not text.strip():
        return [], None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        return [], f"dispositions ledger is not valid JSON ({exc.__class__.__name__}: {exc})"
    if not isinstance(data, dict):
        return [], "dispositions ledger must be a JSON object"
    if data.get("schema_version") != SCHEMA_VERSION:
        return [], (f"dispositions ledger schema_version must be {SCHEMA_VERSION} "
                    f"(got {data.get('schema_version')!r})")
    entries = data.get("dispositions")
    if entries is None:
        return [], "dispositions ledger has no `dispositions` array"
    if not isinstance(entries, list):
        return [], "dispositions `dispositions` must be an array"
    return entries, None


def read_ledger_file(path) -> tuple[list[dict], str | None]:
    """Read a ledger from a filesystem path (absent file -> ([], None))."""
    try:
        text = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return [], None
    except (OSError, UnicodeDecodeError) as exc:
        # UnicodeDecodeError is a ValueError, not an OSError — a non-UTF-8 ledger must
        # degrade to a surfaced parse error, never an uncaught crash (review finding).
        return [], f"could not read dispositions ledger: {exc}"
    return parse_ledger(text)


def validate(entries: list[dict], today: date) -> list[str]:
    """Structural + expiry validation of ledger entries. Returns a list of human-readable
    errors (empty = valid). Mirrors eval_check's dated-reasoned-waiver semantics and
    scan-lint H9's by-human stamp: a disposition the tool may not record alone."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"disposition #{i + 1}"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object")
            continue
        did = entry.get("id")
        if not isinstance(did, str) or not did.strip():
            errors.append(f"{where}: needs a non-empty string `id`")
        else:
            where = f"disposition {did!r}"
            if did in seen_ids:
                errors.append(f"{where}: duplicate id — ids must be unique")
            seen_ids.add(did)
        gate = entry.get("gate")
        if gate not in KNOWN_GATES:
            errors.append(f"{where}: `gate` must be one of {list(KNOWN_GATES)} (got {gate!r})")
        match = entry.get("match")
        if not isinstance(match, dict) or not match:
            errors.append(f"{where}: needs a non-empty `match` object")
        else:
            errors.extend(_validate_match(where, gate, match))
        for field in ("reason", "accepted_by"):
            val = entry.get(field)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"{where}: needs a non-empty `{field}` "
                              f"(a disposition is a human's accepted risk, stamped by whom)")
        errors.extend(_validate_date(where, entry, "date", today, must_be_future=False))
        errors.extend(_validate_date(where, entry, "expires", today, must_be_future=True))
    return errors


def _validate_match(where: str, gate, match: dict) -> list[str]:
    errors: list[str] = []
    if gate == "secrets-guard":
        if not (match.get("file") or match.get("path_glob")):
            errors.append(f"{where}: a secrets-guard match needs `file` or `path_glob`")
    elif gate == "sca-guard":
        pkg = match.get("package")
        if not isinstance(pkg, str) or ":" not in pkg:
            errors.append(f"{where}: a sca-guard match needs `package` as '<ecosystem>:<name>'")
    return errors


def _validate_date(where, entry, field, today, must_be_future) -> list[str]:
    raw = entry.get(field)
    try:
        parsed = date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return [f"{where}: `{field}` must be YYYY-MM-DD (got {raw!r})"]
    if must_be_future and parsed < today:
        return [f"{where}: expired {raw} — fix the finding or consciously renew the "
                f"disposition (a disposition defers, never forgets)"]
    return []


def is_active(entry: dict, today: date) -> bool:
    """Does this disposition still suppress on `today`? Public because a reader that
    must SHOW an expired entry (the evidence pack's accepted-risk register) needs the
    active/expired split without `validate()`, which reports an expired `expires` as an
    error — correct for the lint, wrong for a report that has to render the entry."""
    try:
        return date.fromisoformat(str(entry.get("expires"))) >= today
    except (TypeError, ValueError):
        return False  # an unparseable/expired entry never suppresses


def _matches(entry: dict, gate: str, finding: dict) -> bool:
    if entry.get("gate") != gate:
        return False
    match = entry.get("match")
    if not isinstance(match, dict):
        return False
    if gate == "secrets-guard":
        f_type = match.get("type")
        if f_type is not None and f_type != finding.get("type"):
            return False
        if "file" in match:
            return match["file"] == finding.get("file")
        if "path_glob" in match:
            return fnmatch.fnmatch(str(finding.get("file", "")), str(match["path_glob"]))
        return False
    if gate == "sca-guard":
        pkg = f"{finding.get('ecosystem')}:{finding.get('name')}"
        if match.get("package") != pkg:
            return False
        if "version" in match and str(match["version"]) != str(finding.get("version")):
            return False
        if "advisory" in match and match["advisory"] not in (finding.get("vulns") or []):
            return False
        return True
    return False


def partition(findings: list[dict], entries: list[dict], gate: str, today: date):
    """Split findings into (unaccepted, accepted). `accepted` items are the finding dict
    plus `disposition_id` and `disposition_reason`, so the gate can render them as
    shown-but-accepted — never silently dropped. Only active (non-expired) dispositions
    suppress; an expired one lets its finding re-alarm."""
    active = [e for e in entries if is_active(e, today)]
    unaccepted: list[dict] = []
    accepted: list[dict] = []
    for finding in findings:
        hit = next((e for e in active if _matches(e, gate, finding)), None)
        if hit is None:
            unaccepted.append(finding)
        else:
            accepted.append({**finding,
                             "disposition_id": hit.get("id"),
                             "disposition_reason": hit.get("reason")})
    return unaccepted, accepted
