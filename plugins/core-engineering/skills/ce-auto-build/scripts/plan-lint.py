#!/usr/bin/env python3
"""plan-lint.py — structural-integrity lint for a WRITTEN feature plan.

Checks a plan directory (`plan.json` + `features/<id>.md` + `feature-plan.md`,
produced by the `plan` workflow) for the *mechanical* invariants the plan
artifact must hold on disk. It is the on-disk counterpart to plan's own
pre-write checks: `/core-engineering:ce-plan` validates only the in-flight candidate draft and writes
once, so nothing re-checks the persisted artifact after a manual edit, drift, or a
hand-authored plan. This lint does — and it machine-PROVES the dependency-direction
and cycle-freedom invariants that `plan` itself only *model-reads* (its
SKILL.md Honest Limitations: "Dependency direction is not machine-proven").

It SUPPLEMENTS the model-judged plan-audit review — it does not replace it:

  * An un-runnable lint (missing/garbled inputs) exits 2 so the caller applies
    its owning workflow's documented error disposition. Exit 2 is never a pass.
  * Only the on-disk-checkable subset is covered. Genuine-judgment items (is a
    decision well-founded? is a feature mis-scoped?) stay with the human and the
    model-judged review lenses.
  * It checks STRUCTURE, not soundness. A clean PASS means the plan is *well-formed*
    (resolvable, acyclic, ordered) — never that it is *good*.

HARD checks (a FAIL -> exit 1; facts derivable from plan.json + the filesystem):
  H1  Every feature `file` in plan.json resolves to an existing file in the plan dir.
  H2  Feature `id`s are unique and non-empty.
  H3  Every feature has an integer `ship_order`; they are unique and the `features`
      array is ordered by it ("The features array is in ship order").
  H4  Every hard/soft dependency id resolves — an unqualified id to an in-plan
      feature, a qualified `<slug>/<id>` to a plan registered in plans.json.
  H5  Every in-plan HARD dependency points to a strictly-earlier ship_order
      (no backward and no self dependency).
  H6  The in-plan HARD-dependency graph is acyclic (no direct or transitive cycle).
  H7  Every `bridges[].replaced_by` on a plan.json feature resolves to an in-plan
      feature id with a strictly-LATER ship_order than the bridging feature — a
      bridge is temporary scaffolding retired by a valid FUTURE feature (the
      "Every bridge references a valid future feature" checklist item, now proven).
  H8  A multi-feature plan carries BOTH read-only re-projections on disk —
      `threat-model.md` AND `interaction-contract.md` — each present and non-empty
      (a real projection, or its attested negative `## No Security Surface` /
      `## No Cross-Feature Protocol` written *in place of* the sections). A missing
      or empty file is the silent omission the re-projection discipline forbids.
      (A single-feature minimal plan has no plan.json and never reaches the lint.)
  H9  A present `architecture_disposition` records a structurally valid applicability
      decision and internally consistent architecture-plan convergence evidence.

ADVISORY checks (warnings only; never change the exit code — completeness or
markdown-derived, best-effort):
  A1  Each feature carries title / type / final_complexity / risk_profile.
  A2  ship_order is contiguous from 1 (gaps are allowed but flagged).
  A3  No orphan feature file — every features/*.md on disk is in the manifest.
  A4  Each features/<id>.md exists and its embedded `id:` matches the manifest.
  A5  Each boundary-owner category is claimed by at most one feature.
  A6  Each feature declares <= 5 open unknowns.
  A7  feature-plan.md references every manifest feature id.
  A8  type / risk_profile / final_complexity values are in their known enums.
  A9  A qualified cross-plan dependency could not be verified (plans.json absent).
  A10 Durable-State Closure (feature-plan.md §8) — each reciprocal cell (revisit /
      amend / retire / retain / export / erase) is dispositioned
      `owned-by:<id>` / `bridge:…` / `excluded:<reason>`, never blank.
  A11 Surface-Removal Closure (feature-plan.md §8) — each `continuity` cell is
      dispositioned `deprecate:…` / `shim:…` / `hard-break:…`, never blank.
  A12 `architecture_disposition` is absent on a legacy plan. Compatibility mode
      remains non-blocking until the next explicit plan revision records the posture.

Usage:
    plan-lint.py <plan-dir>                 # dir holding plan.json + features/
    plan-lint.py --plan-json path/plan.json # explicit manifest
    plan-lint.py <plan-dir> --json          # machine-readable result

Exit codes:
    0  PASS  — no hard failures (advisory warnings may still be printed)
    1  FAIL  — at least one hard structural-integrity failure
    2  ERROR — inputs missing or unparseable; caller must apply its owning
               workflow's documented exit-2 disposition (never a pass)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Known vocabularies (plan artifact-template.md "Machine-Readable Feature
# Schema"). Out-of-enum values are an advisory warning, not a hard failure — a plan
# may legitimately extend these.
TYPES = {"foundation", "user-facing", "integration", "infrastructure", "refactor", "enabling"}
RISKS = {"low", "medium", "high"}
COMPLEXITIES = {"Simple", "Moderate", "Complex"}
ARCHITECTURE_DECISIONS = {"required", "recommended", "not-required", "waived"}
ARCHITECTURE_CONVERGENCE_STATES = {
    "converged", "deferred", "not-applicable", "waived",
}
ARCHITECTURE_DISPOSITION_KEYS = {
    "decision", "triggers", "rationale", "decided_by", "convergence",
}
ARCHITECTURE_CONVERGENCE_KEYS = {
    "status", "iteration_count", "summary", "decision_refs",
}
ARCHITECTURE_REQUIRED_TRIGGERS = {
    "explicit-architecture-deliverable",
    "multi-runtime-or-deployment-boundary",
    "cross-feature-durable-or-async-flow",
    "shared-data-ownership-or-migration",
    "trust-residency-or-sensitive-boundary",
    "shared-protocol-or-schema",
    "platform-or-topology-choice",
    "architecture-determining-nfr",
    "contested-cross-feature-owner",
}
ARCHITECTURE_RECOMMENDED_TRIGGERS = {
    "team-policy-recommendation",
    "planned-reuse-recommendation",
    "baseline-preference",
}
ARCHITECTURE_ALL_TRIGGERS = (
    ARCHITECTURE_REQUIRED_TRIGGERS | ARCHITECTURE_RECOMMENDED_TRIGGERS
)

# Placeholder / empty values that must not count as a real boundary-owner category.
EMPTY_VALUES = {"", "-", "none", "null", "n/a", "na", "tbd", "~"}

META_BLOCK = re.compile(r"###\s+Structured Metadata\s*\n+```ya?ml\n(.*?)\n```", re.DOTALL)
ID_LINE = re.compile(r"^id:\s*(\S.*?)\s*$", re.MULTILINE)


class PlanLintError(Exception):
    """Inputs cannot be loaded/parsed -> exit 2, never a pass."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def resolve_inputs(args) -> Path:
    if args.plan_json:
        return Path(args.plan_json)
    if not args.plan_dir:
        raise PlanLintError("provide a plan directory, or --plan-json")
    return Path(args.plan_dir) / "plan.json"


