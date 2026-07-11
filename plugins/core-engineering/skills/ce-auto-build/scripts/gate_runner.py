#!/usr/bin/env python3
"""gate_runner.py — the agent-agnostic merge bar's INTEGRITY conjunct, executed.

Loads plugins/core-engineering/merge-policy.json (fail-closed), resolves the
selected change class's required_integrity_gates, executes each registered gate
script (spec-lint, test-guard, dep-guard today; later gates register additively
in the policy's `gates` dict) against a target repository, and emits ONE
machine verdict: a single JSON object on stdout (--json) plus exit 0 only when
every REQUIRED gate passes. Stdlib-only, offline, Claude-free — the same bar
gates a PR authored by ANY coding agent, because nothing here needs the agent
that wrote the code.

The bar judges COMMITTED state: --head defaults to HEAD, both refs are
resolved to commit SHAs up front (recorded in the verdict as base_sha /
head_sha), the diff gates compare committed refs, and {spec_dir} gates run
against spec dirs MATERIALIZED from the head commit via `git archive` — never
the working tree — so neither an untracked toolkit checkout nor an uncommitted
edit (e.g. restoring a broken spec on disk without committing) can influence
the verdict. The one exception is an explicit --spec-dir, which is an operator
override judged as given, on disk. Gates execute as subprocess argv lists —
never shell=True — and their scripts must be policy-declared plugin-relative
paths that resolve INSIDE --plugin-root, or the runner refuses to run (exit 2).

The change class is resolved from the COMMITTED diff when --change-class is
omitted and the policy carries a `class_rules` block: each rule's path globs are
matched against `git diff --name-only <base> <head>`, the first matching rule
wins, else the mandatory `fallback` class (explicit --change-class always wins;
no class_rules -> the fail-safe defaults bar). The verdict records
`change_class_source` (explicit | rule:<index> | fallback | defaults) plus up to
five sample matched paths, so an auditor sees WHY a class (e.g. a two-human bar)
fired. The optional `spec_lint_scope` key ('all' default, or 'changed-plans')
filters the {spec_dir}/{plan_dir} fan-out to dirs the diff touches — under
'changed-plans' an empty fan-out is a vacuous PASS advisory, not a fail-closed
error, so a legacy/broken spec elsewhere (or an empty repo before the first
plan) no longer fails every PR.

WHAT IT DOES NOT PROVE (stated so the verdict is never mistaken for more):
  * Only the INTEGRITY conjunct of the merge bar — traceability held, tests
    were not weakened, no undeclared dependency entered a manifest. It never
    proves test SUFFICIENCY (a weak-but-unweakened suite passes) and never
    proves a dependency EXISTS on a registry (dep-guard's offline half only).
  * Never the VALIDITY conjunct — the human / two-human attestation the policy
    demands is carried in the verdict (`validity_required`) and enforced only
    by the host platform's branch-protection review requirements, never by
    this script.

Exit codes (house contract, same shape the gates themselves use):
    0  PASS  — every REQUIRED gate of the selected class passed (advisory
               findings may exist; they never change the exit code)
    1  FAIL  — at least one required gate failed OR could not run on this
               input (gate exit 2 / timeout / zero spec dirs while spec-lint
               is required) — all fail CLOSED
    2  ERROR — the RUNNER could not run at all: missing/malformed policy,
               unknown --change-class, unresolvable or path-escaping gate
               script, unreadable --repo, usage error, unexpected exception
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


class GateRunnerError(Exception):
    """The runner itself cannot run -> exit 2 (never impersonates a gate FAIL)."""


# The closed placeholder vocabulary a gate's args may reference. This module is
# the SINGLE SOURCE: scripts/check.py (section 14) and tests/test_merge_policy.py
# import these from here (gate_runner is stdlib-only and safely importable — the
# same eval_check→eval_run precedent), so adding a placeholder here updates every
# validator at once and drift is structurally impossible.
#   {head_tree} — a path to the repo tree AS COMMITTED AT head, materialized by
#   this runner; a gate that would otherwise read the mutable working tree (e.g.
#   sca-guard scanning dependency manifests) uses it so the verdict is a pure
#   function of the recorded head SHA.
#   {spec_dir} / {plan_dir} — a gate whose args reference one of these FANS OUT,
#   running once per resolved spec dir (docs/plans/*/specs/*) or plan dir
#   (docs/plans/* holding a plan.json), each materialized from the head commit.
PLACEHOLDERS = {"repo", "base", "head", "spec_dir", "plan_dir", "declared",
                "head_tree"}

# Placeholders whose presence makes a gate fan out over a materialized dir list
# (one run per dir). A gate references at most one — the runner picks the first.
FANOUT_PLACEHOLDERS = ("spec_dir", "plan_dir")

# The closed validity vocabulary. 'none' is deliberately absent — a bar always
# demands a human attestation (the two-conjunct invariant). Single source; see
# the note above.
VALIDITY_VOCAB = {"human", "two-human"}

# The closed spec-lint scope vocabulary (optional top-level policy key
# `spec_lint_scope`, default 'all'). 'changed-plans' filters the {spec_dir} /
# {plan_dir} fan-out to dirs the committed diff touches, so a legacy/broken spec
# elsewhere — or an empty repo before the first plan — no longer fails every PR.
# Single source; check.py §14 and tests/test_merge_policy.py import it.
SPEC_LINT_SCOPE_VOCAB = {"all", "changed-plans"}

PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PLUGIN_ROOT = SCRIPT_DIR.parent / "plugins" / "core-engineering"
DEFAULT_POLICY = DEFAULT_PLUGIN_ROOT / "merge-policy.json"


# --- policy load (fail-closed: any structural violation is a GateRunnerError) -------

def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise GateRunnerError(f"merge-policy: {msg}")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """object_pairs_hook: a duplicated key in a policy object would silently
    last-win — a lax duplicate of a gate/bar replacing the strict definition
    with no diff a reviewer would parse as such. Fail closed instead.
    Single source — scripts/check.py (section 14) imports this hook from here."""
    obj: dict = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(
                f"duplicate key {key!r} — JSON last-one-wins would silently "
                f"replace the earlier definition")
        obj[key] = value
    return obj


def load_policy(policy_path: Path, plugin_root: Path) -> dict:
    """Load + fully validate the policy — the same structural rules check.py
    section 14 enforces on the shipped file, re-applied here because an adopter
    may point --policy at a local override check.py never saw."""
    try:
        raw = policy_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise GateRunnerError(f"cannot read policy {policy_path}: {e}") from e
    try:
        policy = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except ValueError as e:  # JSONDecodeError + the duplicate-key rejection
        raise GateRunnerError(f"policy {policy_path} rejected: {e}") from e

    _require(isinstance(policy, dict), "top level must be a JSON object")
    _require(policy.get("schema_version") == 1, "schema_version must be 1")

    gates = policy.get("gates")
    _require(isinstance(gates, dict) and gates, "'gates' must be a non-empty object")
    plugin_root_resolved = plugin_root.resolve()
    for gate_id, gate in gates.items():
        _require(isinstance(gate, dict), f"gate '{gate_id}' must be an object")
        script = gate.get("script")
        _require(isinstance(script, str) and script,
                 f"gate '{gate_id}': 'script' must be a non-empty string")
        _require(isinstance(gate.get("proves"), str) and gate["proves"],
                 f"gate '{gate_id}': 'proves' must be a non-empty string")
        args = gate.get("args")
        _require(isinstance(args, list) and all(isinstance(a, str) for a in args),
                 f"gate '{gate_id}': 'args' must be a list of strings")
        for arg in args:
            for token in PLACEHOLDER_RE.findall(arg):
                _require(token in PLACEHOLDERS,
                         f"gate '{gate_id}': unknown placeholder {{{token}}} "
                         f"(closed set: {', '.join(sorted(PLACEHOLDERS))})")
        # Path containment: relative, no '..', resolves inside the plugin root.
        script_path = Path(script)
        _require(not script_path.is_absolute(),
                 f"gate '{gate_id}': script path must be relative, got '{script}'")
        _require(".." not in script_path.parts,
                 f"gate '{gate_id}': script path must not contain '..', got '{script}'")
        resolved = (plugin_root / script_path).resolve()
        _require(resolved.is_relative_to(plugin_root_resolved),
                 f"gate '{gate_id}': script '{script}' escapes the plugin root")
        _require(resolved.is_file(),
                 f"gate '{gate_id}': script '{script}' not found under {plugin_root}")

    classes = policy.get("change_classes")
    _require(isinstance(classes, dict) and classes,
             "'change_classes' must be a non-empty object")
    defaults = policy.get("defaults")
    _require(isinstance(defaults, dict), "'defaults' must be an object")

    for bar_name, bar in [("defaults", defaults)] + sorted(classes.items()):
        _require(isinstance(bar, dict), f"bar '{bar_name}' must be an object")
        required = bar.get("required_integrity_gates")
        _require(isinstance(required, list) and required
                 and all(isinstance(g, str) for g in required),
                 f"bar '{bar_name}': 'required_integrity_gates' must be a "
                 f"non-empty list of strings")
        advisory = bar.get("advisory_gates", [])
        _require(isinstance(advisory, list)
                 and all(isinstance(g, str) for g in advisory),
                 f"bar '{bar_name}': 'advisory_gates' must be a list of strings")
        for g in list(required) + list(advisory):
            _require(g in gates, f"bar '{bar_name}': references unregistered gate '{g}'")
        _require(not set(required) & set(advisory),
                 f"bar '{bar_name}': a gate cannot be both required and advisory")
        _require(bar.get("validity") in VALIDITY_VOCAB,
                 f"bar '{bar_name}': validity must be one of "
                 f"{sorted(VALIDITY_VOCAB)} (got {bar.get('validity')!r}) — "
                 f"'none' does not exist by design")

    # Optional cold-start scope (default 'all' — fail-closed stays the
    # out-of-box posture; see SPEC_LINT_SCOPE_VOCAB).
    scope = policy.get("spec_lint_scope", "all")
    _require(scope in SPEC_LINT_SCOPE_VOCAB,
             f"spec_lint_scope must be one of {sorted(SPEC_LINT_SCOPE_VOCAB)} "
             f"(got {scope!r})")

    # Optional path-based classifier. `fallback` is MANDATORY whenever
    # class_rules is present so an unmatched diff can never silently downgrade
    # below an explicit choice; every rule `class` and the `fallback` must name
    # a defined change class (rules only SELECT AMONG validated bars).
    _validate_class_rules(policy.get("class_rules"), classes, _require)

    return policy


def _validate_class_rules(class_rules, classes: dict, require) -> None:
    """Shared structural validation for the optional `class_rules` block.
    `require(cond, msg)` raises (load_policy) or accumulates (check.py §14) — the
    single source both the runner and check.py §14 call so the rule can never
    drift between them."""
    if class_rules is None:
        return
    require(isinstance(class_rules, dict), "'class_rules' must be an object")
    if not isinstance(class_rules, dict):
        return
    fallback = class_rules.get("fallback")
    require(isinstance(fallback, str) and fallback in classes,
            f"class_rules.fallback must name a change class "
            f"(one of {sorted(classes)}), got {fallback!r}")
    rules = class_rules.get("rules")
    require(isinstance(rules, list),
            "class_rules.rules must be a list")
    if not isinstance(rules, list):
        return
    for i, rule in enumerate(rules):
        require(isinstance(rule, dict),
                f"class_rules.rules[{i}] must be an object")
        if not isinstance(rule, dict):
            continue
        require(isinstance(rule.get("class"), str) and rule.get("class") in classes,
                f"class_rules.rules[{i}].class must name a change class "
                f"(one of {sorted(classes)}), got {rule.get('class')!r}")
        paths = rule.get("paths")
        require(isinstance(paths, list) and bool(paths)
                and all(isinstance(p, str) and p for p in paths),
                f"class_rules.rules[{i}].paths must be a non-empty list of "
                f"non-empty strings")


def select_bar(policy: dict, change_class: str | None) -> tuple[str, dict]:
    if change_class is None:
        return "defaults", policy["defaults"]
    bar = policy["change_classes"].get(change_class)
    if bar is None:
        raise GateRunnerError(
            f"unknown --change-class '{change_class}' — policy defines: "
            f"{', '.join(sorted(policy['change_classes']))} (or omit the flag "
            f"for the fail-safe defaults bar)")
    return change_class, bar


# --- committed-state resolution --------------------------------------------------------

def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, timeout=60)
    except FileNotFoundError as e:
        raise GateRunnerError("git is not on PATH — the bar judges committed "
                              "state and cannot run without git") from e
    except subprocess.TimeoutExpired as e:
        raise GateRunnerError(f"git {' '.join(args[:2])} timed out in {repo}") from e


def resolve_commit(repo: Path, ref: str, flag: str) -> str:
    """Pin a user-supplied ref to the commit SHA it names right now, so the
    verdict records exactly what was judged (audit evidence, not a moving ref)."""
    proc = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if proc.returncode != 0:
        raise GateRunnerError(
            f"{flag} {ref!r} does not resolve to a commit in {repo}: "
            f"{proc.stderr.decode(errors='replace').strip() or 'unknown ref'}")
    return proc.stdout.decode().strip()


def resolve_spec_dirs(repo: Path, explicit: list[str]) -> list[Path]:
    """Explicit --spec-dir paths only — the operator override, judged as given."""
    return [Path(d) if Path(d).is_absolute() else repo / d for d in explicit]


def _materialize_committed_tree(repo: Path, tree_ish: str, dest: Path) -> Path:
    """Check out the tree at `tree_ish` into `dest` via a SCRATCH index, return
    `dest`. Deliberately NOT `git archive`: archive applies `.gitattributes
    export-ignore`, so a committed file carrying that attribute would be silently
    dropped from the materialized tree — hiding a manifest from sca-guard or a
    spec from spec-lint while the file is plainly in the commit. `checkout-index`
    does not apply export-ignore, so the materialized tree is the TRUE committed
    content. It also writes real files (no tar member to sanitize), and an empty
    tree yields an empty `dest` rather than an error. The scratch index leaves
    the repo's real index untouched."""
    dest.mkdir(parents=True, exist_ok=True)
    scratch_index = str(dest) + ".scratch-index"
    env = dict(os.environ, GIT_INDEX_FILE=scratch_index)
    try:
        read = subprocess.run(
            ["git", "-C", str(repo), "read-tree", tree_ish],
            capture_output=True, env=env, timeout=60)
        if read.returncode != 0:
            raise GateRunnerError(
                f"git read-tree {tree_ish} failed: "
                f"{read.stderr.decode(errors='replace').strip()}")
        checkout = subprocess.run(
            ["git", "-C", str(repo), "checkout-index", "--all", "--force",
             f"--prefix={dest}{os.sep}"],
            capture_output=True, env=env, timeout=120)
        if checkout.returncode != 0:
            raise GateRunnerError(
                f"git checkout-index at {tree_ish} failed: "
                f"{checkout.stderr.decode(errors='replace').strip()}")
    finally:
        try:
            Path(scratch_index).unlink()
        except OSError:
            pass
    return dest


