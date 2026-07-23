#!/usr/bin/env python3
"""Deterministic structural lint for ce-architecture schema v2.

``architecture.json`` is the semantic source and the four Markdown files are
deterministic projections.  The v2 path strictly validates object shapes,
plan-relative coverage/readiness, selected-option commitment closure, graph
and feature references, tracked evidence, projection bytes, and approval
digests.  Schema v1 is rejected by default; ``--allow-legacy-v1`` exists only
for explicit migration diagnostics and does not make a package authoritative.

Default publication mode treats every source hash as blocking. ``--consumer``
keeps plan/brief/ADR/reference drift blocking while reporting repository-kind
drift as advisory, so expected implementation changes do not deadlock later
specification.

Exit codes:
  0  PASS  — no hard structural failures (advisories may remain)
  1  FAIL  — package loaded but violates the contract
  2  ERROR — package/manifest could not be loaded
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path


SCHEMA_VERSION = 1
V2_SCHEMA_VERSION = 2
V2_SCHEMA_URN = "urn:vg-sdlc:ce-architecture:architecture:v2"
V2_GENERATOR_NAME = "/core-engineering:ce-architecture"
V2_BASELINE_STATUSES = {
    "accepted-for-specification",
    "accepted-for-specification-with-gaps",
}
V2_LIFECYCLE_STATUSES = {"proposed", "published"}
V2_COVERAGE_DIMENSIONS = (
    "direction_realization",
    "system_context",
    "containers",
    "deployment",
    "data",
    "integrations",
    "dynamic_behavior",
    "security",
    "contracts",
    "transitions",
    "quality_attributes",
    "operability",
    "requirements_traceability",
)
V2_COMMITMENT_DIMENSIONS = (
    "responsibilities_and_boundaries",
    "runtime_and_deployment",
    "data_ownership",
    "integrations_and_failure",
    "trust_residency_and_security",
    "quality_tactics",
    "migration_and_evolution",
    "capability_implications",
    "assumptions",
    "irreversible_commitments",
)
V2_CORE_PROJECTIONS = (
    ("PROJ-001", "solution-architecture", "solution-architecture.md"),
    ("PROJ-002", "architecture-views", "views.md"),
    ("PROJ-003", "data-and-integrations", "data-and-integrations.md"),
    ("PROJ-004", "quality-attributes", "quality-attributes.md"),
)
V2_TOP_LEVEL_KEYS = (
    "$schema",
    "schema_version",
    "generator",
    "project_slug",
    "lifecycle_status",
    "baseline_status",
    "architecture_revision",
    "source_plan_revision",
    "source_plan_path",
    "sources",
    "projections",
    "coverage_profile",
    "coverage",
    "readiness",
    "narrative",
    "drivers",
    "actors",
    "system_boundary",
    "context_relationships",
    "components",
    "relationships",
    "deployment_nodes",
    "deployments",
    "deployment_connections",
    "data_entities",
    "integration_flows",
    "dynamic_scenarios",
    "trust_boundaries",
    "security_realizations",
    "contract_realizations",
    "transitions",
    "quality_scenarios",
    "operations",
    "direction_realizations",
    "feature_mappings",
    "decisions",
    "open_questions",
    "risks",
    "gaps",
    "approval",
    "extensions",
)
V2_TOP_LEVEL_KEYS_WITH_RESET = (
    *V2_TOP_LEVEL_KEYS[:-2],
    "revision_reset",
    *V2_TOP_LEVEL_KEYS[-2:],
)
V2_EVIDENCE_STATES = {"recorded", "observed", "inferred", "unknown"}
V2_COVERAGE_STATES = {"complete", "gap", "not-applicable"}
V2_GAP_STATUSES = {"open", "resolved"}
V2_READINESS_STATUSES = {"ready", "ready-with-gaps", "blocked"}
V2_MAPPING_SCOPES = {"cross-feature", "feature-local"}
V2_REALIZATION_STATUSES = {"realized", "not-applicable", "gap"}
V2_COMPONENT_KINDS = COMPONENT_KINDS if "COMPONENT_KINDS" in globals() else {
    "user-interface",
    "service",
    "worker",
    "data-store",
    "external-system",
    "platform",
}
V2_ID_PATTERNS = {
    "drivers": re.compile(r"^DRV-\d{3}$"),
    "actors": re.compile(r"^A-\d{3}$"),
    "context_relationships": re.compile(r"^CR-\d{3}$"),
    "components": re.compile(r"^C-\d{3}$"),
    "relationships": re.compile(r"^R-\d{3}$"),
    "deployment_nodes": re.compile(r"^N-\d{3}$"),
    "deployments": re.compile(r"^DP-\d{3}$"),
    "deployment_connections": re.compile(r"^DC-\d{3}$"),
    "data_entities": re.compile(r"^DATA-\d{3}$"),
    "integration_flows": re.compile(r"^IF-\d{3}$"),
    "dynamic_scenarios": re.compile(r"^DS-\d{3}$"),
    "trust_boundaries": re.compile(r"^TB-\d{3}$"),
    "security_realizations": re.compile(r"^SR-\d{3}$"),
    "contract_realizations": re.compile(r"^CTR-\d{3}$"),
    "transitions": re.compile(r"^TR-\d{3}$"),
    "quality_scenarios": re.compile(r"^QA-\d{3}$"),
    "operations": re.compile(r"^OP-\d{3}$"),
    "direction_realizations": re.compile(r"^DR-\d{3}$"),
    "decisions": re.compile(r"^D-\d{3}$"),
    "open_questions": re.compile(r"^OQ-\d{3}$"),
    "risks": re.compile(r"^AR-\d{3}$"),
    "gaps": re.compile(r"^GAP-\d{3}$"),
}
V2_TRIGGER_DIMENSIONS = {
    # An explicit deliverable makes every ordinary solution-baseline dimension
    # reviewable, but it cannot manufacture a transition that the exact
    # selected direction says is absent.  Transition applicability is resolved
    # separately, fail-closed, from migration_and_evolution commitments.
    "explicit-architecture-deliverable": (
        set(V2_COVERAGE_DIMENSIONS) - {"transitions"}
    ),
    "multi-runtime-or-deployment-boundary": {
        "deployment",
    },
    "cross-feature-durable-or-async-flow": {
        "integrations",
        "dynamic_behavior",
    },
    "shared-data-ownership-or-migration": {"data"},
    "trust-residency-or-sensitive-boundary": {"security"},
    "shared-protocol-or-schema": {
        "integrations",
        "contracts",
    },
    "platform-or-topology-choice": {"deployment"},
    "architecture-determining-nfr": {"quality_attributes", "operability"},
    "contested-cross-feature-owner": {
        "containers",
        "data",
        "operability",
        "requirements_traceability",
    },
}
V2_BASE_DIMENSIONS = {
    "direction_realization",
    "system_context",
    "containers",
    "requirements_traceability",
}
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
RFC3339_UTC_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
EXTENSION_NAMESPACE_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)
APPROVAL_PLACEHOLDER_RE = re.compile(
    r"^(?:pending|human|unknown|tbd|todo|placeholder|<[^>]+>)$",
    re.IGNORECASE,
)
REQUIRED_FILES = {
    "solution-architecture.md",
    "views.md",
    "data-and-integrations.md",
    "quality-attributes.md",
    "architecture.json",
}
ARTIFACTS = {
    "overview": "solution-architecture.md",
    "views": "views.md",
    "data_and_integrations": "data-and-integrations.md",
    "quality_attributes": "quality-attributes.md",
}
REQUIRED_PLAN_FILES = {
    "plan.json",
    "architecture-selection.json",
    "feature-plan.md",
    "shared-context.md",
    "threat-model.md",
    "interaction-contract.md",
}
COVERAGE_KEYS = {
    "system_context",
    "containers",
    "deployment",
    "data",
    "integrations",
    "quality_attributes",
    "security",
    "operability",
    "requirements_traceability",
}
COVERAGE_STATES = {"complete", "gap", "not-applicable"}
PUBLISHED_STATUSES = {"approved", "approved-with-gaps"}
ALL_STATUSES = PUBLISHED_STATUSES | {"proposed"}
COMPONENT_KINDS = {
    "user-interface", "service", "worker", "data-store", "external-system",
    "platform",
}
DISPOSITIONS = {"cross-feature", "feature-local"}
EVIDENCE_STATES = {"recorded", "observed", "inferred", "unknown"}
LIFECYCLE_KEYS = {"retain", "export", "erase"}
ARCHITECTURE_DECISIONS = {"required", "recommended", "not-required"}
ARCHITECTURE_CONVERGENCE_STATES = {
    "converged", "deferred", "not-applicable",
}
ARCHITECTURE_DISPOSITION_KEYS = {
    "decision", "triggers", "rationale", "decided_by", "direction", "convergence",
}
ARCHITECTURE_CONVERGENCE_KEYS = {
    "status", "iteration_count", "summary", "decision_refs",
}
PLAN_TIERS = {"standard", "light"}
REQUIRED_ARCHITECTURE_TRIGGERS = {
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
ARCHITECTURE_RECOMMENDATION_TRIGGERS = {
    "team-policy-recommendation",
    "planned-reuse-recommendation",
    "baseline-preference",
}
ARCHITECTURE_TRIGGERS = (
    REQUIRED_ARCHITECTURE_TRIGGERS | ARCHITECTURE_RECOMMENDATION_TRIGGERS
)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CONTRACT_ID_RE = re.compile(r"^(?:TZ|IC)-\d{3}$")
CONTRACT_IDS_RE = re.compile(r"(?<![A-Za-z0-9_-])(?:TZ|IC)-\d{3}(?![A-Za-z0-9_-])")
PROJECT_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
AUTHORITY_BOUNDARY = (
    "Authority: architecture-baseline-only; no security acceptance, compliance "
    "attestation, release approval, or deployment authority."
)
ID_PATTERNS = {
    "component": re.compile(r"^C-\d{3}$"),
    "relationship": re.compile(r"^R-\d{3}$"),
    "node": re.compile(r"^N-\d{3}$"),
    "data": re.compile(r"^DATA-\d{3}$"),
    "integration": re.compile(r"^IF-\d{3}$"),
    "quality": re.compile(r"^QA-\d{3}$"),
    "decision": re.compile(r"^D-\d{3}$"),
    "risk": re.compile(r"^AR-\d{3}$"),
}
HEADINGS = {
    "solution-architecture.md": [
        "Executive Summary", "Scope and Non-Goals", "Architecture Drivers",
        "Selected Direction Realization",
        "Architecture Overview", "Decisions and Rationale",
        "Feature Traceability", "Assumptions and Coverage Gaps",
        "Risks and Mitigations", "Validation Strategy", "Evidence Boundary",
    ],
    "views.md": [
        "System Context", "Runtime / Container View", "Deployment View",
        "View Coverage Gaps",
    ],
    "data-and-integrations.md": [
        "Data Ownership and Lifecycle", "Integration Flows", "Flow Details",
        "Consistency, Idempotency, and Concurrency",
        "Security and Privacy Re-Projection", "Data and Integration Gaps",
    ],
    "quality-attributes.md": [
        "Quality Scenarios", "Operability and Observability",
        "Capacity, Resilience, and Recovery",
        "Cost and Complexity Trade-Offs", "Quality Coverage Gaps",
    ],
}
REQUIRED_TABLES = {
    "solution-architecture.md": [
        {"driver", "evidence state", "source", "architecture consequence"},
        {
            "exploration", "option", "selection binding",
            "realization summary", "evidence state", "evidence",
        },
        {
            "decision", "summary", "evidence state", "status", "adr",
            "affected features", "evidence",
        },
        {
            "feature", "components", "data entities", "integration flows",
            "quality scenarios", "disposition", "evidence state", "evidence",
        },
        {"risk", "statement", "evidence state", "owner", "mitigation", "evidence"},
    ],
    "views.md": [
        {"id", "element", "kind", "responsibility", "evidence state", "evidence"},
        {
            "component", "name", "kind", "responsibilities", "features",
            "evidence state", "evidence",
        },
        {"relationship", "from", "to", "interaction", "evidence state", "evidence"},
        {
            "node", "name", "environment", "name selector",
            "environment selector", "evidence state", "evidence",
        },
        {"component", "deployed to", "evidence state", "evidence"},
    ],
    "data-and-integrations.md": [
        {
            "id", "durable noun / data set", "data class", "source of truth",
            "writers", "readers", "retain / export / erase", "evidence state",
            "plan trace", "features", "evidence",
        },
        {
            "flow", "producer", "consumer", "protocol / medium", "data",
            "data entities", "source of truth", "failure behavior",
            "contract refs", "plan trace", "features", "evidence state",
            "evidence",
        },
    ],
    "quality-attributes.md": [
        {
            "id", "attribute", "evidence state", "source", "stimulus",
            "environment", "response", "target", "tactic", "verification",
            "features",
        },
    ],
}

V2_SOURCE_FIELDS = ("path", "sha256", "kind")
V2_PROJECTION_FIELDS = ("id", "projection_type", "path", "required", "sha256")
V2_COVERAGE_PROFILE_FIELDS = ("profile_id", "trigger_ids", "required_dimensions")
V2_COVERAGE_FIELDS = ("status", "gap_ids", "evidence")
V2_READINESS_FIELDS = (
    "status",
    "blocking_gap_ids",
    "non_blocking_gap_ids",
    "summary",
)
V2_NARRATIVE_FIELDS = (
    "executive_summary",
    "scope",
    "non_goals",
    "architecture_overview",
    "assumptions",
    "validation_strategy",
    "evidence_boundary",
    "consistency_model",
    "security_privacy_summary",
    "operability_summary",
    "capacity_resilience_recovery_summary",
    "cost_complexity_summary",
)
V2_ASSUMPTION_FIELDS = ("id", "statement", "evidence_state", "evidence")
V2_VALIDATION_FIELDS = (
    "id",
    "statement",
    "owner",
    "evidence_state",
    "evidence",
)
V2_COLLECTION_FIELDS = {
    "drivers": (
        "id", "name", "statement", "source", "consequence", "feature_ids",
        "evidence_state", "evidence",
    ),
    "actors": (
        "id", "name", "kind", "roles", "feature_ids", "evidence_state",
        "evidence",
    ),
    "context_relationships": (
        "id", "from", "to", "interaction", "feature_ids", "evidence_state",
        "evidence",
    ),
    "components": (
        "id", "name", "kind", "responsibilities", "owner", "feature_ids",
        "evidence_state", "evidence",
    ),
    "relationships": (
        "id", "from", "to", "interaction", "protocol", "communication_mode",
        "contract_realization_ids", "feature_ids", "evidence_state", "evidence",
    ),
    "deployment_nodes": (
        "id", "name", "environment", "provider", "runtime", "region", "zones",
        "network_zone", "residency", "scaling", "availability",
        "trust_boundary_ids", "feature_ids", "evidence_state", "evidence",
        "evidence_claims",
    ),
    "deployments": (
        "id", "component_id", "node_ids", "replica_strategy", "scaling",
        "failover", "feature_ids", "evidence_state", "evidence",
    ),
    "deployment_connections": (
        "id", "from_node", "to_node", "direction", "protocol", "purpose",
        "network_boundary", "feature_ids", "evidence_state", "evidence",
    ),
    "data_entities": (
        "id", "name", "data_class", "source_of_truth", "writers", "readers",
        "lifecycle", "consistency", "storage", "region_residency",
        "backup_recovery", "transition_ids", "plan_trace", "feature_ids",
        "evidence_state", "evidence",
    ),
    "integration_flows": (
        "id", "name", "producer", "consumer", "protocol",
        "communication_mode", "data", "data_entity_ids", "source_of_truth",
        "failure_behavior", "timeout_retry", "contract_realization_ids",
        "security_realization_ids", "plan_trace", "feature_ids", "details",
        "evidence_state", "evidence",
    ),
    "dynamic_scenarios": (
        "id", "name", "journey_ref", "trigger", "success_outcome", "steps",
        "alternate_paths", "feature_ids", "evidence_state", "evidence",
    ),
    "trust_boundaries": (
        "id", "name", "boundary_type", "description", "inside_ids",
        "outside_ids", "crossing_integration_ids", "residency", "feature_ids",
        "evidence_state", "evidence",
    ),
    "security_realizations": (
        "id", "obligation_id", "boundary_ids", "actor_ids", "component_ids",
        "integration_ids", "data_ids", "tactics", "verification",
        "feature_ids", "evidence_state", "evidence",
    ),
    "contract_realizations": (
        "id", "obligation_id", "relationship_ids", "integration_ids",
        "dynamic_scenario_ids", "data_ids", "behavior", "failure_behavior",
        "compatibility", "verification", "feature_ids", "evidence_state",
        "evidence",
    ),
    "transitions": (
        "id", "name", "from_state", "to_state", "strategy", "coexistence",
        "compatibility", "cutover", "rollback", "data_migration", "owner",
        "component_ids", "data_ids", "deployment_ids", "decision_ids",
        "feature_ids", "evidence_state", "evidence",
    ),
    "quality_scenarios": (
        "id", "name", "attribute", "source", "stimulus", "environment",
        "response", "target", "tactic", "verification", "operation_ids",
        "feature_ids", "details", "evidence_state", "evidence",
    ),
    "operations": (
        "id", "name", "category", "responsibility", "owner", "signals",
        "failure_domain", "target", "tactic", "runbook", "verification",
        "component_ids", "deployment_node_ids", "quality_ids", "feature_ids",
        "evidence_state", "evidence",
    ),
    "direction_realizations": (
        "id", "exploration_id", "selected_option_id",
        "selected_option_sha256", "dimension", "ordinal", "statement",
        "statement_sha256", "realization_status", "realized_by", "gap_ids",
        "evidence_state", "evidence",
    ),
    "decisions": (
        "id", "title", "status", "context", "decision", "rationale",
        "alternatives", "consequences", "reversibility", "cost_if_wrong",
        "owner", "decided_by", "decided_at", "adr_path", "feature_ids",
        "evidence_state", "evidence",
    ),
    "open_questions": (
        "id", "status", "question", "material", "owner", "needed_by",
        "options", "related_refs", "feature_ids", "evidence_state", "evidence",
    ),
    "risks": (
        "id", "title", "statement", "likelihood", "impact", "severity",
        "owner", "mitigation", "contingency", "trigger", "related_refs",
        "feature_ids", "evidence_state", "evidence",
    ),
    "gaps": (
        "id", "dimension", "gap_type", "statement", "impact", "material",
        "owner", "next_action", "closure_criteria", "blocking_stage", "status",
        "related_refs", "evidence_state", "evidence",
    ),
}
V2_SYSTEM_BOUNDARY_FIELDS = (
    "id", "name", "responsibility", "in_scope", "out_of_scope",
    "evidence_state", "evidence",
)
V2_EVIDENCE_CLAIM_FIELDS = ("field", "path", "literal", "derivation")
V2_DYNAMIC_STEP_FIELDS = (
    "ordinal", "from", "to", "interaction", "communication_mode",
    "integration_id", "contract_realization_ids", "security_realization_ids",
    "failure_behavior",
)
V2_ALTERNATE_PATH_FIELDS = ("name", "condition", "outcome", "step_ordinals")
V2_RELATED_REF_FIELDS = ("kind", "id")
V2_REALIZED_BY_FIELDS = ("kind", "id")
V2_DECISION_ALTERNATIVE_FIELDS = ("option", "consequence", "rejection_reason")
V2_LIFECYCLE_FIELDS = ("retain", "export", "erase")
V2_FEATURE_MAPPING_FIELDS = (
    "feature_id", "mapping_scope", "evidence_state", "evidence",
    "direction_realization_ids", "driver_ids", "actor_ids",
    "context_relationship_ids", "component_ids", "relationship_ids",
    "deployment_node_ids", "deployment_ids", "deployment_connection_ids",
    "data_ids", "integration_ids", "dynamic_scenario_ids",
    "trust_boundary_ids", "security_realization_ids",
    "contract_realization_ids", "transition_ids", "quality_ids",
    "operation_ids", "decision_ids", "open_question_ids", "risk_ids",
    "gap_ids",
)
V2_APPROVAL_FIELDS = (
    "decision", "recorded_by", "recorded_at", "authority", "reference",
    "gate", "review_payload_sha256", "receipt_sha256",
)
V2_REVISION_RESET_FIELDS = ("reason", "recorded_by", "gate")
V2_MAPPING_COLLECTIONS = {
    "direction_realization_ids": "direction_realizations",
    "driver_ids": "drivers",
    "actor_ids": "actors",
    "context_relationship_ids": "context_relationships",
    "component_ids": "components",
    "relationship_ids": "relationships",
    "deployment_node_ids": "deployment_nodes",
    "deployment_ids": "deployments",
    "deployment_connection_ids": "deployment_connections",
    "data_ids": "data_entities",
    "integration_ids": "integration_flows",
    "dynamic_scenario_ids": "dynamic_scenarios",
    "trust_boundary_ids": "trust_boundaries",
    "security_realization_ids": "security_realizations",
    "contract_realization_ids": "contract_realizations",
    "transition_ids": "transitions",
    "quality_ids": "quality_scenarios",
    "operation_ids": "operations",
    "decision_ids": "decisions",
    "open_question_ids": "open_questions",
    "risk_ids": "risks",
    "gap_ids": "gaps",
}
V2_REALIZED_BY_KINDS = {
    "actor": "actors",
    "system-boundary": None,
    "context-relationship": "context_relationships",
    "component": "components",
    "relationship": "relationships",
    "deployment-node": "deployment_nodes",
    "deployment": "deployments",
    "deployment-connection": "deployment_connections",
    "data-entity": "data_entities",
    "integration-flow": "integration_flows",
    "dynamic-scenario": "dynamic_scenarios",
    "trust-boundary": "trust_boundaries",
    "security-realization": "security_realizations",
    "contract-realization": "contract_realizations",
    "transition": "transitions",
    "quality-scenario": "quality_scenarios",
    "operation": "operations",
    "decision": "decisions",
    "risk": "risks",
}


class ArchitectureLintError(Exception):
    """The package cannot be loaded at all (exit 2)."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except (OSError, ValueError):
        return False


def _symlink_components(base: Path, candidate: Path) -> list[str]:
    """List symlink components on one lexical path below base."""
    try:
        relative = candidate.absolute().relative_to(base.absolute())
    except ValueError:
        return [str(candidate)]
    current = base.absolute()
    found: list[str] = []
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            found.append(current.relative_to(base.absolute()).as_posix())
    return found