def load(plan_json_path: Path) -> tuple[dict, Path]:
    if not plan_json_path.is_file():
        raise PlanLintError(f"plan.json not found: {plan_json_path}")
    try:
        manifest = json.loads(plan_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PlanLintError(f"plan.json is not valid JSON: {e}") from e
    if not isinstance(manifest, dict) or not isinstance(manifest.get("features"), list):
        raise PlanLintError("plan.json must be an object with a `features` array")
    if not manifest["features"]:
        raise PlanLintError("plan.json `features` array is empty — nothing to validate")
    return manifest, plan_json_path.parent


def load_registry(plan_dir: Path) -> set[str] | None:
    """Read docs/plans/plans.json (one level up) -> set of registered slugs, or
    None if it is absent/unparseable (a coverage gap, not an error)."""
    reg = plan_dir.parent / "plans.json"
    if not reg.is_file():
        return None
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
        return {p["slug"] for p in data.get("plans", []) if isinstance(p, dict) and p.get("slug")}
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def dep_id(d) -> str | None:
    if isinstance(d, str):
        return d.strip() or None
    if isinstance(d, dict):
        v = d.get("id")
        return v.strip() if isinstance(v, str) and v.strip() else None
    return None


def deps_of(feature: dict, kind: str) -> list:
    deps = feature.get("dependencies")
    if not isinstance(deps, dict):
        return []
    arr = deps.get(kind)
    return arr if isinstance(arr, list) else []


def parse_feature_md(text: str) -> dict:
    """Best-effort read of a features/<id>.md Structured Metadata block.

    Returns {id, boundary_owner: [categories], open_unknowns: count|None}. Fields
    we cannot confidently parse come back as None / [] — markdown-derived checks
    are advisory, so an unparseable block is skipped, never a false hard failure.
    """
    out: dict = {"id": None, "boundary_owner": [], "open_unknowns": None}
    m = META_BLOCK.search(text)
    block = m.group(1) if m else text
    idm = ID_LINE.search(block)
    if idm:
        out["id"] = idm.group(1)

    lines = block.splitlines()
    for i, ln in enumerate(lines):
        key = re.match(r"^([a-z_]+):\s*(.*)$", ln)
        if not key:
            continue
        name, inline = key.group(1), key.group(2).strip()
        if name == "boundary_owner":
            out["boundary_owner"] = _collect_values(inline, lines, i)
        elif name == "open_unknowns":
            vals = _collect_values(inline, lines, i)
            out["open_unknowns"] = len(vals)
    return out


def _collect_values(inline: str, lines: list[str], idx: int) -> list[str]:
    """Collect a scalar / inline-list / following bullet-list value for a key."""
    if inline.startswith("[") and inline.endswith("]"):
        return [v.strip().strip("'\"") for v in inline[1:-1].split(",") if v.strip()]
    if inline and not inline.endswith(":"):
        v = inline.strip().strip("'\"")
        return [] if v.lower() in EMPTY_VALUES else [v]
    # following indented bullet list, until the next top-level (unindented) key
    vals: list[str] = []
    for ln in lines[idx + 1:]:
        if re.match(r"^\S", ln):  # next top-level key -> stop
            break
        b = re.match(r"^\s+-\s+(.*)$", ln)
        if b:
            v = b.group(1).strip().strip("'\"")
            if v and v.lower() not in EMPTY_VALUES:
                vals.append(v)
    return vals


_SEP_CELL = re.compile(r"^:?-{2,}:?$")


def _split_md_row(line: str) -> list[str]:
    """Split a `| a | b | c |` markdown table row into stripped cell strings."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    non_empty = [c for c in cells if c]
    return bool(non_empty) and all(_SEP_CELL.match(c) for c in non_empty)


def find_md_table(text: str, anchors: list[str]) -> tuple[list[str], list[list[str]]] | tuple[None, list]:
    """Locate the first markdown table whose header row contains ALL `anchors`
    (matched case-insensitively against whole cells) and return
    (header_cells, [data_row_cells, ...]). Returns (None, []) when no such table
    exists — markdown-derived, best-effort, so a missing table is simply skipped.
    """
    lines = text.splitlines()
    anchor_set = [a.lower() for a in anchors]
    for i, ln in enumerate(lines):
        if "|" not in ln:
            continue
        header = _split_md_row(ln)
        low = [c.lower() for c in header]
        if not all(a in low for a in anchor_set):
            continue
        rows: list[list[str]] = []
        j = i + 1
        # A well-formed table separates header from body with a `|---|---|` row.
        if j < len(lines) and "|" in lines[j] and _is_separator_row(_split_md_row(lines[j])):
            j += 1
        while j < len(lines):
            lj = lines[j]
            if "|" not in lj or not lj.strip().startswith("|"):
                break
            rc = _split_md_row(lj)
            if not _is_separator_row(rc):
                rows.append(rc)
            j += 1
        return header, rows
    return None, []


# Reciprocal-disposition vocabularies for the closure tables (feature-plan.md §8).
_DURABLE_DISPOSITIONS = ("owned-by:", "bridge:", "excluded:")
_SURFACE_DISPOSITIONS = ("deprecate:", "shim:", "hard-break:")


def _check_durable_cell(advisory: list, noun: str, col: str, cell: str, id_set: set[str]) -> None:
    norm = cell.strip()
    low = norm.lower()
    if norm == "" or low in EMPTY_VALUES:
        advisory.append(f"A10 {noun}: `{col}` reciprocal is undispositioned (empty)")
        return
    if not low.startswith(_DURABLE_DISPOSITIONS):
        advisory.append(
            f"A10 {noun}: `{col}` = `{cell}` is not a recognized disposition "
            f"(owned-by:<id> / bridge:… / excluded:<reason>)"
        )
        return
    if low.startswith("owned-by:"):
        target = norm.split(":", 1)[1].strip()
        target = re.split(r"[\s,]", target, 1)[0].strip()
        if target and "/" not in target and target not in id_set:
            advisory.append(f"A10 {noun}: `{col}` owner `{target}` does not resolve to an in-plan feature")


def _check_surface_cell(advisory: list, surface: str, cell: str) -> None:
    norm = cell.strip()
    low = norm.lower()
    if norm == "" or low in EMPTY_VALUES:
        advisory.append(f"A11 {surface}: `continuity` is undispositioned (empty)")
        return
    if not low.startswith(_SURFACE_DISPOSITIONS):
        advisory.append(
            f"A11 {surface}: `continuity` = `{cell}` is not a recognized disposition "
            f"(deprecate:… / shim:… / hard-break:…)"
        )


def validate_architecture_disposition(
    manifest: dict,
    hard: list,
    advisory: list,
) -> None:
    """Validate the plan's architecture applicability and convergence posture.

    Absence is a deliberate legacy-compatibility path. Once the field is present,
    malformed or internally contradictory evidence is a hard structural failure.
    """
    plan_tier = manifest.get("plan_tier")
    if "plan_tier" in manifest and (
        not isinstance(plan_tier, str) or plan_tier not in {"standard", "light"}
    ):
        hard.append("H9: `plan_tier`, when present, must be `standard` or `light`")

    if "architecture_disposition" not in manifest:
        advisory.append(
            "A12: `architecture_disposition` is absent — legacy plan; "
            "compatibility mode applies until the next Stage R revision"
        )
        return

    posture = manifest.get("architecture_disposition")
    if not isinstance(posture, dict):
        hard.append("H9: `architecture_disposition` must be an object")
        return

    missing = sorted(ARCHITECTURE_DISPOSITION_KEYS - set(posture))
    extra = sorted(set(posture) - ARCHITECTURE_DISPOSITION_KEYS)
    if missing:
        hard.append(
            "H9: `architecture_disposition` is missing key(s): " + ", ".join(missing)
        )
    if extra:
        hard.append(
            "H9: `architecture_disposition` has unknown key(s): " + ", ".join(extra)
        )

    decision = posture.get("decision")
    if not isinstance(decision, str) or decision not in ARCHITECTURE_DECISIONS:
        hard.append(
            "H9: `architecture_disposition.decision` must be one of "
            f"{sorted(ARCHITECTURE_DECISIONS)}"
        )

    raw_triggers = posture.get("triggers")
    triggers_valid = (
        isinstance(raw_triggers, list)
        and all(isinstance(item, str) and item.strip() for item in raw_triggers)
    )
    if not triggers_valid:
        hard.append(
            "H9: `architecture_disposition.triggers` must be a list of non-empty strings"
        )
        triggers: list[str] = []
    else:
        triggers = [item.strip() for item in raw_triggers]
        duplicates = sorted({item for item in triggers if triggers.count(item) > 1})
        if duplicates:
            hard.append(
                "H9: `architecture_disposition.triggers` contains duplicate "
                "trigger(s): " + ", ".join(duplicates)
            )
        unknown = sorted(set(triggers) - ARCHITECTURE_ALL_TRIGGERS)
        if unknown:
            hard.append(
                "H9: `architecture_disposition.triggers` contains unknown "
                "trigger(s): " + ", ".join(unknown)
            )

    rationale = posture.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        hard.append("H9: `architecture_disposition.rationale` must be non-empty")
    if posture.get("decided_by") != "human":
        hard.append("H9: `architecture_disposition.decided_by` must be 'human'")

    convergence = posture.get("convergence")
    if not isinstance(convergence, dict):
        hard.append("H9: `architecture_disposition.convergence` must be an object")
        return

    missing = sorted(ARCHITECTURE_CONVERGENCE_KEYS - set(convergence))
    extra = sorted(set(convergence) - ARCHITECTURE_CONVERGENCE_KEYS)
    if missing:
        hard.append(
            "H9: `architecture_disposition.convergence` is missing key(s): "
            + ", ".join(missing)
        )
    if extra:
        hard.append(
            "H9: `architecture_disposition.convergence` has unknown key(s): "
            + ", ".join(extra)
        )

    convergence_status = convergence.get("status")
    if (
        not isinstance(convergence_status, str)
        or convergence_status not in ARCHITECTURE_CONVERGENCE_STATES
    ):
        hard.append(
            "H9: `architecture_disposition.convergence.status` must be one of "
            f"{sorted(ARCHITECTURE_CONVERGENCE_STATES)}"
        )
    iteration_count = convergence.get("iteration_count")
    iteration_valid = (
        isinstance(iteration_count, int)
        and not isinstance(iteration_count, bool)
        and iteration_count >= 0
    )
    if not iteration_valid:
        hard.append(
            "H9: `architecture_disposition.convergence.iteration_count` "
            "must be an integer >= 0"
        )
    summary = convergence.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        hard.append(
            "H9: `architecture_disposition.convergence.summary` must be non-empty"
        )
    refs = convergence.get("decision_refs")
    if not (
        isinstance(refs, list)
        and all(isinstance(item, str) and item.strip() for item in refs)
    ):
        hard.append(
            "H9: `architecture_disposition.convergence.decision_refs` "
            "must be a list of non-empty strings"
        )

    # Cross-field consistency. Run these checks only where the constituent value
    # is itself well-typed, avoiding misleading cascades from one malformed leaf.
    if decision == "required":
        if plan_tier == "light":
            hard.append("H9: decision `required` is incompatible with `plan_tier: light`")
        if convergence_status != "converged":
            hard.append("H9: decision `required` requires convergence status `converged`")
        if iteration_valid and iteration_count < 1:
            hard.append("H9: decision `required` requires iteration_count >= 1")
        if triggers_valid and not triggers:
            hard.append("H9: decision `required` requires at least one trigger")
        elif triggers_valid:
            invalid = sorted(set(triggers) - ARCHITECTURE_REQUIRED_TRIGGERS)
            if invalid:
                hard.append(
                    "H9: decision `required` accepts only required architecture "
                    "trigger(s); found: " + ", ".join(invalid)
                )
    elif decision == "recommended":
        if convergence_status not in {"converged", "deferred"}:
            hard.append(
                "H9: decision `recommended` requires convergence status "
                "`converged` or `deferred`"
            )
        if triggers_valid and not triggers:
            hard.append("H9: decision `recommended` requires at least one trigger")
        elif triggers_valid:
            invalid = sorted(set(triggers) - ARCHITECTURE_RECOMMENDED_TRIGGERS)
            if invalid:
                hard.append(
                    "H9: decision `recommended` accepts only recommendation "
                    "trigger(s); found: " + ", ".join(invalid)
                )
        if iteration_valid:
            if convergence_status == "converged" and iteration_count < 1:
                hard.append(
                    "H9: decision `recommended` with status `converged` "
                    "requires iteration_count >= 1"
                )
            elif convergence_status == "deferred" and iteration_count != 0:
                hard.append(
                    "H9: decision `recommended` with status `deferred` "
                    "requires iteration_count 0"
                )
    elif decision == "not-required":
        if convergence_status != "not-applicable":
            hard.append(
                "H9: decision `not-required` requires convergence status `not-applicable`"
            )
        if iteration_valid and iteration_count != 0:
            hard.append("H9: decision `not-required` requires iteration_count 0")
        if triggers_valid and triggers:
            hard.append("H9: decision `not-required` requires an empty triggers list")
    elif decision == "waived":
        if convergence_status != "waived":
            hard.append("H9: decision `waived` requires convergence status `waived`")
        if triggers_valid and not triggers:
            hard.append("H9: decision `waived` requires at least one trigger")
        if iteration_valid and iteration_count < 1:
            hard.append("H9: decision `waived` requires iteration_count >= 1")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def find_cycle(adj: dict[str, list[str]]) -> list[str] | None:
    """Return a cycle path (a -> b -> ... -> a) in a directed graph, or None.

    Iterative DFS (WHITE/GRAY/BLACK) — a deep but ACYCLIC chain must not exhaust
    Python's recursion limit and misreport a well-formed plan as un-runnable.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    for root in adj:
        if color[root] != WHITE:
            continue
        color[root] = GRAY
        path: list[str] = [root]
        stack = [(root, iter(adj.get(root, [])))]
        while stack:
            node, it = stack[-1]
            advanced = False
            for m in it:
                if m not in color:
                    continue
                if color[m] == GRAY:
                    return path[path.index(m):] + [m]
                if color[m] == WHITE:
                    color[m] = GRAY
                    path.append(m)
                    stack.append((m, iter(adj.get(m, []))))
                    advanced = True
                    break
            if not advanced:
                color[node] = BLACK
                stack.pop()
                path.pop()
    return None


def run_checks(manifest: dict, plan_dir: Path, registry: set[str] | None) -> tuple[list, list]:
    hard, advisory = [], []
    features = manifest["features"]

    # Validate feature shape up front; a non-object feature is a hard structural break.
    # `norm` carries each surviving feature WITH its original manifest index, so every
    # `<feature #N>` label refers to the true plan.json array position — a filtered
    # re-enumeration would mislabel features once any non-object entry is dropped.
    norm: list[tuple[int, dict]] = []
    for idx, f in enumerate(features):
        if not isinstance(f, dict):
            hard.append(f"H2 <feature #{idx + 1}>: feature entry is not an object")
            continue
        norm.append((idx, f))

    ids = [f.get("id") for _, f in norm]
    id_set = {i for i in ids if isinstance(i, str) and i.strip()}

    # H2 unique / non-empty ids
    seen: set[str] = set()
    for idx, f in norm:
        fid = f.get("id")
        if not (isinstance(fid, str) and fid.strip()):
            hard.append(f"H2 <feature #{idx + 1}>: missing or empty `id`")
        elif fid in seen:
            hard.append(f"H2 {fid}: duplicate feature id")
        else:
            seen.add(fid)

    # H1 file resolution + A3 orphan files
    referenced: set[str] = set()
    for _idx, f in norm:
        fid = f.get("id") or "<no-id>"
        rel = f.get("file")
        if not isinstance(rel, str) or not rel.strip():
            hard.append(f"H1 {fid}: missing `file` path in manifest")
            continue
        referenced.add(rel)
        if not (plan_dir / rel).is_file():
            hard.append(f"H1 {fid}: `file` -> {rel} does not exist in the plan directory")
    feat_dir = plan_dir / "features"
    if feat_dir.is_dir():
        for md in sorted(feat_dir.glob("*.md")):
            relp = f"features/{md.name}"
            if relp not in referenced:
                advisory.append(f"A3 {relp}: feature file on disk is not referenced by plan.json")

    # H3 ship_order present / int / unique / ordered
    orders: dict[str, int] = {}
    order_vals: list = []
    for idx, f in norm:
        fid = f.get("id") or f"<feature #{idx + 1}>"
        so = f.get("ship_order")
        if not isinstance(so, int) or isinstance(so, bool):
            hard.append(f"H3 {fid}: `ship_order` missing or not an integer (found {so!r})")
            continue
        if isinstance(f.get("id"), str):
            orders[f["id"]] = so
        order_vals.append(so)
    if len(order_vals) != len(set(order_vals)):
        dupes = sorted({v for v in order_vals if order_vals.count(v) > 1})
        hard.append(f"H3: duplicate ship_order value(s): {dupes}")
    if order_vals != sorted(order_vals):
        hard.append("H3: the `features` array is not ordered by ship_order (it must be in ship order)")
    if order_vals:
        expected = list(range(1, len(order_vals) + 1))
        if sorted(order_vals) != expected:
            advisory.append(
                f"A2: ship_order is not contiguous from 1 — got {sorted(order_vals)}, expected {expected}"
            )

    # H4 dependency resolution + H5 direction (collect in-plan hard edges for H6)
    adj: dict[str, list[str]] = {i: [] for i in id_set}
    for _idx, f in norm:
        fid = f.get("id")
        for kind in ("hard", "soft"):
            for d in deps_of(f, kind):
                did = dep_id(d)
                if did is None:
                    advisory.append(f"A1 {fid or '<no-id>'}: a {kind} dependency has no `id`")
                    continue
                if "/" in did:  # qualified cross-plan id
                    slug = did.split("/", 1)[0]
                    if registry is None:
                        advisory.append(
                            f"A9 {fid}: cross-plan {kind} dep `{did}` unverifiable — plans.json absent"
                        )
                    elif slug not in registry:
                        hard.append(
                            f"H4 {fid}: {kind} dep `{did}` names plan `{slug}`, not in plans.json registry"
                        )
                    continue
                # unqualified -> must be an in-plan feature
                if did not in id_set:
                    hard.append(f"H4 {fid}: {kind} dep `{did}` does not resolve to an in-plan feature")
                    continue
                if kind == "hard" and isinstance(fid, str):
                    adj.setdefault(fid, []).append(did)
                    # H5 direction
                    if did == fid:
                        hard.append(f"H5 {fid}: hard self-dependency")
                    elif fid in orders and did in orders and orders[did] >= orders[fid]:
                        hard.append(
                            f"H5 {fid}: hard dep `{did}` (ship_order {orders[did]}) "
                            f"does not point earlier than {fid} (ship_order {orders[fid]})"
                        )

    # H6 acyclicity (in-plan hard edges)
    cycle = find_cycle(adj)
    if cycle:
        hard.append(f"H6: hard-dependency cycle: {' -> '.join(cycle)}")

    # H7 bridge replaced_by resolution (plan.json-derived; a bridge is scaffolding
    # retired by a valid FUTURE feature). Dormant when no feature carries a `bridges`
    # array — a hard check reads only plan.json + the filesystem, never markdown.
    for idx, f in norm:
        fid = f.get("id")
        bridges = f.get("bridges")
        if not isinstance(bridges, list):
            continue
        fid_disp = fid if isinstance(fid, str) and fid.strip() else f"<feature #{idx + 1}>"
        for bi, b in enumerate(bridges):
            if not isinstance(b, dict):
                continue
            label = f"bridge #{bi + 1}"
            btype = b.get("type")
            if isinstance(btype, str) and btype.strip():
                label += f" ({btype.strip()})"
            rb = b.get("replaced_by")
            if not (isinstance(rb, str) and rb.strip()):
                hard.append(
                    f"H7 {fid_disp}: {label} has no `replaced_by` feature id "
                    f"(every bridge must reference a valid future feature)"
                )
                continue
            rb = rb.strip()
            if "/" in rb:  # cross-plan bridge target — outside the in-plan ship-order check
                continue
            if rb not in id_set:
                hard.append(f"H7 {fid_disp}: {label} `replaced_by` -> `{rb}` does not resolve to an in-plan feature")
                continue
            if isinstance(fid, str) and rb == fid:
                hard.append(f"H7 {fid_disp}: {label} is `replaced_by` itself")
            elif isinstance(fid, str) and fid in orders and rb in orders and orders[rb] <= orders[fid]:
                hard.append(
                    f"H7 {fid_disp}: {label} `replaced_by` `{rb}` (ship_order {orders[rb]}) "
                    f"is not strictly later than {fid_disp} (ship_order {orders[fid]})"
                )

    # H8 re-projection presence — a multi-feature plan carries BOTH read-only
    # re-projections on disk (a real projection or its attested negative). A missing
    # or empty file is the silent omission the discipline forbids. Single-feature
    # minimal plans have no plan.json and never reach the lint.
    if len(features) > 1:
        for fname in ("threat-model.md", "interaction-contract.md"):
            fpath = plan_dir / fname
            if not fpath.is_file():
                hard.append(
                    f"H8: `{fname}` is missing — a multi-feature plan must carry it "
                    f"(a re-projection or its attested negative)"
                )
                continue
            try:
                body = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                body = ""
            if not body.strip():
                hard.append(f"H8: `{fname}` is empty — write the re-projection or its attested negative, never a silent omission")

    # H9 architecture posture — structural only. The presence and freshness of a
    # required published baseline is enforced by downstream architecture consumers,
    # after the written plan exists and can be hash-bound without a circular manifest.
    validate_architecture_disposition(manifest, hard, advisory)

    # --- advisory: per-feature completeness + enum sanity ---
    for _idx, f in norm:
        fid = f.get("id") or "<no-id>"
        for field in ("title", "type", "final_complexity", "risk_profile"):
            if not f.get(field):
                advisory.append(f"A1 {fid}: missing `{field}` in manifest")
        if f.get("type") and f["type"] not in TYPES:
            advisory.append(f"A8 {fid}: unknown type `{f['type']}`")
        if f.get("risk_profile") and f["risk_profile"] not in RISKS:
            advisory.append(f"A8 {fid}: unknown risk_profile `{f['risk_profile']}`")
        if f.get("final_complexity") and f["final_complexity"] not in COMPLEXITIES:
            advisory.append(f"A8 {fid}: unknown final_complexity `{f['final_complexity']}`")

    # --- advisory: markdown-derived (best-effort) ---
    owner_claims: dict[str, list[str]] = {}
    for _idx, f in norm:
        fid = f.get("id")
        rel = f.get("file")
        if not (isinstance(fid, str) and isinstance(rel, str)):
            continue
        fpath = plan_dir / rel
        if not fpath.is_file():
            continue
        # Best-effort advisory input — a decode glitch in a secondary markdown file
        # must degrade to skipping its checks, never abort the lint (errors="replace").
        meta = parse_feature_md(fpath.read_text(encoding="utf-8", errors="replace"))
        if meta["id"] and meta["id"] != fid:
            advisory.append(f"A4 {fid}: features file declares id `{meta['id']}` (manifest says `{fid}`)")
        if isinstance(meta["open_unknowns"], int) and meta["open_unknowns"] > 5:
            advisory.append(f"A6 {fid}: {meta['open_unknowns']} open unknowns (cap is 5)")
        for cat in meta["boundary_owner"]:
            owner_claims.setdefault(cat.lower(), []).append(fid)
    for cat, claimants in sorted(owner_claims.items()):
        if len(claimants) > 1:
            advisory.append(f"A5: boundary-owner `{cat}` claimed by {len(claimants)} features: {claimants}")

    # A7 feature-plan.md references every feature id
    fp = plan_dir / "feature-plan.md"
    if fp.is_file():
        fp_text = fp.read_text(encoding="utf-8", errors="replace")  # best-effort; never abort
        for fid in sorted(id_set):
            if fid not in fp_text:
                advisory.append(f"A7 {fid}: not referenced anywhere in feature-plan.md")

        # A10 Durable-State Closure reciprocals (feature-plan.md §8) — each of the six
        # reciprocal cells must be dispositioned owned-by:/bridge:/excluded:.
        d_header, d_rows = find_md_table(
            fp_text, ["noun", "revisit", "amend", "retire", "retain", "export", "erase"]
        )
        if d_header:
            low = [c.lower() for c in d_header]
            noun_i = low.index("noun")
            disp = [(name, low.index(name)) for name in
                    ("revisit", "amend", "retire", "retain", "export", "erase") if name in low]
            for row in d_rows:
                noun = row[noun_i] if noun_i < len(row) else ""
                if not noun or noun.lower() in EMPTY_VALUES or noun.startswith("<"):
                    continue
                for name, ci in disp:
                    cell = row[ci] if ci < len(row) else ""
                    _check_durable_cell(advisory, noun, name, cell, id_set)

        # A11 Surface-Removal Closure continuity (feature-plan.md §8; N/A on greenfield —
        # a greenfield plan writes no table, so absence is simply skipped).
        s_header, s_rows = find_md_table(fp_text, ["surface", "break-class", "continuity"])
        if s_header:
            low = [c.lower() for c in s_header]
            surf_i = low.index("surface")
            cont_i = low.index("continuity")
            for row in s_rows:
                surface = row[surf_i] if surf_i < len(row) else ""
                if not surface or surface.lower() in EMPTY_VALUES or surface.startswith("<"):
                    continue
                cell = row[cont_i] if cont_i < len(row) else ""
                _check_surface_cell(advisory, surface, cell)

    return hard, advisory


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Structural-integrity lint for a written feature plan.")
    p.add_argument("plan_dir", nargs="?", help="directory containing plan.json + features/")
    p.add_argument("--plan-json", help="explicit path to plan.json")
    p.add_argument("--json", action="store_true", help="emit a machine-readable JSON result")
    args = p.parse_args(argv)

    try:
        plan_json_path = resolve_inputs(args)
        manifest, plan_dir = load(plan_json_path)
        registry = load_registry(plan_dir)
        hard, advisory = run_checks(manifest, plan_dir, registry)
    except PlanLintError as e:
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print(f"plan-lint: ERROR — could not run: {e}", file=sys.stderr)
            print("  -> follow the owning workflow's exit-2 disposition; never treat this as a pass.", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        # Any UNEXPECTED failure must honor the exit-2 "could not run" contract,
        # never leak as an uncaught traceback that exits 1 and
        # impersonates a hard FAIL to a caller that gates on the exit code.
        # SystemExit is not an Exception subclass, so argparse --help is unaffected.
        if args.json:
            print(json.dumps({"status": "error", "message": f"unexpected: {type(e).__name__}: {e}"}))
        else:
            print(f"plan-lint: ERROR — unexpected failure ({type(e).__name__}): {e}", file=sys.stderr)
            print("  -> follow the owning workflow's exit-2 disposition; never treat this as a pass.", file=sys.stderr)
        return 2

    status = "fail" if hard else "pass"
    if args.json:
        print(json.dumps({
            "status": status,
            "plan": str(plan_json_path),
            "features": len(manifest["features"]),
            "hard_failures": hard,
            "advisory": advisory,
        }, indent=2))
        return 1 if hard else 0

    print(f"plan-lint: {plan_json_path}")
    print(f"  parsed: {len(manifest['features'])} feature(s)")
    if hard:
        print(f"\n  FAIL — {len(hard)} hard structural-integrity failure(s):")
        for f in hard:
            print(f"    x {f}")
    else:
        print("\n  PASS — hard structural-integrity checks (H1-H9) hold.")
        print("         (checks STRUCTURE, not soundness — well-formed, not necessarily good.)")
    if advisory:
        print(f"\n  advisory ({len(advisory)} — review, non-blocking):")
        for a in advisory:
            print(f"    ! {a}")
    print()
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