def materialize_head_tree(repo: Path, head_sha: str, workdir: Path) -> Path:
    """Materialize the FULL repo tree AS COMMITTED AT head into workdir and
    return its root. A gate that would otherwise scan the mutable working tree
    (e.g. sca-guard reading dependency manifests) runs against this instead, so
    an uncommitted edit cannot change the verdict for a recorded head SHA — the
    reproducible-from-its-SHAs guarantee the merge-license will sign."""
    return _materialize_committed_tree(repo, head_sha, workdir / "head-tree")


def committed_spec_dirs(tree_root: Path) -> list[Path]:
    """Spec dirs under a materialized committed tree — the {spec_dir} gate
    inputs, judged from the head COMMIT, never the working tree. A spec restored
    (or broken) on disk without committing is invisible to the bar."""
    return sorted(
        d for d in tree_root.glob("docs/plans/*/specs/*")
        # ce-spec.md is the canonical spec artifact name; legacy spec.md accepted.
        if d.is_dir() and ((d / "ce-spec.md").is_file() or (d / "spec.md").is_file())
    )


def committed_plan_dirs(tree_root: Path) -> list[Path]:
    """Plan dirs under a materialized committed tree — the {plan_dir} gate
    inputs (docs/plans/<slug> holding a plan.json), judged from the head COMMIT.
    A plan.json restored (or broken) on disk without committing is invisible."""
    return sorted(
        d for d in tree_root.glob("docs/plans/*")
        if d.is_dir() and (d / "plan.json").is_file()
    )


