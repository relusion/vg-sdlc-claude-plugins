#!/usr/bin/env python3
"""review-gate.py — the merge bar's review-evidence gate for one spec dir.

Reads the machine-readable review summary `/core-engineering:ce-review` writes
(`<spec_dir>/review-summary.json`, schema in this skill's artifact-template.md).
Before trusting its precomputed `blocking_high` verdict, this gate verifies the
plan/feature/spec identity and re-derives the exact plan, feature, spec, tasks,
architecture-package, and commit binding. A stale review is an integrity error,
never a current pass/fail verdict.

After provenance passes, the gate checks the summary's `status`
(`pass` / `blocked`) against `blocking_high`. A blocked summary may also carry
the precomputed `blocking_route`: `implement` or `plan-conflict`. Automation
requires that route and the gate cross-checks a plan-conflict route against its
confirmed Security finding. It independently derives the confirmed
correctness/security High count from the structured finding list and requires
exact agreement; it does not re-review code.

Registered in merge-policy.json as an ADVISORY gate: a `blocking_high > 0`
reports a yellow advisory line but never fails the merge verdict, and a missing
review artifact is a degradation the bar surfaces, not a block. An adopter who
wants review evidence to be mandatory promotes it to `required_integrity_gates`
in a local policy override — then exit 1 fails the bar, mechanically.

Stdlib-only, offline, Claude-free — it reads committed repository artifacts and
invokes the colocated deterministic architecture consumer checks.

Exit codes (house contract):
    0  PASS   — review-summary.json present and blocking_high == 0
    1  FAIL   — review-summary.json present and blocking_high > 0
    2  ERROR  — no/unreadable/malformed/contradictory review-summary.json for
                this spec dir, or usage error — could-not-run is loud, never a
                silent pass
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

SUMMARY_NAME = "review-summary.json"
SUMMARY_SCHEMA_VERSION = 2
SUMMARY_STATUSES = {"pass", "blocked"}
BLOCKING_ROUTES = {"implement", "plan-conflict"}
PLAN_CONFLICT_ESCALATION = "/core-engineering:ce-plan"
FINDING_LENSES = {
    "correctness",
    "security",
    "performance",
    "maintainability",
    "conformance",
    "simplicity",
}
FINDING_SEVERITIES = {"high", "medium", "low"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_MISSING = object()


def _load_architecture_context():
    path = Path(__file__).resolve().parent / "architecture_context.py"
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"colocated architecture_context.py is missing: {path}")
    spec = importlib.util.spec_from_file_location(
        "ce_review_architecture_context", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load architecture context helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _security_high_findings(data: dict) -> list[dict]:
    findings = data.get("findings")
    if not isinstance(findings, list):
        return []
    return [
        row
        for row in findings
        if isinstance(row, dict)
        and row.get("lens") == "security"
        and row.get("severity") == "high"
        and row.get("confidence") == "confirmed"
    ]


def _blocking_high_findings(data: dict) -> list[dict]:
    findings = data.get("findings")
    if not isinstance(findings, list):
        return []
    return [
        row
        for row in findings
        if isinstance(row, dict)
        and row.get("lens") in {"correctness", "security"}
        and row.get("severity") == "high"
        and row.get("confidence") == "confirmed"
    ]


def _plan_conflict_candidates(data: dict) -> list[dict]:
    """Return any blocking finding carrying either half of the route signal."""
    return [
        row
        for row in _security_high_findings(data)
        if "plan_conflict" in str(row.get("observation", ""))
        or row.get("suggested_escalation") == PLAN_CONFLICT_ESCALATION
    ]


def _plan_conflict_findings(data: dict) -> list[dict]:
    """Return blocking findings carrying the complete plan-conflict contract."""
    return [
        row
        for row in _plan_conflict_candidates(data)
        if "plan_conflict" in str(row.get("observation", ""))
        and row.get("suggested_escalation") == PLAN_CONFLICT_ESCALATION
    ]


def validate_summary(
    data: object, *, require_blocking_route: bool = False
) -> list[str]:
    """Validate identity, verdict fields, and the optional/required repair route."""
    if not isinstance(data, dict):
        return ["top level must be an object"]

    errors: list[str] = []
    if data.get("schema_version") != SUMMARY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {SUMMARY_SCHEMA_VERSION}")
    feature_id = data.get("feature_id")
    if not isinstance(feature_id, str) or not feature_id.strip():
        errors.append("feature_id must be a non-empty string")
    plan_slug = data.get("plan_slug")
    if not isinstance(plan_slug, str) or SLUG_RE.fullmatch(plan_slug) is None:
        errors.append("plan_slug must be a lowercase kebab-case slug")
    spec_revision = data.get("spec_revision")
    if type(spec_revision) is not int or spec_revision < 1:
        errors.append("spec_revision must be an integer >= 1")
    if not isinstance(data.get("binding"), dict):
        errors.append("binding must be an object")

    findings = data.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be an array")
        findings = []
    finding_ids: set[str] = set()
    for index, row in enumerate(findings):
        label = f"findings[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{label} must be an object")
            continue
        finding_id = row.get("id")
        if not isinstance(finding_id, str) or not finding_id.strip():
            errors.append(f"{label}.id must be non-empty")
        elif finding_id in finding_ids:
            errors.append(f"{label}.id duplicates {finding_id!r}")
        else:
            finding_ids.add(finding_id)
        if row.get("lens") not in FINDING_LENSES:
            errors.append(f"{label}.lens is invalid")
        severity = row.get("severity")
        if severity not in FINDING_SEVERITIES:
            errors.append(f"{label}.severity is invalid")
        if row.get("lens") == "performance" and severity == "high":
            errors.append(f"{label} performance severity cannot be High")
        if severity == "high" and row.get("confidence") not in {
            "confirmed",
            "suspected",
        }:
            errors.append(
                f"{label}.confidence must be confirmed or suspected for High"
            )
        elif severity in {"medium", "low"} and "confidence" in row:
            errors.append(f"{label}.confidence is permitted only for High")
    findings_total = data.get("findings_total")
    if type(findings_total) is not int or findings_total < 0:
        errors.append("findings_total must be a non-negative integer")
    elif findings_total != len(findings):
        errors.append(
            f"findings_total is {findings_total}, expected {len(findings)} "
            "from findings"
        )

    blocking = data.get("blocking_high")
    if type(blocking) is not int or blocking < 0:
        errors.append("blocking_high must be a non-negative integer")
    else:
        derived_blocking = len(_blocking_high_findings(data))
        if blocking != derived_blocking:
            errors.append(
                f"blocking_high is {blocking}, expected {derived_blocking} from "
                "confirmed correctness/security High findings"
            )

    status = data.get("status")
    if not isinstance(status, str) or status not in SUMMARY_STATUSES:
        errors.append("status must be 'pass' or 'blocked'")

    if (
        isinstance(status, str)
        and status in SUMMARY_STATUSES
        and type(blocking) is int
        and blocking >= 0
    ):
        expected = "blocked" if blocking > 0 else "pass"
        if status != expected:
            errors.append(
                f"status is {status!r}, expected {expected!r} for "
                f"blocking_high {blocking}"
            )

    route = data.get("blocking_route", _MISSING)
    plan_conflict_candidates = _plan_conflict_candidates(data)
    plan_conflicts = _plan_conflict_findings(data)
    if route is _MISSING:
        if require_blocking_route:
            errors.append(
                "blocking_route is required for automation and must be null, "
                "'implement', or 'plan-conflict'"
            )
    elif route is not None and (
        not isinstance(route, str) or route not in BLOCKING_ROUTES
    ):
        errors.append(
            "blocking_route must be null, 'implement', or 'plan-conflict'"
        )

    if type(blocking) is int and blocking >= 0 and route is not _MISSING:
        if blocking == 0 and route is not None:
            errors.append("blocking_route must be null when blocking_high is 0")
        elif blocking > 0 and (
            not isinstance(route, str) or route not in BLOCKING_ROUTES
        ):
            errors.append(
                "blocking_route must be 'implement' or 'plan-conflict' when "
                "blocking_high is positive"
            )
    if route == "plan-conflict" and not plan_conflicts:
        errors.append(
            "blocking_route 'plan-conflict' requires a confirmed Security High "
            "whose observation names plan_conflict and whose "
            "suggested_escalation is /core-engineering:ce-plan"
        )
    if plan_conflict_candidates and route != "plan-conflict":
        errors.append(
            "a confirmed Security High carrying a plan_conflict marker or "
            "ce-plan escalation requires blocking_route "
            "'plan-conflict'; it cannot be missing, null, or routed to implement"
        )
    return errors


def _git_toplevel(start: Path) -> Path | None:
    proc = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return None
    root = Path(proc.stdout.strip()).resolve()
    if not root.is_dir():
        return None
    return root


def _artifact_repo_root(spec_dir: Path) -> Path:
    """Infer the root of a canonical materialized docs/plans spec tree."""
    plan_dir = spec_dir.parent.parent.resolve()
    root = plan_dir.parent.parent.parent
    if root / "docs" / "plans" / plan_dir.name != plan_dir:
        raise RuntimeError(
            "artifact repository root could not be inferred from canonical "
            "docs/plans/<slug>/specs/<id> layout; pass --repo-root"
        )
    return root


def _commit_is_current_or_ancestor(
    *, recorded: str | None, current: str | None, repo_root: Path
) -> tuple[bool, str | None]:
    if recorded == current:
        return True, None
    if recorded is None or current is None:
        return False, "binding.commit_sha does not match the current repository"
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", recorded, current],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode == 0:
        return True, None
    if proc.returncode == 1:
        return False, (
            "binding.commit_sha is neither current nor an ancestor of the "
            "current repository commit"
        )
    detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
    raise RuntimeError(f"could not validate binding.commit_sha ancestry: {detail}")


def _resolve_evaluated_commit(repo_root: Path, value: str) -> str:
    candidate = value.strip().lower()
    if COMMIT_RE.fullmatch(candidate) is None:
        raise RuntimeError("--evaluated-commit must be a full lowercase commit id")
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", f"{candidate}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"evaluated commit cannot be resolved: {detail}")
    resolved = proc.stdout.strip().lower()
    if resolved != candidate:
        raise RuntimeError(
            f"evaluated commit resolved to unexpected object {resolved!r}"
        )
    return resolved


def _require_worktree_materializes_evaluated_commit(
    context, *, repo_root: Path, git_root: Path | None, commit: str
) -> None:
    """Fail when a live release worktree differs from the evaluated commit.

    Merge-bar callers may provide a separately materialized committed tree and
    a Git repository used only for ancestry. In that mode the materializer owns
    the tree/commit relationship. When the reviewed repository is itself the
    Git worktree—as it is for ce-ship-release—the gate proves the relationship
    directly and excludes only the same post-review evidence as the receipt.
    """
    if git_root is None or git_root.resolve() != repo_root.resolve():
        return
    differences = context.worktree_commit_differences(repo_root, commit)
    if not differences:
        return
    preview = ", ".join(repr(path) for path in differences[:20])
    remainder = len(differences) - 20
    suffix = f" (+{remainder} more)" if remainder > 0 else ""
    raise RuntimeError(
        "worktree does not materialize evaluated commit for non-evidence "
        f"path(s): {preview}{suffix}"
    )


def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return
    status = result["status"].upper()
    print(f"review-gate [{result.get('spec_dir', '?')}]: {status}")
    for line in result.get("hard_failures", []):
        print(f"  x {line}")
    for line in result.get("advisory", []):
        print(f"  ! {line}")
    if result.get("message"):
        print(f"  {result['message']}")


def evaluate(
    spec_dir: Path,
    *,
    require_blocking_route: bool = False,
    repo_root: Path | None = None,
    plan_dir: Path | None = None,
    feature_id: str | None = None,
    git_repo: Path | None = None,
    evaluated_commit: str | None = None,
) -> tuple[int, dict]:
    """Return (exit_code, verdict_dict) for one spec dir. The verdict mirrors the
    other gate scripts' shape (status / hard_failures / advisory) so the
    merge-runner renders and cross-checks it uniformly."""
    spec_dir = spec_dir.resolve()
    summary_path = spec_dir / SUMMARY_NAME
    base = {"schema_version": 1, "spec_dir": str(spec_dir),
            "hard_failures": [], "advisory": []}

    if summary_path.is_symlink() or not summary_path.is_file():
        return 2, {**base, "status": "error", "blocking_high": None,
                   "message": f"no review evidence for this spec dir "
                              f"({SUMMARY_NAME} missing under {spec_dir}) — run "
                              f"/core-engineering:ce-review before gating on it"}
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return 2, {**base, "status": "error", "blocking_high": None,
                   "message": f"cannot read review evidence "
                              f"{summary_path}: {e}"}
    schema_errors = validate_summary(
        data, require_blocking_route=require_blocking_route
    )
    context = None
    if not schema_errors:
        try:
            context = _load_architecture_context()
        except (OSError, RuntimeError) as exc:
            schema_errors.append(str(exc))
    if context is not None:
        schema_errors.extend(context.validate_binding_shape(data.get("binding")))
    if schema_errors:
        return 2, {**base, "status": "error", "blocking_high": None,
                   "message": f"review evidence {summary_path} has invalid schema: "
                              + "; ".join(schema_errors)}

    try:
        resolved_repo = (
            repo_root.resolve()
            if repo_root is not None
            else _artifact_repo_root(spec_dir)
        )
        if git_repo is not None:
            git_root = _git_toplevel(git_repo.resolve())
            if git_root is None:
                raise RuntimeError(f"--git-repo is not a Git worktree: {git_repo}")
        elif repo_root is not None:
            git_root = _git_toplevel(resolved_repo)
        else:
            # The merge bar reads a materialized committed head tree with no .git
            # directory while running from the actual source repository.
            git_root = _git_toplevel(spec_dir) or _git_toplevel(Path.cwd())
        resolved_plan = (
            plan_dir.resolve() if plan_dir is not None
            else spec_dir.parent.parent.resolve()
        )
        canonical_plan = spec_dir.parent.parent.resolve()
        if resolved_plan != canonical_plan:
            raise RuntimeError(
                f"plan directory {resolved_plan} does not own spec {spec_dir}"
            )
        try:
            spec_dir.relative_to(resolved_repo)
        except ValueError as exc:
            raise RuntimeError(
                f"spec directory escapes repository root: {spec_dir}"
            ) from exc

        tasks_path = spec_dir / "tasks.json"
        if tasks_path.is_symlink() or not tasks_path.is_file():
            raise RuntimeError(f"tasks.json must be a regular file: {tasks_path}")
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        if not isinstance(tasks, dict):
            raise RuntimeError("tasks.json must contain an object")
        resolved_feature = feature_id or spec_dir.name
        identity_errors: list[str] = []
        if spec_dir.name != resolved_feature:
            identity_errors.append(
                f"requested feature {resolved_feature!r} does not match "
                f"spec directory {spec_dir.name!r}"
            )
        if tasks.get("feature_id") != resolved_feature:
            identity_errors.append(
                "tasks.json feature_id does not match the reviewed feature"
            )
        if data.get("feature_id") != resolved_feature:
            identity_errors.append(
                "review-summary feature_id does not match the reviewed feature"
            )
        if data.get("plan_slug") != resolved_plan.name:
            identity_errors.append(
                "review-summary plan_slug does not match the owning plan directory"
            )
        tasks_revision = tasks.get("spec_revision")
        if type(tasks_revision) is not int or tasks_revision < 1:
            identity_errors.append("tasks.json spec_revision must be an integer >= 1")
        elif data.get("spec_revision") != tasks_revision:
            identity_errors.append(
                "review-summary spec_revision does not match tasks.json"
            )
        if identity_errors:
            raise RuntimeError("; ".join(identity_errors))

        current_commit = None
        if evaluated_commit is not None:
            if git_root is None:
                raise RuntimeError(
                    "--evaluated-commit requires an available Git repository"
                )
            current_commit = _resolve_evaluated_commit(
                git_root, evaluated_commit
            )
            _require_worktree_materializes_evaluated_commit(
                context,
                repo_root=resolved_repo,
                git_root=git_root,
                commit=current_commit,
            )

        current_binding = context.review_binding(
            spec_dir,
            repo_root=resolved_repo,
            git_root=git_root or resolved_repo,
            plan_dir=resolved_plan,
            feature_id=resolved_feature,
            script_dir=Path(__file__).resolve().parent,
        )
        if current_commit is not None:
            # Recheck after hashing so a concurrent checkout cannot silently
            # make the binding refer to a different candidate commit.
            _require_worktree_materializes_evaluated_commit(
                context,
                repo_root=resolved_repo,
                git_root=git_root,
                commit=current_commit,
            )
        recorded_binding = data["binding"]
        differing = sorted(
            key
            for key in context.BINDING_KEYS
            if key != "commit_sha"
            and recorded_binding.get(key) != current_binding.get(key)
        )
        if differing:
            raise RuntimeError(
                "review binding is stale or mismatched for: " + ", ".join(differing)
            )
        if current_commit is None:
            current_commit = current_binding.get("commit_sha")
        commit_ok, commit_error = _commit_is_current_or_ancestor(
            recorded=recorded_binding.get("commit_sha"),
            current=current_commit,
            repo_root=git_root or resolved_repo,
        )
        if not commit_ok:
            raise RuntimeError(commit_error or "review commit binding is stale")
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        RuntimeError,
        context.ContextError,
    ) as exc:
        return 2, {
            **base,
            "status": "error",
            "blocking_high": None,
            "message": f"review evidence {summary_path} is not current: {exc}",
        }

    blocking = data["blocking_high"]
    route = data.get("blocking_route")
    if "blocking_route" not in data:
        route = "implement" if blocking > 0 else None
    result = {**base, "blocking_high": blocking, "blocking_route": route,
              "feature_id": data["feature_id"],
              "plan_slug": data["plan_slug"],
              "spec_revision": data["spec_revision"],
              "architecture_package_receipt_sha256":
                  data["binding"]["architecture_package_receipt_sha256"],
              "evaluated_commit": current_commit,
              "binding_status": "current",
              "reviewed_at": data.get("reviewed_at")}
    if blocking > 0:
        result["status"] = "fail"
        result["hard_failures"] = [
            f"{blocking} unresolved confirmed-High review finding(s) "
            f"(correctness/security) — see {spec_dir / 'code-review.md'}"
        ]
        return 1, result
    result["status"] = "pass"
    result["advisory"] = [f"review evidence clean (blocking_high == 0) for "
                          f"{spec_dir}"]
    return 0, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge-bar review-evidence gate: read a spec dir's "
                    "review-summary.json and gate on its blocking_high count.")
    parser.add_argument("spec_dir", metavar="SPEC_DIR",
                        help="spec dir holding review-summary.json "
                             "(docs/plans/<slug>/specs/<id>)")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable verdict on stdout")
    parser.add_argument(
        "--require-blocking-route",
        action="store_true",
        help="require the current blocking_route contract (used by automation)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="repository root (inferred from SPEC_DIR when omitted)",
    )
    parser.add_argument(
        "--plan-dir",
        type=Path,
        help="owning plan directory (defaults to SPEC_DIR/../..)",
    )
    parser.add_argument(
        "--feature",
        help="expected feature id (defaults to the spec-directory basename)",
    )
    parser.add_argument(
        "--git-repo",
        type=Path,
        help=(
            "Git repository used for commit ancestry when SPEC_DIR is a "
            "materialized committed tree"
        ),
    )
    parser.add_argument(
        "--evaluated-commit",
        help="exact full commit id whose materialized artifacts are being gated",
    )
    args = parser.parse_args(argv)

    exit_code, result = evaluate(
        Path(args.spec_dir),
        require_blocking_route=args.require_blocking_route,
        repo_root=args.repo_root,
        plan_dir=args.plan_dir,
        feature_id=args.feature,
        git_repo=args.git_repo,
        evaluated_commit=args.evaluated_commit,
    )
    _emit(result, args.json)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
