"""Tests for ce-architecture's deterministic package/staleness contract."""

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO
    / "plugins/core-engineering/skills/ce-architecture/scripts/architecture-lint.py"
)
SELECTION_SCRIPT = (
    REPO
    / "plugins/core-engineering/skills/ce-architecture/scripts/architecture-selection-lint.py"
)
V2_FIXTURE = REPO / "tests/architecture_v2_fixture.py"
SELECTION_FIXTURE = REPO / "tests/test_architecture_selection_lint.py"
ARTIFACT_TEMPLATE = (
    REPO / "plugins/core-engineering/skills/ce-architecture/artifact-template.md"
)

_spec = importlib.util.spec_from_file_location("architecture_lint_mod", SCRIPT)
al = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(al)

_selection_spec = importlib.util.spec_from_file_location(
    "architecture_selection_lint_mod", SELECTION_SCRIPT
)
sl = importlib.util.module_from_spec(_selection_spec)
_selection_spec.loader.exec_module(sl)
_v2_spec = importlib.util.spec_from_file_location(
    "architecture_v2_fixture_for_lint", V2_FIXTURE
)
v2 = importlib.util.module_from_spec(_v2_spec)
_v2_spec.loader.exec_module(v2)
_selection_fixture_spec = importlib.util.spec_from_file_location(
    "architecture_selection_fixture_for_lint", SELECTION_FIXTURE
)
selection_fixture = importlib.util.module_from_spec(_selection_fixture_spec)
_selection_fixture_spec.loader.exec_module(selection_fixture)


def _legacy_check(*args, **kwargs):
    """Keep v1 tests explicit and migration-only."""
    kwargs["allow_legacy_v1"] = True
    return al.check_package(*args, **kwargs)


OVERVIEW = """# Solution Architecture: team-invitations

> Status: approved
> Source plan: `docs/plans/team-invitations/` revision 2
> Architecture revision: 1
> Authority: architecture-baseline-only; no security acceptance, compliance attestation, release approval, or deployment authority.

## Executive Summary
Two planned features form one invitation system.
## Scope and Non-Goals
Plan scope only.
## Architecture Drivers
| Driver | Evidence state | Source | Architecture consequence |
|---|---|---|---|
| Reuse the existing runtime | recorded | `docs/adr/0001-existing-runtime.md` | Keep one application boundary. |
## Selected Direction Realization
| Exploration | Option | Selection binding | Realization summary | Evidence state | Evidence |
|---|---|---|---|---|---|
| AEX-test | A01 | direction-selected / SELECTED-OPTION-HASH | Preserve the selected single-runtime direction. | recorded | `docs/plans/team-invitations/architecture-selection.json` |
## Architecture Overview
C-001 calls C-002.
## Decisions and Rationale
| Decision | Summary | Evidence state | Status | ADR | Affected features | Evidence |
|---|---|---|---|---|---|---|
| D-001 | Reuse existing runtime | recorded | accepted | `docs/adr/0001-existing-runtime.md` | 01-roles-authz-foundation, 02-team-invitations | `docs/adr/0001-existing-runtime.md` |
## Feature Traceability
| Feature | Components | Data entities | Integration flows | Quality scenarios | Disposition | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|
| 01-roles-authz-foundation | C-002 | DATA-001 | IF-001 | QA-001 | cross-feature | inferred | `docs/plans/team-invitations/features/01-roles-authz-foundation.md` |
| 02-team-invitations | C-001, C-002 | DATA-001, DATA-002 | IF-001 | QA-001 | cross-feature | inferred | `docs/plans/team-invitations/features/02-team-invitations.md` |
## Assumptions and Coverage Gaps
None.
## Risks and Mitigations
| Risk | Statement | Evidence state | Owner | Mitigation | Evidence |
|---|---|---|---|---|---|
| AR-001 | Shared runtime changes can affect both features | observed | architecture owner | Verify both features after runtime changes | `src/application.py` |
## Validation Strategy
Run feature verification and the performance probe.
## Evidence Boundary
Only the source hashes in architecture.json were checked.
"""

VIEWS = """# Architecture Views: team-invitations

## System Context
| ID | Element | Kind | Responsibility | Evidence state | Evidence |
|---|---|---|---|---|---|
| C-001 | Invitation API | service | Accept invitation commands | recorded | `feature-plan.md` |
| C-002 | Membership store | data-store | Persist membership state | recorded | `feature-plan.md` |
## Runtime / Container View
| Component | Name | Kind | Responsibilities | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|
| C-001 | Invitation API | service | Accept invitation commands | 02-team-invitations | recorded | `docs/plans/team-invitations/feature-plan.md` |
| C-002 | Membership store | data-store | Persist membership state | 01-roles-authz-foundation, 02-team-invitations | recorded | `docs/plans/team-invitations/feature-plan.md` |

| Relationship | From | To | Interaction | Evidence state | Evidence |
|---|---|---|---|---|---|
| R-001 | C-001 | C-002 | Write membership state | recorded | `docs/plans/team-invitations/feature-plan.md` |
## Deployment View
| Node | Name | Environment | Name selector | Environment selector | Evidence state | Evidence |
|---|---|---|---|---|---|---|
| N-001 | Application runtime | production | docs/plans/team-invitations/shared-context.md :: Existing Python service | docs/plans/team-invitations/shared-context.md :: Existing Python service | recorded | `docs/plans/team-invitations/shared-context.md` |

| Component | Deployed to | Evidence state | Evidence |
|---|---|---|---|
| C-001 | N-001 | recorded | `docs/plans/team-invitations/shared-context.md` |
| C-002 | N-001 | recorded | `docs/plans/team-invitations/shared-context.md` |
## View Coverage Gaps
None.
"""

DATA = """# Data and Integrations: team-invitations

## Data Ownership and Lifecycle
| ID | Durable noun / data set | Data class | Source of truth | Writers | Readers | Retain / Export / Erase | Plan trace | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| DATA-001 | membership | personal | C-002 | C-001, C-002 | C-001, C-002 | owned-by:01-roles-authz-foundation / owned-by:01-roles-authz-foundation / owned-by:01-roles-authz-foundation | feature-plan.md#durable-state-closure | 01-roles-authz-foundation, 02-team-invitations | recorded | `docs/plans/team-invitations/feature-plan.md` |
| DATA-002 | invitation | personal | C-002 | C-001 | C-001 | owned-by:02-team-invitations / owned-by:02-team-invitations / owned-by:02-team-invitations | feature-plan.md#durable-state-closure | 02-team-invitations | recorded | `docs/plans/team-invitations/feature-plan.md` |
## Integration Flows
| Flow | Producer | Consumer | Protocol / medium | Data | Data entities | Source of truth | Failure behavior | Contract refs | Plan trace | Features | Evidence state | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IF-001 | C-001 | C-002 | in-process | invitation acceptance | DATA-001, DATA-002 | C-002 | Fail explicitly | TZ-001, IC-001 | feature-plan.md#dependency-flow | 01-roles-authz-foundation, 02-team-invitations | recorded | `docs/plans/team-invitations/interaction-contract.md` |
## Flow Details
### IF-001 — Accept invitation
## Consistency, Idempotency, and Concurrency
IC-001 requires idempotency.
## Security and Privacy Re-Projection
TZ-001 remains plan-owned.
## Data and Integration Gaps
None.
"""