def changed_paths(repo: Path, base_sha: str, head_sha: str) -> list[str]:
    """Repo-relative POSIX paths that differ between the two committed trees
    (two-dot `git diff --name-only <base> <head>` — the same diff semantics
    test-guard/dep-guard use), so path classification and changed-plans scoping
    are pure functions of the recorded SHAs, never the working tree."""
    proc = _git(repo, "diff", "--name-only", base_sha, head_sha)
    if proc.returncode != 0:
        raise GateRunnerError(
            f"git diff {base_sha[:12]}..{head_sha[:12]} failed in {repo}: "
            f"{proc.stderr.decode(errors='replace').strip() or 'unknown error'}")
    return [ln for ln in proc.stdout.decode(errors="replace").splitlines() if ln]


def _glob_to_regex(glob: str) -> str:
    """Translate a path glob to an anchored regex. Stdlib `re` only — NO
    third-party glob lib (the portability guarantee). Semantics: `**` matches
    across path separators (`**/` also matches zero leading segments), a single
    `*` matches within one segment (never `/`), `?` matches one non-`/` char,
    everything else is literal. Anchored with `^`/`\\Z` (no trailing-newline
    `$` surprise; committed paths have no newlines anyway)."""
    parts: list[str] = ["^"]
    i, n = 0, len(glob)
    while i < n:
        c = glob[i]
        if c == "*":
            j = i
            while j < n and glob[j] == "*":
                j += 1
            if j - i >= 2:  # '**' — spans path separators
                if j < n and glob[j] == "/":
                    parts.append("(?:.*/)?")  # '**/' also matches zero segments
                    j += 1
                else:
                    parts.append(".*")
                i = j
            else:  # single '*' — within one segment
                parts.append("[^/]*")
                i = j
        elif c == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(c))
            i += 1
    parts.append(r"\Z")
    return "".join(parts)