def _repo_path(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    candidate = root / rel
    return candidate if _inside(root, candidate) else None


def _arch_path(arch_dir: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    rel = Path(value)
    if rel.is_absolute() or len(rel.parts) != 1 or ".." in rel.parts:
        return None
    candidate = arch_dir / rel
    return candidate if _inside(arch_dir, candidate) else None


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _objects(value: object) -> list[dict]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    return [item for item in _list(value) if isinstance(item, str) and item]


def _validate_source_architecture_disposition(
    plan: dict,
    plan_dir: Path,
    hard: list[str],
    advisory: list[str],
) -> None:
    """Validate posture and delegate direction binding to canonical plan-lint."""
    sibling = Path(__file__).with_name("plan-lint.py")
    try:
        spec = importlib.util.spec_from_file_location(
            "ce_architecture_source_plan_lint", sibling
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"could not load {sibling}")
        plan_lint = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plan_lint)
        direction_hard: list[str] = []
        direction_advisory: list[str] = []
        plan_lint.validate_architecture_disposition(
            plan,
            plan_dir,
            direction_hard,
            direction_advisory,
            require_direction=True,
        )
        hard.extend(f"source plan {item}" for item in direction_hard)
        advisory.extend(f"source plan {item}" for item in direction_advisory)
    except Exception as exc:  # a missing canonical validator is never a pass
        hard.append(
            "H10 source plan direction validation could not run: "
            f"{type(exc).__name__}: {exc}"
        )

    if "architecture_disposition" not in plan:
        advisory.append(
            "A12: source plan `architecture_disposition` is absent — legacy plan; "
            "compatibility mode applies until the next Stage R revision"
        )
        return

    plan_tier = plan.get("plan_tier")
    if plan_tier is not None and (
        not isinstance(plan_tier, str) or plan_tier not in PLAN_TIERS
    ):
        hard.append(
            "H9 source plan `plan_tier`, when present, must be `standard` or `light`"
        )

    posture = plan.get("architecture_disposition")
    if not isinstance(posture, dict):
        hard.append("H9 source plan `architecture_disposition` must be an object")
        return

    missing = sorted(ARCHITECTURE_DISPOSITION_KEYS - set(posture))
    extra = sorted(set(posture) - ARCHITECTURE_DISPOSITION_KEYS)
    if missing:
        hard.append(
            "H9 source plan `architecture_disposition` is missing key(s): "
            + ", ".join(missing)
        )
    if extra:
        hard.append(
            "H9 source plan `architecture_disposition` has unknown key(s): "
            + ", ".join(extra)
        )

    decision = posture.get("decision")
    if not isinstance(decision, str) or decision not in ARCHITECTURE_DECISIONS:
        hard.append(
            "H9 source plan `architecture_disposition.decision` must be one of "
            f"{sorted(ARCHITECTURE_DECISIONS)}"
        )

    raw_triggers = posture.get("triggers")
    triggers_valid = (
        isinstance(raw_triggers, list)
        and all(isinstance(item, str) and item.strip() for item in raw_triggers)
    )
    if not triggers_valid:
        hard.append(
            "H9 source plan `architecture_disposition.triggers` must be a list "
            "of non-empty strings"
        )
        triggers: list[str] = []
    else:
        triggers = raw_triggers
        unknown_triggers = sorted(set(triggers) - ARCHITECTURE_TRIGGERS)
        duplicate_triggers = sorted(
            {trigger for trigger in triggers if triggers.count(trigger) > 1}
        )
        if unknown_triggers:
            hard.append(
                "H9 source plan `architecture_disposition.triggers` has unknown "
                "trigger(s): " + ", ".join(unknown_triggers)
            )
        if duplicate_triggers:
            hard.append(
                "H9 source plan `architecture_disposition.triggers` has duplicate "
                "trigger(s): " + ", ".join(duplicate_triggers)
            )

    rationale = posture.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        hard.append(
            "H9 source plan `architecture_disposition.rationale` must be non-empty"
        )
    if posture.get("decided_by") != "human":
        hard.append(
            "H9 source plan `architecture_disposition.decided_by` must be 'human'"
        )

    convergence = posture.get("convergence")
    if not isinstance(convergence, dict):
        hard.append(
            "H9 source plan `architecture_disposition.convergence` must be an object"
        )
        return

    missing = sorted(ARCHITECTURE_CONVERGENCE_KEYS - set(convergence))
    extra = sorted(set(convergence) - ARCHITECTURE_CONVERGENCE_KEYS)
    if missing:
        hard.append(
            "H9 source plan `architecture_disposition.convergence` is missing key(s): "
            + ", ".join(missing)
        )
    if extra:
        hard.append(
            "H9 source plan `architecture_disposition.convergence` has unknown key(s): "
            + ", ".join(extra)
        )

    convergence_status = convergence.get("status")
    if (
        not isinstance(convergence_status, str)
        or convergence_status not in ARCHITECTURE_CONVERGENCE_STATES
    ):
        hard.append(
            "H9 source plan `architecture_disposition.convergence.status` must be one of "
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
            "H9 source plan `architecture_disposition.convergence.iteration_count` "
            "must be an integer >= 0"
        )
    summary = convergence.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        hard.append(
            "H9 source plan `architecture_disposition.convergence.summary` "
            "must be non-empty"
        )
    refs = convergence.get("decision_refs")
    if not (
        isinstance(refs, list)
        and all(isinstance(item, str) and item.strip() for item in refs)
    ):
        hard.append(
            "H9 source plan `architecture_disposition.convergence.decision_refs` "
            "must be a list of non-empty strings"
        )

    if decision == "required":
        if convergence_status != "converged":
            hard.append(
                "H9 source plan decision `required` requires convergence status `converged`"
            )
        if iteration_valid and iteration_count < 1:
            hard.append(
                "H9 source plan decision `required` requires iteration_count >= 1"
            )
        if triggers_valid and not triggers:
            hard.append(
                "H9 source plan decision `required` requires at least one trigger"
            )
        invalid = sorted(set(triggers) - REQUIRED_ARCHITECTURE_TRIGGERS)
        if triggers_valid and invalid:
            hard.append(
                "H9 source plan decision `required` accepts only required architecture "
                "trigger ids; found: " + ", ".join(invalid)
            )
        if plan_tier == "light":
            hard.append(
                "H9 source plan decision `required` is incompatible with "
                "`plan_tier: light`"
            )
    elif decision == "recommended":
        if convergence_status not in {"converged", "deferred"}:
            hard.append(
                "H9 source plan decision `recommended` requires convergence status "
                "`converged` or `deferred`"
            )
        if triggers_valid and not triggers:
            hard.append(
                "H9 source plan decision `recommended` requires at least one trigger"
            )
        invalid = sorted(set(triggers) - ARCHITECTURE_RECOMMENDATION_TRIGGERS)
        if triggers_valid and invalid:
            hard.append(
                "H9 source plan decision `recommended` accepts only recommendation "
                "trigger ids; found: " + ", ".join(invalid)
            )
        if convergence_status == "converged" and iteration_valid and iteration_count < 1:
            hard.append(
                "H9 source plan decision `recommended` with convergence status "
                "`converged` requires iteration_count >= 1"
            )
        if convergence_status == "deferred" and iteration_valid and iteration_count != 0:
            hard.append(
                "H9 source plan decision `recommended` with convergence status "
                "`deferred` requires iteration_count 0"
            )
    elif decision == "not-required":
        if convergence_status != "not-applicable":
            hard.append(
                "H9 source plan decision `not-required` requires convergence status "
                "`not-applicable`"
            )
        if iteration_valid and iteration_count != 0:
            hard.append(
                "H9 source plan decision `not-required` requires iteration_count 0"
            )
        if triggers_valid and triggers:
            hard.append(
                "H9 source plan decision `not-required` requires an empty triggers list"
            )


def _evidence_state(row: dict, label: str, hard: list[str]) -> bool:
    """Validate a structural claim's provenance label; return True for unknown."""
    state = row.get("evidence_state")
    if state not in EVIDENCE_STATES:
        hard.append(
            f"{label}.evidence_state must be one of {sorted(EVIDENCE_STATES)}"
        )
        return False
    return state == "unknown"


def _evidence_refs(
    row: dict,
    label: str,
    source_kinds: dict[str, str],
    hard: list[str],
) -> None:
    """Require every evidence path to be a tracked stale-detection source."""
    raw = row.get("evidence")
    refs = _string_list(raw)
    if not isinstance(raw, list) or len(refs) != len(raw) or not refs:
        hard.append(f"{label}.evidence must be a non-empty list of source paths")
        return
    unknown = sorted(set(refs) - set(source_kinds))
    if unknown:
        hard.append(
            f"{label}.evidence references untracked source(s): {', '.join(unknown)}"
        )
    state = row.get("evidence_state")
    kinds = {source_kinds.get(ref) for ref in refs}
    if state == "recorded" and not kinds.intersection({"plan", "brief", "adr", "reference"}):
        hard.append(f"{label} recorded evidence must cite a recorded source kind")
    if state == "observed" and "repository" not in kinds:
        hard.append(f"{label} observed evidence must cite a repository source")


def _plan_data_rows(plan_dir: Path) -> dict[str, dict[str, str]]:
    """Return exact durable-noun rows from only the plan closure table."""
    try:
        lines = (plan_dir / "feature-plan.md").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {}
    section_start: int | None = None
    section_end = len(lines)
    for idx, line in enumerate(lines):
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if not heading:
            continue
        if _heading_slug(heading.group(1)) == "durable-state-closure":
            section_start = idx + 1
        elif section_start is not None:
            section_end = idx
            break
    if section_start is None:
        return {}
    rows: dict[str, dict[str, str]] = {}
    header_seen = False
    headers: list[str] = []
    for line in lines[section_start:section_end]:
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        normalized = [_heading_slug(cell) for cell in cells]
        if not header_seen:
            if "noun" in normalized and ("data-class" in normalized or "data-classification" in normalized):
                header_seen = True
                headers = normalized
            continue
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if not cells:
            continue
        noun = cells[0].strip().strip("`")
        if not noun or noun in {"<noun>", "…", "...", "-"}:
            continue
        if len(cells) == len(headers):
            rows[noun] = dict(zip(headers, cells))
    return rows


def _plan_data_cells(plan_dir: Path, noun: object) -> dict[str, str]:
    """Return the plan table row for one exact durable noun, if present."""
    if not isinstance(noun, str) or not noun.strip():
        return {}
    return _plan_data_rows(plan_dir).get(noun.strip().strip("`"), {})


def _plan_contract_ids(plan_dir: Path, filename: str, prefix: str) -> set[str]:
    """Extract the exact plan-owned obligation ids from one canonical projection."""
    try:
        text = (plan_dir / filename).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return set()
    return {
        value
        for value in CONTRACT_IDS_RE.findall(text)
        if value.startswith(f"{prefix}-")
    }


def _contains_exact_id(text: str, value: str) -> bool:
    """Match one obligation id without accepting a longer id as its prefix."""
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(value)}(?![A-Za-z0-9_-])",
            text,
        )
    )


def _heading_slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _table_header_cells(text: str) -> list[set[str]]:
    headers: list[set[str]] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = {
            cell.strip().casefold()
            for cell in line.strip().strip("|").split("|")
            if cell.strip()
        }
        if cells and not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            headers.append(cells)
    return headers


def _section_under_exact_heading(text: str, heading: str) -> str:
    """Return one H2 section body, stopping at the next H2 heading."""
    lines = text.splitlines()
    start: int | None = None
    expected = heading.casefold()
    for idx, line in enumerate(lines):
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if not match:
            continue
        if start is None and match.group(1).strip().casefold() == expected:
            start = idx + 1
            continue
        if start is not None:
            return "\n".join(lines[start:idx])
    return "" if start is None else "\n".join(lines[start:])