QUALITY = """# Quality Attributes: team-invitations

## Quality Scenarios
| ID | Attribute | Evidence state | Source | Stimulus | Environment | Response | Target | Tactic | Verification | Features |
|---|---|---|---|---|---|---|---|---|---|---|
| QA-001 | latency | recorded | `docs/briefs/team-invitations.md` | Invitation acceptance | normal load | Return a result | p95 under 500 ms | Bound the synchronous path | `/core-engineering:ce-probe-perf` | 01-roles-authz-foundation, 02-team-invitations |
## QA-001 — Invitation response latency
## Operability and Observability
Use the existing application telemetry.
## Capacity, Resilience, and Recovery
No new recovery model is introduced.
## Cost and Complexity Trade-Offs
Reuse the existing runtime.
## Quality Coverage Gaps
None.
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _selection_option(
    option_id: str,
    hard_constraints: list[dict],
    score: int,
) -> dict:
    option = {
        "option_id": option_id,
        "title": f"Direction {option_id}",
        "summary": f"Complete invitation-system direction {option_id}.",
        "responsibilities_and_boundaries": [
            "The application owns invitation orchestration and the membership store owns membership state."
        ],
        "runtime_and_deployment": [
            "Reuse the existing regional application runtime and managed store."
        ],
        "data_ownership": [
            "The application owns invitations and the membership store owns memberships."
        ],
        "integrations_and_failure": [
            "The in-process membership write fails explicitly and is idempotent."
        ],
        "trust_residency_and_security": [
            "Invitation and membership data remain inside the existing trust boundary."
        ],
        "quality_tactics": [
            "Bound the synchronous acceptance path and retain existing telemetry."
        ],
        "migration_and_evolution": [
            "Introduce invitation state additively before enabling acceptance."
        ],
        "capability_implications": [
            "Supports invitation creation, delivery, and acceptance."
        ],
        "assumptions": ["The existing runtime remains available."],
        "irreversible_commitments": [
            "No irreversible commitment is made before the additive cutover."
        ],
        "constraint_verdicts": [
            {
                "constraint_id": constraint["id"],
                "verdict": "pass",
                "basis": f"{option_id} preserves {constraint['statement']}",
            }
            for constraint in hard_constraints
        ],
        "scores": [
            {
                "criterion_id": criterion,
                "score": score,
                "basis": f"{option_id} fit against {criterion}.",
                "evidence_state": "recorded",
                "evidence": ["docs/briefs/team-invitations.md"],
            }
            for criterion in sl.CRITERIA
        ],
        "weighted_score": score,
        "confidence": "high",
        "option_sha256": "",
    }
    option["option_sha256"] = sl.option_hash(option)
    return option


def _write_current_selection(plan_dir: Path, selection: dict) -> None:
    """Write a current selected-direction fixture and its reviewed report."""

    selection["schema_version"] = 2
    report_path = plan_dir / "architecture-options.md"
    _write(report_path, selection_fixture.render_options_report(selection))
    selection["architecture_options_report"] = {
        "schema_version": 1,
        "status": "present",
        "path": "architecture-options.md",
        "sha256": _sha(report_path),
        "reason": None,
    }
    _write(
        plan_dir / "architecture-selection.json",
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n",
    )


def _write_selection(root: Path, plan_dir: Path) -> dict:
    brief = root / "docs/briefs/team-invitations.md"
    sources = [
        {
            "path": "docs/adr/0001-existing-runtime.md",
            "sha256": _sha(root / "docs/adr/0001-existing-runtime.md"),
            "kind": "adr",
        },
        {
            "path": "docs/briefs/team-invitations.md",
            "sha256": _sha(brief),
            "kind": "brief",
        }
    ]
    evaluation_frame = {
        "project_intent": "Add team invitations while preserving existing membership boundaries.",
        "non_goals": ["Replace the application runtime."],
        "decision_owner": {
            "identity_or_role": "Invitation Architecture Owner",
            "authority_basis": (
                "The accepted delivery governance assigns solution-direction "
                "approval to the Invitation Architecture Owner."
            ),
        },
        "architecture_applicability": "required",
        "driver_screen": [
            {
                "id": driver_id,
                "verdict": "positive" if driver_id == "shared-data-ownership-or-migration" else "negative",
                "basis": f"Recorded applicability basis for {driver_id}.",
                "evidence": ["docs/briefs/team-invitations.md"],
            }
            for driver_id in sl.DRIVER_IDS
        ],
        "accepted_decisions": [
            {
                "ref": "docs/adr/0001-existing-runtime.md",
                "summary": "Reuse the existing application runtime.",
            }
        ],
        "material_gaps": [],
        "capabilities": [
            {
                "id": "C01",
                "outcome": "An administrator can invite a teammate.",
                "actors": ["administrator"],
                "data": ["invitation", "membership"],
                "integrations": ["membership store"],
                "observable": "The invitation can be accepted exactly once.",
            }
        ],
        "journeys": [
            {
                "id": "J01",
                "outcome": "An invitee joins a team.",
                "actors": ["administrator", "invitee"],
                "capability_refs": ["C01"],
                "steps": ["Create, deliver, and accept an invitation."],
                "observable": "The invitee becomes a team member.",
            }
        ],
        "quality_attribute_scenarios": [
            {
                "id": "QA01",
                "attribute": "latency",
                "stimulus": "An invitee accepts a valid invitation.",
                "environment": "normal load",
                "response": "Return the acceptance result.",
                "target": "p95 under 500 ms",
                "priority": "must",
                "evidence": ["docs/briefs/team-invitations.md"],
            }
        ],
    }
    criteria = [
        {"id": criterion, "weight": weight, "basis": f"Priority for {criterion}."}
        for criterion, weight in zip(
            sl.CRITERIA,
            (0.25, 0.20, 0.15, 0.15, 0.15, 0.10),
        )
    ]
    hard_constraints = [
        {
            "id": "HC01",
            "statement": "Reuse the accepted existing application runtime.",
            "basis": "Accepted ADR and human-confirmed evaluation frame.",
            "authority": "Architecture owner.",
        }
    ]
    options = [
        _selection_option("A01", hard_constraints, 5),
        _selection_option("A02", hard_constraints, 4),
    ]
    option_set_sha256 = sl.option_set_hash(options, [])
    selected = options[0]
    selection = {
        "schema_version": 2,
        "project_slug": "team-invitations",
        "exploration_id": f"AEX-{option_set_sha256[:12]}",
        "source_capability_revision": 1,
        "source_exploration_attempt": 1,
        "source_input_sha256": "0" * 64,
        "evaluation_frame": evaluation_frame,
        "blocking_decision": None,
        "sources": sources,
        "evidence_fingerprint": sl.canonical_sha256(sources),
        "criteria": criteria,
        "hard_constraints": hard_constraints,
        "options": options,
        "eliminated_options": [],
        "option_set_sha256": option_set_sha256,
        "recommendation": {
            "option_id": selected["option_id"],
            "confidence": "high",
            "sensitivity": "stable",
            "sensitivity_witness": None,
            "basis": "Best evidence-backed fit across the confirmed frame.",
        },
        "selection": {
            "status": "direction-selected",
            "option_id": selected["option_id"],
            "option_sha256": selected["option_sha256"],
            "decided_by": "human",
            "approved_by": "Invitation Architecture Owner",
            "rationale": "Preserve the accepted runtime and strongest requirement fit.",
        },
        "next_owner": "ce-plan",
    }
    selection["source_input_sha256"] = sl.source_input_hash(selection)
    _write_current_selection(plan_dir, selection)
    return selection


def _make_repo(root: Path) -> tuple[Path, dict]:
    plan_dir = root / "docs/plans/team-invitations"
    plan = {
        "project_slug": "team-invitations",
        "status": "planned",
        "plan_revision": 2,
        "plan_tier": "standard",
        "architecture_disposition": {
            "decision": "required",
            "triggers": [
                "shared-data-ownership-or-migration",
                "trust-residency-or-sensitive-boundary",
            ],
            "rationale": "Cross-feature state and authorization shape the plan.",
            "decided_by": "human",
            "convergence": {
                "status": "converged",
                "iteration_count": 1,
                "summary": "The architecture shaping pass confirmed the feature cut.",
                "decision_refs": ["docs/adr/0001-existing-runtime.md"],
            },
        },
        "relates_to": [],
        "features": [
            {
                "id": "01-roles-authz-foundation",
                "file": "features/01-roles-authz-foundation.md",
            },
            {
                "id": "02-team-invitations",
                "file": "features/02-team-invitations.md",
            },
        ],
    }
    _write(
        plan_dir / "feature-plan.md",
        "# Plan\n\n## Journey Map\nInvite and accept.\n\n"
        "## Dependency Flow\n02-team-invitations uses 01-roles-authz-foundation.\n\n"
        "## Durable-State Closure\n"
        "| Noun | Data-class | retain | export | erase |\n"
        "|---|---|---|---|---|\n"
        "| membership | personal | owned-by:01-roles-authz-foundation | owned-by:01-roles-authz-foundation | owned-by:01-roles-authz-foundation |\n"
        "| invitation | personal | owned-by:02-team-invitations | owned-by:02-team-invitations | owned-by:02-team-invitations |\n",
    )
    _write(
        plan_dir / "shared-context.md",
        "# Context\nExisting Python service.\nApplication runtime: production.\n",
    )
    _write(plan_dir / "threat-model.md", "# Threat Model\nTZ-001 public invitation token.\n")
    _write(
        plan_dir / "interaction-contract.md",
        "# Interaction Contract\nIC-001 acceptance is idempotent.\n",
    )
    _write(
        plan_dir / "features/01-roles-authz-foundation.md",
        "# 01-roles-authz-foundation\n",
    )
    _write(
        plan_dir / "features/02-team-invitations.md",
        "# 02-team-invitations\n",
    )
    _write(
        root / "docs/briefs/team-invitations.md",
        "# Brief\nThe invitation response target is p95 under 500 ms.\n",
    )
    _write(
        root / "docs/adr/0001-existing-runtime.md",
        "# Existing runtime\n\nStatus: accepted\n",
    )
    _write(root / "src/application.py", "RUNTIME = 'existing'\n")

    selection = _write_selection(root, plan_dir)
    selected = selection["options"][0]
    plan["architecture_disposition"]["direction"] = {
        "status": selection["selection"]["status"],
        "artifact": "architecture-selection.json",
        "artifact_sha256": _sha(plan_dir / "architecture-selection.json"),
        "exploration_id": selection["exploration_id"],
        "selected_option_id": selected["option_id"],
        "selected_option_sha256": selected["option_sha256"],
        "decided_by": "human",
        "summary": "Reuse the existing runtime with explicit invitation ownership.",
    }
    _write(plan_dir / "plan.json", json.dumps(plan, indent=2) + "\n")

    arch_dir = plan_dir / "architecture"
    _write(
        arch_dir / "solution-architecture.md",
        OVERVIEW.replace("AEX-test", selection["exploration_id"]).replace(
            "SELECTED-OPTION-HASH", selected["option_sha256"]
        ),
    )
    _write(arch_dir / "views.md", VIEWS)
    _write(arch_dir / "data-and-integrations.md", DATA)
    _write(arch_dir / "quality-attributes.md", QUALITY)

    source_paths = [
        "docs/plans/team-invitations/plan.json",
        "docs/plans/team-invitations/architecture-selection.json",
        "docs/plans/team-invitations/feature-plan.md",
        "docs/plans/team-invitations/shared-context.md",
        "docs/plans/team-invitations/threat-model.md",
        "docs/plans/team-invitations/interaction-contract.md",
        "docs/plans/team-invitations/features/01-roles-authz-foundation.md",
        "docs/plans/team-invitations/features/02-team-invitations.md",
        "docs/briefs/team-invitations.md",
        "docs/adr/0001-existing-runtime.md",
        "src/application.py",
    ]
    sources = []
    for rel in source_paths:
        kind = "plan"
        if "/briefs/" in rel:
            kind = "brief"
        elif "/adr/" in rel:
            kind = "adr"
        elif rel.startswith("src/"):
            kind = "repository"
        sources.append({"path": rel, "sha256": _sha(root / rel), "kind": kind})

    coverage = {
        key: {"status": "complete", "material": False, "reason": f"{key} is traced"}
        for key in al.COVERAGE_KEYS
    }
    manifest = {
        "schema_version": 1,
        "project_slug": "team-invitations",
        "status": "approved",
        "architecture_revision": 1,
        "source_plan_revision": 2,
        "source_plan_path": "docs/plans/team-invitations",
        "sources": sources,
        "artifacts": copy.deepcopy(al.ARTIFACTS),
        "coverage": coverage,
        "components": [
            {
                "id": "C-001",
                "name": "Invitation API",
                "kind": "service",
                "responsibilities": ["Accept invitation commands"],
                "features": ["02-team-invitations"],
                "evidence_state": "recorded",
                "evidence": ["docs/plans/team-invitations/feature-plan.md"],
            },
            {
                "id": "C-002",
                "name": "Membership store",
                "kind": "data-store",
                "responsibilities": ["Persist membership state"],
                "features": ["01-roles-authz-foundation", "02-team-invitations"],
                "evidence_state": "recorded",
                "evidence": ["docs/plans/team-invitations/feature-plan.md"],
            },
        ],
        "relationships": [
            {
                "id": "R-001",
                "from": "C-001",
                "to": "C-002",
                "interaction": "Write membership state",
                "evidence_state": "recorded",
                "evidence": ["docs/plans/team-invitations/feature-plan.md"],
            }
        ],
        "deployment_nodes": [
            {
                "id": "N-001",
                "name": "Application runtime",
                "environment": "production",
                "evidence_state": "recorded",
                "evidence": ["docs/plans/team-invitations/shared-context.md"],
                "evidence_claims": {
                    "name": {
                        "path": "docs/plans/team-invitations/shared-context.md",
                        "literal": "Existing Python service",
                        "derivation": "Application runtime",
                    },
                    "environment": {
                        "path": "docs/plans/team-invitations/shared-context.md",
                        "literal": "Existing Python service",
                        "derivation": "production",
                    },
                },
            }
        ],
        "deployments": [
            {"component_id": "C-001", "node_ids": ["N-001"], "evidence_state": "recorded", "evidence": ["docs/plans/team-invitations/shared-context.md"]},
            {"component_id": "C-002", "node_ids": ["N-001"], "evidence_state": "recorded", "evidence": ["docs/plans/team-invitations/shared-context.md"]},
        ],
        "data_entities": [
            {
                "id": "DATA-001",
                "name": "membership",
                "data_class": "personal",
                "source_of_truth": "C-002",
                "writers": ["C-001", "C-002"],
                "readers": ["C-001", "C-002"],
                "lifecycle": {
                    "retain": "owned-by:01-roles-authz-foundation",
                    "export": "owned-by:01-roles-authz-foundation",
                    "erase": "owned-by:01-roles-authz-foundation",
                },
                "plan_trace": "feature-plan.md#durable-state-closure",
                "features": ["01-roles-authz-foundation", "02-team-invitations"],
                "evidence_state": "recorded",
                "evidence": ["docs/plans/team-invitations/feature-plan.md"],
            },
            {
                "id": "DATA-002",
                "name": "invitation",
                "data_class": "personal",
                "source_of_truth": "C-002",
                "writers": ["C-001"],
                "readers": ["C-001"],
                "lifecycle": {
                    "retain": "owned-by:02-team-invitations",
                    "export": "owned-by:02-team-invitations",
                    "erase": "owned-by:02-team-invitations",
                },
                "plan_trace": "feature-plan.md#durable-state-closure",
                "features": ["02-team-invitations"],
                "evidence_state": "recorded",
                "evidence": ["docs/plans/team-invitations/feature-plan.md"],
            },
        ],
        "integration_flows": [
            {
                "id": "IF-001",
                "producer": "C-001",
                "consumer": "C-002",
                "protocol": "in-process",
                "data": ["invitation acceptance"],
                "data_entity_ids": ["DATA-001", "DATA-002"],
                "source_of_truth": "C-002",
                "failure_behavior": "Fail explicitly",
                "plan_trace": "feature-plan.md#dependency-flow",
                "features": ["01-roles-authz-foundation", "02-team-invitations"],
                "contract_refs": ["TZ-001", "IC-001"],
                "evidence_state": "recorded",
                "evidence": ["docs/plans/team-invitations/interaction-contract.md"],
            }
        ],
        "quality_scenarios": [
            {
                "id": "QA-001",
                "attribute": "latency",
                "source": "docs/briefs/team-invitations.md",
                "stimulus": "Invitation acceptance",
                "environment": "normal load",
                "response": "Return a result",
                "target": "p95 under 500 ms",
                "tactic": "Bound the synchronous path",
                "verification": "/core-engineering:ce-probe-perf",
                "features": ["01-roles-authz-foundation", "02-team-invitations"],
                "evidence_state": "recorded",
            }
        ],
        "feature_mappings": [
            {
                "feature_id": "01-roles-authz-foundation",
                "component_ids": ["C-002"],
                "data_ids": ["DATA-001"],
                "integration_ids": ["IF-001"],
                "quality_ids": ["QA-001"],
                "architecture_disposition": "cross-feature",
                "evidence_state": "inferred",
                "evidence": [
                    "docs/plans/team-invitations/features/01-roles-authz-foundation.md"
                ],
            },
            {
                "feature_id": "02-team-invitations",
                "component_ids": ["C-001", "C-002"],
                "data_ids": ["DATA-001", "DATA-002"],
                "integration_ids": ["IF-001"],
                "quality_ids": ["QA-001"],
                "architecture_disposition": "cross-feature",
                "evidence_state": "inferred",
                "evidence": [
                    "docs/plans/team-invitations/features/02-team-invitations.md"
                ],
            },
        ],
        "decisions": [
            {
                "id": "D-001",
                "status": "accepted",
                "summary": "Reuse existing runtime",
                "adr_path": "docs/adr/0001-existing-runtime.md",
                "features": ["01-roles-authz-foundation", "02-team-invitations"],
                "evidence_state": "recorded",
                "evidence": ["docs/adr/0001-existing-runtime.md"],
            }
        ],
        "open_questions": [],
        "risks": [
            {
                "id": "AR-001",
                "statement": "Shared runtime changes can affect both features",
                "owner": "architecture owner",
                "mitigation": "Verify both features after runtime changes",
                "evidence_state": "observed",
                "evidence": ["src/application.py"],
            }
        ],
        "approval": {
            "decision": "approved",
            "recorded_by": "human",
            "gate": "Final Architecture Approval",
        },
    }
    _write(arch_dir / "architecture.json", json.dumps(manifest, indent=2))
    return arch_dir, manifest


def _save(arch_dir: Path, manifest: dict) -> None:
    _write(arch_dir / "architecture.json", json.dumps(manifest, indent=2))


class ArchitectureLintGreen(unittest.TestCase):
    def test_source_plan_trigger_taxonomies_are_frozen(self):
        self.assertEqual(
            al.REQUIRED_ARCHITECTURE_TRIGGERS,
            {
                "explicit-architecture-deliverable",
                "multi-runtime-or-deployment-boundary",
                "cross-feature-durable-or-async-flow",
                "shared-data-ownership-or-migration",
                "trust-residency-or-sensitive-boundary",
                "shared-protocol-or-schema",
                "platform-or-topology-choice",
                "architecture-determining-nfr",
                "contested-cross-feature-owner",
            },
        )
        self.assertEqual(
            al.ARCHITECTURE_RECOMMENDATION_TRIGGERS,
            {
                "team-policy-recommendation",
                "planned-reuse-recommendation",
                "baseline-preference",
            },
        )

    def test_valid_package_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, _ = _make_repo(root)
            hard, advisory = _legacy_check(arch_dir, root, al.load_package(arch_dir))
            self.assertEqual(hard, [])
            self.assertTrue(any(item.startswith("A2 legacy schema v1") for item in advisory))

    def test_valid_package_is_bound_to_exact_human_selected_direction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            plan_dir = root / "docs/plans/team-invitations"
            plan = json.loads((plan_dir / "plan.json").read_text(encoding="utf-8"))
            selection = json.loads(
                (plan_dir / "architecture-selection.json").read_text(encoding="utf-8")
            )
            direction = plan["architecture_disposition"]["direction"]

            self.assertEqual(direction["decided_by"], "human")
            self.assertEqual(direction["exploration_id"], selection["exploration_id"])
            self.assertEqual(
                direction["selected_option_id"], selection["selection"]["option_id"]
            )
            self.assertEqual(
                direction["selected_option_sha256"],
                selection["selection"]["option_sha256"],
            )
            self.assertEqual(
                direction["artifact_sha256"],
                _sha(plan_dir / "architecture-selection.json"),
            )
            self.assertIn(
                "docs/plans/team-invitations/architecture-selection.json",
                {row["path"] for row in manifest["sources"]},
            )
            hard, advisory = _legacy_check(arch_dir, root, manifest)
            self.assertEqual(hard, [])
            self.assertTrue(any(item.startswith("A2 legacy schema v1") for item in advisory))

    def test_incomplete_source_plan_cannot_seed_new_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            plan_path = root / "docs/plans/team-invitations/plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            del plan["architecture_disposition"]
            _write(plan_path, json.dumps(plan, indent=2))
            source = next(
                row for row in manifest["sources"]
                if row["path"] == "docs/plans/team-invitations/plan.json"
            )
            source["sha256"] = _sha(plan_path)
            hard, advisory = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    item.startswith("source plan H9")
                    and "requires `architecture_disposition`" in item
                    for item in hard
                ),
                hard,
            )
            self.assertFalse(any(item.startswith("A12") for item in advisory), advisory)

    def test_proposed_scratch_requires_explicit_flag(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["status"] = "proposed"
            manifest["approval"]["decision"] = "pending"
            manifest["approval"]["recorded_by"] = "pending"
            _save(arch_dir, manifest)
            hard, _ = _legacy_check(arch_dir, root, manifest, allow_proposed=True)
            self.assertEqual(hard, [])
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("--allow-proposed" in item for item in hard))

    def test_consumer_mode_advises_on_repository_drift_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            _write(root / "src/application.py", "RUNTIME = 'implemented-feature-one'\n")
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("stale source hash" in item for item in hard))
            hard, advisory = _legacy_check(arch_dir, root, manifest, consumer=True)
            self.assertEqual(hard, [])
            self.assertTrue(any("repository evidence drift" in item for item in advisory))

    def test_consumer_cannot_relabel_plan_input_as_repository_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            shared = "docs/plans/team-invitations/shared-context.md"
            next(row for row in manifest["sources"] if row["path"] == shared)["kind"] = "repository"
            _write(root / shared, "# Context\nNew residency requirement.\n")
            hard, advisory = _legacy_check(
                arch_dir, root, manifest, consumer=True
            )
            self.assertTrue(any("must use kind 'plan'" in item for item in hard), hard)
            self.assertTrue(any("repository evidence drift" in item for item in advisory), advisory)

    def test_empty_optional_collections_allow_header_only_projection_tables(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["relationships"] = []
            manifest["decisions"] = []
            manifest["risks"] = []
            _write(
                arch_dir / "views.md",
                VIEWS.replace(
                    "| R-001 | C-001 | C-002 | Write membership state | recorded | `docs/plans/team-invitations/feature-plan.md` |\n",
                    "",
                ),
            )
            _write(
                arch_dir / "solution-architecture.md",
                (arch_dir / "solution-architecture.md").read_text(encoding="utf-8").replace(
                    "| D-001 | Reuse existing runtime | recorded | accepted | `docs/adr/0001-existing-runtime.md` | 01-roles-authz-foundation, 02-team-invitations | `docs/adr/0001-existing-runtime.md` |\n",
                    "",
                ).replace(
                    "| AR-001 | Shared runtime changes can affect both features | observed | architecture owner | Verify both features after runtime changes | `src/application.py` |\n",
                    "",
                ),
            )
            hard, advisory = _legacy_check(arch_dir, root, manifest)
            self.assertEqual(hard, [])
            self.assertTrue(any(item.startswith("A2 legacy schema v1") for item in advisory))


class ArchitectureLintRed(unittest.TestCase):
    def _check_source_plan(self, mutate):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            plan_path = root / "docs/plans/team-invitations/plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            mutate(plan)
            _write(plan_path, json.dumps(plan, indent=2))
            source = next(
                row for row in manifest["sources"]
                if row["path"] == "docs/plans/team-invitations/plan.json"
            )
            source["sha256"] = _sha(plan_path)
            return _legacy_check(arch_dir, root, manifest)

    def test_malformed_source_plan_posture_is_h9_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            plan_path = root / "docs/plans/team-invitations/plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["architecture_disposition"]["decision"] = "required"
            plan["architecture_disposition"]["triggers"] = []
            plan["architecture_disposition"]["convergence"]["status"] = "deferred"
            plan["architecture_disposition"]["convergence"]["iteration_count"] = 0
            _write(plan_path, json.dumps(plan, indent=2))
            source = next(
                row for row in manifest["sources"]
                if row["path"] == "docs/plans/team-invitations/plan.json"
            )
            source["sha256"] = _sha(plan_path)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            posture_failures = [item for item in hard if item.startswith("H9")]
            self.assertTrue(posture_failures, hard)
            joined = " ".join(posture_failures)
            self.assertIn("status `converged`", joined)
            self.assertIn("iteration_count >= 1", joined)
            self.assertIn("at least one trigger", joined)

    def test_direction_summary_mismatch_with_selection_is_h10_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            plan_path = root / "docs/plans/team-invitations/plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["architecture_disposition"]["direction"]["selected_option_id"] = "A02"
            _write(plan_path, json.dumps(plan, indent=2) + "\n")
            source = next(
                row
                for row in manifest["sources"]
                if row["path"] == "docs/plans/team-invitations/plan.json"
            )
            source["sha256"] = _sha(plan_path)

            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    item.startswith("source plan H10")
                    and "selected_option_id" in item
                    and "does not match architecture-selection.json" in item
                    for item in hard
                ),
                hard,
            )

    def test_selected_direction_markdown_projection_is_exact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            plan = json.loads(
                (root / "docs/plans/team-invitations/plan.json").read_text(
                    encoding="utf-8"
                )
            )
            selected_hash = plan["architecture_disposition"]["direction"][
                "selected_option_sha256"
            ]
            overview_path = arch_dir / "solution-architecture.md"
            overview = overview_path.read_text(encoding="utf-8").replace(
                selected_hash, "0" * 64
            )
            _write(overview_path, overview)

            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    item.startswith("H8 selected-direction projection")
                    and "selection binding" in item
                    for item in hard
                ),
                hard,
            )

    def test_source_plan_rejects_unknown_duplicate_and_cross_category_triggers(self):
        def invalid_required(plan):
            plan["architecture_disposition"]["triggers"] = [
                "shared-data-ownership-or-migration",
                "bogus-trigger",
                "shared-data-ownership-or-migration",
                "team-policy-recommendation",
            ]

        hard, _ = self._check_source_plan(invalid_required)
        joined = " ".join(item for item in hard if item.startswith("H9"))
        self.assertIn("unknown trigger(s): bogus-trigger", joined)
        self.assertIn("duplicate trigger(s): shared-data-ownership-or-migration", joined)
        self.assertIn("only required architecture trigger ids", joined)

        def invalid_recommended(plan):
            posture = plan["architecture_disposition"]
            posture["decision"] = "recommended"
            posture["triggers"] = ["platform-or-topology-choice"]
            posture["convergence"]["status"] = "deferred"
            posture["convergence"]["iteration_count"] = 0

        hard, _ = self._check_source_plan(invalid_recommended)
        self.assertIn(
            "only recommendation trigger ids",
            " ".join(item for item in hard if item.startswith("H9")),
        )

    def test_source_plan_enforces_recommended_iteration_semantics(self):
        def zero_iteration_convergence(plan):
            posture = plan["architecture_disposition"]
            posture["decision"] = "recommended"
            posture["triggers"] = ["planned-reuse-recommendation"]
            posture["convergence"]["status"] = "converged"
            posture["convergence"]["iteration_count"] = 0

        hard, _ = self._check_source_plan(zero_iteration_convergence)
        self.assertIn(
            "iteration_count >= 1",
            " ".join(item for item in hard if item.startswith("H9")),
        )

        def iterated_deferral(plan):
            posture = plan["architecture_disposition"]
            posture["decision"] = "recommended"
            posture["triggers"] = ["baseline-preference"]
            posture["convergence"]["status"] = "deferred"
            posture["convergence"]["iteration_count"] = 1

        hard, _ = self._check_source_plan(iterated_deferral)
        self.assertIn(
            "iteration_count 0",
            " ".join(item for item in hard if item.startswith("H9")),
        )

    def test_source_plan_rejects_retired_waiver_and_allows_many_iterations(self):
        def retired_waiver(plan):
            posture = plan["architecture_disposition"]
            posture["decision"] = "waived"
            posture["convergence"]["status"] = "waived"

        hard, _ = self._check_source_plan(retired_waiver)
        joined = " ".join(item for item in hard if item.startswith("H9"))
        self.assertIn("architecture_disposition.decision", joined)
        self.assertIn("architecture_disposition.convergence.status", joined)

        def many_iterations(plan):
            plan["architecture_disposition"]["convergence"]["iteration_count"] = 99

        hard, _ = self._check_source_plan(many_iterations)
        self.assertFalse(
            any(item.startswith("H9") for item in hard),
            hard,
        )

    def test_source_plan_validates_plan_tier_and_required_light_conflict(self):
        for invalid_tier in ("minimal", []):
            with self.subTest(invalid_tier=invalid_tier):
                hard, _ = self._check_source_plan(
                    lambda plan, value=invalid_tier: plan.__setitem__(
                        "plan_tier", value
                    )
                )
                self.assertIn(
                    "must be `standard` or `light`",
                    " ".join(item for item in hard if item.startswith("H9")),
                )

        hard, _ = self._check_source_plan(
            lambda plan: plan.__setitem__("plan_tier", "light")
        )
        self.assertIn(
            "incompatible with `plan_tier: light`",
            " ".join(item for item in hard if item.startswith("H9")),
        )

    def test_source_plan_rejects_unhashable_enum_leaf_values(self):
        def invalid_enum_leaves(plan):
            posture = plan["architecture_disposition"]
            posture["decision"] = []
            posture["convergence"]["status"] = []

        hard, _ = self._check_source_plan(invalid_enum_leaves)
        joined = " ".join(item for item in hard if item.startswith("H9"))
        self.assertIn("architecture_disposition.decision", joined)
        self.assertIn("architecture_disposition.convergence.status", joined)

    def test_stale_source_hash_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            _write(root / manifest["sources"][0]["path"], "{}\n")
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("stale source hash" in item for item in hard))

    def test_missing_required_file_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            (arch_dir / "views.md").unlink()
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("missing required file" in item for item in hard))

    def test_dangling_relationship_endpoint_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["relationships"][0]["to"] = "C-999"
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("unknown component 'C-999'" in item for item in hard))

    def test_unknown_contract_reference_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["integration_flows"][0]["contract_refs"] = ["TZ-999"]
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("unknown threat id TZ-999" in item for item in hard))

    def test_contract_id_prefix_and_malformed_id_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            threat = root / "docs/plans/team-invitations/threat-model.md"
            _write(threat, "# Threat Model\nTZ-0010 only.\nTZ-foo malformed.\n")
            for source in manifest["sources"]:
                if source["path"].endswith("threat-model.md"):
                    source["sha256"] = _sha(threat)
            manifest["integration_flows"][0]["contract_refs"] = ["TZ-001", "TZ-foo"]
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("unknown threat id TZ-001" in item for item in hard))
            self.assertTrue(any("invalid contract ref 'TZ-foo'" in item for item in hard))

    def test_untraced_cross_feature_flow_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["integration_flows"][0]["plan_trace"] = "feature-plan.md#missing-edge"
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("plan_trace does not resolve" in item for item in hard))

    def test_flow_trace_to_unowned_plan_heading_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["integration_flows"][0]["plan_trace"] = "feature-plan.md#notes"
            _write(
                root / "docs/plans/team-invitations/feature-plan.md",
                (root / "docs/plans/team-invitations/feature-plan.md").read_text()
                + "\n## Notes\nMiscellaneous.\n",
            )
            for source in manifest["sources"]:
                if source["path"].endswith("feature-plan.md"):
                    source["sha256"] = _sha(root / source["path"])
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("must target Journey Map" in item for item in hard))

    def test_flow_trace_must_use_feature_plan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            feature = root / "docs/plans/team-invitations/features/02-team-invitations.md"
            _write(feature, feature.read_text() + "\n## Dependency Flow\nLocal heading.\n")
            for source in manifest["sources"]:
                if source["path"].endswith("02-team-invitations.md"):
                    source["sha256"] = _sha(feature)
            manifest["integration_flows"][0]["plan_trace"] = (
                "features/02-team-invitations.md#dependency-flow"
            )
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("must target feature-plan.md" in item for item in hard))

    def test_invented_quality_target_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["quality_scenarios"][0]["target"] = "p99 under 10 ms"
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("does not occur literally" in item for item in hard))

    def test_missing_feature_mapping_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["feature_mappings"].pop()
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("missing exactly-one mapping" in item for item in hard))

    def test_feature_mapping_requires_tracked_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            del manifest["feature_mappings"][0]["evidence"]
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    "feature mapping '01-roles-authz-foundation'.evidence must be "
                    "a non-empty list" in item
                    for item in hard
                ),
                hard,
            )

    def test_extra_and_duplicate_structural_rows_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            row = (
                "| C-001 | Invitation API | service | Accept invitation commands | "
                "02-team-invitations | recorded | "
                "`docs/plans/team-invitations/feature-plan.md` |\n"
            )
            extra = (
                "| C-999 | Invented | service | Invented responsibility | — | "
                "inferred | `docs/plans/team-invitations/feature-plan.md` |\n"
            )
            _write(
                arch_dir / "views.md",
                VIEWS.replace(row, row + row + extra, 1),
            )
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any("component table has duplicate row key(s): ['C-001']" in item for item in hard),
                hard,
            )
            self.assertTrue(
                any("component table has extra or invalid row key(s): ['C-999']" in item for item in hard),
                hard,
            )

    def test_review_significant_projection_fields_are_exact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            views = VIEWS.replace(
                "| C-001 | Invitation API | service |",
                "| C-001 | Wrong API name | service |",
            ).replace(
                "docs/plans/team-invitations/shared-context.md :: Existing Python service",
                "docs/plans/team-invitations/shared-context.md :: Invented selector",
                1,
            )
            overview = OVERVIEW.replace(
                "| D-001 | Reuse existing runtime | recorded |",
                "| D-001 | Invent a new runtime | recorded |",
            ).replace(
                "| AR-001 | Shared runtime changes can affect both features | observed |",
                "| AR-001 | No shared-runtime risk | observed |",
            )
            data = DATA.replace(
                "| IF-001 | C-001 | C-002 | in-process | invitation acceptance | "
                "DATA-001, DATA-002 | C-002 |",
                "| IF-001 | C-001 | C-002 | in-process | invitation acceptance | "
                "DATA-001, DATA-002 | C-001 |",
            )
            _write(arch_dir / "views.md", views)
            _write(arch_dir / "solution-architecture.md", overview)
            _write(arch_dir / "data-and-integrations.md", data)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            for expected in (
                "component C-001 column 'name' must project 'Invitation API'",
                "deployment node N-001 column 'name selector' must project",
                "decision D-001 column 'summary' must project 'Reuse existing runtime'",
                "risk AR-001 column 'statement' must project",
                "integration IF-001 column 'source of truth' must project 'C-002'",
            ):
                self.assertTrue(any(expected in item for item in hard), (expected, hard))

    def test_markdown_review_status_is_bound_to_approval_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["status"] = "proposed"
            manifest["approval"]["decision"] = "pending"
            manifest["approval"]["recorded_by"] = "pending"
            _write(
                arch_dir / "solution-architecture.md",
                OVERVIEW.replace("> Status: approved", "> Status: proposed"),
            )
            hard, _ = _legacy_check(
                arch_dir, root, manifest, allow_proposed=True
            )
            self.assertTrue(any("reviewed Status must equal 'approved'" in item for item in hard), hard)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["status"] = "approved-with-gaps"
            manifest["approval"]["decision"] = "approved-with-gaps"
            manifest["coverage"]["operability"] = {
                "status": "gap",
                "material": False,
                "reason": "alert ownership remains open",
            }
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any("reviewed Status must equal 'approved-with-gaps'" in item for item in hard),
                hard,
            )

    def test_contradictory_intended_status_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            _write(
                arch_dir / "solution-architecture.md",
                OVERVIEW.replace(
                    "> Status: approved\n",
                    "> Status: approved\n> Intended status: approved-with-gaps\n",
                ),
            )
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("Intended status contradicts" in item for item in hard), hard)

    def test_overview_identity_and_revisions_are_bound_to_manifest(self):
        cases = (
            (
                "heading",
                lambda text: text.replace(
                    "# Solution Architecture: team-invitations",
                    "# Solution Architecture: another-project",
                ),
                "H1 must equal 'Solution Architecture: team-invitations'",
            ),
            (
                "source",
                lambda text: text.replace(
                    "`docs/plans/team-invitations/` revision 2",
                    "`docs/plans/another-project/` revision 9",
                ),
                "Source plan must equal `docs/plans/team-invitations/` revision 2",
            ),
            (
                "revision",
                lambda text: text.replace(
                    "> Architecture revision: 1",
                    "> Architecture revision: 9",
                ),
                "Architecture revision must equal 1",
            ),
            (
                "duplicate heading",
                lambda text: text + "\n# Solution Architecture: team-invitations\n",
                "must contain exactly one H1 heading",
            ),
        )
        for label, mutate, expected in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                arch_dir, manifest = _make_repo(root)
                _write(arch_dir / "solution-architecture.md", mutate(OVERVIEW))
                hard, _ = _legacy_check(arch_dir, root, manifest)
                self.assertTrue(any(expected in item for item in hard), hard)

    def test_unaccepted_adr_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            _write(root / "docs/adr/0001-existing-runtime.md", "Status: proposed\n")
            # Refresh its source digest so this isolates the ADR-status check.
            for source in manifest["sources"]:
                if source["path"].endswith("0001-existing-runtime.md"):
                    source["sha256"] = _sha(root / source["path"])
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("exactly one canonical Status: accepted" in item for item in hard))

    def test_adr_historical_accepted_line_cannot_mask_proposed_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            adr = root / "docs/adr/0001-existing-runtime.md"
            _write(
                adr,
                "Status: proposed\n\n## Historical example\nStatus: accepted\n",
            )
            for source in manifest["sources"]:
                if source["path"].endswith("0001-existing-runtime.md"):
                    source["sha256"] = _sha(adr)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any("found ['proposed', 'accepted']" in item for item in hard), hard
            )

    def test_approved_status_cannot_hide_gap_or_question(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["coverage"]["deployment"] = {
                "status": "gap", "material": False, "reason": "unknown"
            }
            manifest["open_questions"] = [{"question": "Which region?", "material": False}]
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("approved cannot contain coverage gaps" in item for item in hard))
            self.assertTrue(any("approved cannot contain open questions" in item for item in hard))

    def test_material_open_question_blocks_even_with_gaps_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["status"] = "approved-with-gaps"
            manifest["approval"]["decision"] = "approved-with-gaps"
            manifest["coverage"]["deployment"] = {
                "status": "gap", "material": False, "reason": "unknown"
            }
            manifest["open_questions"] = [{"question": "Database choice", "material": True}]
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("material open question blocks" in item for item in hard))

    def test_projection_omission_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            relationship_row = (
                "| R-001 | C-001 | C-002 | Write membership state | recorded | "
                "`docs/plans/team-invitations/feature-plan.md` |\n"
            )
            _write(
                arch_dir / "views.md",
                VIEWS.replace(relationship_row, "")
                + "\nR-001 still connects C-001 to C-002 in this prose note.\n",
            )
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("R-001 is absent" in item for item in hard))

    def test_header_only_component_table_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            component_rows = (
                "| C-001 | Invitation API | service | Accept invitation commands | "
                "02-team-invitations | recorded | "
                "`docs/plans/team-invitations/feature-plan.md` |\n"
                "| C-002 | Membership store | data-store | Persist membership state | "
                "01-roles-authz-foundation, 02-team-invitations | recorded | "
                "`docs/plans/team-invitations/feature-plan.md` |\n"
            )
            _write(arch_dir / "views.md", VIEWS.replace(component_rows, ""))
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any("Runtime / Container View authoritative table is header-only" in item for item in hard)
            )

    def test_projection_table_under_wrong_heading_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            component_table = (
                "| Component | Name | Kind | Responsibilities | Features | Evidence state | Evidence |\n"
                "|---|---|---|---|---|---|---|\n"
                "| C-001 | Invitation API | service | Accept invitation commands | "
                "02-team-invitations | recorded | "
                "`docs/plans/team-invitations/feature-plan.md` |\n"
                "| C-002 | Membership store | data-store | Persist membership state | "
                "01-roles-authz-foundation, 02-team-invitations | recorded | "
                "`docs/plans/team-invitations/feature-plan.md` |\n"
            )
            views = VIEWS.replace(component_table, "")
            views = views.replace(
                "## View Coverage Gaps\n",
                f"## View Coverage Gaps\n{component_table}\n",
            )
            _write(arch_dir / "views.md", views)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    "views.md ## Runtime / Container View is missing its authoritative table"
                    in item
                    for item in hard
                )
            )

    def test_component_feature_refs_must_be_in_same_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            views = VIEWS.replace(
                "| C-001 | Invitation API | service | Accept invitation commands | "
                "02-team-invitations | recorded | "
                "`docs/plans/team-invitations/feature-plan.md` |",
                "| C-001 | Invitation API | service | Accept invitation commands | "
                "01-roles-authz-foundation | recorded | "
                "`docs/plans/team-invitations/feature-plan.md` |",
                1,
            )
            _write(arch_dir / "views.md", views)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    "component C-001 column 'features' is missing reference "
                    "02-team-invitations" in item
                    for item in hard
                )
            )

    def test_relationship_endpoints_must_be_in_their_columns(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            _write(
                arch_dir / "views.md",
                VIEWS.replace(
                    "| R-001 | C-001 | C-002 | Write membership state | recorded |",
                    "| R-001 | C-002 | C-001 | Write membership state | recorded |",
                ),
            )
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    "relationship R-001 column 'from' must project 'C-001'"
                    in item
                    for item in hard
                )
            )
            self.assertTrue(
                any(
                    "relationship R-001 column 'to' must project 'C-002'"
                    in item
                    for item in hard
                )
            )

    def test_deployment_node_and_mapping_values_must_share_their_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            views = VIEWS.replace(
                "| N-001 | Application runtime | production |",
                "| N-001 | Application runtime | staging |",
            ).replace(
                "| C-001 | N-001 | recorded | "
                "`docs/plans/team-invitations/shared-context.md` |",
                "| C-001 | N-999 | recorded | "
                "`docs/plans/team-invitations/shared-context.md` |",
            )
            _write(arch_dir / "views.md", views)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    "deployment node N-001 column 'environment' must project "
                    "'production'" in item
                    for item in hard
                )
            )
            self.assertTrue(
                any(
                    "deployment mapping C-001 column 'deployed to' is missing "
                    "reference N-001" in item
                    for item in hard
                )
            )

    def test_data_owner_and_lifecycle_must_be_in_same_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            data = DATA.replace(
                "| DATA-001 | membership | personal | C-002 | C-001, C-002 |",
                "| DATA-001 | membership | personal | C-001 | C-001, C-002 |",
            ).replace(
                "owned-by:01-roles-authz-foundation / "
                "owned-by:01-roles-authz-foundation / "
                "owned-by:01-roles-authz-foundation",
                "owned-by:02-team-invitations / "
                "owned-by:01-roles-authz-foundation / "
                "owned-by:01-roles-authz-foundation",
                1,
            )
            _write(arch_dir / "data-and-integrations.md", data)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    "data entity DATA-001 column 'source of truth' must project "
                    "'C-002'" in item
                    for item in hard
                )
            )
            self.assertTrue(
                any(
                    "data entity DATA-001 column 'Retain / Export / Erase' must project"
                    in item
                    for item in hard
                )
            )

    def test_integration_refs_must_be_in_same_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            integration_row = (
                "| IF-001 | C-001 | C-002 | in-process | invitation acceptance | "
                "DATA-001, DATA-002 | C-002 | Fail explicitly | TZ-001, IC-001 | "
                "feature-plan.md#dependency-flow | 01-roles-authz-foundation, "
                "02-team-invitations | recorded | "
                "`docs/plans/team-invitations/interaction-contract.md` |"
            )
            bad_row = (
                "| IF-001 | C-002 | C-002 | in-process | wrong payload | DATA-001 | "
                "C-002 | Fail explicitly | TZ-001 | "
                "feature-plan.md#dependency-flow | 01-roles-authz-foundation, "
                "02-team-invitations | recorded | "
                "`docs/plans/team-invitations/interaction-contract.md` |"
            )
            _write(
                arch_dir / "data-and-integrations.md",
                DATA.replace(integration_row, bad_row),
            )
            hard, _ = _legacy_check(arch_dir, root, manifest)
            for expected in (
                "integration IF-001 column 'producer' must project 'C-001'",
                "integration IF-001 column 'data entities' is missing reference DATA-002",
                "integration IF-001 column 'contract refs' is missing reference IC-001",
            ):
                self.assertTrue(any(expected in item for item in hard), expected)

    def test_quality_feature_refs_must_be_in_same_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            quality = QUALITY.replace(
                "| `/core-engineering:ce-probe-perf` | "
                "01-roles-authz-foundation, 02-team-invitations |",
                "| `/core-engineering:ce-probe-perf` | "
                "01-roles-authz-foundation |",
            )
            _write(arch_dir / "quality-attributes.md", quality)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    "quality QA-001 column 'features' is missing reference "
                    "02-team-invitations" in item
                    for item in hard
                )
            )

    def test_feature_mapping_refs_must_be_in_same_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            overview = OVERVIEW.replace(
                "| 01-roles-authz-foundation | C-002 | DATA-001 | IF-001 | QA-001 |",
                "| 01-roles-authz-foundation | C-002 | DATA-002 | IF-001 | QA-001 |",
            )
            _write(arch_dir / "solution-architecture.md", overview)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    "feature mapping 01-roles-authz-foundation column 'data entities' "
                    "is missing reference DATA-001" in item
                    for item in hard
                )
            )

    def test_decision_and_risk_values_must_be_in_same_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            overview = OVERVIEW.replace(
                "| D-001 | Reuse existing runtime | recorded | accepted | "
                "`docs/adr/0001-existing-runtime.md` | "
                "01-roles-authz-foundation, 02-team-invitations | "
                "`docs/adr/0001-existing-runtime.md` |",
                "| D-001 | Reuse existing runtime | recorded | accepted | "
                "`docs/adr/9999-wrong.md` | 01-roles-authz-foundation | "
                "`docs/adr/0001-existing-runtime.md` |",
            ).replace(
                "| AR-001 | Shared runtime changes can affect both features | observed | "
                "architecture owner | Verify both features after runtime changes | "
                "`src/application.py` |",
                "| AR-001 | Shared runtime changes can affect both features | observed | "
                "nobody | | `src/application.py` |",
            )
            _write(arch_dir / "solution-architecture.md", overview)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            for expected in (
                "decision D-001 column 'affected features' is missing reference "
                "02-team-invitations",
                "decision D-001 column 'adr' must project "
                "'docs/adr/0001-existing-runtime.md'",
                "risk AR-001 column 'owner' must project 'architecture owner'",
                "risk AR-001 column 'mitigation' must project "
                "'Verify both features after runtime changes'",
            ):
                self.assertTrue(any(expected in item for item in hard), expected)

    def test_material_coverage_gap_blocks_publication(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["status"] = "approved-with-gaps"
            manifest["approval"]["decision"] = "approved-with-gaps"
            manifest["coverage"]["security"] = {
                "status": "gap", "material": True, "reason": "trust boundary unknown"
            }
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("material coverage gap blocks" in item for item in hard))

    def test_untracked_evidence_path_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["components"][0]["evidence"] = ["docs/untracked.md"]
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("untracked source" in item for item in hard))

    def test_observed_state_requires_repository_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["components"][0]["evidence_state"] = "observed"
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("observed evidence must cite a repository" in item for item in hard))

    def test_missing_evidence_state_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            del manifest["relationships"][0]["evidence_state"]
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("evidence_state" in item for item in hard))

    def test_unknown_claim_requires_coverage_gap(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["components"][0]["evidence_state"] = "unknown"
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("unknown structural claim" in item for item in hard))

    def test_inferred_deployment_node_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["deployment_nodes"][0]["evidence_state"] = "inferred"
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("must be recorded or observed" in item for item in hard))

    def test_deployment_node_selector_and_derivation_must_be_grounded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            claims = manifest["deployment_nodes"][0]["evidence_claims"]
            claims["name"]["literal"] = "Invented deployment evidence"
            claims["environment"]["derivation"] = "staging"
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(
                any(
                    "evidence_claims.name.literal does not occur" in item
                    for item in hard
                )
            )
            self.assertTrue(
                any(
                    "evidence_claims.environment.derivation must equal" in item
                    for item in hard
                )
            )

    def test_deployment_mapping_requires_nodes_and_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["deployments"][0]["node_ids"] = []
            manifest["deployments"][0]["evidence"] = []
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("node_ids must be a non-empty" in item for item in hard))
            self.assertTrue(any("evidence must be a non-empty" in item for item in hard))

    def test_complete_flow_and_quality_coverage_cannot_be_empty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["integration_flows"] = []
            manifest["quality_scenarios"] = []
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("integration coverage is complete" in item for item in hard))
            self.assertTrue(any("quality coverage is complete" in item for item in hard))

    def test_orphan_and_bidirectional_feature_mapping_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["feature_mappings"][0]["quality_ids"] = []
            manifest["feature_mappings"][0]["component_ids"].append("C-001")
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("quality QA-001 feature declaration" in item for item in hard))
            self.assertTrue(any("component C-001 feature declaration" in item for item in hard))

    def test_data_class_reassignment_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            manifest["data_entities"][0]["data_class"] = "public"
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("does not match plan column" in item for item in hard))

    def test_prohibited_authority_claim_is_hard_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            _write(arch_dir / "solution-architecture.md", OVERVIEW + "\nProduction approved.\n")
            hard, advisory = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("prohibited authority claim" in item for item in hard))
            self.assertTrue(any(item.startswith("A2 legacy schema v1") for item in advisory))

    def test_negated_authority_disclaimer_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            _write(
                arch_dir / "solution-architecture.md",
                (arch_dir / "solution-architecture.md").read_text(encoding="utf-8")
                + "\nThis is not a compliance attestation and is not production ready.\n",
            )
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertEqual(hard, [])

    def test_all_external_authority_claims_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            _write(
                arch_dir / "solution-architecture.md",
                OVERVIEW
                + "\nSecurity approved. Release approved. Production ready. "
                "Approved for deployment.\n",
            )
            hard, _ = _legacy_check(arch_dir, root, manifest)
            for phrase in (
                "security approved", "release approved", "production ready",
                "approved for deployment",
            ):
                self.assertTrue(any(phrase in item for item in hard), phrase)

    def test_missing_authoritative_table_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            _write(
                arch_dir / "quality-attributes.md",
                QUALITY.replace(
                    "| ID | Attribute | Evidence state | Source | Stimulus | Environment | Response | Target | Tactic | Verification | Features |",
                    "Quality scenario prose",
                ),
            )
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("missing authoritative table header" in item for item in hard))

    def test_unexpected_nested_payload_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            _write(arch_dir / "evidence/payload.txt", "unexpected\n")
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("unexpected file" in item for item in hard))

    def test_symlinked_required_artifact_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            target = root / "outside-view.md"
            target.write_text(VIEWS, encoding="utf-8")
            (arch_dir / "views.md").unlink()
            (arch_dir / "views.md").symlink_to(target)
            hard, _ = _legacy_check(arch_dir, root, manifest)
            self.assertTrue(any("must not be a symlink" in item for item in hard), hard)


class ArchitectureLintCli(unittest.TestCase):
    def _run_json(self, root: Path, arch_dir: Path, *flags: str):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(arch_dir),
                "--repo-root",
                str(root),
                "--allow-legacy-v1",
                *flags,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_missing_manifest_is_exit_two(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir = root / "architecture"
            arch_dir.mkdir()
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(arch_dir), "--repo-root", str(root), "--allow-legacy-v1", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stdout)["status"], "error")

    def test_valid_package_cli_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, _ = _make_repo(root)
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(arch_dir), "--repo-root", str(root), "--allow-legacy-v1", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["status"], "pass")

    def test_invalid_utf8_projection_returns_json_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, _ = _make_repo(root)
            (arch_dir / "views.md").write_bytes(b"\xff\xfe")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(arch_dir), "--repo-root", str(root), "--allow-legacy-v1", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "fail")
            self.assertTrue(any("cannot read views.md" in item for item in payload["hard_failures"]))

    def test_malformed_json_leaf_types_never_emit_a_traceback(self):
        cases = (
            ("scalar", lambda manifest: manifest["components"][0].__setitem__("evidence", 7)),
            ("list", lambda manifest: manifest.__setitem__("status", [])),
            ("dict", lambda manifest: manifest["relationships"][0].__setitem__("to", {})),
        )
        for label, mutate in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                arch_dir, manifest = _make_repo(root)
                mutate(manifest)
                _save(arch_dir, manifest)
                proc = self._run_json(root, arch_dir)
                self.assertIn(proc.returncode, {1, 2}, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertIn(payload["status"], {"fail", "error"})

    def test_consumer_cli_allows_repository_drift_but_blocks_plan_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, _ = _make_repo(root)
            _write(root / "src/application.py", "RUNTIME = 'changed'\n")
            command = [
                sys.executable, str(SCRIPT), str(arch_dir), "--repo-root", str(root),
                "--allow-legacy-v1", "--consumer", "--json",
            ]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(
                any("repository evidence drift" in item for item in json.loads(proc.stdout)["advisory"])
            )

            _write(root / "docs/plans/team-invitations/shared-context.md", "# Changed plan input\n")
            proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertTrue(
                any("stale source hash" in item for item in json.loads(proc.stdout)["hard_failures"])
            )

    def test_consumer_rejects_symlinked_canonical_package(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            root = Path(td)
            arch_dir, _ = _make_repo(root)
            outside = Path(outside_td) / "architecture"
            shutil.copytree(arch_dir, outside)
            shutil.rmtree(arch_dir)
            arch_dir.symlink_to(outside, target_is_directory=True)
            proc = subprocess.run(
                [
                    sys.executable, str(SCRIPT), str(arch_dir), "--repo-root", str(root),
                    "--allow-legacy-v1", "--consumer", "--json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertTrue(
                any("canonical non-symlink" in item for item in json.loads(proc.stdout)["hard_failures"])
            )


class ArchitectureLintV2(unittest.TestCase):
    def test_authoring_template_uses_generator_contract_version(self):
        template = ARTIFACT_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(f'"version": "{al.V2_GENERATOR_VERSION}"', template)
        self.assertIn(
            "not the plugin delivery version",
            template,
        )

    def test_plugin_delivery_version_is_not_a_generator_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = v2.make_v2_repo(root)
            manifest["generator"]["version"] = "0.11.3"
            self._refinalize(arch_dir, manifest)

            hard, _ = self._check(root, arch_dir, manifest)

            self.assertIn(
                "H2 generator.version must equal the architecture generator "
                f"contract version {al.V2_GENERATOR_VERSION!r}",
                hard,
            )

    def _check(self, root: Path, arch_dir: Path, manifest: dict):
        _save(arch_dir, manifest)
        return al.check_package(
            arch_dir,
            root,
            manifest,
            allow_proposed=True,
        )

    @staticmethod
    def _refinalize(arch_dir: Path, manifest: dict) -> None:
        renderer = al._v2_load_renderer()
        finalized, documents = renderer.finalize_review_manifest(manifest)
        manifest.clear()
        manifest.update(finalized)
        for path, payload in documents.items():
            (arch_dir / path).write_bytes(payload)
        _save(arch_dir, manifest)

    @staticmethod
    def _operability_gap(manifest: dict) -> None:
        manifest["baseline_status"] = "accepted-for-specification-with-gaps"
        manifest["coverage"]["operability"] = {
            "status": "gap",
            "gap_ids": ["GAP-001"],
            "evidence": ["docs/briefs/team-invitations.md"],
        }
        manifest["readiness"] = {
            "status": "ready-with-gaps",
            "blocking_gap_ids": [],
            "non_blocking_gap_ids": ["GAP-001"],
            "summary": "A non-material implementation-stage ownership gap remains.",
        }
        manifest["gaps"] = [
            {
                "id": "GAP-001",
                "dimension": "operability",
                "gap_type": "ownership",
                "statement": "Detailed alert ownership is not recorded.",
                "impact": "An alert could lack its implementation owner.",
                "material": False,
                "owner": "operations owner",
                "next_action": "Assign the owner before implementation.",
                "closure_criteria": "OP-001 names the accepted owner.",
                "blocking_stage": "implementation",
                "status": "open",
                "related_refs": [{"kind": "operation", "id": "OP-001"}],
                "evidence_state": "recorded",
                "evidence": ["docs/briefs/team-invitations.md"],
            }
        ]

    def test_schema_v1_requires_explicit_migration_diagnostic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = _make_repo(root)
            hard, advisory = al.check_package(arch_dir, root, manifest)
            self.assertTrue(any("requires regeneration" in item for item in hard))
            self.assertEqual(advisory, [])

    def test_complete_v2_fixture_passes_and_exposes_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = v2.make_v2_repo(root)
            plan_dir = root / "docs/plans/team-invitations"
            selection_path = plan_dir / "architecture-selection.json"
            selection = json.loads(selection_path.read_text(encoding="utf-8"))
            report_path = plan_dir / "architecture-options.md"
            self.assertEqual(selection["schema_version"], 2)
            self.assertEqual(
                selection["architecture_options_report"]["status"],
                "present",
            )
            self.assertEqual(
                selection["architecture_options_report"]["sha256"],
                _sha(report_path),
            )
            _, selection_failures = sl.validate_file(
                selection_path,
                repo_root=root,
            )
            self.assertEqual(selection_failures, [])
            hard, advisory = al.check_package(
                arch_dir, root, manifest, allow_proposed=True
            )
            self.assertEqual(hard, [])
            self.assertEqual(advisory, [])
            payload = al.result_payload(hard, advisory, manifest)
            self.assertEqual(payload["architecture_schema_version"], 2)
            self.assertIsNone(payload["package_receipt_sha256"])

    def test_transition_applicability_follows_exact_selected_commitment(self):
        cases = (
            (
                "no current migration",
                (
                    "No runtime migration; logical boundaries can later be "
                    "extracted if evidence requires it."
                ),
                False,
            ),
            (
                "real migration",
                "Introduce invitation state additively before enabling acceptance.",
                True,
            ),
            (
                "migration with no downtime",
                "Migration with no downtime introduces invitation state additively.",
                True,
            ),
        )
        for label, statement, transition_applicable in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                arch_dir, manifest = v2.make_v2_repo(
                    root, migration_statement=statement
                )
                hard, advisory = al.check_package(
                    arch_dir, root, manifest, allow_proposed=True
                )
                self.assertEqual(hard, [])
                self.assertEqual(advisory, [])
                self.assertEqual(
                    "transitions"
                    in manifest["coverage_profile"]["required_dimensions"],
                    transition_applicable,
                )
                self.assertEqual(
                    manifest["coverage"]["transitions"]["status"],
                    "complete" if transition_applicable else "not-applicable",
                )
                self.assertEqual(
                    bool(manifest["transitions"]), transition_applicable
                )
                migration_row = next(
                    row
                    for row in manifest["direction_realizations"]
                    if row["dimension"] == "migration_and_evolution"
                )
                self.assertEqual(
                    migration_row["realization_status"],
                    "realized" if transition_applicable else "not-applicable",
                )

    def test_transition_absence_cannot_be_represented_by_noop_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = v2.make_v2_repo(
                root,
                migration_statement="No current data migration is introduced.",
            )
            manifest["coverage"]["transitions"]["status"] = "complete"
            manifest["transitions"] = [
                {
                    "id": "TR-001",
                    "name": "Ceremonial no-op",
                }
            ]
            hard, _ = self._check(root, arch_dir, manifest)
            self.assertTrue(
                any(
                    "requires coverage.transitions.status not-applicable" in item
                    for item in hard
                ),
                hard,
            )
            self.assertTrue(
                any(
                    "requires an empty transitions collection" in item
                    for item in hard
                ),
                hard,
            )

    def test_trust_boundary_crossings_accept_both_flow_directions(self):
        for label, producer, consumer in (
            ("outside-to-inside", "C-001", "C-002"),
            ("inside-to-outside", "C-002", "C-001"),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                arch_dir, manifest = v2.make_v2_repo(root)
                flow = manifest["integration_flows"][0]
                flow["producer"] = producer
                flow["consumer"] = consumer
                self._refinalize(arch_dir, manifest)
                hard, advisory = al.check_package(
                    arch_dir, root, manifest, allow_proposed=True
                )
                self.assertEqual(hard, [])
                self.assertEqual(advisory, [])

    def test_trust_boundary_crossing_set_is_exact(self):
        cases = (
            ("missing", lambda boundary: boundary.__setitem__(
                "crossing_integration_ids", []
            ), "expected ['IF-001']"),
            ("unexpected", lambda boundary: (
                boundary.__setitem__("inside_ids", ["C-001", "C-002"]),
                boundary.__setitem__("outside_ids", ["A-001"]),
            ), "expected []"),
        )
        for label, mutate, expected in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                arch_dir, manifest = v2.make_v2_repo(root)
                mutate(manifest["trust_boundaries"][0])
                self._refinalize(arch_dir, manifest)
                hard, _ = al.check_package(
                    arch_dir, root, manifest, allow_proposed=True
                )
                self.assertTrue(
                    any(
                        "crossing_integration_ids must exactly equal" in item
                        and expected in item
                        for item in hard
                    ),
                    hard,
                )

    def test_unlisted_flow_endpoint_is_non_crossing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = v2.make_v2_repo(root)
            boundary = manifest["trust_boundaries"][0]
            boundary["outside_ids"] = ["A-001"]
            boundary["crossing_integration_ids"] = []
            self._refinalize(arch_dir, manifest)
            hard, advisory = al.check_package(
                arch_dir, root, manifest, allow_proposed=True
            )
            self.assertEqual(hard, [])
            self.assertEqual(advisory, [])

    def test_unknown_nested_key_and_commitment_rewrite_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = v2.make_v2_repo(root)
            manifest["actors"][0]["invented"] = True
            manifest["direction_realizations"][0]["statement"] += " rewritten"
            hard, _ = self._check(root, arch_dir, manifest)
            self.assertTrue(any("unknown key(s): invented" in item for item in hard))
            self.assertTrue(any("ordered bijection" in item for item in hard))

    def test_unknown_value_cannot_hide_under_complete_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = v2.make_v2_repo(root)
            manifest["deployment_nodes"][0]["region"] = "unknown"
            hard, _ = self._check(root, arch_dir, manifest)
            self.assertTrue(
                any("open same-dimension typed gap" in item for item in hard),
                hard,
            )

    def test_feature_source_and_deployment_claim_are_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = v2.make_v2_repo(root)
            feature_path = (
                "docs/plans/team-invitations/features/"
                "01-roles-authz-foundation.md"
            )
            manifest["sources"] = [
                row for row in manifest["sources"] if row["path"] != feature_path
            ]
            manifest["deployment_nodes"][0]["evidence_claims"][0][
                "derivation"
            ] = "different"
            hard, _ = self._check(root, arch_dir, manifest)
            self.assertTrue(any("feature source is not tracked" in item for item in hard))
            self.assertTrue(any("derivation must exactly equal" in item for item in hard))

    def test_feature_source_wrong_kind_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = v2.make_v2_repo(root)
            feature_path = (
                "docs/plans/team-invitations/features/"
                "01-roles-authz-foundation.md"
            )
            next(
                row for row in manifest["sources"] if row["path"] == feature_path
            )["kind"] = "reference"
            hard, _ = self._check(root, arch_dir, manifest)
            self.assertTrue(any("not tracked as plan" in item for item in hard))

    def test_quality_target_must_be_literal_source_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = v2.make_v2_repo(root)
            manifest["quality_scenarios"][0]["target"] = "p99 under 10 ms"
            hard, _ = self._check(root, arch_dir, manifest)
            self.assertTrue(any("target must occur literally" in item for item in hard))

    def test_open_gap_must_route_through_coverage_and_every_affected_feature(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, manifest = v2.make_v2_repo(root)
            self._operability_gap(manifest)
            manifest["feature_mappings"][0]["gap_ids"] = ["GAP-001"]
            hard, _ = self._check(root, arch_dir, manifest)
            self.assertTrue(
                any("feature mapping must equal the union" in item for item in hard),
                hard,
            )

            manifest["feature_mappings"][1]["gap_ids"] = ["GAP-001"]
            manifest["coverage"]["operability"] = {
                "status": "complete",
                "gap_ids": [],
                "evidence": ["docs/briefs/team-invitations.md"],
            }
            hard, _ = self._check(root, arch_dir, manifest)
            self.assertTrue(
                any("must occur exactly once" in item for item in hard),
                hard,
            )
            self.assertTrue(
                any("requires its coverage row status to be gap" in item for item in hard),
                hard,
            )

    def test_duplicate_manifest_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            arch_dir, _ = v2.make_v2_repo(root)
            manifest_path = arch_dir / "architecture.json"
            text = manifest_path.read_text(encoding="utf-8")
            manifest_path.write_text(
                text.replace(
                    '"schema_version": 2,',
                    '"schema_version": 2,\n  "schema_version": 2,',
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                al.ArchitectureLintError, "duplicate JSON object key"
            ):
                al.load_package(arch_dir)


if __name__ == "__main__":
    unittest.main()