def _dirs_touched_by_diff(dirs: list[Path], tree_root: Path,
                          changed: list[str]) -> list[Path]:
    """Filter materialized fan-out dirs to those the committed diff touches (the
    `changed-plans` scope): a spec/plan dir whose repo-relative prefix contains
    no changed path is out of scope for this PR."""
    kept: list[Path] = []
    for d in dirs:
        rel = d.relative_to(tree_root).as_posix()
        prefix = rel + "/"
        if any(p == rel or p.startswith(prefix) for p in changed):
            kept.append(d)
    return kept


def classify_change(policy: dict, explicit: str | None,
                    changed: list[str]) -> tuple[str | None, str, list[str]]:
    """Resolve the change class + its provenance for the verdict. Returns
    (class_selector, source, matched_paths) — class_selector feeds select_bar
    (None -> the fail-safe defaults bar). Precedence:
      * an explicit --change-class ALWAYS wins (source 'explicit');
      * else, if the policy carries class_rules, match the committed diff against
        each rule's globs IN ORDER — the first rule any of whose globs matches
        any changed path wins (source 'rule:<index>', up to 5 sample matched
        paths recorded so an auditor sees WHY the class fired), else the
        mandatory 'fallback' class (source 'fallback');
      * else no class is selected and the fail-safe defaults bar applies
        (source 'defaults')."""
    if explicit is not None:
        return explicit, "explicit", []
    class_rules = policy.get("class_rules")
    if not class_rules:
        return None, "defaults", []
    for idx, rule in enumerate(class_rules["rules"]):
        regexes = [re.compile(_glob_to_regex(g)) for g in rule["paths"]]
        matched = [p for p in changed if any(rx.match(p) for rx in regexes)]
        if matched:
            return rule["class"], f"rule:{idx}", matched[:5]
    return class_rules["fallback"], "fallback", []