def _pipe_cells(line: str) -> list[str]:
    """Split the deliberately simple pipe tables used by architecture artifacts."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _markdown_tables(section: str) -> list[dict[str, object]]:
    """Parse Markdown pipe tables from one already-scoped H2 section."""
    lines = section.splitlines()
    tables: list[dict[str, object]] = []
    idx = 0
    while idx + 1 < len(lines):
        if not lines[idx].lstrip().startswith("|"):
            idx += 1
            continue
        header = _pipe_cells(lines[idx])
        separator = _pipe_cells(lines[idx + 1])
        if not _is_table_separator(separator) or len(separator) != len(header):
            idx += 1
            continue
        normalized = [cell.casefold() for cell in header]
        rows: list[dict[str, str]] = []
        idx += 2
        while idx < len(lines) and lines[idx].lstrip().startswith("|"):
            cells = _pipe_cells(lines[idx])
            if not _is_table_separator(cells):
                if len(cells) == len(header):
                    rows.append(dict(zip(normalized, cells)))
                else:
                    rows.append({"__raw__": lines[idx], "__malformed__": "true"})
            idx += 1
        tables.append({"headers": set(normalized), "rows": rows})
    return tables


def _projection_table(
    markdown: dict[str, str],
    filename: str,
    heading: str,
    required_headers: set[str],
    hard: list[str],
    require_rows: bool,
) -> dict[str, object] | None:
    """Resolve one authoritative table under its exact H2."""
    section = _section_under_exact_heading(markdown.get(filename, ""), heading)
    matches = [
        table
        for table in _markdown_tables(section)
        if required_headers.issubset(table["headers"])
    ]
    label = f"{filename} ## {heading}"
    if not matches:
        hard.append(
            f"H8 {label} is missing its authoritative table with: "
            f"{', '.join(sorted(required_headers))}"
        )
        return None
    if len(matches) > 1:
        hard.append(f"H8 {label} contains multiple authoritative tables")
    table = matches[0]
    if require_rows and not table["rows"]:
        hard.append(f"H8 {label} authoritative table is header-only")
    return table


def _projection_row(
    table: dict[str, object] | None,
    key_column: str,
    value: str,
    label: str,
    hard: list[str],
) -> dict[str, str] | None:
    """Find exactly one table row by an exact structural identifier."""
    if table is None:
        return None
    rows = [
        row
        for row in table["rows"]
        if _plain_cell(row.get(key_column.casefold(), "")) == _plain_cell(value)
    ]
    if not rows:
        hard.append(f"H8 {label} {value} is absent from its authoritative table")
        return None
    if len(rows) > 1:
        hard.append(f"H8 {label} {value} appears in multiple authoritative rows")
    return rows[0]


EMPTY_PROJECTION_CELLS = {"", "-", "—", "none", "n/a", "not applicable"}


def _plain_cell(value: str) -> str:
    """Normalize one scalar cell while allowing conventional Markdown wrappers."""
    normalized = re.sub(r"\s+", " ", value.strip())
    wrappers = (("`", "`"), ("**", "**"), ("__", "__"), ("*", "*"), ("_", "_"))
    changed = True
    while changed:
        changed = False
        for left, right in wrappers:
            if (
                normalized.startswith(left)
                and normalized.endswith(right)
                and len(normalized) >= len(left) + len(right)
            ):
                normalized = normalized[len(left):-len(right)].strip()
                changed = True
                break
    return normalized.casefold()


def _projection_values(value: str, separator: str) -> list[str]:
    if _plain_cell(value) in EMPTY_PROJECTION_CELLS:
        return []
    return [_plain_cell(item) for item in value.split(separator)]


def _projection_list(
    row: dict[str, str] | None,
    column: str,
    expected: object,
    label: str,
    hard: list[str],
    *,
    separator: str = ",",
) -> None:
    if row is None:
        return
    actual = _projection_values(row.get(column.casefold(), ""), separator)
    wanted = [_plain_cell(value) for value in _string_list(expected)]
    if actual != wanted:
        hard.append(
            f"H8 {label} column {column!r} must project {wanted!r}, got {actual!r}"
        )


def _projection_optional_scalar(
    row: dict[str, str] | None,
    column: str,
    expected: object,
    label: str,
    hard: list[str],
) -> None:
    if row is None:
        return
    actual = _plain_cell(row.get(column.casefold(), ""))
    wanted = _plain_cell(expected) if isinstance(expected, str) else ""
    if not wanted and actual in EMPTY_PROJECTION_CELLS:
        return
    if actual != wanted:
        hard.append(
            f"H8 {label} column {column!r} must project {expected!r}, "
            f"got {row.get(column.casefold(), '')!r}"
        )


def _projection_key_set(
    table: dict[str, object] | None,
    key_column: str,
    expected: object,
    label: str,
    hard: list[str],
) -> None:
    """Require exactly one canonical table row for every JSON structural key."""
    if table is None:
        return
    expected_values = _string_list(expected)
    expected_by_normalized = {_plain_cell(value): value for value in expected_values}
    counts = {value: 0 for value in expected_values}
    extras: list[str] = []
    for row in table["rows"]:
        if row.get("__malformed__") == "true":
            extras.append(row.get("__raw__", "<malformed row>"))
            continue
        raw = row.get(key_column.casefold(), "")
        canonical = expected_by_normalized.get(_plain_cell(raw))
        if canonical is None:
            extras.append(raw or "<empty>")
        else:
            counts[canonical] += 1
    missing = [value for value, count in counts.items() if count == 0]
    duplicates = [value for value, count in counts.items() if count > 1]
    if extras:
        hard.append(f"H8 {label} has extra or invalid row key(s): {extras!r}")
    if missing:
        hard.append(f"H8 {label} is missing row key(s): {missing!r}")
    if duplicates:
        hard.append(f"H8 {label} has duplicate row key(s): {duplicates!r}")


def _projection_selector(
    row: dict[str, str] | None,
    column: str,
    claim: object,
    label: str,
    hard: list[str],
) -> None:
    if row is None or not isinstance(claim, dict):
        return
    path = claim.get("path")
    literal = claim.get("literal")
    if not isinstance(path, str) or not isinstance(literal, str):
        return
    expected = f"{path} :: {literal}"
    _projection_scalar(row, column, expected, label, hard)


def _projection_markdown_status(
    markdown: dict[str, str],
    manifest_status: object,
    gap_count: int,
    hard: list[str],
) -> None:
    text = markdown.get("solution-architecture.md", "")
    statuses = re.findall(r"(?im)^>\s*Status:\s*([a-z][a-z-]*)\s*$", text)
    if len(statuses) != 1:
        hard.append(
            "H8 solution-architecture.md must contain exactly one '> Status: <status>' line"
        )
        return
    expected = manifest_status
    if manifest_status == "proposed":
        expected = "approved-with-gaps" if gap_count else "approved"
    if expected in PUBLISHED_STATUSES and statuses[0].casefold() != expected:
        hard.append(
            "H8 solution-architecture.md reviewed Status must equal "
            f"{expected!r}, got {statuses[0]!r}"
        )
    intended = re.findall(
        r"(?im)^>\s*Intended status:\s*([a-z][a-z-]*)\s*$", text
    )
    contradictory = [value for value in intended if value.casefold() != expected]
    if contradictory:
        hard.append(
            "H8 solution-architecture.md Intended status contradicts the reviewed "
            f"status: {contradictory!r}"
        )


def _projection_overview_identity(
    markdown: dict[str, str],
    data: dict,
    hard: list[str],
) -> None:
    """Bind the human overview header and revision banner to the manifest."""
    text = markdown.get("solution-architecture.md", "")

    headings = re.findall(r"(?m)^#(?!#)\s+(.+?)\s*$", text)
    expected_heading = f"Solution Architecture: {data.get('project_slug')}"
    if len(headings) != 1:
        hard.append(
            "H8 solution-architecture.md must contain exactly one H1 heading"
        )
    elif headings[0] != expected_heading:
        hard.append(
            "H8 solution-architecture.md H1 must equal "
            f"{expected_heading!r}, got {headings[0]!r}"
        )

    source_lines = re.findall(r"(?im)^>\s*Source plan:.*$", text)
    if len(source_lines) != 1:
        hard.append(
            "H8 solution-architecture.md must contain exactly one canonical "
            "Source plan line"
        )
    else:
        match = re.fullmatch(
            r">\s*Source plan:\s*`([^`]+/)`\s+revision\s+([0-9]+)\s*",
            source_lines[0],
        )
        expected_path = data.get("source_plan_path")
        expected_revision = data.get("source_plan_revision")
        if (
            match is None
            or match.group(1) != f"{expected_path}/"
            or match.group(2) != str(expected_revision)
        ):
            hard.append(
                "H8 solution-architecture.md Source plan must equal "
                f"`{expected_path}/` revision {expected_revision}"
            )

    revision_lines = re.findall(
        r"(?im)^>\s*Architecture revision:.*$", text
    )
    if len(revision_lines) != 1:
        hard.append(
            "H8 solution-architecture.md must contain exactly one canonical "
            "Architecture revision line"
        )
    else:
        match = re.fullmatch(
            r">\s*Architecture revision:\s*([0-9]+)\s*",
            revision_lines[0],
        )
        expected_revision = data.get("architecture_revision")
        if match is None or match.group(1) != str(expected_revision):
            hard.append(
                "H8 solution-architecture.md Architecture revision must equal "
                f"{expected_revision}"
            )


def _projection_scalar(
    row: dict[str, str] | None,
    column: str,
    expected: object,
    label: str,
    hard: list[str],
) -> None:
    if row is None or not isinstance(expected, str):
        return
    actual = row.get(column.casefold(), "")
    if _plain_cell(actual) != _plain_cell(expected):
        hard.append(
            f"H8 {label} column {column!r} must project {expected!r}, got {actual!r}"
        )


def _projection_refs(
    row: dict[str, str] | None,
    column: str,
    expected: object,
    label: str,
    hard: list[str],
) -> None:
    if row is None:
        return
    actual = _projection_values(row.get(column.casefold(), ""), ",")
    wanted_values = _string_list(expected)
    wanted = [_plain_cell(value) for value in wanted_values]
    for value, normalized in zip(wanted_values, wanted):
        if normalized not in actual:
            hard.append(
                f"H8 {label} column {column!r} is missing reference {value}"
            )
    for value in actual:
        if value not in wanted:
            hard.append(
                f"H8 {label} column {column!r} has unexpected reference {value!r}"
            )
    if actual != wanted and set(actual) == set(wanted):
        hard.append(
            f"H8 {label} column {column!r} must preserve reference order "
            f"{wanted!r}, got {actual!r}"
        )


def _projection_literals(
    row: dict[str, str] | None,
    column: str,
    expected: object,
    label: str,
    hard: list[str],
) -> None:
    if row is None:
        return
    actual = row.get(column.casefold(), "")
    for value in _string_list(expected):
        if value not in actual:
            hard.append(
                f"H8 {label} column {column!r} is missing value {value!r}"
            )


def _projection_lifecycle(
    row: dict[str, str] | None,
    lifecycle: object,
    label: str,
    hard: list[str],
) -> None:
    if row is None or not isinstance(lifecycle, dict):
        return
    actual = [
        _plain_cell(value)
        for value in row.get("retain / export / erase", "").split("/")
    ]
    expected = [
        _plain_cell(str(lifecycle.get(key, "")))
        for key in ("retain", "export", "erase")
    ]
    if actual != expected:
        hard.append(
            f"H8 {label} column 'Retain / Export / Erase' must project "
            f"{expected!r}, got {actual!r}"
        )


def _ids(
    rows: object,
    kind: str,
    hard: list[str],
    prefix: str,
) -> tuple[list[dict], set[str]]:
    if not isinstance(rows, list):
        hard.append(f"{prefix} must be a list")
        return [], set()
    objects = _objects(rows)
    if len(objects) != len(rows):
        hard.append(f"{prefix} entries must be objects")
    found: set[str] = set()
    for idx, row in enumerate(objects):
        value = row.get("id")
        if not isinstance(value, str) or not ID_PATTERNS[kind].match(value):
            hard.append(f"{prefix}[{idx}].id must match {ID_PATTERNS[kind].pattern}")
            continue
        if value in found:
            hard.append(f"{prefix} contains duplicate id {value}")
        found.add(value)
    return objects, found


def _plan_feature_rows(plan: dict, hard: list[str]) -> tuple[list[dict], set[str]]:
    rows = plan.get("features")
    if not isinstance(rows, list) or len(rows) < 2:
        hard.append("source plan must contain at least two feature objects")
        return [], set()
    objects = _objects(rows)
    if len(objects) != len(rows):
        hard.append("source plan features must all be objects")
    ids: set[str] = set()
    for idx, row in enumerate(objects):
        value = row.get("id")
        if not isinstance(value, str) or not value:
            hard.append(f"source plan features[{idx}].id must be a non-empty string")
        elif value in ids:
            hard.append(f"source plan contains duplicate feature id {value}")
        else:
            ids.add(value)
    return objects, ids


def _plan_trace_resolves(plan_dir: Path, trace: object) -> bool:
    if not isinstance(trace, str) or not trace.strip():
        return False
    raw_path, _, fragment = trace.partition("#")
    rel = Path(raw_path)
    if rel.is_absolute() or ".." in rel.parts:
        return False
    target = plan_dir / rel
    if not _inside(plan_dir, target) or not target.is_file():
        return False
    if not fragment:
        return True
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    heading_slugs = {
        _heading_slug(match.group(1))
        for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.MULTILINE)
    }
    return fragment in heading_slugs


def _strict_object_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _strict_json_loads(payload: str) -> object:
    return json.loads(payload, object_pairs_hook=_strict_object_pairs)


def load_package(arch_dir: Path) -> dict:
    if not arch_dir.is_dir():
        raise ArchitectureLintError(f"architecture directory not found: {arch_dir}")
    manifest_path = arch_dir / "architecture.json"
    if not manifest_path.is_file():
        raise ArchitectureLintError(f"architecture.json not found: {manifest_path}")
    try:
        data = _strict_json_loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ArchitectureLintError(f"architecture.json is unreadable or invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ArchitectureLintError("architecture.json must contain a JSON object")
    return data


def _check_package_v1(
    arch_dir: Path,
    repo_root: Path,
    data: dict,
    allow_proposed: bool = False,
    consumer: bool = False,
    architecture_input: Path | None = None,
) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    advisory: list[str] = []

    # H1 — exact coherent file set and required headings.
    present = {p.name for p in arch_dir.iterdir()}
    missing = sorted(REQUIRED_FILES - present)
    extra = sorted(present - REQUIRED_FILES)
    if missing:
        hard.append(f"H1 missing required file(s): {', '.join(missing)}")
    if extra:
        hard.append(f"H1 unexpected file(s) in coherent package: {', '.join(extra)}")
    markdown: dict[str, str] = {}
    for name in sorted(REQUIRED_FILES):
        path = arch_dir / name
        if path.is_symlink():
            hard.append(f"H1 required artifact must not be a symlink: {name}")
        if path.exists() and not path.is_file():
            hard.append(f"H1 required artifact is not a file: {name}")
        if path.is_file() and path.stat().st_size == 0:
            hard.append(f"H1 required file is empty: {name}")
        if name.endswith(".md") and path.is_file():
            try:
                markdown[name] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                hard.append(f"H1 cannot read {name}: {exc}")
    for name, headings in HEADINGS.items():
        text = markdown.get(name, "")
        for heading in headings:
            if not re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.MULTILINE):
                hard.append(f"H1 {name} missing heading: {heading}")
        headers = _table_header_cells(text)
        for required in REQUIRED_TABLES.get(name, []):
            if not any(required.issubset(cells) for cells in headers):
                hard.append(
                    f"H1 {name} missing authoritative table header with: "
                    f"{', '.join(sorted(required))}"
                )
    if AUTHORITY_BOUNDARY not in markdown.get("solution-architecture.md", ""):
        hard.append("H1 solution-architecture.md missing the canonical authority boundary")

    # H2 — manifest shape and artifact references.
    if data.get("schema_version") != SCHEMA_VERSION:
        hard.append(f"H2 schema_version must be {SCHEMA_VERSION}")
    slug = data.get("project_slug")
    if not isinstance(slug, str) or not PROJECT_SLUG_RE.fullmatch(slug):
        hard.append(
            "H2 project_slug must be canonical lowercase kebab-case and contain "
            "no path separators or dot segments"
        )
        slug = ""
    if consumer and slug:
        expected_consumer_dir = repo_root / "docs" / "plans" / slug / "architecture"
        supplied = architecture_input if architecture_input is not None else arch_dir
        unsafe_components = _symlink_components(repo_root, expected_consumer_dir)
        if (
            supplied.is_symlink()
            or unsafe_components
            or not _inside(repo_root, expected_consumer_dir)
            or arch_dir.resolve() != expected_consumer_dir.resolve()
        ):
            detail = ", ".join(unsafe_components) if unsafe_components else str(supplied)
            hard.append(
                "H2 consumer architecture path must be the canonical non-symlink "
                f"repository package; unsafe path(s): {detail}"
            )
    status = data.get("status")
    if status not in ALL_STATUSES:
        hard.append(f"H2 status must be one of {sorted(ALL_STATUSES)}")
    elif status == "proposed" and not allow_proposed:
        hard.append("H2 status proposed is valid only for scratch lint with --allow-proposed")
    for field in ("architecture_revision", "source_plan_revision"):
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            hard.append(f"H2 {field} must be an integer >= 1")
    if data.get("artifacts") != ARTIFACTS:
        hard.append(f"H2 artifacts must equal the canonical mapping {ARTIFACTS}")
    for value in ARTIFACTS.values():
        path = _arch_path(arch_dir, value)
        if path is None or not path.is_file():
            hard.append(f"H2 artifact path does not resolve inside package: {value}")

    # H3 — source plan and feature set.
    expected_plan_path = f"docs/plans/{slug}" if slug else None
    if expected_plan_path and data.get("source_plan_path") != expected_plan_path:
        hard.append(
            f"H3 source_plan_path must equal canonical path {expected_plan_path!r}"
        )
    plan_dir = _repo_path(repo_root, data.get("source_plan_path"))
    if plan_dir is None or not plan_dir.is_dir():
        hard.append("H3 source_plan_path must resolve to a repository directory")
        plan_dir = repo_root / "__missing_plan__"
    plan_path = plan_dir / "plan.json"
    plan: dict = {}
    if plan_path.is_file():
        try:
            loaded = json.loads(plan_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                plan = loaded
            else:
                hard.append("H3 source plan.json must contain an object")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            hard.append(f"H3 source plan.json is unreadable/invalid: {exc}")
    else:
        hard.append(f"H3 source plan.json not found: {plan_path}")
    plan_slug = plan.get("project_slug", plan.get("slug"))
    if slug and plan_slug != slug:
        hard.append(f"H3 project_slug {slug!r} does not match source plan {plan_slug!r}")
    _validate_source_architecture_disposition(plan, plan_dir, hard, advisory)
    plan_revision = plan.get("plan_revision", 1)
    if data.get("source_plan_revision") != plan_revision:
        hard.append(
            f"H3 source_plan_revision {data.get('source_plan_revision')!r} "
            f"does not match current plan revision {plan_revision!r}"
        )
    plan_rows, feature_ids = _plan_feature_rows(plan, hard)
    prior_manifest_unreadable = False
    if status == "proposed" and plan_dir.is_dir():
        current_arch_dir = plan_dir / "architecture"
        current_manifest = current_arch_dir / "architecture.json"
        scratch_manifest = arch_dir / "architecture.json"
        if current_manifest.resolve() != scratch_manifest.resolve():
            expected_arch_revision = 1
            if (
                (current_arch_dir.exists() or current_arch_dir.is_symlink())
                and not current_manifest.is_file()
            ):
                prior_manifest_unreadable = True
            elif current_manifest.exists():
                try:
                    prior = json.loads(current_manifest.read_text(encoding="utf-8"))
                    prior_revision = prior.get("architecture_revision") if isinstance(prior, dict) else None
                except (OSError, UnicodeError, json.JSONDecodeError):
                    prior_revision = None
                if not isinstance(prior_revision, int) or isinstance(prior_revision, bool):
                    prior_manifest_unreadable = True
                    prior_revision = 0
                expected_arch_revision = prior_revision + 1
            if data.get("architecture_revision") != expected_arch_revision:
                hard.append(
                    "H3 proposed architecture_revision must be "
                    f"{expected_arch_revision} for this package history"
                )
    revision_reset = data.get("revision_reset")
    reset_record_allowed = prior_manifest_unreadable or (
        status in PUBLISHED_STATUSES and data.get("architecture_revision") == 1
    )
    if prior_manifest_unreadable and not isinstance(revision_reset, dict):
        hard.append(
            "H3 unreadable prior architecture requires a human-recorded "
            "revision_reset disposition"
        )
    if revision_reset is not None:
        if not reset_record_allowed:
            hard.append(
                "H3 revision_reset is allowed only for a human-approved unreadable "
                "prior-package reset at architecture_revision 1"
            )
        if not isinstance(revision_reset, dict):
            hard.append(
                "H3 revision_reset must be an object"
            )
        else:
            if set(revision_reset) != {"reason", "recorded_by", "gate"}:
                hard.append(
                    "H3 revision_reset must contain exactly reason, recorded_by, and gate"
                )
            if revision_reset.get("recorded_by") != "human":
                hard.append("H3 revision_reset.recorded_by must be 'human'")
            if revision_reset.get("gate") != "Invalid Architecture Package Recovery":
                hard.append(
                    "H3 revision_reset.gate must be "
                    "'Invalid Architecture Package Recovery'"
                )
            if not isinstance(revision_reset.get("reason"), str) or not revision_reset.get("reason", "").strip():
                hard.append("H3 revision_reset.reason must be non-empty")

    # H4 — complete, current source hashes.
    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        hard.append("H4 sources must be a non-empty list")
        source_rows: list[dict] = []
    else:
        source_rows = _objects(sources)
        if len(source_rows) != len(sources):
            hard.append("H4 every sources entry must be an object")
    source_paths: set[str] = set()
    source_kinds: dict[str, str] = {}
    for idx, row in enumerate(source_rows):
        value = row.get("path")
        if not isinstance(value, str) or value in source_paths:
            hard.append(f"H4 sources[{idx}].path must be a unique repository-relative string")
            continue
        source_paths.add(value)
        path = _repo_path(repo_root, value)
        if path is None or not path.is_file():
            hard.append(f"H4 source path does not resolve to a file: {value}")
            continue
        expected = row.get("sha256")
        source_kind = row.get("kind")
        if isinstance(source_kind, str):
            source_kinds[value] = source_kind
        if not isinstance(expected, str) or not SHA_RE.match(expected):
            hard.append(f"H4 source {value} sha256 must be 64 lowercase hex characters")
        else:
            actual = _sha256(path)
            if expected != actual:
                detail = (
                    f"H4 stale source hash for {value}: expected {expected}, "
                    f"current {actual}"
                )
                if consumer and source_kind == "repository":
                    advisory.append(
                        f"A1 repository evidence drift while consuming package: {detail}"
                    )
                else:
                    hard.append(detail)
        if source_kind not in {"plan", "brief", "adr", "repository", "reference"}:
            hard.append(f"H4 source {value} has invalid kind {source_kind!r}")
    if plan_dir.is_dir() and _inside(repo_root, plan_dir):
        plan_rel = plan_dir.resolve().relative_to(repo_root.resolve()).as_posix()
        required_sources = {f"{plan_rel}/{name}" for name in REQUIRED_PLAN_FILES}
        for row in plan_rows:
            feature_file = row.get("file") or f"features/{row.get('id', '')}.md"
            required_sources.add(f"{plan_rel}/{feature_file}")
        absent_sources = sorted(required_sources - source_paths)
        if absent_sources:
            hard.append(f"H4 required stale-detection source(s) absent: {', '.join(absent_sources)}")
        wrong_plan_kinds = sorted(
            path for path in required_sources if source_kinds.get(path) != "plan"
        )
        if wrong_plan_kinds:
            hard.append(
                "H4 required plan source(s) must use kind 'plan': "
                f"{', '.join(wrong_plan_kinds)}"
            )
    for path, expected_kind in sorted(
        (
            (path, "brief")
            if path.startswith("docs/briefs/")
            else (path, "adr")
            for path in source_paths
            if path.startswith("docs/briefs/") or path.startswith("docs/adr/")
        )
    ):
        if source_kinds.get(path) != expected_kind:
            hard.append(
                f"H4 source {path} must use canonical kind {expected_kind!r}"
            )

    # H5 — coverage posture.
    coverage = data.get("coverage")
    if not isinstance(coverage, dict):
        hard.append("H5 coverage must be an object")
        coverage = {}
    missing_coverage = sorted(COVERAGE_KEYS - set(coverage))
    extra_coverage = sorted(set(coverage) - COVERAGE_KEYS)
    if missing_coverage:
        hard.append(f"H5 missing coverage dimension(s): {', '.join(missing_coverage)}")
    if extra_coverage:
        hard.append(f"H5 unknown coverage dimension(s): {', '.join(extra_coverage)}")
    gap_count = 0
    for key in sorted(COVERAGE_KEYS):
        row = coverage.get(key)
        if not isinstance(row, dict):
            hard.append(f"H5 coverage.{key} must be an object")
            continue
        state = row.get("status")
        if state not in COVERAGE_STATES:
            hard.append(f"H5 coverage.{key}.status must be one of {sorted(COVERAGE_STATES)}")
        if not isinstance(row.get("reason"), str) or not row.get("reason", "").strip():
            hard.append(f"H5 coverage.{key}.reason must be non-empty")
        material = row.get("material")
        if not isinstance(material, bool):
            hard.append(f"H5 coverage.{key}.material must be boolean")
        if state == "gap":
            gap_count += 1
            if material is True:
                hard.append(f"H5 material coverage gap blocks publication: {key}")
        elif material is True:
            hard.append(f"H5 coverage.{key}.material may be true only for a gap")
    if status == "approved" and gap_count:
        hard.append("H5 status approved cannot contain coverage gaps")
    if status == "approved-with-gaps" and gap_count == 0:
        hard.append("H5 status approved-with-gaps requires at least one coverage gap")

    # H6 — id graphs, provenance, data ownership, and plan references.
    unknown_claims = 0
    components, component_ids = _ids(data.get("components"), "component", hard, "H6 components")
    component_declared_features: dict[str, set[str]] = {}
    if not components:
        hard.append("H6 components must contain at least one component")
    for row in components:
        label = f"H6 component {row.get('id')}"
        unknown_claims += int(_evidence_state(row, label, hard))
        _evidence_refs(row, label, source_kinds, hard)
        if not isinstance(row.get("name"), str) or not row.get("name", "").strip():
            hard.append(f"{label}.name must be non-empty")
        if row.get("kind") not in COMPONENT_KINDS:
            hard.append(f"H6 component {row.get('id')} has invalid kind {row.get('kind')!r}")
        mapped = set(_string_list(row.get("features")))
        if isinstance(row.get("id"), str):
            component_declared_features[row["id"]] = mapped
        if not mapped:
            hard.append(f"{label}.features must contain at least one plan feature")
        unknown = sorted(mapped - feature_ids)
        if unknown:
            hard.append(f"H6 component {row.get('id')} references unknown feature(s): {', '.join(unknown)}")
        if not _string_list(row.get("responsibilities")):
            hard.append(f"H6 component {row.get('id')} needs at least one responsibility")

    relationships, relationship_ids = _ids(
        data.get("relationships"), "relationship", hard, "H6 relationships"
    )
    for row in relationships:
        label = f"H6 relationship {row.get('id')}"
        unknown_claims += int(_evidence_state(row, label, hard))
        _evidence_refs(row, label, source_kinds, hard)
        if not isinstance(row.get("interaction"), str) or not row.get("interaction", "").strip():
            hard.append(f"{label}.interaction must be non-empty")
        for endpoint in ("from", "to"):
            if row.get(endpoint) not in component_ids:
                hard.append(
                    f"H6 relationship {row.get('id')} {endpoint} references unknown "
                    f"component {row.get(endpoint)!r}"
                )

    nodes, node_ids = _ids(data.get("deployment_nodes"), "node", hard, "H6 deployment_nodes")
    for row in nodes:
        label = f"H6 deployment node {row.get('id')}"
        unknown_claims += int(_evidence_state(row, label, hard))
        _evidence_refs(row, label, source_kinds, hard)
        if row.get("evidence_state") not in {"recorded", "observed"}:
            hard.append(f"{label}.evidence_state must be recorded or observed")
        for field in ("name", "environment"):
            if not isinstance(row.get(field), str) or not row.get(field, "").strip():
                hard.append(f"{label}.{field} must be non-empty")
        claims = row.get("evidence_claims")
        if not isinstance(claims, dict) or set(claims) != {"name", "environment"}:
            hard.append(
                f"{label}.evidence_claims must have exactly name and environment selectors"
            )
            claims = {}
        for field in ("name", "environment"):
            claim = claims.get(field)
            if not isinstance(claim, dict):
                hard.append(f"{label}.evidence_claims.{field} must be an object")
                continue
            claim_path = claim.get("path")
            literal = claim.get("literal")
            if claim.get("derivation") != row.get(field):
                hard.append(
                    f"{label}.evidence_claims.{field}.derivation must equal the "
                    f"normalized node {field}"
                )
            if claim_path not in _string_list(row.get("evidence")):
                hard.append(
                    f"{label}.evidence_claims.{field}.path must be listed in node evidence"
                )
                continue
            source_path = _repo_path(repo_root, claim_path)
            if not isinstance(literal, str) or not literal.strip():
                hard.append(
                    f"{label}.evidence_claims.{field}.literal must be non-empty"
                )
                continue
            try:
                source_text = (
                    source_path.read_text(encoding="utf-8")
                    if source_path is not None and source_path.is_file()
                    else ""
                )
            except (OSError, UnicodeError):
                source_text = ""
            if literal not in source_text:
                hard.append(
                    f"{label}.evidence_claims.{field}.literal does not occur in "
                    f"{claim_path!r}; otherwise record a deployment coverage gap"
                )
    deployments = data.get("deployments")
    if not isinstance(deployments, list):
        hard.append("H6 deployments must be a list")
        deployments = []
    deployment_rows = _objects(deployments)
    if len(deployment_rows) != len(deployments):
        hard.append("H6 deployments entries must be objects")
    for idx, row in enumerate(deployment_rows):
        label = f"H6 deployments[{idx}]"
        unknown_claims += int(_evidence_state(row, label, hard))
        _evidence_refs(row, label, source_kinds, hard)
        if row.get("component_id") not in component_ids:
            hard.append(f"H6 deployments[{idx}] references unknown component {row.get('component_id')!r}")
        raw_node_ids = row.get("node_ids")
        mapped_node_ids = set(_string_list(raw_node_ids))
        if (
            not isinstance(raw_node_ids, list)
            or len(mapped_node_ids) != len(raw_node_ids)
            or not mapped_node_ids
        ):
            hard.append(f"H6 deployments[{idx}].node_ids must be a non-empty unique string list")
        unknown_nodes = sorted(mapped_node_ids - node_ids)
        if unknown_nodes:
            hard.append(f"H6 deployments[{idx}] references unknown node(s): {', '.join(unknown_nodes)}")
    deployment_counts: dict[str, int] = {}
    for row in deployment_rows:
        component_id = row.get("component_id")
        if isinstance(component_id, str):
            deployment_counts[component_id] = deployment_counts.get(component_id, 0) + 1
    duplicates = sorted(
        component_id
        for component_id, count in deployment_counts.items()
        if count > 1
    )
    if duplicates:
        hard.append(
            f"H6 components have duplicate deployment mappings: {', '.join(duplicates)}"
        )
    deployment_coverage = coverage.get("deployment")
    deployment_state = (
        deployment_coverage.get("status")
        if isinstance(deployment_coverage, dict)
        else None
    )
    if deployment_state == "complete":
        required_deployments = {
            row.get("id")
            for row in components
            if row.get("kind") != "external-system" and isinstance(row.get("id"), str)
        }
        missing_deployments = sorted(required_deployments - set(deployment_counts))
        if missing_deployments:
            hard.append(
                "H6 deployment coverage is complete but component mapping(s) are "
                f"missing: {', '.join(missing_deployments)}"
            )

    data_entities, data_ids = _ids(
        data.get("data_entities"), "data", hard, "H6 data_entities"
    )
    data_declared_features: dict[str, set[str]] = {}
    plan_data_rows = _plan_data_rows(plan_dir)
    plan_data_nouns = set(plan_data_rows)
    data_coverage = coverage.get("data")
    data_coverage_state = (
        data_coverage.get("status") if isinstance(data_coverage, dict) else None
    )
    if data_coverage_state == "complete" and not data_entities:
        hard.append("H6 data coverage is complete but data_entities is empty")
    projected_data_nouns = [
        row.get("name").strip().strip("`")
        for row in data_entities
        if isinstance(row.get("name"), str) and row.get("name", "").strip()
    ]
    duplicate_data_nouns = sorted(
        {noun for noun in projected_data_nouns if projected_data_nouns.count(noun) > 1}
    )
    if duplicate_data_nouns:
        hard.append(
            "H6 data_entities duplicate plan durable noun(s): "
            f"{', '.join(duplicate_data_nouns)}"
        )
    if data_coverage_state == "complete":
        missing_data_nouns = sorted(plan_data_nouns - set(projected_data_nouns))
        if missing_data_nouns:
            hard.append(
                "H6 data coverage is complete but plan durable noun(s) are missing: "
                f"{', '.join(missing_data_nouns)}"
            )
    elif data_coverage_state == "gap":
        missing_data_nouns = sorted(plan_data_nouns - set(projected_data_nouns))
        gap_reason = data_coverage.get("reason", "") if isinstance(data_coverage, dict) else ""
        undispositioned = [noun for noun in missing_data_nouns if noun not in gap_reason]
        if undispositioned:
            hard.append(
                "H6 data coverage gap reason must name each omitted plan durable noun: "
                f"{', '.join(undispositioned)}"
            )
    if data_coverage_state == "not-applicable" and plan_data_nouns:
        hard.append(
            "H6 data coverage cannot be not-applicable while the plan owns durable "
            f"noun(s): {', '.join(sorted(plan_data_nouns))}"
        )
    for row in data_entities:
        label = f"H6 data entity {row.get('id')}"
        unknown_claims += int(_evidence_state(row, label, hard))
        _evidence_refs(row, label, source_kinds, hard)
        noun = row.get("name")
        data_class = row.get("data_class")
        if not isinstance(noun, str) or not noun.strip():
            hard.append(f"{label}.name must be non-empty")
        if not isinstance(data_class, str) or not data_class.strip():
            hard.append(f"{label}.data_class must be non-empty")
        if row.get("source_of_truth") not in component_ids:
            hard.append(
                f"{label}.source_of_truth references unknown component "
                f"{row.get('source_of_truth')!r}"
            )
        for field in ("writers", "readers"):
            raw_refs = row.get(field)
            refs = set(_string_list(raw_refs))
            if not isinstance(raw_refs, list) or len(refs) != len(raw_refs):
                hard.append(f"{label}.{field} must be a unique string list")
            if field == "writers" and not refs:
                hard.append(f"{label}.writers must contain at least one component")
            unknown = sorted(refs - component_ids)
            if unknown:
                hard.append(
                    f"{label}.{field} references unknown component(s): "
                    f"{', '.join(unknown)}"
                )
        declared_features = set(_string_list(row.get("features")))
        if isinstance(row.get("id"), str):
            data_declared_features[row["id"]] = declared_features
        unknown_features = sorted(declared_features - feature_ids)
        if not declared_features:
            hard.append(f"{label}.features must contain at least one plan feature")
        if unknown_features:
            hard.append(
                f"{label}.features references unknown feature(s): "
                f"{', '.join(unknown_features)}"
            )
        if not _plan_trace_resolves(plan_dir, row.get("plan_trace")):
            hard.append(f"{label}.plan_trace does not resolve to a plan heading")
        data_trace_path, _, data_trace_fragment = str(row.get("plan_trace", "")).partition("#")
        if data_trace_path != "feature-plan.md" or data_trace_fragment != "durable-state-closure":
            hard.append(
                f"{label}.plan_trace must target feature-plan.md#durable-state-closure"
            )
        lifecycle = row.get("lifecycle")
        if not isinstance(lifecycle, dict) or set(lifecycle) != LIFECYCLE_KEYS:
            hard.append(
                f"{label}.lifecycle must have exactly {sorted(LIFECYCLE_KEYS)}"
            )
            lifecycle = {}
        plan_cells = _plan_data_cells(plan_dir, noun)
        if not plan_cells:
            hard.append(f"{label} noun {noun!r} does not resolve to a plan data row")
        else:
            for field, value in (("data_class", data_class), *sorted(lifecycle.items())):
                if not isinstance(value, str) or not value.strip():
                    hard.append(f"{label}.{field} must be non-empty")
                    continue
                plan_column = "data-class" if field == "data_class" else field
                expected_value = plan_cells.get(plan_column)
                if value != expected_value:
                    hard.append(
                        f"{label}.{field} value {value!r} does not match plan column "
                        f"{plan_column!r} value {expected_value!r}"
                    )

    integrations, integration_ids = _ids(
        data.get("integration_flows"), "integration", hard, "H6 integration_flows"
    )
    integration_declared_features: dict[str, set[str]] = {}
    integration_coverage = coverage.get("integrations")
    if (
        isinstance(integration_coverage, dict)
        and integration_coverage.get("status") == "complete"
        and not integrations
    ):
        hard.append("H6 integration coverage is complete but integration_flows is empty")
    threat_text = ""
    interaction_text = ""
    plan_threat_ids = _plan_contract_ids(plan_dir, "threat-model.md", "TZ")
    plan_interaction_ids = _plan_contract_ids(
        plan_dir, "interaction-contract.md", "IC"
    )
    projected_contract_refs: set[str] = set()
    for name, target in (("threat-model.md", "threat"), ("interaction-contract.md", "interaction")):
        path = plan_dir / name
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            content = ""
        if target == "threat":
            threat_text = content
        else:
            interaction_text = content
    for row in integrations:
        label = f"H6 integration {row.get('id')}"
        unknown_claims += int(_evidence_state(row, label, hard))
        _evidence_refs(row, label, source_kinds, hard)
        for endpoint in ("producer", "consumer"):
            if row.get(endpoint) not in component_ids:
                hard.append(
                    f"H6 integration {row.get('id')} {endpoint} references unknown "
                    f"component {row.get(endpoint)!r}"
                )
        declared_features = set(_string_list(row.get("features")))
        if isinstance(row.get("id"), str):
            integration_declared_features[row["id"]] = declared_features
        unknown_features = sorted(declared_features - feature_ids)
        if not declared_features:
            hard.append(
                f"H6 integration {row.get('id')} features must contain at least one plan feature"
            )
        if unknown_features:
            hard.append(f"H6 integration {row.get('id')} references unknown feature(s): {', '.join(unknown_features)}")
        if not _plan_trace_resolves(plan_dir, row.get("plan_trace")):
            hard.append(f"H6 integration {row.get('id')} plan_trace does not resolve to a plan heading")
        trace_path, _, trace_fragment = str(row.get("plan_trace", "")).partition("#")
        if trace_path != "feature-plan.md":
            hard.append(
                f"H6 integration {row.get('id')} plan_trace must target feature-plan.md"
            )
        if trace_fragment not in {"journey-map", "dependency-flow", "durable-state-closure"}:
            hard.append(
                f"H6 integration {row.get('id')} plan_trace must target Journey Map, "
                "Dependency Flow, or Durable-State Closure"
            )
        flow_data_ids = set(_string_list(row.get("data_entity_ids")))
        raw_flow_data_ids = row.get("data_entity_ids")
        if not isinstance(raw_flow_data_ids, list) or len(flow_data_ids) != len(raw_flow_data_ids):
            hard.append(
                f"H6 integration {row.get('id')} data_entity_ids must be a unique string list"
            )
        unknown_data = sorted(flow_data_ids - data_ids)
        if unknown_data:
            hard.append(
                f"H6 integration {row.get('id')} references unknown data entity id(s): "
                f"{', '.join(unknown_data)}"
            )
        source_of_truth = row.get("source_of_truth")
        if source_of_truth not in component_ids:
            hard.append(
                f"H6 integration {row.get('id')} source_of_truth references unknown "
                f"component {source_of_truth!r}"
            )
        for field in ("protocol", "failure_behavior"):
            if not isinstance(row.get(field), str) or not row.get(field, "").strip():
                hard.append(f"H6 integration {row.get('id')} {field} must be non-empty")
        if not _string_list(row.get("data")):
            hard.append(f"H6 integration {row.get('id')} data must be non-empty")
        raw_contract_refs = row.get("contract_refs")
        contract_refs = _string_list(raw_contract_refs)
        projected_contract_refs.update(contract_refs)
        if not isinstance(raw_contract_refs, list) or len(set(contract_refs)) != len(raw_contract_refs):
            hard.append(
                f"H6 integration {row.get('id')} contract_refs must be a unique string list"
            )
        for ref in contract_refs:
            if not CONTRACT_ID_RE.match(ref):
                hard.append(f"H6 integration {row.get('id')} has invalid contract ref {ref!r}")
            elif ref.startswith("TZ-") and not _contains_exact_id(threat_text, ref):
                hard.append(f"H6 integration {row.get('id')} references unknown threat id {ref}")
            elif ref.startswith("IC-") and not _contains_exact_id(interaction_text, ref):
                hard.append(f"H6 integration {row.get('id')} references unknown interaction id {ref}")
    security_coverage = coverage.get("security")
    security_state = (
        security_coverage.get("status")
        if isinstance(security_coverage, dict)
        else None
    )
    integration_state = (
        integration_coverage.get("status")
        if isinstance(integration_coverage, dict)
        else None
    )
    missing_threat_ids = sorted(plan_threat_ids - projected_contract_refs)
    missing_interaction_ids = sorted(plan_interaction_ids - projected_contract_refs)
    if security_state == "complete" and missing_threat_ids:
        hard.append(
            "H6 security coverage is complete but plan TZ obligation(s) are missing: "
            f"{', '.join(missing_threat_ids)}"
        )
    if integration_state == "complete" and missing_interaction_ids:
        hard.append(
            "H6 integration coverage is complete but plan IC obligation(s) are missing: "
            f"{', '.join(missing_interaction_ids)}"
        )
    if security_state == "gap":
        security_reason = (
            security_coverage.get("reason", "")
            if isinstance(security_coverage, dict)
            else ""
        )
        undispositioned = [
            ref for ref in missing_threat_ids if not _contains_exact_id(security_reason, ref)
        ]
        if undispositioned:
            hard.append(
                "H6 security coverage gap reason must name each omitted TZ obligation: "
                f"{', '.join(undispositioned)}"
            )
    if integration_state == "gap":
        integration_reason = (
            integration_coverage.get("reason", "")
            if isinstance(integration_coverage, dict)
            else ""
        )
        undispositioned = [
            ref
            for ref in missing_interaction_ids
            if not _contains_exact_id(integration_reason, ref)
        ]
        if undispositioned:
            hard.append(
                "H6 integration coverage gap reason must name each omitted IC obligation: "
                f"{', '.join(undispositioned)}"
            )
    if security_state == "not-applicable" and plan_threat_ids:
        hard.append(
            "H6 security coverage cannot be not-applicable while the plan owns TZ "
            f"obligation(s): {', '.join(sorted(plan_threat_ids))}"
        )
    if integration_state == "not-applicable" and plan_interaction_ids:
        hard.append(
            "H6 integration coverage cannot be not-applicable while the plan owns IC "
            f"obligation(s): {', '.join(sorted(plan_interaction_ids))}"
        )

    qualities, quality_ids = _ids(
        data.get("quality_scenarios"), "quality", hard, "H6 quality_scenarios"
    )
    quality_declared_features: dict[str, set[str]] = {}
    quality_coverage = coverage.get("quality_attributes")
    if (
        isinstance(quality_coverage, dict)
        and quality_coverage.get("status") == "complete"
        and not qualities
    ):
        hard.append("H6 quality coverage is complete but quality_scenarios is empty")
    for row in qualities:
        label = f"H6 quality {row.get('id')}"
        unknown_claims += int(_evidence_state(row, label, hard))
        declared_features = set(_string_list(row.get("features")))
        if isinstance(row.get("id"), str):
            quality_declared_features[row["id"]] = declared_features
        unknown_features = sorted(declared_features - feature_ids)
        if not declared_features:
            hard.append(f"{label}.features must contain at least one plan feature")
        if unknown_features:
            hard.append(f"H6 quality {row.get('id')} references unknown feature(s): {', '.join(unknown_features)}")
        target = row.get("target")
        source = row.get("source")
        for field in ("attribute", "stimulus", "environment", "response", "tactic", "verification"):
            if not isinstance(row.get(field), str) or not row.get(field, "").strip():
                hard.append(f"{label}.{field} must be non-empty")
        if source not in source_paths:
            hard.append(f"{label}.source must be a tracked stale-detection source")
        source_kind = source_kinds.get(source)
        if row.get("evidence_state") == "recorded" and source_kind not in {
            "plan", "brief", "adr", "reference"
        }:
            hard.append(f"{label} recorded evidence must cite a recorded source kind")
        if row.get("evidence_state") == "observed" and source_kind != "repository":
            hard.append(f"{label} observed evidence must cite a repository source")
        if not isinstance(target, str) or not target.strip():
            hard.append(f"H6 quality {row.get('id')} target must be a non-empty string or 'unknown'")
        elif target != "unknown":
            source_path = _repo_path(repo_root, source)
            if source_path is None or not source_path.is_file():
                hard.append(f"H6 quality {row.get('id')} source does not resolve: {source!r}")
            else:
                try:
                    source_text = source_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    source_text = ""
                if target not in source_text:
                    hard.append(
                        f"H6 quality {row.get('id')} target {target!r} does not occur "
                        f"literally in cited source {source}"
                    )
        elif isinstance(quality_coverage, dict) and quality_coverage.get("status") != "gap":
            hard.append(
                f"{label} target unknown requires quality_attributes coverage gap"
            )

    mappings = data.get("feature_mappings")
    if not isinstance(mappings, list):
        hard.append("H6 feature_mappings must be a list")
        mappings = []
    mapping_rows = _objects(mappings)
    if len(mapping_rows) != len(mappings):
        hard.append("H6 feature_mappings entries must be objects")
    mapped_ids: list[str] = []
    mapped_component_refs: set[str] = set()
    mapped_data_refs: set[str] = set()
    mapped_integration_refs: set[str] = set()
    mapped_quality_refs: set[str] = set()
    for idx, row in enumerate(mapping_rows):
        feature_id = row.get("feature_id")
        unknown_claims += int(
            _evidence_state(row, f"H6 feature mapping {feature_id!r}", hard)
        )
        _evidence_refs(
            row,
            f"H6 feature mapping {feature_id!r}",
            source_kinds,
            hard,
        )
        if feature_id not in feature_ids:
            hard.append(f"H6 feature_mappings[{idx}] references unknown feature {feature_id!r}")
        elif feature_id in mapped_ids:
            hard.append(f"H6 feature_mappings duplicates feature {feature_id}")
        else:
            mapped_ids.append(feature_id)
        component_refs = set(_string_list(row.get("component_ids")))
        mapped_component_refs.update(component_refs)
        if not component_refs:
            hard.append(f"H6 feature mapping {feature_id!r} must reference at least one component")
        for field, refs, valid in (
            ("component_ids", component_refs, component_ids),
            ("data_ids", set(_string_list(row.get("data_ids"))), data_ids),
            ("integration_ids", set(_string_list(row.get("integration_ids"))), integration_ids),
            ("quality_ids", set(_string_list(row.get("quality_ids"))), quality_ids),
        ):
            if field == "data_ids":
                mapped_data_refs.update(refs)
            elif field == "integration_ids":
                mapped_integration_refs.update(refs)
            elif field == "quality_ids":
                mapped_quality_refs.update(refs)
            unknown = sorted(refs - valid)
            if unknown:
                hard.append(f"H6 feature mapping {feature_id!r} {field} has unknown id(s): {', '.join(unknown)}")
        if row.get("architecture_disposition") not in DISPOSITIONS:
            hard.append(
                f"H6 feature mapping {feature_id!r} architecture_disposition must be "
                f"one of {sorted(DISPOSITIONS)}"
            )
    missing_mappings = sorted(feature_ids - set(mapped_ids))
    if missing_mappings:
        hard.append(f"H6 plan feature(s) missing exactly-one mapping: {', '.join(missing_mappings)}")
    for label, all_ids, used_ids in (
        ("component", component_ids, mapped_component_refs),
        ("data entity", data_ids, mapped_data_refs),
        ("integration", integration_ids, mapped_integration_refs),
        ("quality", quality_ids, mapped_quality_refs),
    ):
        orphaned = sorted(all_ids - used_ids)
        if orphaned:
            hard.append(
                f"H6 orphaned {label} id(s) absent from feature mappings: "
                f"{', '.join(orphaned)}"
            )
    for label, field, declared_by_id in (
        ("component", "component_ids", component_declared_features),
        ("data entity", "data_ids", data_declared_features),
        ("integration", "integration_ids", integration_declared_features),
        ("quality", "quality_ids", quality_declared_features),
    ):
        for structural_id, declared_features in sorted(declared_by_id.items()):
            projected_features = {
                row.get("feature_id")
                for row in mapping_rows
                if structural_id in set(_string_list(row.get(field)))
                and row.get("feature_id") in feature_ids
            }
            if declared_features != projected_features:
                hard.append(
                    f"H6 {label} {structural_id} feature declaration "
                    f"{sorted(declared_features)} disagrees with feature mappings "
                    f"{sorted(projected_features)}"
                )

    # H7 — decisions, open material calls, and approval consistency.
    decisions, _ = _ids(data.get("decisions"), "decision", hard, "H7 decisions")
    for row in decisions:
        label = f"H7 decision {row.get('id')}"
        unknown_claims += int(_evidence_state(row, label, hard))
        _evidence_refs(row, label, source_kinds, hard)
        if row.get("status") != "accepted":
            hard.append(f"H7 decision {row.get('id')} status must be accepted in a published package")
        if not isinstance(row.get("summary"), str) or not row.get("summary", "").strip():
            hard.append(f"{label}.summary must be non-empty")
        unknown_features = sorted(set(_string_list(row.get("features"))) - feature_ids)
        if not _string_list(row.get("features")):
            hard.append(f"{label}.features must contain at least one plan feature")
        if unknown_features:
            hard.append(f"H7 decision {row.get('id')} references unknown feature(s): {', '.join(unknown_features)}")
        adr = row.get("adr_path")
        if adr not in (None, ""):
            if adr not in set(_string_list(row.get("evidence"))):
                hard.append(f"{label} ADR path must be included in decision evidence")
            adr_path = _repo_path(repo_root, adr)
            if adr_path is None or not adr_path.is_file():
                hard.append(f"H7 decision {row.get('id')} ADR path does not resolve: {adr!r}")
            else:
                try:
                    adr_text = adr_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    adr_text = ""
                adr_statuses = re.findall(
                    r"(?im)^status\s*:\s*([a-z][a-z-]*)\s*$", adr_text
                )
                if len(adr_statuses) != 1 or adr_statuses[0].casefold() != "accepted":
                    hard.append(
                        f"H7 decision {row.get('id')} ADR must contain exactly one "
                        f"canonical Status: accepted line: {adr} (found {adr_statuses!r})"
                    )
    open_questions = data.get("open_questions")
    if not isinstance(open_questions, list):
        hard.append("H7 open_questions must be a list")
        open_questions = []
    for idx, item in enumerate(open_questions):
        if not isinstance(item, dict):
            hard.append(f"H7 open_questions[{idx}] must be an object")
        else:
            if not isinstance(item.get("question"), str) or not item.get("question", "").strip():
                hard.append(f"H7 open_questions[{idx}].question must be non-empty")
            if not isinstance(item.get("material"), bool):
                hard.append(f"H7 open_questions[{idx}].material must be boolean")
            elif item.get("material") is True:
                hard.append(f"H7 material open question blocks publication: {item.get('question', idx)!r}")
    if status == "approved" and open_questions:
        hard.append("H7 status approved cannot contain open questions")
    risks, _ = _ids(data.get("risks"), "risk", hard, "H7 risks")
    for row in risks:
        label = f"H7 risk {row.get('id')}"
        unknown_claims += int(_evidence_state(row, label, hard))
        _evidence_refs(row, label, source_kinds, hard)
        for field in ("statement", "owner", "mitigation"):
            if not isinstance(row.get(field), str) or not row.get(field, "").strip():
                hard.append(f"{label}.{field} must be non-empty")
    if unknown_claims and gap_count == 0:
        hard.append(
            "H7 unknown structural claim(s) require an explicit coverage gap"
        )
    approval = data.get("approval")
    if not isinstance(approval, dict):
        hard.append("H7 approval must be an object")
    elif status == "proposed":
        if approval.get("decision") != "pending":
            hard.append("H7 proposed package approval.decision must be pending")
        if approval.get("recorded_by") != "pending":
            hard.append("H7 proposed package approval.recorded_by must be pending")
        if approval.get("gate") != "Final Architecture Approval":
            hard.append("H7 approval.gate must be 'Final Architecture Approval'")
    else:
        if approval.get("decision") != status:
            hard.append("H7 approval.decision must equal package status")
        if approval.get("recorded_by") != "human":
            hard.append("H7 approval.recorded_by must be 'human'")
        if approval.get("gate") != "Final Architecture Approval":
            hard.append("H7 approval.gate must be 'Final Architecture Approval'")

    # H8 — authoritative Markdown tables project the JSON graph row-by-row.
    # Prose and Mermaid may repeat ids, but cannot satisfy this contract.
    direction_table = _projection_table(
        markdown, "solution-architecture.md", "Selected Direction Realization",
        {
            "exploration", "option", "selection binding",
            "realization summary", "evidence state", "evidence",
        },
        hard,
        require_rows=True,
    )
    direction = (
        plan.get("architecture_disposition", {}).get("direction", {})
        if isinstance(plan.get("architecture_disposition"), dict)
        else {}
    )
    direction_rows = direction_table["rows"] if direction_table is not None else []
    if len(direction_rows) != 1:
        hard.append(
            "H8 solution-architecture.md ## Selected Direction Realization "
            "must contain exactly one authoritative row"
        )
    elif isinstance(direction, dict):
        row = direction_rows[0]
        expected_option = direction.get("selected_option_id") or "None"
        expected_binding = [
            _plain_cell(str(direction.get("status", ""))),
            _plain_cell(str(direction.get("selected_option_sha256") or "None")),
        ]
        exact_cells = (
            ("exploration", direction.get("exploration_id")),
            ("option", expected_option),
            ("evidence state", "recorded"),
            ("evidence", f"docs/plans/{slug}/architecture-selection.json"),
        )
        for column, expected in exact_cells:
            if _plain_cell(row.get(column, "")) != _plain_cell(str(expected or "")):
                hard.append(
                    "H8 selected-direction projection "
                    f"{column!r} must equal {expected!r}"
                )
        actual_binding = _projection_values(row.get("selection binding", ""), "/")
        if actual_binding != expected_binding:
            hard.append(
                "H8 selected-direction projection 'selection binding' must equal "
                "`<status> / <selected-option-sha256-or-None>`"
            )
        if not _plain_cell(row.get("realization summary", "")):
            hard.append(
                "H8 selected-direction projection 'realization summary' must be non-empty"
            )
    driver_table = _projection_table(
        markdown, "solution-architecture.md", "Architecture Drivers",
        {"driver", "evidence state", "source", "architecture consequence"}, hard,
        require_rows=True,
    )
    context_table = _projection_table(
        markdown, "views.md", "System Context",
        {"id", "element", "kind", "responsibility", "evidence state", "evidence"}, hard,
        require_rows=bool(components),
    )
    component_table = _projection_table(
        markdown, "views.md", "Runtime / Container View",
        {
            "component", "name", "kind", "responsibilities", "features",
            "evidence state", "evidence",
        },
        hard,
        require_rows=bool(components),
    )
    relationship_table = _projection_table(
        markdown, "views.md", "Runtime / Container View",
        {"relationship", "from", "to", "interaction", "evidence state", "evidence"}, hard,
        require_rows=bool(relationships),
    )
    node_table = _projection_table(
        markdown, "views.md", "Deployment View",
        {
            "node", "name", "environment", "name selector",
            "environment selector", "evidence state", "evidence",
        },
        hard,
        require_rows=bool(nodes),
    )
    deployment_table = _projection_table(
        markdown, "views.md", "Deployment View",
        {"component", "deployed to", "evidence state", "evidence"}, hard,
        require_rows=bool(deployment_rows),
    )
    data_table = _projection_table(
        markdown, "data-and-integrations.md", "Data Ownership and Lifecycle",
        {
            "id", "durable noun / data set", "data class", "source of truth",
            "writers", "readers", "retain / export / erase", "evidence state",
            "plan trace", "features", "evidence",
        },
        hard,
        require_rows=bool(data_entities),
    )
    integration_table = _projection_table(
        markdown, "data-and-integrations.md", "Integration Flows",
        {
            "flow", "producer", "consumer", "protocol / medium", "data",
            "data entities", "source of truth", "failure behavior",
            "contract refs", "plan trace", "features", "evidence state",
            "evidence",
        },
        hard,
        require_rows=bool(integrations),
    )
    quality_table = _projection_table(
        markdown, "quality-attributes.md", "Quality Scenarios",
        {
            "id", "attribute", "evidence state", "source", "stimulus",
            "environment", "response", "target", "tactic", "verification",
            "features",
        },
        hard,
        require_rows=bool(qualities),
    )
    decision_table = _projection_table(
        markdown, "solution-architecture.md", "Decisions and Rationale",
        {
            "decision", "summary", "evidence state", "status", "adr",
            "affected features", "evidence",
        },
        hard,
        require_rows=bool(decisions),
    )
    mapping_table = _projection_table(
        markdown, "solution-architecture.md", "Feature Traceability",
        {
            "feature", "components", "data entities", "integration flows",
            "quality scenarios", "disposition", "evidence state", "evidence",
        },
        hard,
        require_rows=bool(mapping_rows),
    )
    risk_table = _projection_table(
        markdown, "solution-architecture.md", "Risks and Mitigations",
        {
            "risk", "statement", "evidence state", "owner", "mitigation",
            "evidence",
        },
        hard,
        require_rows=bool(risks),
    )

    # Required narrative tables must carry a real row too, even where their rows
    # do not have a one-to-one manifest collection.
    _ = direction_table, driver_table, context_table

    _projection_markdown_status(markdown, status, gap_count, hard)
    _projection_overview_identity(markdown, data, hard)
    _projection_key_set(
        component_table, "component",
        [row.get("id") for row in components if isinstance(row.get("id"), str)],
        "component table", hard,
    )
    _projection_key_set(
        relationship_table, "relationship",
        [row.get("id") for row in relationships if isinstance(row.get("id"), str)],
        "relationship table", hard,
    )
    _projection_key_set(
        node_table, "node",
        [row.get("id") for row in nodes if isinstance(row.get("id"), str)],
        "deployment node table", hard,
    )
    _projection_key_set(
        deployment_table, "component",
        [
            row.get("component_id")
            for row in deployment_rows
            if isinstance(row.get("component_id"), str)
        ],
        "deployment mapping table", hard,
    )
    _projection_key_set(
        data_table, "id",
        [row.get("id") for row in data_entities if isinstance(row.get("id"), str)],
        "data entity table", hard,
    )
    _projection_key_set(
        integration_table, "flow",
        [row.get("id") for row in integrations if isinstance(row.get("id"), str)],
        "integration table", hard,
    )
    _projection_key_set(
        quality_table, "id",
        [row.get("id") for row in qualities if isinstance(row.get("id"), str)],
        "quality table", hard,
    )
    _projection_key_set(
        mapping_table, "feature",
        [
            row.get("feature_id")
            for row in mapping_rows
            if isinstance(row.get("feature_id"), str)
        ],
        "feature mapping table", hard,
    )
    _projection_key_set(
        decision_table, "decision",
        [row.get("id") for row in decisions if isinstance(row.get("id"), str)],
        "decision table", hard,
    )
    _projection_key_set(
        risk_table, "risk",
        [row.get("id") for row in risks if isinstance(row.get("id"), str)],
        "risk table", hard,
    )

    for item in components:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        label = f"component {item_id}"
        row = _projection_row(component_table, "component", item_id, label, hard)
        _projection_scalar(row, "name", item.get("name"), label, hard)
        _projection_scalar(row, "kind", item.get("kind"), label, hard)
        _projection_list(
            row, "responsibilities", item.get("responsibilities"), label, hard,
            separator=";",
        )
        _projection_scalar(row, "evidence state", item.get("evidence_state"), label, hard)
        _projection_refs(row, "features", item.get("features"), label, hard)
        _projection_list(row, "evidence", item.get("evidence"), label, hard)

    for item in relationships:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        label = f"relationship {item_id}"
        row = _projection_row(relationship_table, "relationship", item_id, label, hard)
        _projection_scalar(row, "from", item.get("from"), label, hard)
        _projection_scalar(row, "to", item.get("to"), label, hard)
        _projection_scalar(row, "interaction", item.get("interaction"), label, hard)
        _projection_scalar(row, "evidence state", item.get("evidence_state"), label, hard)
        _projection_list(row, "evidence", item.get("evidence"), label, hard)

    for item in nodes:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        label = f"deployment node {item_id}"
        row = _projection_row(node_table, "node", item_id, label, hard)
        _projection_scalar(row, "name", item.get("name"), label, hard)
        _projection_scalar(row, "environment", item.get("environment"), label, hard)
        claims = item.get("evidence_claims")
        if isinstance(claims, dict):
            _projection_selector(row, "name selector", claims.get("name"), label, hard)
            _projection_selector(
                row, "environment selector", claims.get("environment"), label, hard
            )
        _projection_scalar(row, "evidence state", item.get("evidence_state"), label, hard)
        _projection_list(row, "evidence", item.get("evidence"), label, hard)

    for item in deployment_rows:
        component_id = item.get("component_id")
        if not isinstance(component_id, str):
            continue
        label = f"deployment mapping {component_id}"
        row = _projection_row(deployment_table, "component", component_id, label, hard)
        _projection_refs(row, "deployed to", item.get("node_ids"), label, hard)
        _projection_scalar(row, "evidence state", item.get("evidence_state"), label, hard)
        _projection_list(row, "evidence", item.get("evidence"), label, hard)

    for item in data_entities:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        label = f"data entity {item_id}"
        row = _projection_row(data_table, "id", item_id, label, hard)
        _projection_scalar(
            row, "durable noun / data set", item.get("name"), label, hard
        )
        _projection_scalar(row, "data class", item.get("data_class"), label, hard)
        _projection_scalar(
            row, "source of truth", item.get("source_of_truth"), label, hard
        )
        _projection_refs(row, "writers", item.get("writers"), label, hard)
        _projection_refs(row, "readers", item.get("readers"), label, hard)
        _projection_lifecycle(row, item.get("lifecycle"), label, hard)
        _projection_scalar(row, "plan trace", item.get("plan_trace"), label, hard)
        _projection_refs(row, "features", item.get("features"), label, hard)
        _projection_scalar(row, "evidence state", item.get("evidence_state"), label, hard)
        _projection_list(row, "evidence", item.get("evidence"), label, hard)

    for item in integrations:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        label = f"integration {item_id}"
        row = _projection_row(integration_table, "flow", item_id, label, hard)
        _projection_scalar(row, "producer", item.get("producer"), label, hard)
        _projection_scalar(row, "consumer", item.get("consumer"), label, hard)
        _projection_scalar(row, "protocol / medium", item.get("protocol"), label, hard)
        _projection_list(
            row, "data", item.get("data"), label, hard, separator=";"
        )
        _projection_refs(row, "data entities", item.get("data_entity_ids"), label, hard)
        _projection_scalar(
            row, "source of truth", item.get("source_of_truth"), label, hard
        )
        _projection_scalar(
            row, "failure behavior", item.get("failure_behavior"), label, hard
        )
        _projection_refs(row, "contract refs", item.get("contract_refs"), label, hard)
        _projection_scalar(row, "plan trace", item.get("plan_trace"), label, hard)
        _projection_refs(row, "features", item.get("features"), label, hard)
        _projection_scalar(row, "evidence state", item.get("evidence_state"), label, hard)
        _projection_list(row, "evidence", item.get("evidence"), label, hard)

    for item in qualities:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        label = f"quality {item_id}"
        row = _projection_row(quality_table, "id", item_id, label, hard)
        for column, field in (
            ("attribute", "attribute"),
            ("source", "source"),
            ("stimulus", "stimulus"),
            ("environment", "environment"),
            ("response", "response"),
            ("target", "target"),
            ("tactic", "tactic"),
            ("verification", "verification"),
        ):
            _projection_scalar(row, column, item.get(field), label, hard)
        _projection_scalar(row, "evidence state", item.get("evidence_state"), label, hard)
        _projection_refs(row, "features", item.get("features"), label, hard)

    for item in mapping_rows:
        feature_id = item.get("feature_id")
        if not isinstance(feature_id, str):
            continue
        label = f"feature mapping {feature_id}"
        row = _projection_row(mapping_table, "feature", feature_id, label, hard)
        _projection_refs(row, "components", item.get("component_ids"), label, hard)
        _projection_refs(row, "data entities", item.get("data_ids"), label, hard)
        _projection_refs(row, "integration flows", item.get("integration_ids"), label, hard)
        _projection_refs(row, "quality scenarios", item.get("quality_ids"), label, hard)
        _projection_scalar(
            row, "disposition", item.get("architecture_disposition"), label, hard
        )
        _projection_scalar(row, "evidence state", item.get("evidence_state"), label, hard)
        _projection_list(row, "evidence", item.get("evidence"), label, hard)

    for item in decisions:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        label = f"decision {item_id}"
        row = _projection_row(decision_table, "decision", item_id, label, hard)
        _projection_scalar(row, "summary", item.get("summary"), label, hard)
        _projection_scalar(row, "status", item.get("status"), label, hard)
        _projection_scalar(row, "evidence state", item.get("evidence_state"), label, hard)
        _projection_refs(row, "affected features", item.get("features"), label, hard)
        _projection_optional_scalar(row, "adr", item.get("adr_path"), label, hard)
        _projection_list(row, "evidence", item.get("evidence"), label, hard)

    for item in risks:
        item_id = item.get("id")
        if not isinstance(item_id, str):
            continue
        label = f"risk {item_id}"
        row = _projection_row(risk_table, "risk", item_id, label, hard)
        _projection_scalar(row, "statement", item.get("statement"), label, hard)
        _projection_scalar(row, "evidence state", item.get("evidence_state"), label, hard)
        _projection_scalar(row, "owner", item.get("owner"), label, hard)
        _projection_scalar(row, "mitigation", item.get("mitigation"), label, hard)
        _projection_list(row, "evidence", item.get("evidence"), label, hard)

    # Hard authority boundary; qualitative architecture truth remains human-owned.
    all_markdown = "\n".join(markdown.values()).lower()
    prohibited_claims: set[str] = set()
    for line in all_markdown.splitlines():
        for phrase in (
            "approved for deployment",
            "certified compliant",
            "compliance attestation",
            "deployment approved",
            "deployment authorized",
            "production approved",
            "production ready",
            "ready for production",
            "release approved",
            "approved to release",
            "security accepted",
            "security approved",
            "certified for compliance",
        ):
            start = line.find(phrase)
            while start >= 0:
                prefix = line[max(0, start - 80):start]
                negated = re.search(
                    r"\b(?:not|never|no|without)\b[^.!?]{0,70}$",
                    prefix,
                )
                if not negated:
                    prohibited_claims.add(phrase)
                start = line.find(phrase, start + len(phrase))
    for phrase in sorted(prohibited_claims):
        hard.append(f"H8 prohibited authority claim {phrase!r}")
    deployment_coverage = coverage.get("deployment")
    deployment_state = (
        deployment_coverage.get("status")
        if isinstance(deployment_coverage, dict)
        else None
    )
    if not nodes and deployment_state == "complete":
        hard.append("H8 deployment coverage is complete but deployment_nodes is empty")

    return hard, advisory


def _v2_exact(
    value: object,
    label: str,
    fields: tuple[str, ...],
    hard: list[str],
) -> dict:
    if not isinstance(value, dict):
        hard.append(f"H2 {label} must be an object")
        return {}
    missing = [field for field in fields if field not in value]
    extra = sorted(set(value) - set(fields))
    if missing:
        hard.append(f"H2 {label} is missing key(s): {', '.join(missing)}")
    if extra:
        hard.append(f"H2 {label} has unknown key(s): {', '.join(extra)}")
    return value


def _v2_nonempty_string(value: object, label: str, hard: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        hard.append(f"H2 {label} must be a non-empty string")
        return None
    return value


def _v2_string_list(
    value: object,
    label: str,
    hard: list[str],
    *,
    nonempty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        hard.append(f"H2 {label} must be a list of non-empty strings")
        return []
    if nonempty and not value:
        hard.append(f"H2 {label} must not be empty")
    duplicates = sorted({item for item in value if value.count(item) > 1})
    if duplicates:
        hard.append(f"H2 {label} contains duplicate value(s): {', '.join(duplicates)}")
    return value


def _v2_int(
    value: object,
    label: str,
    hard: list[str],
    *,
    minimum: int = 1,
) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        hard.append(f"H2 {label} must be an integer >= {minimum}")
        return None
    return value


def _v2_load_renderer():
    sibling = Path(__file__).with_name("architecture-render.py")
    spec = importlib.util.spec_from_file_location("ce_architecture_v2_renderer", sibling)
    if spec is None or spec.loader is None:
        raise ArchitectureLintError(f"could not load deterministic renderer: {sibling}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _v2_plugin_version(hard: list[str]) -> str | None:
    manifest = Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        hard.append(f"H2 cannot read core-engineering plugin manifest version: {exc}")
        return None
    version = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        hard.append("H2 core-engineering plugin manifest version is not canonical semver")
        return None
    return version


def _v2_collection(
    data: dict,
    name: str,
    source_kinds: dict[str, str],
    hard: list[str],
) -> tuple[list[dict], dict[str, dict]]:
    raw = data.get(name)
    if not isinstance(raw, list):
        hard.append(f"H2 {name} must be an array")
        return [], {}
    rows: list[dict] = []
    by_id: dict[str, dict] = {}
    ids: list[str] = []
    fields = V2_COLLECTION_FIELDS[name]
    pattern = V2_ID_PATTERNS[name]
    for index, value in enumerate(raw):
        label = f"{name}[{index}]"
        row = _v2_exact(value, label, fields, hard)
        if not row:
            continue
        rows.append(row)
        row_id = row.get("id")
        if not isinstance(row_id, str) or not pattern.fullmatch(row_id):
            hard.append(f"H2 {label}.id is not a canonical {name} id")
        elif row_id in by_id:
            hard.append(f"H2 {name} contains duplicate id {row_id}")
        else:
            by_id[row_id] = row
            ids.append(row_id)
        state = row.get("evidence_state")
        if state not in V2_EVIDENCE_STATES:
            hard.append(
                f"H2 {label}.evidence_state must be one of "
                f"{sorted(V2_EVIDENCE_STATES)}"
            )
        _evidence_refs(row, label, source_kinds, hard)
        if "feature_ids" in row:
            _v2_string_list(
                row.get("feature_ids"),
                f"{label}.feature_ids",
                hard,
                nonempty=True,
            )
    numeric_order = sorted(
        ids,
        key=lambda value: int(value.rsplit("-", 1)[1]),
    )
    if ids != numeric_order:
        hard.append(f"H2 {name} must be ordered by numeric id")
    return rows, by_id


def _v2_sources(
    data: dict,
    repo_root: Path,
    plan_dir: Path,
    *,
    consumer: bool,
    hard: list[str],
    advisory: list[str],
) -> dict[str, str]:
    raw = data.get("sources")
    if not isinstance(raw, list):
        hard.append("H2 sources must be an array")
        return {}
    source_kinds: dict[str, str] = {}
    ordered_paths: list[str] = []
    allowed_kinds = {"plan", "brief", "adr", "repository", "reference"}
    for index, value in enumerate(raw):
        label = f"sources[{index}]"
        row = _v2_exact(value, label, V2_SOURCE_FIELDS, hard)
        if not row:
            continue
        path_value = _v2_nonempty_string(row.get("path"), f"{label}.path", hard)
        digest = row.get("sha256")
        kind = row.get("kind")
        if not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
            hard.append(f"H2 {label}.sha256 must be 64 lowercase hex characters")
        if kind not in allowed_kinds:
            hard.append(f"H2 {label}.kind must be one of {sorted(allowed_kinds)}")
        if path_value is None:
            continue
        if path_value in source_kinds:
            hard.append(f"H2 sources contains duplicate path {path_value}")
            continue
        ordered_paths.append(path_value)
        source_kinds[path_value] = kind if isinstance(kind, str) else ""
        target = _repo_path(repo_root, path_value)
        if target is None:
            hard.append(f"H4 source path is unsafe: {path_value}")
            continue
        symlinks = _symlink_components(repo_root, target)
        if symlinks or target.is_symlink() or not target.is_file():
            hard.append(f"H4 source is missing, non-regular, or symlinked: {path_value}")
            continue
        actual = _sha256(target)
        if isinstance(digest, str) and actual != digest:
            message = f"H4 stale source hash for {path_value}"
            if consumer and kind == "repository":
                advisory.append("A4 " + message[3:])
            else:
                hard.append(message)
    if ordered_paths != sorted(ordered_paths):
        hard.append("H2 sources must be ordered by repository-relative path")
    required = {
        (plan_dir / filename).relative_to(repo_root).as_posix()
        for filename in REQUIRED_PLAN_FILES
    }
    plan_json = (plan_dir / "plan.json").relative_to(repo_root).as_posix()
    required.add(plan_json)
    missing = sorted(required - set(source_kinds))
    if missing:
        hard.append("H4 required plan source(s) are not tracked: " + ", ".join(missing))
    wrong_kind = sorted(
        path for path in required if source_kinds.get(path) not in {None, "plan"}
    )
    if wrong_kind:
        hard.append(
            "H4 required plan source(s) must use kind plan: "
            + ", ".join(wrong_kind)
        )
    return source_kinds


def _v2_projections(data: dict, source_kinds: dict[str, str], hard: list[str]) -> None:
    raw = data.get("projections")
    if not isinstance(raw, list):
        hard.append("H2 projections must be an array")
        return
    if len(raw) != len(V2_CORE_PROJECTIONS):
        hard.append("H2 projections must contain exactly the four core projections")
    for index, expected in enumerate(V2_CORE_PROJECTIONS):
        if index >= len(raw):
            break
        label = f"projections[{index}]"
        row = _v2_exact(raw[index], label, V2_PROJECTION_FIELDS, hard)
        expected_id, expected_type, expected_path = expected
        if (
            row.get("id"),
            row.get("projection_type"),
            row.get("path"),
            row.get("required"),
        ) != (expected_id, expected_type, expected_path, True):
            hard.append(
                f"H2 {label} must be the canonical required projection "
                f"{expected_id}/{expected_type}/{expected_path}"
            )
        digest = row.get("sha256")
        if not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
            hard.append(f"H2 {label}.sha256 must be 64 lowercase hex characters")


def _v2_narrative(
    data: dict,
    source_kinds: dict[str, str],
    hard: list[str],
) -> None:
    narrative = _v2_exact(
        data.get("narrative"), "narrative", V2_NARRATIVE_FIELDS, hard
    )
    if not narrative:
        return
    for field in (
        "executive_summary",
        "architecture_overview",
        "evidence_boundary",
        "consistency_model",
        "security_privacy_summary",
        "operability_summary",
        "capacity_resilience_recovery_summary",
        "cost_complexity_summary",
    ):
        _v2_nonempty_string(narrative.get(field), f"narrative.{field}", hard)
    _v2_string_list(narrative.get("scope"), "narrative.scope", hard, nonempty=True)
    _v2_string_list(
        narrative.get("non_goals"), "narrative.non_goals", hard, nonempty=True
    )
    for key, fields, pattern in (
        ("assumptions", V2_ASSUMPTION_FIELDS, re.compile(r"^AS-\d{3}$")),
        ("validation_strategy", V2_VALIDATION_FIELDS, re.compile(r"^VAL-\d{3}$")),
    ):
        raw = narrative.get(key)
        if not isinstance(raw, list):
            hard.append(f"H2 narrative.{key} must be an array")
            continue
        ids: list[str] = []
        for index, value in enumerate(raw):
            label = f"narrative.{key}[{index}]"
            row = _v2_exact(value, label, fields, hard)
            row_id = row.get("id")
            if not isinstance(row_id, str) or not pattern.fullmatch(row_id):
                hard.append(f"H2 {label}.id is not canonical")
            else:
                ids.append(row_id)
            _v2_nonempty_string(row.get("statement"), f"{label}.statement", hard)
            if key == "validation_strategy":
                _v2_nonempty_string(row.get("owner"), f"{label}.owner", hard)
            if row.get("evidence_state") not in V2_EVIDENCE_STATES:
                hard.append(f"H2 {label}.evidence_state is invalid")
            elif row.get("evidence_state") == "unknown":
                hard.append(
                    f"H6 {label}.evidence_state cannot be unknown; route the "
                    "uncertainty through an open question and typed gap"
                )
            _evidence_refs(row, label, source_kinds, hard)
        if len(ids) != len(set(ids)):
            hard.append(f"H2 narrative.{key} contains duplicate ids")
        if ids != sorted(ids, key=lambda value: int(value.rsplit('-', 1)[1])):
            hard.append(f"H2 narrative.{key} must be ordered by numeric id")


def _v2_validate_rows(
    rows: dict[str, list[dict]],
    source_kinds: dict[str, str],
    repo_root: Path,
    hard: list[str],
) -> None:
    string_list_fields = {
        "roles", "responsibilities", "feature_ids", "contract_realization_ids",
        "zones", "trust_boundary_ids", "node_ids", "writers", "readers",
        "transition_ids", "data", "data_entity_ids", "security_realization_ids",
        "inside_ids", "outside_ids", "crossing_integration_ids", "boundary_ids",
        "actor_ids", "component_ids", "integration_ids", "data_ids", "tactics",
        "relationship_ids", "dynamic_scenario_ids", "deployment_ids",
        "decision_ids", "operation_ids", "signals", "deployment_node_ids",
        "quality_ids", "gap_ids", "consequences", "options",
    }
    nested_fields = {
        "evidence_claims", "steps", "alternate_paths", "lifecycle",
        "realized_by", "alternatives", "related_refs",
    }
    nullable_string_fields = {"decided_at", "adr_path"}
    list_nonempty = {
        "roles", "responsibilities", "feature_ids", "writers", "readers",
        "data", "tactics", "signals", "consequences", "options",
    }
    placeholder = re.compile(r"^(?:tbd|todo|placeholder|<[^>]+>)$", re.IGNORECASE)
    communication_modes = {
        "synchronous", "asynchronous", "in-process", "data-access", "human",
    }
    for collection, collection_rows in rows.items():
        for index, row in enumerate(collection_rows):
            label = f"{collection}[{index}]"
            for field in V2_COLLECTION_FIELDS[collection]:
                value = row.get(field)
                if field in {"id", "evidence_state", "evidence"} | nested_fields:
                    continue
                if field == "ordinal":
                    _v2_int(value, f"{label}.ordinal", hard)
                elif field == "material":
                    if not isinstance(value, bool):
                        hard.append(f"H2 {label}.material must be boolean")
                elif field in string_list_fields:
                    _v2_string_list(
                        value,
                        f"{label}.{field}",
                        hard,
                        nonempty=field in list_nonempty,
                    )
                elif field in nullable_string_fields:
                    if value is not None:
                        _v2_nonempty_string(value, f"{label}.{field}", hard)
                else:
                    text = _v2_nonempty_string(value, f"{label}.{field}", hard)
                    if text is not None and placeholder.fullmatch(text.strip()):
                        hard.append(f"H2 {label}.{field} contains a placeholder value")

            if "communication_mode" in row and row.get("communication_mode") not in communication_modes:
                hard.append(
                    f"H2 {label}.communication_mode must be one of "
                    f"{sorted(communication_modes)}"
                )
            if collection == "actors" and row.get("kind") not in {
                "person", "role", "organization", "external-system",
            }:
                hard.append(f"H2 {label}.kind is not a canonical actor kind")
            if collection == "components" and row.get("kind") not in COMPONENT_KINDS:
                hard.append(f"H2 {label}.kind is not a canonical component kind")
            if collection == "deployment_connections" and row.get("direction") not in {
                "one-way", "bidirectional",
            }:
                hard.append(f"H2 {label}.direction must be one-way or bidirectional")
            if collection == "operations" and row.get("category") not in {
                "observability", "capacity", "resilience", "recovery", "cost",
                "supportability",
            }:
                hard.append(f"H2 {label}.category is not a canonical operation category")
            if collection == "risks" and row.get("severity") not in {
                "low", "medium", "high", "critical",
            }:
                hard.append(f"H2 {label}.severity must be low, medium, high, or critical")
            if collection == "open_questions" and row.get("status") not in {
                "open", "resolved",
            }:
                hard.append(f"H2 {label}.status must be open or resolved")
            if collection == "gaps":
                if row.get("dimension") not in V2_COVERAGE_DIMENSIONS:
                    hard.append(f"H2 {label}.dimension is not a coverage dimension")
                if row.get("gap_type") not in {
                    "evidence", "ownership", "decision", "topology", "behavior",
                    "control", "transition", "quality-target", "other",
                }:
                    hard.append(f"H2 {label}.gap_type is not canonical")
                if row.get("blocking_stage") not in {
                    "specification", "implementation", "verification",
                    "deployment", "none",
                }:
                    hard.append(f"H2 {label}.blocking_stage is not canonical")
                if row.get("status") not in V2_GAP_STATUSES:
                    hard.append(f"H2 {label}.status must be open or resolved")
            if collection == "decisions":
                if row.get("status") not in {"accepted", "proposed", "superseded"}:
                    hard.append(f"H2 {label}.status is not canonical")
                if row.get("decided_by") != "human":
                    hard.append(f"H2 {label}.decided_by must be 'human'")
                decided_at = row.get("decided_at")
                if decided_at is not None and (
                    not isinstance(decided_at, str)
                    or not RFC3339_UTC_RE.fullmatch(decided_at)
                ):
                    hard.append(f"H2 {label}.decided_at must be null or RFC 3339 UTC")
                adr_path = row.get("adr_path")
                if adr_path is not None:
                    if adr_path not in source_kinds or source_kinds.get(adr_path) != "adr":
                        hard.append(f"H2 {label}.adr_path must reference a tracked ADR source")
                    target = _repo_path(repo_root, adr_path)
                    if target is not None and target.is_file():
                        try:
                            text = target.read_text(encoding="utf-8")
                        except (OSError, UnicodeError):
                            text = ""
                        if not re.search(
                            r"(?im)^\s*(?:status\s*:\s*|##\s*status\s*\n+\s*)accepted\b",
                            text,
                        ):
                            hard.append(f"H2 {label}.adr_path does not resolve to an accepted ADR")
            if collection == "drivers" and row.get("source") not in source_kinds:
                hard.append(f"H2 {label}.source must reference a tracked source")
            if collection == "quality_scenarios" and row.get("source") not in source_kinds:
                hard.append(f"H2 {label}.source must reference a tracked source")

            if collection == "deployment_nodes":
                claims = row.get("evidence_claims")
                if not isinstance(claims, list):
                    hard.append(f"H2 {label}.evidence_claims must be an array")
                else:
                    claim_fields: list[str] = []
                    canonical_claim_fields = {
                        "name", "environment", "provider", "runtime", "region",
                        "zones", "network_zone", "residency", "scaling",
                        "availability",
                    }
                    for claim_index, value in enumerate(claims):
                        claim_label = f"{label}.evidence_claims[{claim_index}]"
                        claim = _v2_exact(
                            value, claim_label, V2_EVIDENCE_CLAIM_FIELDS, hard
                        )
                        for field in V2_EVIDENCE_CLAIM_FIELDS:
                            _v2_nonempty_string(
                                claim.get(field), f"{claim_label}.{field}", hard
                            )
                        path = claim.get("path")
                        literal = claim.get("literal")
                        field = claim.get("field")
                        if field not in canonical_claim_fields:
                            hard.append(
                                f"H2 {claim_label}.field is not a canonical "
                                "deployment-node evidence field"
                            )
                        else:
                            claim_fields.append(field)
                            if claim.get("derivation") != str(row.get(field)):
                                hard.append(
                                    f"H2 {claim_label}.derivation must exactly equal "
                                    f"str({label}.{field})"
                                )
                        if path not in row.get("evidence", []):
                            hard.append(
                                f"H2 {claim_label}.path must occur in the node evidence"
                            )
                        target = _repo_path(repo_root, path)
                        if (
                            isinstance(literal, str)
                            and target is not None
                            and target.is_file()
                        ):
                            try:
                                payload = target.read_text(encoding="utf-8")
                            except (OSError, UnicodeError):
                                payload = ""
                            if literal not in payload:
                                hard.append(
                                    f"H4 {claim_label}.literal does not occur in {path}"
                                )
                    duplicate_claims = sorted(
                        {
                            field
                            for field in claim_fields
                            if claim_fields.count(field) > 1
                        }
                    )
                    if duplicate_claims:
                        hard.append(
                            f"H2 {label}.evidence_claims contains duplicate field(s): "
                            + ", ".join(duplicate_claims)
                        )
                    missing_identity_claims = sorted(
                        {"name", "environment"} - set(claim_fields)
                    )
                    if missing_identity_claims:
                        hard.append(
                            f"H2 {label}.evidence_claims must select source-backed "
                            "identity field(s): " + ", ".join(missing_identity_claims)
                        )
            elif collection == "data_entities":
                lifecycle = _v2_exact(
                    row.get("lifecycle"), f"{label}.lifecycle",
                    V2_LIFECYCLE_FIELDS, hard,
                )
                for field in V2_LIFECYCLE_FIELDS:
                    _v2_nonempty_string(
                        lifecycle.get(field), f"{label}.lifecycle.{field}", hard
                    )
            elif collection == "dynamic_scenarios":
                steps = row.get("steps")
                if not isinstance(steps, list) or not steps:
                    hard.append(f"H2 {label}.steps must be a non-empty array")
                    steps = []
                ordinals: list[int] = []
                for step_index, value in enumerate(steps):
                    step_label = f"{label}.steps[{step_index}]"
                    step = _v2_exact(value, step_label, V2_DYNAMIC_STEP_FIELDS, hard)
                    ordinal = _v2_int(step.get("ordinal"), f"{step_label}.ordinal", hard)
                    if ordinal is not None:
                        ordinals.append(ordinal)
                    for field in (
                        "from", "to", "interaction", "communication_mode",
                        "failure_behavior",
                    ):
                        _v2_nonempty_string(
                            step.get(field), f"{step_label}.{field}", hard
                        )
                    if (
                        step.get("communication_mode") not in communication_modes
                    ):
                        hard.append(f"H2 {step_label}.communication_mode is invalid")
                    integration_id = step.get("integration_id")
                    if integration_id is not None:
                        _v2_nonempty_string(
                            integration_id, f"{step_label}.integration_id", hard
                        )
                    for field in (
                        "contract_realization_ids", "security_realization_ids",
                    ):
                        _v2_string_list(step.get(field), f"{step_label}.{field}", hard)
                if ordinals != list(range(1, len(steps) + 1)):
                    hard.append(f"H2 {label}.steps ordinals must be contiguous from one")
                alternates = row.get("alternate_paths")
                if not isinstance(alternates, list):
                    hard.append(f"H2 {label}.alternate_paths must be an array")
                    alternates = []
                for alt_index, value in enumerate(alternates):
                    alt_label = f"{label}.alternate_paths[{alt_index}]"
                    alt = _v2_exact(value, alt_label, V2_ALTERNATE_PATH_FIELDS, hard)
                    for field in ("name", "condition", "outcome"):
                        _v2_nonempty_string(alt.get(field), f"{alt_label}.{field}", hard)
                    step_ordinals = alt.get("step_ordinals")
                    if (
                        not isinstance(step_ordinals, list)
                        or not step_ordinals
                        or any(
                            not isinstance(item, int)
                            or isinstance(item, bool)
                            or item not in ordinals
                            for item in step_ordinals
                        )
                    ):
                        hard.append(
                            f"H2 {alt_label}.step_ordinals must reference scenario steps"
                        )
            elif collection == "direction_realizations":
                realized_by = row.get("realized_by")
                if not isinstance(realized_by, list):
                    hard.append(f"H2 {label}.realized_by must be an array")
                    realized_by = []
                seen_refs: set[tuple[object, object]] = set()
                for ref_index, value in enumerate(realized_by):
                    ref_label = f"{label}.realized_by[{ref_index}]"
                    ref = _v2_exact(value, ref_label, V2_REALIZED_BY_FIELDS, hard)
                    kind = ref.get("kind")
                    ref_id = ref.get("id")
                    if kind not in V2_REALIZED_BY_KINDS:
                        hard.append(f"H2 {ref_label}.kind is not canonical")
                    _v2_nonempty_string(ref_id, f"{ref_label}.id", hard)
                    key = (kind, ref_id)
                    if key in seen_refs:
                        hard.append(f"H2 {label}.realized_by contains duplicate refs")
                    seen_refs.add(key)
                status = row.get("realization_status")
                gaps = row.get("gap_ids") if isinstance(row.get("gap_ids"), list) else []
                if status not in V2_REALIZATION_STATUSES:
                    hard.append(f"H2 {label}.realization_status is invalid")
                elif status == "realized" and (not realized_by or gaps):
                    hard.append(
                        f"H2 {label} realized requires realized_by and no gap_ids"
                    )
                elif status == "gap" and not gaps:
                    hard.append(f"H2 {label} gap requires at least one gap id")
                elif status == "not-applicable" and (realized_by or gaps):
                    hard.append(
                        f"H2 {label} not-applicable requires empty references"
                    )
                if status == "not-applicable" and not re.search(
                    r"\b(?:no|none|not applicable|without|absent)\b",
                    str(row.get("statement", "")),
                    re.IGNORECASE,
                ):
                    hard.append(
                        f"H2 {label} not-applicable statement must explicitly describe absence"
                    )
            elif collection == "decisions":
                alternatives = row.get("alternatives")
                if not isinstance(alternatives, list) or not alternatives:
                    hard.append(f"H2 {label}.alternatives must be a non-empty array")
                    alternatives = []
                for alt_index, value in enumerate(alternatives):
                    alt_label = f"{label}.alternatives[{alt_index}]"
                    alt = _v2_exact(
                        value, alt_label, V2_DECISION_ALTERNATIVE_FIELDS, hard
                    )
                    for field in V2_DECISION_ALTERNATIVE_FIELDS:
                        _v2_nonempty_string(
                            alt.get(field), f"{alt_label}.{field}", hard
                        )

            if collection == "quality_scenarios":
                source = row.get("source")
                target_value = row.get("target")
                target = _repo_path(repo_root, source)
                if (
                    isinstance(target_value, str)
                    and target_value != "unknown"
                    and target is not None
                    and target.is_file()
                ):
                    try:
                        source_text = target.read_text(encoding="utf-8")
                    except (OSError, UnicodeError):
                        source_text = ""
                    if target_value not in source_text:
                        hard.append(
                            f"H6 {label}.target must occur literally in its source"
                        )

            if collection in {"open_questions", "risks", "gaps"}:
                refs = row.get("related_refs")
                if not isinstance(refs, list):
                    hard.append(f"H2 {label}.related_refs must be an array")
                    continue
                if collection == "gaps" and not refs:
                    hard.append(f"H2 {label}.related_refs must not be empty")
                seen: set[tuple[object, object]] = set()
                allowed_extra = {
                    "driver": "drivers",
                    "open-question": "open_questions",
                    "gap": "gaps",
                }
                for ref_index, value in enumerate(refs):
                    ref_label = f"{label}.related_refs[{ref_index}]"
                    ref = _v2_exact(value, ref_label, V2_RELATED_REF_FIELDS, hard)
                    kind, ref_id = ref.get("kind"), ref.get("id")
                    if kind not in V2_REALIZED_BY_KINDS and kind not in allowed_extra:
                        hard.append(f"H2 {ref_label}.kind is not canonical")
                    _v2_nonempty_string(ref_id, f"{ref_label}.id", hard)
                    key = (kind, ref_id)
                    if key in seen:
                        hard.append(f"H2 {label}.related_refs contains duplicate refs")
                    seen.add(key)


def _v2_reference_checks(
    data: dict,
    rows: dict[str, list[dict]],
    by_id: dict[str, dict[str, dict]],
    hard: list[str],
) -> None:
    def refs(row: dict, field: str, collection: str, label: str) -> None:
        raw = row.get(field)
        if not isinstance(raw, list):
            return
        unknown = [value for value in raw if value not in by_id[collection]]
        if unknown:
            hard.append(
                f"H5 {label}.{field} has unresolved {collection} id(s): "
                + ", ".join(str(value) for value in unknown)
            )

    boundary = data.get("system_boundary", {})
    context_ids = set(by_id["actors"]) | {boundary.get("id")}
    endpoint_ids = context_ids | set(by_id["components"])
    for index, row in enumerate(rows["context_relationships"]):
        for field in ("from", "to"):
            if row.get(field) not in context_ids:
                hard.append(
                    f"H5 context_relationships[{index}].{field} must resolve to "
                    "an actor or the system boundary: "
                    f"{row.get(field)!r}"
                )
        if {
            row.get("from"),
            row.get("to"),
        } & set(by_id["actors"]) == set() or (
            boundary.get("id") not in {row.get("from"), row.get("to")}
        ):
            hard.append(
                f"H5 context_relationships[{index}] must connect exactly one "
                "actor to SB-001"
            )
    for index, row in enumerate(rows["relationships"]):
        for field in ("from", "to"):
            if row.get(field) not in by_id["components"]:
                hard.append(
                    f"H5 relationships[{index}].{field} is unresolved: "
                    f"{row.get(field)!r}"
                )
        refs(row, "contract_realization_ids", "contract_realizations", f"relationships[{index}]")
    for index, row in enumerate(rows["deployment_nodes"]):
        refs(row, "trust_boundary_ids", "trust_boundaries", f"deployment_nodes[{index}]")
    for index, row in enumerate(rows["deployments"]):
        if row.get("component_id") not in by_id["components"]:
            hard.append(
                f"H5 deployments[{index}].component_id is unresolved: "
                f"{row.get('component_id')!r}"
            )
        if not row.get("node_ids"):
            hard.append(f"H5 deployments[{index}].node_ids must not be empty")
        refs(row, "node_ids", "deployment_nodes", f"deployments[{index}]")
    for index, row in enumerate(rows["deployment_connections"]):
        for field in ("from_node", "to_node"):
            if row.get(field) not in by_id["deployment_nodes"]:
                hard.append(
                    f"H5 deployment_connections[{index}].{field} is unresolved: "
                    f"{row.get(field)!r}"
                )
    for index, row in enumerate(rows["data_entities"]):
        for field in ("source_of_truth",):
            if row.get(field) not in by_id["components"]:
                hard.append(
                    f"H5 data_entities[{index}].{field} is unresolved: "
                    f"{row.get(field)!r}"
                )
        refs(row, "writers", "components", f"data_entities[{index}]")
        refs(row, "readers", "components", f"data_entities[{index}]")
        refs(row, "transition_ids", "transitions", f"data_entities[{index}]")
    for index, row in enumerate(rows["integration_flows"]):
        for field in ("producer", "consumer", "source_of_truth"):
            if row.get(field) not in by_id["components"]:
                hard.append(
                    f"H5 integration_flows[{index}].{field} is unresolved: "
                    f"{row.get(field)!r}"
                )
        refs(row, "data_entity_ids", "data_entities", f"integration_flows[{index}]")
        refs(row, "contract_realization_ids", "contract_realizations", f"integration_flows[{index}]")
        refs(row, "security_realization_ids", "security_realizations", f"integration_flows[{index}]")
    for index, row in enumerate(rows["dynamic_scenarios"]):
        for step_index, step in enumerate(row.get("steps", [])):
            if not isinstance(step, dict):
                continue
            for field in ("from", "to"):
                if step.get(field) not in endpoint_ids:
                    hard.append(
                        f"H5 dynamic_scenarios[{index}].steps[{step_index}].{field} "
                        "is unresolved"
                    )
            integration_id = step.get("integration_id")
            if integration_id is not None and integration_id not in by_id["integration_flows"]:
                hard.append(
                    f"H5 dynamic_scenarios[{index}].steps[{step_index}].integration_id "
                    "is unresolved"
                )
            refs(step, "contract_realization_ids", "contract_realizations", f"dynamic_scenarios[{index}].steps[{step_index}]")
            refs(step, "security_realization_ids", "security_realizations", f"dynamic_scenarios[{index}].steps[{step_index}]")
    for index, row in enumerate(rows["trust_boundaries"]):
        universe = endpoint_ids | set(by_id["deployment_nodes"])
        for field in ("inside_ids", "outside_ids"):
            unknown = [value for value in row.get(field, []) if value not in universe]
            if unknown:
                hard.append(f"H5 trust_boundaries[{index}].{field} is unresolved")
        if set(row.get("inside_ids", [])) & set(row.get("outside_ids", [])):
            hard.append(f"H5 trust_boundaries[{index}] inside/outside ids overlap")
        for field in ("inside_ids", "outside_ids"):
            if not row.get(field):
                hard.append(f"H5 trust_boundaries[{index}].{field} must not be empty")
        refs(row, "crossing_integration_ids", "integration_flows", f"trust_boundaries[{index}]")
        inside = set(row.get("inside_ids", []))
        outside = set(row.get("outside_ids", []))
        expected_crossings = [
            flow.get("id")
            for flow in rows["integration_flows"]
            if (
                flow.get("producer") in inside
                and flow.get("consumer") in outside
            )
            or (
                flow.get("producer") in outside
                and flow.get("consumer") in inside
            )
        ]
        declared_crossings = row.get("crossing_integration_ids")
        if (
            isinstance(declared_crossings, list)
            and declared_crossings != expected_crossings
        ):
            hard.append(
                f"H5 trust_boundaries[{index}].crossing_integration_ids must "
                "exactly equal the producer/consumer crossings in canonical "
                f"flow order: expected {expected_crossings!r}"
            )
    for index, row in enumerate(rows["security_realizations"]):
        for field, collection in (
            ("boundary_ids", "trust_boundaries"), ("actor_ids", "actors"),
            ("component_ids", "components"), ("integration_ids", "integration_flows"),
            ("data_ids", "data_entities"),
        ):
            refs(row, field, collection, f"security_realizations[{index}]")
        if not row.get("boundary_ids"):
            hard.append(
                f"H5 security_realizations[{index}].boundary_ids must not be empty"
            )
        if not any(
            row.get(field)
            for field in ("component_ids", "integration_ids", "data_ids")
        ):
            hard.append(
                f"H5 security_realizations[{index}] must affect a component, "
                "integration, or data entity"
            )
    for index, row in enumerate(rows["contract_realizations"]):
        for field, collection in (
            ("relationship_ids", "relationships"),
            ("integration_ids", "integration_flows"),
            ("dynamic_scenario_ids", "dynamic_scenarios"),
            ("data_ids", "data_entities"),
        ):
            refs(row, field, collection, f"contract_realizations[{index}]")
        if not any(
            row.get(field)
            for field in (
                "relationship_ids", "integration_ids", "dynamic_scenario_ids",
            )
        ):
            hard.append(
                f"H5 contract_realizations[{index}] must affect a relationship, "
                "integration, or dynamic scenario"
            )
    for index, row in enumerate(rows["transitions"]):
        for field, collection in (
            ("component_ids", "components"), ("data_ids", "data_entities"),
            ("deployment_ids", "deployments"), ("decision_ids", "decisions"),
        ):
            refs(row, field, collection, f"transitions[{index}]")
    for index, row in enumerate(rows["quality_scenarios"]):
        refs(row, "operation_ids", "operations", f"quality_scenarios[{index}]")
    for index, row in enumerate(rows["operations"]):
        for field, collection in (
            ("component_ids", "components"),
            ("deployment_node_ids", "deployment_nodes"),
            ("quality_ids", "quality_scenarios"),
        ):
            refs(row, field, collection, f"operations[{index}]")
    for index, row in enumerate(rows["direction_realizations"]):
        refs(row, "gap_ids", "gaps", f"direction_realizations[{index}]")
        for ref_index, ref in enumerate(row.get("realized_by", [])):
            if not isinstance(ref, dict):
                continue
            collection = V2_REALIZED_BY_KINDS.get(ref.get("kind"))
            resolved = (
                ref.get("id") == boundary.get("id")
                if collection is None and ref.get("kind") == "system-boundary"
                else collection is not None and ref.get("id") in by_id[collection]
            )
            if not resolved:
                hard.append(
                    f"H5 direction_realizations[{index}].realized_by[{ref_index}] "
                    "is unresolved"
                )
    extra_kinds = {
        "driver": "drivers",
        "open-question": "open_questions",
        "gap": "gaps",
    }
    for collection in ("open_questions", "risks", "gaps"):
        for index, row in enumerate(rows[collection]):
            for ref_index, ref in enumerate(row.get("related_refs", [])):
                if not isinstance(ref, dict):
                    continue
                target_collection = (
                    V2_REALIZED_BY_KINDS.get(ref.get("kind"))
                    or extra_kinds.get(ref.get("kind"))
                )
                if target_collection is None:
                    resolved = (
                        ref.get("kind") == "system-boundary"
                        and ref.get("id") == boundary.get("id")
                    )
                else:
                    resolved = ref.get("id") in by_id[target_collection]
                if not resolved:
                    hard.append(
                        f"H5 {collection}[{index}].related_refs[{ref_index}] is unresolved"
                    )


def _v2_is_explicit_no_current_transition(statement: object) -> bool:
    """Recognize only an anchored, explicit absence of a current transition.

    The migration dimension supplies the subject context, but incidental
    modifiers such as "no downtime" or "without data loss" must never turn a
    real migration into not-applicable coverage.  Anything outside these
    narrow absence forms therefore fails closed to transition-applicable.
    """
    if not isinstance(statement, str) or not statement.strip():
        return False
    normalized = " ".join(
        statement.strip().casefold().replace("\u2014", ";").split()
    )
    first_clause = re.split(r"\s*[;,:.]\s*", normalized, maxsplit=1)[0].strip()
    if first_clause in {"none", "not applicable", "not-applicable"}:
        return True

    scope = (
        r"(?:(?:current\s+)?"
        r"(?:(?:runtime|data|schema|state|ownership)"
        r"(?:\s+or\s+(?:runtime|data|schema|state|ownership))*\s+)?)"
    )
    subject = (
        r"(?:migrations?|transitions?|cutovers?|"
        r"data\s+movements?|ownership\s+transfers?)"
    )
    predicate = (
        r"(?:introduced|required|planned|needed|applicable|performed|undertaken)"
    )
    no_subject = re.fullmatch(
        rf"(?:there\s+(?:is|are)\s+)?no\s+{scope}{subject}"
        rf"(?:\s+(?:is|are|will\s+be)\s+(?:currently\s+)?{predicate})?",
        first_clause,
    )
    if no_subject:
        return True
    subject_is_absent = re.fullmatch(
        rf"{scope}{subject}\s+(?:is|are)\s+"
        rf"(?:(?:currently\s+)?not\s+{predicate}|absent)",
        first_clause,
    )
    if subject_is_absent:
        return True
    without_subject = re.fullmatch(
        rf"without\s+(?:(?:a|any)\s+)?{scope}{subject}",
        first_clause,
    )
    return without_subject is not None


def _v2_transition_is_applicable(option: dict | None) -> bool:
    """Resolve transition applicability from the exact selected commitments."""
    if option is None:
        return True
    statements = option.get("migration_and_evolution")
    if not isinstance(statements, list) or not statements:
        return True
    return not all(
        _v2_is_explicit_no_current_transition(statement)
        for statement in statements
    )


def _v2_selected_direction(
    data: dict,
    plan: dict,
    plan_dir: Path,
    rows: dict[str, list[dict]],
    by_id: dict[str, dict[str, dict]],
    hard: list[str],
) -> tuple[bool, dict | None]:
    selection_path = plan_dir / "architecture-selection.json"
    try:
        selection = _strict_json_loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        hard.append(f"H10 architecture-selection.json is unreadable: {exc}")
        return True, None
    if not isinstance(selection, dict):
        hard.append("H10 architecture-selection.json must contain an object")
        return True, None
    direction = plan.get("architecture_disposition", {}).get("direction")
    if not isinstance(direction, dict):
        hard.append("H10 source plan direction binding must be an object")
        return True, None
    selection_record = selection.get("selection")
    if not isinstance(selection_record, dict):
        hard.append("H10 architecture selection must contain selection object")
        return True, None
    selected_id = selection_record.get("option_id")
    selected_hash = selection_record.get("option_sha256")
    exploration_id = selection.get("exploration_id")
    if selection_record.get("status") != "direction-selected":
        hard.append("H10 v2 architecture requires a human direction-selected posture")
    if selection_record.get("decided_by") != "human":
        hard.append("H10 selected architecture direction must be human-owned")
    for field, expected in (
        ("exploration_id", exploration_id),
        ("selected_option_id", selected_id),
        ("selected_option_sha256", selected_hash),
    ):
        if direction.get(field) != expected:
            hard.append(f"H10 plan direction.{field} does not match architecture selection")
    options = selection.get("options")
    if not isinstance(options, list):
        hard.append("H10 architecture selection options must be an array")
        return True, None
    matches = [
        option for option in options
        if isinstance(option, dict) and option.get("option_id") == selected_id
    ]
    if len(matches) != 1:
        hard.append("H10 selected option id must resolve exactly once")
        return True, None
    option = matches[0]
    if option.get("option_sha256") != selected_hash or not isinstance(
        selected_hash, str
    ) or not SHA_RE.fullmatch(selected_hash):
        hard.append("H10 selected option hash does not bind the selected option")

    expected_rows: list[tuple[str, int, str, str]] = []
    for dimension in V2_COMMITMENT_DIMENSIONS:
        statements = option.get(dimension)
        if not isinstance(statements, list) or not statements or any(
            not isinstance(item, str) or not item for item in statements
        ):
            hard.append(
                f"H10 selected option {dimension} must be a non-empty array "
                "of exact strings"
            )
            continue
        for ordinal, statement in enumerate(statements, 1):
            statement_hash = hashlib.sha256(statement.encode("utf-8")).hexdigest()
            expected_rows.append((dimension, ordinal, statement, statement_hash))

    actual_rows: list[tuple[str, int, object, object]] = []
    for index, row in enumerate(rows["direction_realizations"]):
        label = f"direction_realizations[{index}]"
        if row.get("exploration_id") != exploration_id:
            hard.append(f"H10 {label}.exploration_id is not the selected exploration")
        if row.get("selected_option_id") != selected_id:
            hard.append(f"H10 {label}.selected_option_id is not selected")
        if row.get("selected_option_sha256") != selected_hash:
            hard.append(f"H10 {label}.selected_option_sha256 is not selected")
        statement = row.get("statement")
        expected_statement_hash = (
            hashlib.sha256(statement.encode("utf-8")).hexdigest()
            if isinstance(statement, str)
            else None
        )
        if row.get("statement_sha256") != expected_statement_hash:
            hard.append(
                f"H10 {label}.statement_sha256 must hash exact UTF-8 statement bytes"
            )
        actual_rows.append(
            (
                row.get("dimension"),
                row.get("ordinal"),
                statement,
                row.get("statement_sha256"),
            )
        )
        if row.get("dimension") == "migration_and_evolution":
            explicitly_absent = _v2_is_explicit_no_current_transition(statement)
            if (
                explicitly_absent
                and row.get("realization_status") != "not-applicable"
            ):
                hard.append(
                    f"H10 {label} explicitly absent current transition must "
                    "be not-applicable"
                )
            elif (
                not explicitly_absent
                and row.get("realization_status") == "not-applicable"
            ):
                hard.append(
                    f"H10 {label} non-absence migration commitment cannot be "
                    "not-applicable"
                )
    if actual_rows != expected_rows:
        hard.append(
            "H10 direction_realizations must be an ordered bijection with every "
            "selected option commitment"
        )
    return _v2_transition_is_applicable(option), option


def _v2_required_dimensions(
    triggers: list[str],
    plan_dir: Path,
    transition_applicable: bool,
    rows: dict[str, list[dict]],
) -> list[str]:
    required = set(V2_BASE_DIMENSIONS)
    for trigger in triggers:
        required.update(V2_TRIGGER_DIMENSIONS.get(trigger, set()))
    if _plan_data_rows(plan_dir) and "cross-feature-durable-or-async-flow" in triggers:
        required.add("data")
    if transition_applicable:
        required.add("transitions")
    if any(
        row.get("communication_mode") == "asynchronous"
        for row in rows["relationships"] + rows["integration_flows"]
    ):
        required.add("dynamic_behavior")
    return [
        dimension
        for dimension in V2_COVERAGE_DIMENSIONS
        if dimension in required
    ]


def _v2_coverage_and_readiness(
    data: dict,
    triggers: list[str],
    required_dimensions: list[str],
    transition_applicable: bool,
    source_kinds: dict[str, str],
    rows: dict[str, list[dict]],
    by_id: dict[str, dict[str, dict]],
    hard: list[str],
) -> None:
    profile = _v2_exact(
        data.get("coverage_profile"),
        "coverage_profile",
        V2_COVERAGE_PROFILE_FIELDS,
        hard,
    )
    if profile.get("profile_id") != "solution-baseline-v2":
        hard.append("H6 coverage_profile.profile_id must be solution-baseline-v2")
    trigger_ids = _v2_string_list(
        profile.get("trigger_ids"), "coverage_profile.trigger_ids", hard
    )
    if trigger_ids != triggers:
        hard.append("H6 coverage_profile.trigger_ids must exactly copy plan trigger ids")
    profile_dimensions = _v2_string_list(
        profile.get("required_dimensions"),
        "coverage_profile.required_dimensions",
        hard,
        nonempty=True,
    )
    if profile_dimensions != required_dimensions:
        hard.append(
            "H6 coverage_profile.required_dimensions does not equal the "
            "plan-relative conditional dimension set"
        )

    coverage = data.get("coverage")
    if not isinstance(coverage, dict):
        hard.append("H6 coverage must be an object")
        coverage = {}
    elif tuple(coverage) != V2_COVERAGE_DIMENSIONS:
        missing = sorted(set(V2_COVERAGE_DIMENSIONS) - set(coverage))
        extra = sorted(set(coverage) - set(V2_COVERAGE_DIMENSIONS))
        if missing:
            hard.append("H6 coverage is missing dimension(s): " + ", ".join(missing))
        if extra:
            hard.append("H6 coverage has unknown dimension(s): " + ", ".join(extra))
        if not missing and not extra:
            hard.append("H6 coverage dimensions must occur in canonical order")
    for dimension in V2_COVERAGE_DIMENSIONS:
        row = _v2_exact(
            coverage.get(dimension),
            f"coverage.{dimension}",
            V2_COVERAGE_FIELDS,
            hard,
        )
        status = row.get("status")
        if status not in V2_COVERAGE_STATES:
            hard.append(f"H6 coverage.{dimension}.status is invalid")
        gap_ids = _v2_string_list(
            row.get("gap_ids"), f"coverage.{dimension}.gap_ids", hard
        )
        evidence = _v2_string_list(
            row.get("evidence"),
            f"coverage.{dimension}.evidence",
            hard,
            nonempty=True,
        )
        unknown_evidence = sorted(set(evidence) - set(source_kinds))
        if unknown_evidence:
            hard.append(
                f"H6 coverage.{dimension}.evidence has untracked source(s): "
                + ", ".join(unknown_evidence)
            )
        if status == "gap":
            if not gap_ids:
                hard.append(f"H6 coverage.{dimension} gap requires gap_ids")
            for gap_id in gap_ids:
                gap = by_id["gaps"].get(gap_id)
                if gap is None:
                    hard.append(f"H6 coverage.{dimension} has unresolved gap {gap_id}")
                elif gap.get("dimension") != dimension or gap.get("status") != "open":
                    hard.append(
                        f"H6 coverage.{dimension} gap {gap_id} must be open "
                        "and in the same dimension"
                    )
        elif gap_ids:
            hard.append(f"H6 coverage.{dimension} {status} requires empty gap_ids")
        if dimension in required_dimensions and status == "not-applicable":
            hard.append(f"H6 required dimension {dimension} cannot be not-applicable")

    transition_coverage = coverage.get("transitions")
    if not transition_applicable:
        if (
            not isinstance(transition_coverage, dict)
            or transition_coverage.get("status") != "not-applicable"
        ):
            hard.append(
                "H6 explicitly absent current transition requires "
                "coverage.transitions.status not-applicable"
            )
        if rows["transitions"]:
            hard.append(
                "H6 explicitly absent current transition requires an empty "
                "transitions collection"
            )

    dimension_collections = {
        "direction_realization": ("direction_realizations",),
        "system_context": ("actors", "context_relationships"),
        "containers": ("components",),
        "deployment": ("deployment_nodes", "deployments"),
        "data": ("data_entities",),
        "integrations": ("integration_flows",),
        "dynamic_behavior": ("dynamic_scenarios",),
        "security": ("trust_boundaries", "security_realizations"),
        "contracts": ("contract_realizations",),
        "transitions": ("transitions",),
        "quality_attributes": ("quality_scenarios",),
        "operability": ("operations",),
        "requirements_traceability": ("feature_mappings",),
    }
    for dimension, collections in dimension_collections.items():
        row = coverage.get(dimension)
        if isinstance(row, dict) and row.get("status") == "complete":
            for collection in collections:
                collection_value = (
                    data.get(collection)
                    if collection == "feature_mappings"
                    else rows[collection]
                )
                if not collection_value:
                    hard.append(
                        f"H6 {dimension} coverage is complete but {collection} is empty"
                    )
    if (
        isinstance(coverage.get("deployment"), dict)
        and coverage["deployment"].get("status") == "complete"
        and len(rows["deployment_nodes"]) > 1
        and not rows["deployment_connections"]
    ):
        hard.append(
            "H6 complete multi-node deployment requires deployment_connections"
        )
    if (
        isinstance(coverage.get("operability"), dict)
        and coverage["operability"].get("status") == "complete"
    ):
        for index, operation in enumerate(rows["operations"]):
            if not (
                operation.get("component_ids")
                or operation.get("deployment_node_ids")
            ):
                hard.append(
                    f"H6 operations[{index}] must reference a component or node"
                )
            if not operation.get("quality_ids"):
                hard.append(
                    f"H6 operations[{index}].quality_ids must not be empty "
                    "when operability is complete"
                )

    open_gaps = {
        row["id"]: row
        for row in rows["gaps"]
        if row.get("status") == "open" and isinstance(row.get("id"), str)
    }
    for gap_id, gap in open_gaps.items():
        occurrences = [
            dimension
            for dimension, coverage_row in coverage.items()
            if isinstance(coverage_row, dict)
            and gap_id in coverage_row.get("gap_ids", [])
        ]
        if occurrences != [gap.get("dimension")]:
            hard.append(
                f"H6 open gap {gap_id} must occur exactly once in "
                f"coverage.{gap.get('dimension')}.gap_ids"
            )
        own_coverage = coverage.get(gap.get("dimension"))
        if not isinstance(own_coverage, dict) or own_coverage.get("status") != "gap":
            hard.append(
                f"H6 open gap {gap_id} requires its coverage row status to be gap"
            )
    blocking_ids = [
        row_id for row_id, row in open_gaps.items()
        if row.get("material") is True or row.get("blocking_stage") == "specification"
    ]
    non_blocking_ids = [
        row_id for row_id in open_gaps if row_id not in set(blocking_ids)
    ]
    material_questions = [
        row.get("id")
        for row in rows["open_questions"]
        if row.get("status") == "open" and row.get("material") is True
    ]
    commitment_conflict = any(
        row.get("realization_status") == "gap"
        for row in rows["direction_realizations"]
    )
    expected_status = (
        "blocked"
        if blocking_ids or material_questions or commitment_conflict
        else "ready-with-gaps"
        if non_blocking_ids
        else "ready"
    )
    readiness = _v2_exact(
        data.get("readiness"), "readiness", V2_READINESS_FIELDS, hard
    )
    if readiness.get("status") not in V2_READINESS_STATUSES:
        hard.append("H6 readiness.status is invalid")
    elif readiness.get("status") != expected_status:
        hard.append(
            f"H6 readiness.status must be {expected_status!r} from open gaps/questions"
        )
    actual_blocking = _v2_string_list(
        readiness.get("blocking_gap_ids"), "readiness.blocking_gap_ids", hard
    )
    actual_non_blocking = _v2_string_list(
        readiness.get("non_blocking_gap_ids"),
        "readiness.non_blocking_gap_ids",
        hard,
    )
    if actual_blocking != blocking_ids:
        hard.append("H6 readiness.blocking_gap_ids does not equal blocking open gaps")
    if actual_non_blocking != non_blocking_ids:
        hard.append(
            "H6 readiness.non_blocking_gap_ids does not equal non-blocking open gaps"
        )
    _v2_nonempty_string(readiness.get("summary"), "readiness.summary", hard)
    baseline = data.get("baseline_status")
    expected_baseline = (
        "accepted-for-specification"
        if expected_status == "ready"
        else "accepted-for-specification-with-gaps"
    )
    if expected_status != "blocked" and baseline != expected_baseline:
        hard.append(
            f"H6 baseline_status must be {expected_baseline!r} for readiness "
            f"{expected_status!r}"
        )
    if data.get("lifecycle_status") == "published" and expected_status == "blocked":
        hard.append("H6 a blocked architecture package cannot be published")


def _v2_plan_closure(
    plan_dir: Path,
    rows: dict[str, list[dict]],
    coverage: dict,
    hard: list[str],
) -> None:
    durable = _plan_data_rows(plan_dir)
    data_by_name = {
        row.get("name"): row
        for row in rows["data_entities"]
        if isinstance(row.get("name"), str)
    }
    if (
        isinstance(coverage.get("data"), dict)
        and coverage["data"].get("status") == "complete"
        and set(data_by_name) != set(durable)
    ):
        hard.append(
            "H6 complete data coverage must exactly re-project every plan durable noun"
        )
    for noun, cells in durable.items():
        row = data_by_name.get(noun)
        if row is None:
            continue
        plan_class = cells.get("data-class") or cells.get("data-classification")
        if row.get("data_class") != plan_class:
            hard.append(f"H6 data entity {noun!r} does not copy plan data class")
        lifecycle = row.get("lifecycle", {})
        for field in V2_LIFECYCLE_FIELDS:
            if isinstance(lifecycle, dict) and lifecycle.get(field) != cells.get(field):
                hard.append(
                    f"H6 data entity {noun!r} does not copy plan {field} disposition"
                )
        if row.get("plan_trace") != "feature-plan.md#durable-state-closure":
            hard.append(
                f"H6 data entity {noun!r} must trace feature-plan.md#durable-state-closure"
            )
    for collection, field in (
        ("integration_flows", "plan_trace"),
        ("dynamic_scenarios", "journey_ref"),
    ):
        for index, row in enumerate(rows[collection]):
            if not _plan_trace_resolves(plan_dir, row.get(field)):
                hard.append(f"H6 {collection}[{index}].{field} does not resolve")

    threat_ids = _plan_contract_ids(plan_dir, "threat-model.md", "TZ")
    interaction_ids = _plan_contract_ids(
        plan_dir, "interaction-contract.md", "IC"
    )
    security_ids = [row.get("obligation_id") for row in rows["security_realizations"]]
    contract_ids = [row.get("obligation_id") for row in rows["contract_realizations"]]
    if (
        isinstance(coverage.get("security"), dict)
        and coverage["security"].get("status") == "complete"
        and (set(security_ids) != threat_ids or len(security_ids) != len(set(security_ids)))
    ):
        hard.append(
            "H6 complete security coverage requires exactly one realization per TZ obligation"
        )
    if (
        isinstance(coverage.get("contracts"), dict)
        and coverage["contracts"].get("status") == "complete"
        and (
            set(contract_ids) != interaction_ids
            or len(contract_ids) != len(set(contract_ids))
        )
    ):
        hard.append(
            "H6 complete contracts coverage requires exactly one realization per IC obligation"
        )


def _v2_feature_mappings(
    data: dict,
    plan_features: list[str],
    source_kinds: dict[str, str],
    rows: dict[str, list[dict]],
    by_id: dict[str, dict[str, dict]],
    hard: list[str],
) -> None:
    raw = data.get("feature_mappings")
    if not isinstance(raw, list):
        hard.append("H7 feature_mappings must be an array")
        return
    mappings: dict[str, dict] = {}
    ordered_features: list[str] = []
    collection_order = {
        collection: list(by_id[collection])
        for collection in V2_COLLECTION_FIELDS
    }
    for index, value in enumerate(raw):
        label = f"feature_mappings[{index}]"
        row = _v2_exact(value, label, V2_FEATURE_MAPPING_FIELDS, hard)
        feature_id = row.get("feature_id")
        if not isinstance(feature_id, str) or not feature_id:
            hard.append(f"H7 {label}.feature_id must be non-empty")
            continue
        if feature_id in mappings:
            hard.append(f"H7 feature_mappings contains duplicate feature {feature_id}")
        mappings[feature_id] = row
        ordered_features.append(feature_id)
        if row.get("mapping_scope") not in V2_MAPPING_SCOPES:
            hard.append(f"H7 {label}.mapping_scope is invalid")
        if row.get("evidence_state") not in V2_EVIDENCE_STATES:
            hard.append(f"H7 {label}.evidence_state is invalid")
        elif row.get("evidence_state") == "unknown":
            hard.append(
                f"H7 {label}.evidence_state cannot be unknown because feature "
                "mapping rows are not typed-gap reference targets"
            )
        _evidence_refs(row, label, source_kinds, hard)
        shared = False
        for field, collection in V2_MAPPING_COLLECTIONS.items():
            values = _v2_string_list(row.get(field), f"{label}.{field}", hard)
            unknown = [item for item in values if item not in by_id[collection]]
            if unknown:
                hard.append(
                    f"H7 {label}.{field} has unresolved id(s): "
                    + ", ".join(unknown)
                )
            expected_order = [
                item for item in collection_order[collection] if item in set(values)
            ]
            if values != expected_order:
                hard.append(
                    f"H7 {label}.{field} must preserve canonical collection order"
                )
            for item in values:
                features = by_id[collection].get(item, {}).get("feature_ids", [])
                if isinstance(features, list) and len(features) > 1:
                    shared = True
        expected_scope = "cross-feature" if shared else "feature-local"
        if row.get("mapping_scope") != expected_scope:
            hard.append(
                f"H7 {label}.mapping_scope must be {expected_scope!r} from "
                "its mapped structural rows"
            )
    if ordered_features != plan_features:
        hard.append(
            "H7 feature_mappings must contain exactly one row per plan feature "
            "in plan order"
        )

    for field, collection in V2_MAPPING_COLLECTIONS.items():
        if collection in {"direction_realizations", "gaps"}:
            continue
        for item_id, item in by_id[collection].items():
            expected = item.get("feature_ids", [])
            actual = [
                feature_id
                for feature_id in plan_features
                if item_id in mappings.get(feature_id, {}).get(field, [])
            ]
            if actual != expected:
                hard.append(
                    f"H7 {collection} {item_id} feature_ids must equal the "
                    "reverse projection from feature_mappings"
                )
    for collection, field in (
        ("direction_realizations", "direction_realization_ids"),
        ("gaps", "gap_ids"),
    ):
        for item_id, item in by_id[collection].items():
            actual = [
                feature_id
                for feature_id in plan_features
                if item_id in mappings.get(feature_id, {}).get(field, [])
            ]
            if not actual:
                hard.append(f"H7 {collection} {item_id} is not mapped to a feature")

    related_collections = {
        **V2_REALIZED_BY_KINDS,
        "driver": "drivers",
        "open-question": "open_questions",
        "gap": "gaps",
    }
    for gap_id, gap in by_id["gaps"].items():
        affected: set[str] = set()
        for ref in gap.get("related_refs", []):
            if not isinstance(ref, dict):
                continue
            collection = related_collections.get(ref.get("kind"))
            if collection is None:
                continue
            target = by_id[collection].get(ref.get("id"))
            if isinstance(target, dict):
                affected.update(
                    value
                    for value in target.get("feature_ids", [])
                    if isinstance(value, str)
                )
        expected = [feature_id for feature_id in plan_features if feature_id in affected]
        actual = [
            feature_id
            for feature_id in plan_features
            if gap_id in mappings.get(feature_id, {}).get("gap_ids", [])
        ]
        if not expected:
            hard.append(
                f"H7 gap {gap_id} must have at least one related structural "
                "reference with affected feature_ids"
            )
        if actual != expected:
            hard.append(
                f"H7 gap {gap_id} feature mapping must equal the union of "
                "related target feature_ids"
            )


def _check_package_v2(
    arch_dir: Path,
    repo_root: Path,
    data: dict,
    *,
    allow_proposed: bool,
    consumer: bool,
    architecture_input: Path | None,
) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    advisory: list[str] = []

    present = {entry.name for entry in arch_dir.iterdir()}
    missing = sorted(REQUIRED_FILES - present)
    extra = sorted(present - REQUIRED_FILES)
    if missing:
        hard.append("H1 missing required file(s): " + ", ".join(missing))
    if extra:
        hard.append("H1 unexpected file(s) in coherent package: " + ", ".join(extra))
    for name in sorted(REQUIRED_FILES):
        target = arch_dir / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            hard.append(f"H1 required artifact must be a regular non-symlink file: {name}")
        elif target.is_file() and target.stat().st_size == 0:
            hard.append(f"H1 required artifact is empty: {name}")

    expected_keys = (
        V2_TOP_LEVEL_KEYS_WITH_RESET
        if "revision_reset" in data
        else V2_TOP_LEVEL_KEYS
    )
    if tuple(data) != expected_keys:
        missing_keys = [field for field in expected_keys if field not in data]
        extra_keys = sorted(set(data) - set(expected_keys))
        if missing_keys:
            hard.append("H2 architecture.json is missing key(s): " + ", ".join(missing_keys))
        if extra_keys:
            hard.append("H2 architecture.json has unknown key(s): " + ", ".join(extra_keys))
        if not missing_keys and not extra_keys:
            hard.append("H2 architecture.json keys must occur in canonical v2 order")
    if data.get("$schema") != V2_SCHEMA_URN:
        hard.append(f"H2 $schema must be {V2_SCHEMA_URN!r}")
    if data.get("schema_version") != V2_SCHEMA_VERSION:
        hard.append("H2 schema_version must be 2")
    generator = _v2_exact(
        data.get("generator"), "generator", ("name", "version"), hard
    )
    if generator.get("name") != V2_GENERATOR_NAME:
        hard.append(f"H2 generator.name must be {V2_GENERATOR_NAME!r}")
    plugin_version = _v2_plugin_version(hard)
    if generator.get("version") != plugin_version:
        hard.append("H2 generator.version must equal the core-engineering plugin version")

    slug = data.get("project_slug")
    if not isinstance(slug, str) or not PROJECT_SLUG_RE.fullmatch(slug):
        hard.append("H2 project_slug must be canonical lowercase kebab-case")
        slug = ""
    lifecycle = data.get("lifecycle_status")
    if lifecycle not in V2_LIFECYCLE_STATUSES:
        hard.append(f"H2 lifecycle_status must be one of {sorted(V2_LIFECYCLE_STATUSES)}")
    elif lifecycle == "proposed" and not allow_proposed:
        hard.append(
            "H2 lifecycle_status proposed is valid only for scratch lint "
            "with --allow-proposed"
        )
    if data.get("baseline_status") not in V2_BASELINE_STATUSES:
        hard.append(f"H2 baseline_status must be one of {sorted(V2_BASELINE_STATUSES)}")
    _v2_int(data.get("architecture_revision"), "architecture_revision", hard)
    _v2_int(data.get("source_plan_revision"), "source_plan_revision", hard)

    expected_plan_path = (
        (Path("docs") / "plans" / slug).as_posix() if slug else None
    )
    if data.get("source_plan_path") != expected_plan_path:
        hard.append(f"H2 source_plan_path must be {expected_plan_path!r}")
    plan_dir = (
        repo_root / expected_plan_path
        if isinstance(expected_plan_path, str)
        else repo_root / "__invalid_plan_path__"
    )
    if (
        not _inside(repo_root, plan_dir)
        or plan_dir.is_symlink()
        or not plan_dir.is_dir()
        or _symlink_components(repo_root, plan_dir)
    ):
        hard.append("H3 source plan directory is missing or unsafe")
    if consumer and slug:
        canonical = repo_root / "docs" / "plans" / slug / "architecture"
        supplied = architecture_input if architecture_input is not None else arch_dir
        if (
            supplied.is_symlink()
            or _symlink_components(repo_root, canonical)
            or arch_dir.resolve() != canonical.resolve()
        ):
            hard.append(
                "H2 consumer architecture path must be the canonical "
                "non-symlink repository package"
            )

    plan: dict = {}
    plan_path = plan_dir / "plan.json"
    try:
        loaded_plan = _strict_json_loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(loaded_plan, dict):
            raise ValueError("plan.json does not contain an object")
        plan = loaded_plan
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        hard.append(f"H3 source plan.json is unreadable: {exc}")
    if plan:
        if plan.get("project_slug") != slug:
            hard.append("H3 source plan project_slug does not match architecture")
        if plan.get("plan_revision") != data.get("source_plan_revision"):
            hard.append("H3 source_plan_revision does not equal plan.json plan_revision")
        _validate_source_architecture_disposition(plan, plan_dir, hard, advisory)

    source_kinds = _v2_sources(
        data,
        repo_root,
        plan_dir,
        consumer=consumer,
        hard=hard,
        advisory=advisory,
    )
    for index, feature in enumerate(
        plan.get("features", []) if isinstance(plan.get("features"), list) else []
    ):
        file_value = feature.get("file") if isinstance(feature, dict) else None
        if not isinstance(file_value, str) or not file_value.strip():
            hard.append(f"H4 plan features[{index}].file must be a non-empty path")
            continue
        relative = Path(file_value)
        candidate = plan_dir / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not _inside(plan_dir, candidate)
            or candidate.is_symlink()
            or not candidate.is_file()
        ):
            hard.append(f"H4 plan feature source path is missing or unsafe: {file_value}")
            continue
        feature_path = candidate.relative_to(repo_root).as_posix()
        if source_kinds.get(feature_path) != "plan":
            hard.append(f"H4 plan feature source is not tracked as plan: {feature_path}")
    _v2_projections(data, source_kinds, hard)
    _v2_narrative(data, source_kinds, hard)

    system_boundary = _v2_exact(
        data.get("system_boundary"),
        "system_boundary",
        V2_SYSTEM_BOUNDARY_FIELDS,
        hard,
    )
    if system_boundary.get("id") != "SB-001":
        hard.append("H2 system_boundary.id must be SB-001")
    for field in ("name", "responsibility"):
        _v2_nonempty_string(
            system_boundary.get(field), f"system_boundary.{field}", hard
        )
    for field in ("in_scope", "out_of_scope"):
        _v2_string_list(
            system_boundary.get(field),
            f"system_boundary.{field}",
            hard,
            nonempty=True,
        )
    if system_boundary.get("evidence_state") not in V2_EVIDENCE_STATES:
        hard.append("H2 system_boundary.evidence_state is invalid")
    _evidence_refs(system_boundary, "system_boundary", source_kinds, hard)

    rows: dict[str, list[dict]] = {}
    by_id: dict[str, dict[str, dict]] = {}
    for collection in V2_COLLECTION_FIELDS:
        rows[collection], by_id[collection] = _v2_collection(
            data, collection, source_kinds, hard
        )
    _v2_validate_rows(rows, source_kinds, repo_root, hard)
    _v2_reference_checks(data, rows, by_id, hard)

    triggers: list[str] = []
    posture = plan.get("architecture_disposition")
    if isinstance(posture, dict):
        raw_triggers = posture.get("triggers")
        if isinstance(raw_triggers, list) and all(
            isinstance(item, str) for item in raw_triggers
        ):
            triggers = raw_triggers
    transition_applicable, _ = _v2_selected_direction(
        data, plan, plan_dir, rows, by_id, hard
    )
    required_dimensions = _v2_required_dimensions(
        triggers, plan_dir, transition_applicable, rows
    )
    _v2_coverage_and_readiness(
        data,
        triggers,
        required_dimensions,
        transition_applicable,
        source_kinds,
        rows,
        by_id,
        hard,
    )
    coverage = data.get("coverage")
    _v2_plan_closure(
        plan_dir,
        rows,
        coverage if isinstance(coverage, dict) else {},
        hard,
    )

    plan_features: list[str] = []
    raw_features = plan.get("features")
    if not isinstance(raw_features, list) or not raw_features:
        hard.append("H7 source plan features must be a non-empty array")
    else:
        for index, feature in enumerate(raw_features):
            feature_id = feature.get("id") if isinstance(feature, dict) else None
            if not isinstance(feature_id, str) or not feature_id:
                hard.append(f"H7 source plan features[{index}].id must be non-empty")
            else:
                plan_features.append(feature_id)
    if len(plan_features) != len(set(plan_features)):
        hard.append("H7 source plan feature ids must be unique")
    _v2_feature_mappings(
        data, plan_features, source_kinds, rows, by_id, hard
    )

    open_gap_ids = {
        row.get("id")
        for row in rows["gaps"]
        if row.get("status") == "open"
    }
    collection_gap_routing: dict[str, tuple[str, str | None]] = {
        "drivers": ("driver", "requirements_traceability"),
        "actors": ("actor", "system_context"),
        "context_relationships": ("context-relationship", "system_context"),
        "components": ("component", "containers"),
        "relationships": ("relationship", "containers"),
        "deployment_nodes": ("deployment-node", "deployment"),
        "deployments": ("deployment", "deployment"),
        "deployment_connections": ("deployment-connection", "deployment"),
        "data_entities": ("data-entity", "data"),
        "integration_flows": ("integration-flow", "integrations"),
        "dynamic_scenarios": ("dynamic-scenario", "dynamic_behavior"),
        "trust_boundaries": ("trust-boundary", "security"),
        "security_realizations": ("security-realization", "security"),
        "contract_realizations": ("contract-realization", "contracts"),
        "transitions": ("transition", "transitions"),
        "quality_scenarios": ("quality-scenario", "quality_attributes"),
        "operations": ("operation", "operability"),
        "decisions": ("decision", None),
        "open_questions": ("open-question", None),
        "risks": ("risk", None),
    }

    def has_routed_open_gap(
        row_id: object,
        related_kind: str,
        dimension: str | None,
    ) -> bool:
        return any(
            gap.get("id") in open_gap_ids
            and (dimension is None or gap.get("dimension") == dimension)
            and any(
                isinstance(ref, dict)
                and ref.get("kind") == related_kind
                and ref.get("id") == row_id
                for ref in gap.get("related_refs", [])
            )
            for gap in rows["gaps"]
        )

    def contains_literal_unknown(value: object, *, root: bool = False) -> bool:
        if isinstance(value, str):
            return value == "unknown"
        if isinstance(value, list):
            return any(contains_literal_unknown(item) for item in value)
        if isinstance(value, dict):
            return any(
                contains_literal_unknown(item)
                for key, item in value.items()
                if not root or key not in {"evidence", "evidence_state"}
            )
        return False

    for collection, collection_rows in rows.items():
        if collection == "gaps":
            continue
        routing = collection_gap_routing.get(collection)
        for index, row in enumerate(collection_rows):
            unknown_evidence = row.get("evidence_state") == "unknown"
            unknown_value = contains_literal_unknown(row, root=True)
            if not unknown_evidence and not unknown_value:
                continue
            if routing is None:
                hard.append(
                    f"H6 {collection}[{index}] cannot use unknown because the "
                    "row has no typed-gap routing kind"
                )
                continue
            related_kind, dimension = routing
            if not has_routed_open_gap(row.get("id"), related_kind, dimension):
                hard.append(
                    f"H6 {collection}[{index}] unknown evidence/value requires "
                    "an open same-dimension typed gap related to the exact row"
                )
    if system_boundary.get("evidence_state") == "unknown" or contains_literal_unknown(
        system_boundary, root=True
    ):
        if not has_routed_open_gap("SB-001", "system-boundary", "system_context"):
            hard.append(
                "H6 system_boundary unknown evidence/value requires an open "
                "system_context gap related to SB-001"
            )

    if lifecycle == "published":
        for index, decision in enumerate(rows["decisions"]):
            if decision.get("status") != "accepted":
                hard.append(
                    f"H6 published decisions[{index}].status must be accepted"
                )

    reset = data.get("revision_reset")
    if reset is not None:
        reset_row = _v2_exact(
            reset, "revision_reset", V2_REVISION_RESET_FIELDS, hard
        )
        _v2_nonempty_string(reset_row.get("reason"), "revision_reset.reason", hard)
        if reset_row.get("recorded_by") != "human":
            hard.append("H2 revision_reset.recorded_by must be human")
        if reset_row.get("gate") != "Invalid Architecture Package Recovery":
            hard.append("H2 revision_reset.gate is invalid")
    extensions = data.get("extensions")
    if not isinstance(extensions, dict):
        hard.append("H2 extensions must be an object")
    else:
        for namespace, payload in extensions.items():
            if not isinstance(namespace, str) or not EXTENSION_NAMESPACE_RE.fullmatch(
                namespace
            ):
                hard.append(
                    f"H2 extensions key is not a reverse-DNS namespace: {namespace!r}"
                )
            if not isinstance(payload, dict):
                hard.append(f"H2 extensions.{namespace} must be an object")

    approval = _v2_exact(
        data.get("approval"), "approval", V2_APPROVAL_FIELDS, hard
    )
    if approval.get("gate") != "Final Architecture Approval":
        hard.append("H8 approval.gate must be 'Final Architecture Approval'")
    review_digest = approval.get("review_payload_sha256")
    if not isinstance(review_digest, str) or not SHA_RE.fullmatch(review_digest):
        hard.append("H8 approval.review_payload_sha256 must be 64 lowercase hex")
    if lifecycle == "proposed":
        expected_pending = {
            "decision": "pending",
            "recorded_by": "pending",
            "recorded_at": None,
            "authority": None,
            "reference": None,
            "gate": "Final Architecture Approval",
            "receipt_sha256": None,
        }
        for field, expected in expected_pending.items():
            if approval.get(field) != expected:
                hard.append(f"H8 proposed approval.{field} must be {expected!r}")
    elif lifecycle == "published":
        if approval.get("decision") != data.get("baseline_status"):
            hard.append("H8 published approval.decision must equal baseline_status")
        recorded_by = _v2_nonempty_string(
            approval.get("recorded_by"), "approval.recorded_by", hard
        )
        if recorded_by is not None and APPROVAL_PLACEHOLDER_RE.fullmatch(
            recorded_by.strip()
        ):
            hard.append(
                "H8 approval.recorded_by must identify the human or recorded role"
            )
        recorded_at = approval.get("recorded_at")
        if not isinstance(recorded_at, str) or not RFC3339_UTC_RE.fullmatch(recorded_at):
            hard.append("H8 approval.recorded_at must be RFC 3339 UTC")
        for field in ("authority", "reference"):
            value = _v2_nonempty_string(
                approval.get(field), f"approval.{field}", hard
            )
            if value is not None and APPROVAL_PLACEHOLDER_RE.fullmatch(value.strip()):
                hard.append(f"H8 approval.{field} must not be a placeholder")
        receipt = approval.get("receipt_sha256")
        if not isinstance(receipt, str) or not SHA_RE.fullmatch(receipt):
            hard.append("H8 approval.receipt_sha256 must be 64 lowercase hex")

    try:
        renderer = _v2_load_renderer()
        render_result, render_code = renderer.check_package(arch_dir)
        if render_code != 0:
            details = render_result.get("mismatches") or [render_result.get("message")]
            hard.extend(
                f"H1 deterministic renderer check failed: {detail}"
                for detail in details
                if isinstance(detail, str)
            )
    except Exception as exc:
        hard.append(
            "H1 deterministic renderer check could not run: "
            f"{type(exc).__name__}: {exc}"
        )

    prohibited_claims = (
        "approved for deployment", "certified compliant", "deployment authorized",
        "production ready", "ready for production", "release approved",
        "security accepted", "security approved",
    )
    try:
        projection_text = "\n".join(
            (arch_dir / path).read_text(encoding="utf-8").lower()
            for path in (
                "solution-architecture.md", "views.md",
                "data-and-integrations.md", "quality-attributes.md",
            )
            if (arch_dir / path).is_file()
        )
    except (OSError, UnicodeError):
        projection_text = ""
    for claim in prohibited_claims:
        if claim in projection_text:
            hard.append(f"H8 prohibited authority claim {claim!r}")
    return hard, advisory


def check_package(
    arch_dir: Path,
    repo_root: Path,
    data: dict,
    allow_proposed: bool = False,
    consumer: bool = False,
    architecture_input: Path | None = None,
    allow_legacy_v1: bool = False,
) -> tuple[list[str], list[str]]:
    schema_version = data.get("schema_version")
    if schema_version == V2_SCHEMA_VERSION:
        return _check_package_v2(
            arch_dir,
            repo_root,
            data,
            allow_proposed=allow_proposed,
            consumer=consumer,
            architecture_input=architecture_input,
        )
    if schema_version == SCHEMA_VERSION and allow_legacy_v1:
        hard, advisory = _check_package_v1(
            arch_dir,
            repo_root,
            data,
            allow_proposed=allow_proposed,
            consumer=consumer,
            architecture_input=architecture_input,
        )
        advisory.insert(
            0,
            "A2 legacy schema v1 lint is diagnostic only; regenerate the package "
            "as schema v2 before any consumer or publication use",
        )
        return hard, advisory
    if schema_version == SCHEMA_VERSION:
        return (
            [
                "H2 schema v1 is non-authoritative and requires regeneration to "
                "ce-architecture schema v2; use --allow-legacy-v1 only for "
                "diagnostic migration"
            ],
            [],
        )
    return (
        [
            f"H2 unsupported architecture schema_version {schema_version!r}; "
            "regenerate to ce-architecture schema v2"
        ],
        [],
    )


def result_payload(
    hard: list[str],
    advisory: list[str],
    data: dict | None = None,
) -> dict:
    payload = {
        "schema_version": 1,
        "status": "fail" if hard else "pass",
        "hard_failures": hard,
        "advisory": advisory,
        "blocking_hard": len(hard),
    }
    if isinstance(data, dict) and data.get("schema_version") == V2_SCHEMA_VERSION:
        payload.update(
            {
                "architecture_schema_version": V2_SCHEMA_VERSION,
                "project_slug": data.get("project_slug"),
                "lifecycle_status": data.get("lifecycle_status"),
                "baseline_status": data.get("baseline_status"),
                "architecture_revision": data.get("architecture_revision"),
                "source_plan_revision": data.get("source_plan_revision"),
                "package_receipt_sha256": (
                    data.get("approval", {}).get("receipt_sha256")
                    if not hard
                    and data.get("lifecycle_status") == "published"
                    and isinstance(data.get("approval"), dict)
                    else None
                ),
            }
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint a ce-architecture package")
    parser.add_argument("architecture_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--consumer",
        action="store_true",
        help=(
            "consumer mode: repository-kind source drift is advisory while "
            "plan/brief/ADR/reference drift remains blocking"
        ),
    )
    parser.add_argument(
        "--allow-proposed",
        action="store_true",
        help="allow lifecycle_status=proposed for the pre-approval scratch package only",
    )
    parser.add_argument(
        "--allow-legacy-v1",
        action="store_true",
        help=(
            "run non-authoritative schema-v1 migration diagnostics; schema v1 "
            "is rejected by default and can never be consumed or published"
        ),
    )
    args = parser.parse_args(argv)

    try:
        repo_root = args.repo_root.resolve()
        if not repo_root.is_dir():
            raise ArchitectureLintError(f"repository root not found: {repo_root}")
        architecture_input = args.architecture_dir.absolute()
        arch_dir = architecture_input.resolve()
        data = load_package(arch_dir)
        hard, advisory = check_package(
            arch_dir,
            repo_root,
            data,
            allow_proposed=args.allow_proposed,
            consumer=args.consumer,
            architecture_input=architecture_input,
            allow_legacy_v1=args.allow_legacy_v1,
        )
    except (
        ArchitectureLintError,
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        payload = {
            "schema_version": 1,
            "status": "error",
            "hard_failures": [],
            "advisory": [],
            "blocking_hard": 0,
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"architecture-lint: ERROR — {exc}", file=sys.stderr)
        return 2

    payload = result_payload(hard, advisory, data)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"architecture-lint: {payload['status'].upper()}")
        for item in hard:
            print(f"HARD: {item}")
        for item in advisory:
            print(f"ADVISORY: {item}")
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
