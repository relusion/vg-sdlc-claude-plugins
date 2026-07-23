"""Deterministic schema-v2 ce-architecture fixture builder.

The builder intentionally reuses the established plan/source fixture and then
creates a fresh v2 semantic manifest.  Tests and golden-upgrade work can call
``make_v2_repo(root)`` and receive ``(architecture_dir, manifest)``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
LEGACY_FIXTURE = REPO / "tests/test_architecture_lint.py"
RENDERER = (
    REPO
    / "plugins/core-engineering/skills/ce-architecture/scripts/architecture-render.py"
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fixture dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_v2_repo(
    root: Path,
    *,
    migration_statement: str | None = None,
) -> tuple[Path, dict]:
    legacy = _load(LEGACY_FIXTURE, "architecture_v2_legacy_fixture")
    renderer = _load(RENDERER, "architecture_v2_fixture_renderer")
    arch_dir, legacy_manifest = legacy._make_repo(root)
    plan_dir = root / "docs/plans/team-invitations"
    plan = json.loads((plan_dir / "plan.json").read_text(encoding="utf-8"))
    selection = json.loads(
        (plan_dir / "architecture-selection.json").read_text(encoding="utf-8")
    )
    selected = next(
        row
        for row in selection["options"]
        if row["option_id"] == selection["selection"]["option_id"]
    )
    if migration_statement is not None:
        selected["migration_and_evolution"] = [migration_statement]
        selected["option_sha256"] = legacy.sl.option_hash(selected)
        option_set_sha256 = legacy.sl.option_set_hash(
            selection["options"], selection["eliminated_options"]
        )
        selection["option_set_sha256"] = option_set_sha256
        selection["exploration_id"] = f"AEX-{option_set_sha256[:12]}"
        selection["selection"]["option_sha256"] = selected["option_sha256"]
        selection["source_input_sha256"] = legacy.sl.source_input_hash(selection)
        legacy._write_current_selection(plan_dir, selection)
        direction = plan["architecture_disposition"]["direction"]
        direction["artifact_sha256"] = legacy._sha(
            plan_dir / "architecture-selection.json"
        )
        direction["exploration_id"] = selection["exploration_id"]
        direction["selected_option_sha256"] = selected["option_sha256"]
        (plan_dir / "plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    transition_applicable = legacy.al._v2_transition_is_applicable(selected)
    evidence_plan = ["docs/plans/team-invitations/feature-plan.md"]
    evidence_context = ["docs/plans/team-invitations/shared-context.md"]
    evidence_threat = ["docs/plans/team-invitations/threat-model.md"]
    evidence_contract = ["docs/plans/team-invitations/interaction-contract.md"]
    evidence_selection = [
        "docs/plans/team-invitations/architecture-selection.json"
    ]
    all_features = [
        "01-roles-authz-foundation",
        "02-team-invitations",
    ]
    invitation_feature = ["02-team-invitations"]

    direction_rows = []
    for dimension in legacy.al.V2_COMMITMENT_DIMENSIONS:
        for ordinal, statement in enumerate(selected[dimension], 1):
            absent_transition = (
                dimension == "migration_and_evolution"
                and legacy.al._v2_is_explicit_no_current_transition(statement)
            )
            direction_rows.append(
                {
                    "id": f"DR-{len(direction_rows) + 1:03d}",
                    "exploration_id": selection["exploration_id"],
                    "selected_option_id": selected["option_id"],
                    "selected_option_sha256": selected["option_sha256"],
                    "dimension": dimension,
                    "ordinal": ordinal,
                    "statement": statement,
                    "statement_sha256": legacy.hashlib.sha256(
                        statement.encode("utf-8")
                    ).hexdigest(),
                    "realization_status": (
                        "not-applicable" if absent_transition else "realized"
                    ),
                    "realized_by": (
                        [] if absent_transition
                        else [{"kind": "component", "id": "C-001"}]
                    ),
                    "gap_ids": [],
                    "evidence_state": "recorded",
                    "evidence": evidence_selection,
                }
            )

    sources = sorted(
        [
            {
                **row,
                "sha256": legacy._sha(root / row["path"]),
            }
            for row in legacy_manifest["sources"]
        ],
        key=lambda row: row["path"],
    )
    required_dimensions = [
        "direction_realization",
        "system_context",
        "containers",
        "data",
        "security",
        "requirements_traceability",
    ]
    if transition_applicable:
        required_dimensions.insert(-1, "transitions")
    coverage_evidence = {
        "direction_realization": evidence_selection,
        "system_context": evidence_plan,
        "containers": evidence_plan,
        "deployment": evidence_context,
        "data": evidence_plan,
        "integrations": evidence_contract,
        "dynamic_behavior": evidence_plan,
        "security": evidence_threat,
        "contracts": evidence_contract,
        "transitions": evidence_selection,
        "quality_attributes": ["docs/briefs/team-invitations.md"],
        "operability": ["docs/briefs/team-invitations.md"],
        "requirements_traceability": [
            "docs/plans/team-invitations/plan.json"
        ],
    }
    coverage = {
        dimension: {
            "status": (
                "not-applicable"
                if dimension == "transitions" and not transition_applicable
                else "complete"
            ),
            "gap_ids": [],
            "evidence": coverage_evidence[dimension],
        }
        for dimension in legacy.al.V2_COVERAGE_DIMENSIONS
    }

    manifest = {
        "$schema": renderer.SCHEMA_URN,
        "schema_version": 2,
        "generator": {
            "name": "/core-engineering:ce-architecture",
            "version": "0.11.0",
        },
        "project_slug": "team-invitations",
        "lifecycle_status": "proposed",
        "baseline_status": "accepted-for-specification",
        "architecture_revision": 1,
        "source_plan_revision": plan["plan_revision"],
        "source_plan_path": "docs/plans/team-invitations",
        "sources": sources,
        "projections": [
            {
                "id": projection_id,
                "projection_type": projection_type,
                "path": path,
                "required": True,
                "sha256": "0" * 64,
            }
            for projection_id, projection_type, path in renderer.CORE_PROJECTIONS
        ],
        "coverage_profile": {
            "profile_id": "solution-baseline-v2",
            "trigger_ids": plan["architecture_disposition"]["triggers"],
            "required_dimensions": required_dimensions,
        },
        "coverage": coverage,
        "readiness": {
            "status": "ready",
            "blocking_gap_ids": [],
            "non_blocking_gap_ids": [],
            "summary": "All plan-relative architecture dimensions are complete.",
        },
        "narrative": {
            "executive_summary": "Two planned features form one invitation system.",
            "scope": ["Invitation authorization, delivery, and acceptance."],
            "non_goals": ["Replacing the existing application runtime."],
            "architecture_overview": "C-001 coordinates invitation state in C-002.",
            "assumptions": [
                {
                    "id": "AS-001",
                    "statement": "The existing runtime remains available.",
                    "evidence_state": "recorded",
                    "evidence": evidence_selection,
                }
            ],
            "validation_strategy": [
                {
                    "id": "VAL-001",
                    "statement": "Verify feature behavior and the recorded latency target.",
                    "owner": "specification and verification owners",
                    "evidence_state": "recorded",
                    "evidence": ["docs/plans/team-invitations/plan.json"],
                }
            ],
            "evidence_boundary": "Only tracked source files were examined.",
            "consistency_model": "IC-001 defines idempotent invitation acceptance.",
            "security_privacy_summary": "TZ-001 is realized without granting security acceptance.",
            "operability_summary": "The application owner monitors invitation health.",
            "capacity_resilience_recovery_summary": "The existing runtime recovery model is retained.",
            "cost_complexity_summary": "Reuse avoids a new service boundary.",
        },
        "drivers": [
            {
                "id": "DRV-001",
                "name": "Central authorization",
                "statement": "Invitation writes require central authorization.",
                "source": "docs/plans/team-invitations/threat-model.md",
                "consequence": "Authorization precedes persistence.",
                "feature_ids": all_features,
                "evidence_state": "recorded",
                "evidence": evidence_threat,
            }
        ],
        "actors": [
            {
                "id": "A-001",
                "name": "Team administrator",
                "kind": "role",
                "roles": ["Create and accept invitations"],
                "feature_ids": invitation_feature,
                "evidence_state": "recorded",
                "evidence": evidence_plan,
            }
        ],
        "system_boundary": {
            "id": "SB-001",
            "name": "Invitation system",
            "responsibility": "Serve the invitation journeys in the plan.",
            "in_scope": ["Invitation and membership state"],
            "out_of_scope": ["Replacing the application runtime"],
            "evidence_state": "recorded",
            "evidence": evidence_plan,
        },
        "context_relationships": [
            {
                "id": "CR-001",
                "from": "A-001",
                "to": "SB-001",
                "interaction": "Manage team invitations",
                "feature_ids": invitation_feature,
                "evidence_state": "recorded",
                "evidence": evidence_plan,
            }
        ],
        "components": [
            {
                "id": "C-001",
                "name": "Invitation API",
                "kind": "service",
                "responsibilities": ["Authorize and coordinate invitation commands"],
                "owner": "application team",
                "feature_ids": invitation_feature,
                "evidence_state": "recorded",
                "evidence": evidence_plan,
            },
            {
                "id": "C-002",
                "name": "Membership store",
                "kind": "data-store",
                "responsibilities": ["Persist invitation and membership state"],
                "owner": "application data team",
                "feature_ids": all_features,
                "evidence_state": "recorded",
                "evidence": evidence_plan,
            },
        ],
        "relationships": [
            {
                "id": "R-001",
                "from": "C-001",
                "to": "C-002",
                "interaction": "Persist invitation acceptance",
                "protocol": "in-process data access",
                "communication_mode": "in-process",
                "contract_realization_ids": ["CTR-001"],
                "feature_ids": all_features,
                "evidence_state": "recorded",
                "evidence": evidence_contract,
            }
        ],
        "deployment_nodes": [
            {
                "id": "N-001",
                "name": "Application runtime",
                "environment": "production",
                "provider": "existing managed platform",
                "runtime": "Python application",
                "region": "existing region",
                "zones": ["existing placement"],
                "network_zone": "application network",
                "residency": "existing residency policy",
                "scaling": "existing application scaling",
                "availability": "existing runtime availability",
                "trust_boundary_ids": ["TB-001"],
                "feature_ids": all_features,
                "evidence_state": "recorded",
                "evidence": evidence_context,
                "evidence_claims": [
                    {
                        "field": "name",
                        "path": evidence_context[0],
                        "literal": "Existing Python service",
                        "derivation": "Application runtime",
                    },
                    {
                        "field": "environment",
                        "path": evidence_context[0],
                        "literal": "production",
                        "derivation": "production",
                    },
                ],
            }
        ],
        "deployments": [
            {
                "id": "DP-001",
                "component_id": "C-001",
                "node_ids": ["N-001"],
                "replica_strategy": "existing application replicas",
                "scaling": "existing application scaling",
                "failover": "existing runtime recovery",
                "feature_ids": invitation_feature,
                "evidence_state": "recorded",
                "evidence": evidence_context,
            },
            {
                "id": "DP-002",
                "component_id": "C-002",
                "node_ids": ["N-001"],
                "replica_strategy": "co-located data access",
                "scaling": "with the application runtime",
                "failover": "with the application runtime",
                "feature_ids": all_features,
                "evidence_state": "recorded",
                "evidence": evidence_context,
            },
        ],
        "deployment_connections": [],
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
                "consistency": "Membership updates are transactionally persisted.",
                "storage": "existing relational store",
                "region_residency": "existing residency policy",
                "backup_recovery": "existing managed recovery policy",
                "transition_ids": ["TR-001"] if transition_applicable else [],
                "plan_trace": "feature-plan.md#durable-state-closure",
                "feature_ids": all_features,
                "evidence_state": "recorded",
                "evidence": evidence_plan,
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
                "consistency": "Invitation acceptance is idempotent.",
                "storage": "existing relational store",
                "region_residency": "existing residency policy",
                "backup_recovery": "existing managed recovery policy",
                "transition_ids": ["TR-001"] if transition_applicable else [],
                "plan_trace": "feature-plan.md#durable-state-closure",
                "feature_ids": invitation_feature,
                "evidence_state": "recorded",
                "evidence": evidence_plan,
            },
        ],
        "integration_flows": [
            {
                "id": "IF-001",
                "name": "Invitation acceptance",
                "producer": "C-001",
                "consumer": "C-002",
                "protocol": "in-process",
                "communication_mode": "in-process",
                "data": ["invitation acceptance"],
                "data_entity_ids": ["DATA-001", "DATA-002"],
                "source_of_truth": "C-002",
                "failure_behavior": "Return an explicit failure.",
                "timeout_retry": "IC-001 defines idempotent retry.",
                "contract_realization_ids": ["CTR-001"],
                "security_realization_ids": ["SR-001"],
                "plan_trace": "feature-plan.md#dependency-flow",
                "feature_ids": all_features,
                "details": "Authorization precedes the idempotent membership write.",
                "evidence_state": "recorded",
                "evidence": evidence_contract,
            }
        ],
        "dynamic_scenarios": [
            {
                "id": "DS-001",
                "name": "Accept invitation",
                "journey_ref": "feature-plan.md#journey-map",
                "trigger": "An administrator accepts a valid invitation.",
                "success_outcome": "Membership state records the acceptance once.",
                "steps": [
                    {
                        "ordinal": 1,
                        "from": "A-001",
                        "to": "C-001",
                        "interaction": "Submit invitation acceptance",
                        "communication_mode": "synchronous",
                        "integration_id": "IF-001",
                        "contract_realization_ids": ["CTR-001"],
                        "security_realization_ids": ["SR-001"],
                        "failure_behavior": "Return an explicit denial or failure.",
                    }
                ],
                "alternate_paths": [
                    {
                        "name": "Authorization denied",
                        "condition": "The actor is not authorized.",
                        "outcome": "No state is written.",
                        "step_ordinals": [1],
                    }
                ],
                "feature_ids": all_features,
                "evidence_state": "inferred",
                "evidence": evidence_plan,
            }
        ],
        "trust_boundaries": [
            {
                "id": "TB-001",
                "name": "Caller to application",
                "boundary_type": "trust",
                "description": "Caller input crosses into the application.",
                "inside_ids": ["C-002"],
                "outside_ids": ["A-001", "C-001"],
                "crossing_integration_ids": ["IF-001"],
                "residency": "existing application boundary",
                "feature_ids": all_features,
                "evidence_state": "recorded",
                "evidence": evidence_threat,
            }
        ],
        "security_realizations": [
            {
                "id": "SR-001",
                "obligation_id": "TZ-001",
                "boundary_ids": ["TB-001"],
                "actor_ids": ["A-001"],
                "component_ids": ["C-001"],
                "integration_ids": ["IF-001"],
                "data_ids": ["DATA-001", "DATA-002"],
                "tactics": ["Authorize before persistence"],
                "verification": "Denial and no-write assertions",
                "feature_ids": all_features,
                "evidence_state": "inferred",
                "evidence": evidence_threat,
            }
        ],
        "contract_realizations": [
            {
                "id": "CTR-001",
                "obligation_id": "IC-001",
                "relationship_ids": ["R-001"],
                "integration_ids": ["IF-001"],
                "dynamic_scenario_ids": ["DS-001"],
                "data_ids": ["DATA-001", "DATA-002"],
                "behavior": "Acceptance is idempotent per invitation.",
                "failure_behavior": "Replay returns the accepted result.",
                "compatibility": "The plan interaction contract remains authoritative.",
                "verification": "Replay and concurrency tests",
                "feature_ids": all_features,
                "evidence_state": "recorded",
                "evidence": evidence_contract,
            }
        ],
        "transitions": ([
            {
                "id": "TR-001",
                "name": "Invitation state introduction",
                "from_state": "Membership exists without invitation state.",
                "to_state": "Invitation state is accepted by the existing runtime.",
                "strategy": "Add invitation state before enabling acceptance.",
                "coexistence": "Existing membership reads remain available.",
                "compatibility": "IC-001 remains authoritative.",
                "cutover": "Enable acceptance after additive state is ready.",
                "rollback": "Disable acceptance while retaining additive state.",
                "data_migration": "No destructive migration is required.",
                "owner": "application and data owners",
                "component_ids": ["C-001", "C-002"],
                "data_ids": ["DATA-001", "DATA-002"],
                "deployment_ids": ["DP-001", "DP-002"],
                "decision_ids": ["D-001"],
                "feature_ids": all_features,
                "evidence_state": "inferred",
                "evidence": evidence_selection,
            }
        ] if transition_applicable else []),
        "quality_scenarios": [
            {
                "id": "QA-001",
                "name": "Invitation latency",
                "attribute": "latency",
                "source": "docs/briefs/team-invitations.md",
                "stimulus": "Invitation acceptance",
                "environment": "normal load",
                "response": "Return an acceptance result.",
                "target": "p95 under 500 ms",
                "tactic": "Bound the synchronous path.",
                "verification": "/core-engineering:ce-probe-perf",
                "operation_ids": ["OP-001"],
                "feature_ids": all_features,
                "details": "The target is a requirement, not measured evidence.",
                "evidence_state": "recorded",
                "evidence": ["docs/briefs/team-invitations.md"],
            }
        ],
        "operations": [
            {
                "id": "OP-001",
                "name": "Invitation request health",
                "category": "observability",
                "responsibility": "Detect latency and explicit failures.",
                "owner": "application operations owner",
                "signals": ["request latency", "failure count"],
                "failure_domain": "application request path",
                "target": "Use QA-001 as the latency threshold.",
                "tactic": "Emit correlated metrics without invitation values.",
                "runbook": "owned-by:application-operations",
                "verification": "Telemetry review and runtime probe",
                "component_ids": ["C-001"],
                "deployment_node_ids": ["N-001"],
                "quality_ids": ["QA-001"],
                "feature_ids": all_features,
                "evidence_state": "inferred",
                "evidence": ["docs/briefs/team-invitations.md"],
            }
        ],
        "direction_realizations": direction_rows,
        "feature_mappings": [],
        "decisions": [
            {
                "id": "D-001",
                "title": "Application runtime",
                "status": "accepted",
                "context": "The plan requires shared authorization and state.",
                "decision": "Reuse the existing application runtime.",
                "rationale": "It preserves the selected direction.",
                "alternatives": [
                    {
                        "option": "Separate invitation service",
                        "consequence": "Adds a runtime boundary.",
                        "rejection_reason": "No requirement justifies it.",
                    }
                ],
                "consequences": ["Invitation and membership share a runtime."],
                "reversibility": "A later extraction needs a transition.",
                "cost_if_wrong": "Cross-feature runtime rework.",
                "owner": "solution architecture owner",
                "decided_by": "human",
                "decided_at": "2026-07-23T10:00:00Z",
                "adr_path": "docs/adr/0001-existing-runtime.md",
                "feature_ids": all_features,
                "evidence_state": "recorded",
                "evidence": ["docs/adr/0001-existing-runtime.md"],
            }
        ],
        "open_questions": [],
        "risks": [
            {
                "id": "AR-001",
                "title": "Shared runtime coupling",
                "statement": "Runtime changes can affect both features.",
                "likelihood": "possible",
                "impact": "Both invitation and membership behavior may regress.",
                "severity": "medium",
                "owner": "architecture owner",
                "mitigation": "Verify both feature slices.",
                "contingency": "Disable invitation acceptance.",
                "trigger": "A shared runtime regression is observed.",
                "related_refs": [{"kind": "component", "id": "C-001"}],
                "feature_ids": all_features,
                "evidence_state": "observed",
                "evidence": ["src/application.py"],
            }
        ],
        "gaps": [],
        "approval": dict(renderer.PENDING_APPROVAL),
        "extensions": {},
    }

    collection_to_mapping = {
        "direction_realizations": "direction_realization_ids",
        "drivers": "driver_ids",
        "actors": "actor_ids",
        "context_relationships": "context_relationship_ids",
        "components": "component_ids",
        "relationships": "relationship_ids",
        "deployment_nodes": "deployment_node_ids",
        "deployments": "deployment_ids",
        "deployment_connections": "deployment_connection_ids",
        "data_entities": "data_ids",
        "integration_flows": "integration_ids",
        "dynamic_scenarios": "dynamic_scenario_ids",
        "trust_boundaries": "trust_boundary_ids",
        "security_realizations": "security_realization_ids",
        "contract_realizations": "contract_realization_ids",
        "transitions": "transition_ids",
        "quality_scenarios": "quality_ids",
        "operations": "operation_ids",
        "decisions": "decision_ids",
        "open_questions": "open_question_ids",
        "risks": "risk_ids",
        "gaps": "gap_ids",
    }
    for feature_id in all_features:
        mapping = {
            "feature_id": feature_id,
            "mapping_scope": "cross-feature",
            "evidence_state": "inferred",
            "evidence": [
                f"docs/plans/team-invitations/features/{feature_id}.md"
            ],
        }
        for collection, field in collection_to_mapping.items():
            if collection == "direction_realizations":
                values = [row["id"] for row in manifest[collection]]
            elif collection == "gaps":
                values = []
            else:
                values = [
                    row["id"]
                    for row in manifest[collection]
                    if feature_id in row.get("feature_ids", [])
                ]
            mapping[field] = values
        manifest["feature_mappings"].append(mapping)

    finalized, documents = renderer.finalize_review_manifest(manifest)
    for path, payload in documents.items():
        (arch_dir / path).write_bytes(payload)
    (arch_dir / "architecture.json").write_text(
        json.dumps(finalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return arch_dir, finalized