def bar_references(policy: dict, bar: dict, placeholder: str) -> bool:
    """True if any gate the bar runs (required or advisory) references the given
    {placeholder} in its args — used to materialize head state only on demand."""
    token = "{" + placeholder + "}"
    gate_ids = list(bar["required_integrity_gates"]) + list(bar.get("advisory_gates", []))
    return any(token in a for gid in gate_ids for a in policy["gates"][gid]["args"])


# --- gate execution ------------------------------------------------------------------


def substitute(args: list[str], values: dict[str, str]) -> list[str]:
    out = []
    for arg in args:
        def repl(m: re.Match) -> str:
            return values[m.group(1)]
        out.append(PLACEHOLDER_RE.sub(repl, arg))
    return out


def run_gate_once(script: Path, args: list[str], repo: Path,
                  timeout: float) -> dict:
    """One subprocess execution -> a run record {args, exit_code, status, detail}."""
    try:
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True, text=True, timeout=timeout, cwd=str(repo),
        )
        exit_code: int | None = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired:
        return {"args": args, "exit_code": None, "status": "error",
                "detail": None,
                "raw_output": f"timed out after {timeout}s"}
    status = {0: "pass", 1: "fail"}.get(exit_code, "error")
    try:
        detail = json.loads(stdout)
    except ValueError:
        detail = None
    if not isinstance(detail, dict):  # a bare JSON scalar/array is not a verdict
        detail = None
    record = {"args": args, "exit_code": exit_code, "status": status,
              "detail": detail}
    # Cross-check the exit code against the gate's own JSON verdict: a wrapper
    # that prints {"status": "fail", ...} but forgets sys.exit(1) must fail
    # CLOSED (as an error run), never be scored pass on exit code alone.
    claimed = detail.get("status") if detail is not None else None
    if claimed in ("pass", "fail", "error") and claimed != status:
        record["status"] = "error"
        record["contradiction"] = (
            f"exit code {exit_code} says {status!r} but the gate's own JSON "
            f"verdict says {claimed!r} — failing closed")
    # A gate that emits hard_failures but exits 0 (no status field to catch it
    # above) would otherwise be laundered to PASS on its exit code. Non-empty
    # hard_failures contradicts a pass — fail closed as an error run.
    elif status == "pass" and detail is not None and detail.get("hard_failures"):
        record["status"] = "error"
        record["contradiction"] = (
            f"exit code {exit_code} says pass but the gate reported "
            f"{len(detail['hard_failures'])} hard failure(s) — failing closed")
    if detail is None:
        record["raw_output"] = (stdout or stderr).strip()
    return record


def gate_failure_lines(gate_id: str, runs: list[dict]) -> list[str]:
    """Human-evidence lines for a gate's failing/erroring runs."""
    lines: list[str] = []
    for run in runs:
        detail = run.get("detail")
        if run["status"] == "error":
            reason = (run.get("contradiction")
                      or (detail or {}).get("message")
                      or run.get("raw_output") or "no output")
            lines.append(f"{gate_id}: could not run (exit "
                         f"{run['exit_code']}): {reason}")
        elif run["status"] == "fail":
            hard = (detail or {}).get("hard_failures") or []
            if hard:
                lines.extend(f"{gate_id}: {h}" for h in hard)
            else:
                lines.append(f"{gate_id}: FAIL "
                             f"({run.get('raw_output', 'no detail')})")
    return lines


def gate_advisory_lines(gate_id: str, runs: list[dict]) -> list[str]:
    lines: list[str] = []
    for run in runs:
        for a in ((run.get("detail") or {}).get("advisory") or []):
            lines.append(f"{gate_id}: {a}")
    return lines


# Human-facing text for the two ends of an empty fan-out (no matching dir).
# 'all' scope fails CLOSED (an error run); 'changed-plans' scope records a
# vacuous PASS with this advisory instead, so a legacy/broken spec elsewhere —
# or an empty repo before the first plan — no longer fails every PR (by choice).
_EMPTY_FANOUT_ERROR = {
    "spec_dir": "no spec dirs found under docs/plans/*/specs/ as committed at "
                "{head} — did the layout change? pass --spec-dir",
    "plan_dir": "no plan dirs found under docs/plans/* as committed at {head} "
                "— did the layout change?",
}
_EMPTY_FANOUT_VACUOUS = {
    "spec_dir": "no spec artifacts in this change — spec-lint vacuously holds "
                "under spec_lint_scope=changed-plans",
    "plan_dir": "no plan artifacts in this change — plan-lint vacuously holds "
                "under spec_lint_scope=changed-plans",
}


def _empty_fanout_run(gate_args: list[str], placeholder: str, head_ref: str,
                      vacuous_ok: bool) -> dict:
    """The single synthetic run record for a fan-out gate that matched no dirs:
    a vacuous PASS+advisory under changed-plans scope, else a fail-closed error."""
    if vacuous_ok:
        return {"args": gate_args, "exit_code": 0, "status": "pass",
                "detail": {"status": "pass",
                           "advisory": [_EMPTY_FANOUT_VACUOUS[placeholder]]},
                "raw_output": None}
    return {"args": gate_args, "exit_code": None, "status": "error",
            "detail": None,
            "raw_output": _EMPTY_FANOUT_ERROR[placeholder].format(head=head_ref)}


def execute_bar(policy: dict, bar: dict, repo: Path, plugin_root: Path,
                values: dict[str, str], fanout_dirs: dict[str, list[Path]],
                timeout: float, vacuous_ok: bool = False
                ) -> tuple[list[dict], list[str], list[str]]:
    """Run every required + advisory gate of the bar. A gate whose args
    reference a fan-out placeholder ({spec_dir} or {plan_dir}) runs once per
    resolved dir of that kind; `fanout_dirs` maps each placeholder to its dir
    list. `vacuous_ok` (changed-plans scope) turns an empty fan-out into a
    vacuous PASS advisory rather than a fail-closed error.

    Returns (gate_records, hard_failures, advisory_lines)."""
    gates = policy["gates"]
    records: list[dict] = []
    hard_failures: list[str] = []
    advisory: list[str] = []

    plan = ([(g, "required") for g in bar["required_integrity_gates"]]
            + [(g, "advisory") for g in bar.get("advisory_gates", [])])
    for gate_id, disposition in plan:
        gate = gates[gate_id]
        script = (plugin_root / gate["script"]).resolve()
        fan_ph = next((ph for ph in FANOUT_PLACEHOLDERS
                       if any("{" + ph + "}" in a for a in gate["args"])), None)

        runs: list[dict] = []
        if fan_ph is not None:
            dirs = fanout_dirs.get(fan_ph, [])
            if not dirs:
                runs.append(_empty_fanout_run(
                    gate["args"], fan_ph, values.get("head", "HEAD"),
                    vacuous_ok))
            for d in dirs:
                run_values = dict(values, **{fan_ph: str(d)})
                runs.append(run_gate_once(
                    script, substitute(gate["args"], run_values), repo, timeout))
        else:
            runs.append(run_gate_once(
                script, substitute(gate["args"], values), repo, timeout))

        gate_status = "pass"
        if any(r["status"] == "error" for r in runs):
            gate_status = "error"
        elif any(r["status"] == "fail" for r in runs):
            gate_status = "fail"

        records.append({
            "id": gate_id,
            "disposition": disposition,
            "status": gate_status,
            "proves": gate["proves"],
            "runs": runs,
        })
        lines = gate_failure_lines(gate_id, runs)
        if disposition == "required":
            hard_failures.extend(lines)   # fail OR error -> fail closed
        else:
            advisory.extend(lines)        # advisory findings never gate
        advisory.extend(gate_advisory_lines(gate_id, runs))

    return records, hard_failures, advisory


# --- verdict emission ----------------------------------------------------------------

# ANSI SGR codes for the HUMAN emit path only. Color is presentation, never
# content: every painted line is the byte-identical prose wrapped in escape
# codes, so committed run-records that quote today's uncolored lines verbatim
# still match whenever color is off (non-TTY, NO_COLOR, or --no-color). The
# --json verdict never carries ANSI.
_SGR_BOLD_GREEN = "1;32"   # PASS headline
_SGR_BOLD_RED = "1;31"     # FAIL headline
_SGR_RED = "31"            # hard-failure detail lines
_SGR_YELLOW = "33"         # advisory (non-blocking) lines


def _paint(text: str, sgr: str, color: bool) -> str:
    return f"\x1b[{sgr}m{text}\x1b[0m" if color else text


def color_enabled(no_color_flag: bool) -> bool:
    """Human-path color gate: on only for a TTY stdout, off when the adopter
    sets NO_COLOR (https://no-color.org/) or passes --no-color."""
    if no_color_flag or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def emit(verdict: dict, as_json: bool, color: bool = False) -> None:
    if as_json:
        print(json.dumps(verdict, indent=2))
        return
    headline_sgr = _SGR_BOLD_GREEN if verdict["status"] == "pass" else _SGR_BOLD_RED
    print(_paint(f"merge bar [{verdict['change_class']}]: integrity conjunct "
                 f"{verdict['status'].upper()}", headline_sgr, color))
    print(f"  base {verdict['base']} ({verdict['base_sha'][:12]}) -> "
          f"head {verdict['head']} ({verdict['head_sha'][:12]}) in {verdict['repo']}")
    source = verdict.get("change_class_source")
    if source and source != "explicit":
        line = f"  class {verdict['change_class']} selected via {source}"
        sample = verdict.get("change_class_matched_paths") or []
        if sample:
            line += f" (e.g. {', '.join(sample[:3])})"
        print(line)
    policy = verdict["policy"]
    origin = "shipped default" if policy["shipped_default"] else "LOCAL OVERRIDE"
    print(f"  policy: {policy['path']} ({origin}, sha256 {policy['sha256'][:12]})")
    for gate in verdict["gates"]:
        print(f"  {gate['id']} ({gate['disposition']}): {gate['status']} — "
              f"proves: {gate['proves']}")
    if verdict["hard_failures"]:
        print("\n" + _paint(
            f"  FAIL — {len(verdict['hard_failures'])} hard failure(s):",
            _SGR_RED, color))
        for line in verdict["hard_failures"]:
            print(_paint(f"    x {line}", _SGR_RED, color))
    if verdict["advisory"]:
        print("\n" + _paint(
            f"  advisory ({len(verdict['advisory'])} — review, non-blocking):",
            _SGR_YELLOW, color))
        for line in verdict["advisory"]:
            print(_paint(f"    ! {line}", _SGR_YELLOW, color))
    print(f"\n  {verdict['summary']}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Agent-agnostic merge bar: run a change class's required "
                    "integrity gates against a repo and emit one verdict.")
    p.add_argument("--repo", required=True, metavar="PATH",
                   help="target repository root (the adopter repo, not this toolkit)")
    p.add_argument("--base", required=True, metavar="REF",
                   help="committed baseline ref the diff gates compare against")
    p.add_argument("--change-class", metavar="NAME",
                   help="policy change class; omitted -> the policy's fail-safe "
                        "'defaults' bar")
    p.add_argument("--head", default="HEAD", metavar="REF",
                   help="head ref (default: HEAD — the bar judges committed state)")
    p.add_argument("--policy", default=str(DEFAULT_POLICY), metavar="PATH",
                   help="merge-policy.json (default: the toolkit's shipped policy)")
    p.add_argument("--plugin-root", default=str(DEFAULT_PLUGIN_ROOT), metavar="PATH",
                   help="root the policy's plugin-relative gate scripts resolve "
                        "against (default: the toolkit's plugins/core-engineering)")
    p.add_argument("--spec-dir", action="append", default=[], metavar="PATH",
                   help="spec dir for {spec_dir} gates, judged AS GIVEN on disk "
                        "(repeatable operator override; default: spec dirs under "
                        "docs/plans/*/specs/ materialized from the head COMMIT)")
    p.add_argument("--declared", default="", metavar="N1,N2",
                   help="deps declared/verified for dep-guard (default '' — "
                        "fail-safe: every new dep is undeclared)")
    p.add_argument("--gate-timeout", type=float, default=120, metavar="SECONDS",
                   help="per-gate-run subprocess timeout (default: 120)")
    p.add_argument("--json", action="store_true",
                   help="print the single machine verdict object to stdout")
    p.add_argument("--no-color", action="store_true",
                   help="disable ANSI color in the human-readable verdict "
                        "(color is TTY-only anyway; NO_COLOR is also honored; "
                        "--json output never carries color)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo = Path(args.repo).resolve()
        if not repo.is_dir():
            raise GateRunnerError(f"--repo {args.repo} is not a readable directory")
        plugin_root = Path(args.plugin_root)
        policy_path = Path(args.policy).resolve()
        policy = load_policy(policy_path, plugin_root)
        # Provenance: WHICH bar produced this verdict must be auditable from
        # the verdict alone — a local --policy override is otherwise
        # indistinguishable from the shipped bar to a consuming host.
        policy_sha256 = hashlib.sha256(policy_path.read_bytes()).hexdigest()

        # Pin refs to SHAs: the verdict must be reproducible from what it records,
        # and classification + changed-plans scoping are pure functions of them.
        base_sha = resolve_commit(repo, args.base, "--base")
        head_sha = resolve_commit(repo, args.head, "--head")

        scope = policy.get("spec_lint_scope", "all")
        # Compute the committed diff ONCE, and only when something needs it: the
        # path classifier (policy carries class_rules and no explicit class was
        # named) or the changed-plans fan-out scope.
        need_diff = ((policy.get("class_rules") is not None
                      and args.change_class is None)
                     or scope == "changed-plans")
        changed = changed_paths(repo, base_sha, head_sha) if need_diff else []

        class_selector, class_source, matched_paths = classify_change(
            policy, args.change_class, changed)
        class_name, bar = select_bar(policy, class_selector)

        values = {"repo": str(repo), "base": base_sha, "head": head_sha,
                  "declared": args.declared}
        with tempfile.TemporaryDirectory(prefix="gate-runner-specs-") as workdir:
            # Materialize the committed head tree ONCE (checkout-index, not
            # archive — see _materialize_committed_tree), then derive the spec
            # dirs, plan dirs, and the {head_tree} value from it so no gate reads
            # the working tree. An explicit --spec-dir override is judged as
            # given on disk; the tree is materialized only if the selected bar
            # references a committed-state placeholder.
            needs_tree = (
                bar_references(policy, bar, "head_tree")
                or bar_references(policy, bar, "plan_dir")
                or (bar_references(policy, bar, "spec_dir") and not args.spec_dir))
            tree_root = (materialize_head_tree(repo, head_sha, Path(workdir))
                         if needs_tree else None)

            fanout_dirs: dict[str, list[Path]] = {}
            if bar_references(policy, bar, "spec_dir"):
                if args.spec_dir:
                    fanout_dirs["spec_dir"] = resolve_spec_dirs(repo, args.spec_dir)
                else:
                    dirs = committed_spec_dirs(tree_root)
                    if scope == "changed-plans":
                        dirs = _dirs_touched_by_diff(dirs, tree_root, changed)
                    fanout_dirs["spec_dir"] = dirs
            if bar_references(policy, bar, "plan_dir"):
                dirs = committed_plan_dirs(tree_root)
                if scope == "changed-plans":
                    dirs = _dirs_touched_by_diff(dirs, tree_root, changed)
                fanout_dirs["plan_dir"] = dirs
            if bar_references(policy, bar, "head_tree"):
                values["head_tree"] = str(tree_root)

            records, hard_failures, advisory = execute_bar(
                policy, bar, repo, plugin_root, values, fanout_dirs,
                args.gate_timeout, vacuous_ok=(scope == "changed-plans"))

        required_total = len(bar["required_integrity_gates"])
        required_passed = sum(1 for g in records
                              if g["disposition"] == "required"
                              and g["status"] == "pass")
        status = "pass" if not hard_failures else "fail"
        conjunct = "holds" if status == "pass" else "FAILED"
        verdict = {
            "status": status,
            "schema_version": 1,
            "change_class": class_name,
            "change_class_source": class_source,
            "change_class_matched_paths": matched_paths,
            "validity_required": bar["validity"],
            "base": args.base,
            "head": args.head,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "repo": str(repo),
            "policy": {
                "path": str(policy_path),
                "sha256": policy_sha256,
                "shipped_default": policy_path == DEFAULT_POLICY.resolve(),
            },
            "gates": records,
            "hard_failures": hard_failures,
            "advisory": advisory,
            "summary": (
                f"{required_passed}/{required_total} required gates pass — "
                f"integrity conjunct {conjunct}; validity conjunct "
                f"({bar['validity']}) is attested via branch protection, "
                f"never by this script"),
        }
        emit(verdict, args.json,
             color=(not args.json) and color_enabled(args.no_color))
        return 0 if status == "pass" else 1
    except GateRunnerError as e:
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            print(f"gate-runner: ERROR — could not run: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — a runner crash must exit 2, never
        # exit 1 and impersonate a gate FAIL to a gating caller.
        if args.json:
            print(json.dumps({"status": "error",
                              "message": f"unexpected: {type(e).__name__}: {e}"}))
        else:
            print(f"gate-runner: ERROR — unexpected failure "
                  f"({type(e).__name__}): {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
