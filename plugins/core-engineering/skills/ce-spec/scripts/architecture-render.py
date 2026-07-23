#!/usr/bin/env python3
"""Deterministically render and verify a ce-architecture schema-v2 package.

The v2 manifest is the only authored source.  This helper renders the four core
Markdown projections, records their hashes for a proposed review payload, and
checks that a package still matches those deterministic bytes.

Exit codes:
  0  rendered / matching
  1  deterministic mismatch or invalid v2 render input
  2  input/output could not be read or written safely
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path


SCHEMA_URN = "urn:vg-sdlc:ce-architecture:architecture:v2"
SCHEMA_VERSION = 2
FINAL_APPROVAL_GATE = "Final Architecture Approval"
CORE_PROJECTIONS = (
    ("PROJ-001", "solution-architecture", "solution-architecture.md"),
    ("PROJ-002", "architecture-views", "views.md"),
    ("PROJ-003", "data-and-integrations", "data-and-integrations.md"),
    ("PROJ-004", "quality-attributes", "quality-attributes.md"),
)
CORE_PATHS = tuple(row[2] for row in CORE_PROJECTIONS)
PENDING_APPROVAL = {
    "decision": "pending",
    "recorded_by": "pending",
    "recorded_at": None,
    "authority": None,
    "reference": None,
    "gate": FINAL_APPROVAL_GATE,
    "review_payload_sha256": None,
    "receipt_sha256": None,
}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class RenderInputError(ValueError):
    """The manifest cannot be rendered deterministically."""


def _strict_object_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise RenderInputError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _strict_json_loads(payload: str) -> object:
    return json.loads(payload, object_pairs_hook=_strict_object_pairs)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_package(manifest: dict, documents: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    manifest_bytes = _json_bytes(manifest)
    digest.update(b"architecture.json\0")
    digest.update(str(len(manifest_bytes)).encode("ascii"))
    digest.update(b"\0")
    digest.update(manifest_bytes)
    for projection in manifest.get("projections", []):
        path = projection.get("path") if isinstance(projection, dict) else None
        if not isinstance(path, str) or path not in documents:
            raise RenderInputError(
                f"registered projection path is not renderable: {path!r}"
            )
        payload = documents[path]
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
    return digest.hexdigest()


def review_payload_sha256(
    data: dict,
    documents: dict[str, bytes] | None = None,
) -> str:
    """Hash the exact review model and projections in a reproducible posture.

    Publication changes lifecycle and approval receipt fields.  Consumers can
    still reproduce the reviewed payload because this hash normalizes those
    mutable fields back to the canonical proposed/pending posture.
    """

    normalized = copy.deepcopy(data)
    normalized["lifecycle_status"] = "proposed"
    normalized["approval"] = copy.deepcopy(PENDING_APPROVAL)
    # Always derive review bytes from the normalized review manifest.  The
    # optional argument remains accepted for source compatibility, but cannot
    # accidentally make a published projection redefine the reviewed payload.
    normalized_documents = render_documents(normalized)
    return _digest_package(normalized, normalized_documents)


def receipt_sha256(data: dict, documents: dict[str, bytes]) -> str:
    """Hash a published package while excluding only the receipt's own value."""

    normalized = copy.deepcopy(data)
    approval = normalized.get("approval")
    if not isinstance(approval, dict):
        raise RenderInputError("approval must be an object before receipt hashing")
    approval["receipt_sha256"] = None
    return _digest_package(normalized, documents)


def _text(value: object, *, fallback: str = "—") -> str:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        rendered = str(value).strip()
        return rendered or fallback
    return fallback


def _cell(value: object) -> str:
    rendered = _text(value)
    return (
        rendered.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", "<br>")
        .replace("\n", "<br>")
    )


def _list(value: object, *, separator: str = ", ") -> str:
    if not isinstance(value, list) or not value:
        return "—"
    return separator.join(_text(item) for item in value)


def _refs(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "—"
    return ", ".join(f"`{_text(item)}`" for item in value)


def _paragraphs(value: object) -> str:
    if isinstance(value, str):
        return value.strip() or "None recorded."
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "\n".join(f"- {item}" for item in items) or "None recorded."
    return "None recorded."


def _table(headers: list[str], rows: list[list[object]]) -> str:
    result = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    for row in rows:
        result.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return "\n".join(result)


def _evidence(row: dict) -> str:
    return _refs(row.get("evidence"))


def _feature_ids(row: dict) -> str:
    return _list(row.get("feature_ids"))


def _realized_by(row: dict) -> str:
    values = row.get("realized_by")
    if not isinstance(values, list) or not values:
        return "—"
    rendered: list[str] = []
    for value in values:
        if isinstance(value, dict):
            rendered.append(f"{_text(value.get('kind'))}:{_text(value.get('id'))}")
    return ", ".join(rendered) or "—"


def _related_refs(row: dict) -> str:
    values = row.get("related_refs")
    if not isinstance(values, list) or not values:
        return "—"
    rendered: list[str] = []
    for value in values:
        if isinstance(value, dict):
            rendered.append(f"{_text(value.get('kind'))}:{_text(value.get('id'))}")
    return ", ".join(rendered) or "—"


def _mermaid_label(value: object) -> str:
    return _text(value).replace('"', "'").replace("\n", " ")


def _projection_gaps(data: dict, dimensions: set[str]) -> str:
    rows = [
        [
            row.get("id"),
            row.get("dimension"),
            row.get("gap_type"),
            row.get("statement"),
            row.get("status"),
        ]
        for row in data.get("gaps", [])
        if row.get("dimension") in dimensions
    ]
    if rows:
        return _table(["Gap", "Dimension", "Type", "Statement", "Status"], rows)
    states = [
        f"{dimension}={data.get('coverage', {}).get(dimension, {}).get('status')}"
        for dimension in data.get("coverage", {})
        if dimension in dimensions
    ]
    return "Coverage: " + (", ".join(states) if states else "—")


def _alternatives(row: dict) -> str:
    values = row.get("alternatives")
    if not isinstance(values, list) or not values:
        return "—"
    return "; ".join(
        f"{_text(value.get('option'))}: {_text(value.get('consequence'))} "
        f"(rejected: {_text(value.get('rejection_reason'))})"
        for value in values
        if isinstance(value, dict)
    ) or "—"


def _evidence_claims(row: dict) -> str:
    claims = row.get("evidence_claims")
    if not isinstance(claims, list) or not claims:
        return "—"
    return "; ".join(
        f"{_text(claim.get('field'))}={_text(claim.get('path'))} :: "
        f"{_text(claim.get('literal'))} → {_text(claim.get('derivation'))}"
        for claim in claims
        if isinstance(claim, dict)
    ) or "—"


def _slice(row: dict, fields: tuple[str, ...]) -> str:
    parts = [
        f"{field.removesuffix('_ids')}={_list(row.get(field))}"
        for field in fields
        if row.get(field)
    ]
    return "; ".join(parts) or "—"


def _diagram_id(value: object) -> str:
    result = re.sub(r"[^A-Za-z0-9]", "", _text(value, fallback="node"))
    return f"N{result}" if result[:1].isdigit() else result or "node"


def _flowchart(
    nodes: list[dict],
    edges: list[dict],
    *,
    direction: str,
    edge_from: str = "from",
    edge_to: str = "to",
    edge_detail: str = "interaction",
) -> str:
    known = {
        row.get("id"): row
        for row in nodes
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    lines = ["```mermaid", f"flowchart {direction}"]
    for row_id, row in known.items():
        lines.append(
            f'  {_diagram_id(row_id)}["{_mermaid_label(row_id)} '
            f'{_mermaid_label(row.get("name"))}"]'
        )
    for row in edges:
        source, target = row.get(edge_from), row.get(edge_to)
        if source not in known or target not in known:
            continue
        label = f"{_text(row.get('id'))} {_text(row.get(edge_detail))}"
        lines.append(
            f'  {_diagram_id(source)} -->|"{_mermaid_label(label)}"| '
            f"{_diagram_id(target)}"
        )
    lines.append("```")
    return "\n".join(lines)


def _sequence_diagram(scenario: dict) -> str:
    lines = ["```mermaid", "sequenceDiagram"]
    for step in scenario.get("steps", []):
        if not isinstance(step, dict):
            continue
        lines.append(
            f"  {_diagram_id(step.get('from'))}->>"
            f"{_diagram_id(step.get('to'))}: {_text(step.get('ordinal'))} "
            f"{_mermaid_label(step.get('interaction'))}"
        )
    lines.append("```")
    return "\n".join(lines)


def _render_solution_v2(data: dict) -> str:
    narrative = data.get("narrative", {})
    drivers = [
        [
            row.get("id"), row.get("name"), row.get("statement"),
            row.get("evidence_state"), row.get("source"), row.get("consequence"),
            _feature_ids(row), _evidence(row),
        ]
        for row in data.get("drivers", [])
    ]
    realizations = [
        [
            row.get("id"), row.get("exploration_id"),
            row.get("selected_option_id"), row.get("selected_option_sha256"),
            row.get("dimension"), row.get("ordinal"), row.get("statement"),
            row.get("statement_sha256"), row.get("realization_status"),
            _realized_by(row), _list(row.get("gap_ids")),
            row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("direction_realizations", [])
    ]
    decisions = [
        [
            row.get("id"), row.get("title"), row.get("context"),
            row.get("decision"), row.get("rationale"), _alternatives(row),
            _list(row.get("consequences"), separator="; "),
            row.get("reversibility"), row.get("cost_if_wrong"), row.get("status"),
            row.get("adr_path"), row.get("owner"),
            f"{_text(row.get('decided_by'))} / {_text(row.get('decided_at'))}",
            _feature_ids(row), row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("decisions", [])
    ]
    mappings = [
        [
            row.get("feature_id"),
            row.get("mapping_scope"),
            _slice(row, ("direction_realization_ids", "driver_ids")),
            _slice(row, ("actor_ids", "context_relationship_ids")),
            _slice(row, ("component_ids", "relationship_ids")),
            _slice(
                row,
                (
                    "deployment_node_ids", "deployment_ids",
                    "deployment_connection_ids",
                ),
            ),
            _slice(
                row,
                (
                    "data_ids", "integration_ids", "dynamic_scenario_ids",
                ),
            ),
            _slice(
                row,
                (
                    "trust_boundary_ids", "security_realization_ids",
                    "contract_realization_ids",
                ),
            ),
            _slice(row, ("transition_ids",)),
            _slice(row, ("quality_ids", "operation_ids")),
            _slice(
                row,
                (
                    "decision_ids", "open_question_ids", "risk_ids", "gap_ids",
                ),
            ),
            row.get("evidence_state"),
            _evidence(row),
        ]
        for row in data.get("feature_mappings", [])
    ]
    assumptions = [
        [
            row.get("id"), row.get("statement"), row.get("evidence_state"),
            _evidence(row),
        ]
        for row in narrative.get("assumptions", [])
    ]
    gaps = [
        [
            row.get("id"), row.get("dimension"), row.get("gap_type"),
            row.get("statement"), row.get("impact"), row.get("material"),
            row.get("owner"), row.get("next_action"), row.get("closure_criteria"),
            row.get("blocking_stage"), row.get("status"),
            _related_refs(row), _evidence(row),
        ]
        for row in data.get("gaps", [])
    ]
    risks = [
        [
            row.get("id"), row.get("title"), row.get("statement"),
            row.get("likelihood"), row.get("impact"), row.get("severity"),
            row.get("owner"), row.get("mitigation"), row.get("contingency"),
            row.get("trigger"), _related_refs(row), _feature_ids(row),
            row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("risks", [])
    ]
    questions = [
        [
            row.get("id"), row.get("question"), row.get("status"), row.get("material"),
            row.get("owner"), row.get("needed_by"), _list(row.get("options")),
            _related_refs(row), _feature_ids(row), row.get("evidence_state"),
            _evidence(row),
        ]
        for row in data.get("open_questions", [])
    ]
    validation = [
        [
            row.get("id"), row.get("statement"), row.get("owner"),
            row.get("evidence_state"), _evidence(row),
        ]
        for row in narrative.get("validation_strategy", [])
    ]
    required_dimensions = set(
        data.get("coverage_profile", {}).get("required_dimensions", [])
    )
    coverage_rows = [
        [
            dimension,
            dimension in required_dimensions,
            row.get("status"),
            _list(row.get("gap_ids")),
            _refs(row.get("evidence")),
        ]
        for dimension, row in data.get("coverage", {}).items()
    ]
    return (
        f"# Solution Architecture: {data.get('project_slug')}\n\n"
        f"> Generated by `{data.get('generator', {}).get('name')}` "
        f"{data.get('generator', {}).get('version')}\n"
        f"> Baseline status: {data.get('baseline_status')}\n"
        f"> Source plan: `{data.get('source_plan_path')}/` revision "
        f"{data.get('source_plan_revision')}\n"
        f"> Architecture revision: {data.get('architecture_revision')}\n"
        "> Authority: architecture-baseline-only; no security acceptance, compliance "
        "attestation, release approval, or deployment authority.\n\n"
        "## Executive Summary\n\n"
        f"{_paragraphs(narrative.get('executive_summary'))}\n\n"
        "## Scope and Non-Goals\n\n"
        f"**Scope**\n\n{_paragraphs(narrative.get('scope'))}\n\n"
        f"**Non-goals**\n\n{_paragraphs(narrative.get('non_goals'))}\n\n"
        "## Architecture Drivers\n\n"
        f"{_table(['Driver', 'Name', 'Statement', 'Evidence state', 'Source', 'Architecture consequence', 'Features', 'Evidence'], drivers)}\n\n"
        "## Selected Direction Realizations\n\n"
        f"{_table(['Realization', 'Exploration', 'Option', 'Option hash', 'Dimension', 'Ordinal', 'Statement', 'Statement hash', 'Status', 'Realized by', 'Gaps', 'Evidence state', 'Evidence'], realizations)}\n\n"
        "## Architecture Overview\n\n"
        f"{_paragraphs(narrative.get('architecture_overview'))}\n\n"
        "## Decisions and Rationale\n\n"
        f"{_table(['Decision', 'Title', 'Context', 'Decision', 'Rationale', 'Alternatives', 'Consequences', 'Reversibility', 'Cost if wrong', 'Status', 'ADR', 'Owner', 'Decided by / at', 'Features', 'Evidence state', 'Evidence'], decisions)}\n\n"
        "## Feature Traceability\n\n"
        f"{_table(['Feature', 'Scope', 'Direction / drivers', 'Context', 'Runtime', 'Deployment', 'Data / integrations / dynamics', 'Security / contracts', 'Transitions', 'Quality / operations', 'Decisions / questions / risks / gaps', 'Evidence state', 'Evidence'], mappings)}\n\n"
        "## Assumptions and Coverage Gaps\n\n"
        f"Coverage profile: `{_text(data.get('coverage_profile', {}).get('profile_id'))}`\n\n"
        f"Plan triggers: {_list(data.get('coverage_profile', {}).get('trigger_ids'))}\n\n"
        f"Required dimensions: {_list(data.get('coverage_profile', {}).get('required_dimensions'))}\n\n"
        f"Readiness: **{_text(data.get('readiness', {}).get('status'))}** — "
        f"{_text(data.get('readiness', {}).get('summary'))}\n\n"
        f"{_table(['Assumption', 'Statement', 'Evidence state', 'Evidence'], assumptions)}\n\n"
        f"{_table(['Dimension', 'Required', 'Status', 'Gap IDs', 'Evidence'], coverage_rows)}\n\n"
        f"{_table(['Gap', 'Dimension', 'Type', 'Statement', 'Impact', 'Material', 'Owner', 'Next action', 'Closure criteria', 'Blocking stage', 'Status', 'Related refs', 'Evidence'], gaps)}\n\n"
        "## Risks and Mitigations\n\n"
        f"{_table(['Risk', 'Title', 'Statement', 'Likelihood', 'Impact', 'Severity', 'Owner', 'Mitigation', 'Contingency', 'Trigger', 'Related refs', 'Features', 'Evidence state', 'Evidence'], risks)}\n\n"
        "## Open Questions\n\n"
        f"{_table(['Question ID', 'Question', 'Status', 'Material', 'Owner', 'Needed by', 'Options', 'Related refs', 'Features', 'Evidence state', 'Evidence'], questions)}\n\n"
        "## Validation Strategy\n\n"
        f"{_table(['Validation', 'Statement', 'Owner', 'Evidence state', 'Evidence'], validation)}\n\n"
        "## Evidence Boundary\n\n"
        f"{_paragraphs(narrative.get('evidence_boundary'))}\n"
    )


def _render_views_v2(data: dict) -> str:
    boundary = data.get("system_boundary", {})
    boundary_rows = [[
        boundary.get("id"), boundary.get("name"), boundary.get("responsibility"),
        _list(boundary.get("in_scope"), separator="; "),
        _list(boundary.get("out_of_scope"), separator="; "),
        boundary.get("evidence_state"), _evidence(boundary),
    ]]
    actors = [
        [
            row.get("id"), row.get("name"), row.get("kind"),
            _list(row.get("roles"), separator="; "), _feature_ids(row),
            row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("actors", [])
    ]
    context = [
        [
            row.get("id"), row.get("from"), row.get("to"),
            row.get("interaction"), _feature_ids(row),
            row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("context_relationships", [])
    ]
    components = [
        [
            row.get("id"), row.get("name"), row.get("kind"),
            _list(row.get("responsibilities"), separator="; "), row.get("owner"),
            _feature_ids(row), row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("components", [])
    ]
    relationships = [
        [
            row.get("id"), row.get("from"), row.get("to"),
            row.get("interaction"), row.get("protocol"),
            row.get("communication_mode"),
            _list(row.get("contract_realization_ids")), _feature_ids(row),
            row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("relationships", [])
    ]
    nodes = [
        [
            row.get("id"), row.get("name"), row.get("environment"),
            f"{_text(row.get('provider'))} / {_text(row.get('runtime'))}",
            f"{_text(row.get('region'))} / {_list(row.get('zones'))}",
            row.get("network_zone"), row.get("residency"),
            f"{_text(row.get('scaling'))} / {_text(row.get('availability'))}",
            _list(row.get("trust_boundary_ids")), _feature_ids(row),
            row.get("evidence_state"), _evidence_claims(row), _evidence(row),
        ]
        for row in data.get("deployment_nodes", [])
    ]
    deployments = [
        [
            row.get("id"), row.get("component_id"), _list(row.get("node_ids")),
            row.get("replica_strategy"), row.get("scaling"), row.get("failover"),
            _feature_ids(row), row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("deployments", [])
    ]
    connections = [
        [
            row.get("id"), row.get("from_node"), row.get("to_node"),
            row.get("direction"), row.get("protocol"), row.get("purpose"),
            row.get("network_boundary"), _feature_ids(row),
            row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("deployment_connections", [])
    ]
    transitions = [
        [
            row.get("id"), row.get("name"), row.get("from_state"),
            row.get("to_state"), row.get("strategy"), row.get("coexistence"),
            row.get("compatibility"), row.get("cutover"), row.get("rollback"),
            row.get("data_migration"), row.get("owner"),
            _slice(row, ("component_ids", "data_ids", "deployment_ids")),
            _list(row.get("decision_ids")), _feature_ids(row),
            row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("transitions", [])
    ]
    context_nodes = [*data.get("actors", []), boundary]
    dynamic_sections: list[str] = []
    for scenario in data.get("dynamic_scenarios", []):
        steps = [
            [
                step.get("ordinal"), step.get("from"), step.get("to"),
                step.get("interaction"), step.get("communication_mode"),
                step.get("integration_id"),
                _list(step.get("contract_realization_ids")),
                _list(step.get("security_realization_ids")),
                step.get("failure_behavior"),
            ]
            for step in scenario.get("steps", [])
        ]
        alternates = [
            [
                alt.get("name"), alt.get("condition"), alt.get("outcome"),
                _list(alt.get("step_ordinals")),
            ]
            for alt in scenario.get("alternate_paths", [])
        ]
        dynamic_sections.append(
            f"### {scenario.get('id')} — {scenario.get('name')}\n\n"
            + _table(
                ["Journey ref", "Features", "Evidence state", "Evidence"],
                [[
                    scenario.get("journey_ref"),
                    _feature_ids(scenario),
                    scenario.get("evidence_state"),
                    _evidence(scenario),
                ]],
            )
            + "\n\n"
            f"Trigger: {_text(scenario.get('trigger'))}\n\n"
            f"Success outcome: {_text(scenario.get('success_outcome'))}\n\n"
            f"{_table(['Step', 'From', 'To', 'Interaction', 'Mode', 'Integration', 'Contract realizations', 'Security realizations', 'Failure behavior'], steps)}\n\n"
            f"{_table(['Alternate path', 'Condition', 'Outcome', 'Steps'], alternates)}\n\n"
            f"{_sequence_diagram(scenario)}"
        )
    return (
        f"# Architecture Views: {data.get('project_slug')}\n\n"
        "> Generated projection. Tables and Mermaid are derived from "
        "`architecture.json`.\n\n"
        "## System Context\n\n"
        f"{_table(['Boundary', 'Name', 'Responsibility', 'In scope', 'Out of scope', 'Evidence state', 'Evidence'], boundary_rows)}\n\n"
        f"{_table(['Actor', 'Name', 'Kind', 'Roles', 'Features', 'Evidence state', 'Evidence'], actors)}\n\n"
        f"{_table(['Context relationship', 'From', 'To', 'Interaction', 'Features', 'Evidence state', 'Evidence'], context)}\n\n"
        f"{_flowchart(context_nodes, data.get('context_relationships', []), direction='LR')}\n\n"
        "## Runtime / Container View\n\n"
        f"{_table(['Component', 'Name', 'Kind', 'Responsibilities', 'Owner', 'Features', 'Evidence state', 'Evidence'], components)}\n\n"
        f"{_table(['Relationship', 'From', 'To', 'Interaction', 'Protocol', 'Mode', 'Contract realizations', 'Features', 'Evidence state', 'Evidence'], relationships)}\n\n"
        f"{_flowchart(data.get('components', []), data.get('relationships', []), direction='LR', edge_detail='protocol')}\n\n"
        "## Deployment View\n\n"
        f"{_table(['Node', 'Name', 'Environment', 'Provider / runtime', 'Region / zones', 'Network zone', 'Residency', 'Scaling / availability', 'Trust boundaries', 'Features', 'Evidence state', 'Evidence selectors', 'Evidence'], nodes)}\n\n"
        f"{_table(['Deployment', 'Component', 'Nodes', 'Replica strategy', 'Scaling', 'Failover', 'Features', 'Evidence state', 'Evidence'], deployments)}\n\n"
        f"{_table(['Connection', 'From node', 'To node', 'Direction', 'Protocol', 'Purpose', 'Network boundary', 'Features', 'Evidence state', 'Evidence'], connections)}\n\n"
        f"{_flowchart(data.get('deployment_nodes', []), data.get('deployment_connections', []), direction='TB', edge_from='from_node', edge_to='to_node', edge_detail='protocol')}\n\n"
        "## Dynamic Scenarios\n\n"
        + ("\n\n".join(dynamic_sections) or _projection_gaps(data, {"dynamic_behavior"}))
        + "\n\n## Transition Architecture\n\n"
        f"{_table(['Transition', 'Name', 'From', 'To', 'Strategy', 'Coexistence', 'Compatibility', 'Cutover', 'Rollback', 'Data migration', 'Owner', 'Components / data / deployments', 'Decisions', 'Features', 'Evidence state', 'Evidence'], transitions)}\n\n"
        "## View Coverage Gaps\n\n"
        f"{_projection_gaps(data, {'system_context', 'containers', 'deployment', 'dynamic_behavior', 'transitions'})}\n"
    )


def _render_data_v2(data: dict) -> str:
    narrative = data.get("narrative", {})
    entities = [
        [
            row.get("id"), row.get("name"), row.get("data_class"),
            row.get("source_of_truth"), _list(row.get("writers")),
            _list(row.get("readers")),
            " / ".join(
                _text(row.get("lifecycle", {}).get(field))
                for field in ("retain", "export", "erase")
            ),
            row.get("consistency"), row.get("storage"),
            row.get("region_residency"), row.get("backup_recovery"),
            _list(row.get("transition_ids")), row.get("plan_trace"),
            _feature_ids(row), row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("data_entities", [])
    ]
    flows = [
        [
            row.get("id"), row.get("name"), row.get("producer"),
            row.get("consumer"),
            f"{_text(row.get('protocol'))} / {_text(row.get('communication_mode'))}",
            _list(row.get("data"), separator="; "),
            _list(row.get("data_entity_ids")), row.get("source_of_truth"),
            row.get("failure_behavior"), row.get("timeout_retry"),
            _list(row.get("contract_realization_ids")),
            _list(row.get("security_realization_ids")), row.get("plan_trace"),
            _feature_ids(row), row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("integration_flows", [])
    ]
    boundaries = [
        [
            row.get("id"), row.get("name"), row.get("boundary_type"),
            row.get("description"), _list(row.get("inside_ids")),
            _list(row.get("outside_ids")),
            _list(row.get("crossing_integration_ids")), row.get("residency"),
            _feature_ids(row), row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("trust_boundaries", [])
    ]
    security = [
        [
            row.get("id"), row.get("obligation_id"),
            _list(row.get("boundary_ids")), _list(row.get("actor_ids")),
            _list(row.get("component_ids")), _list(row.get("integration_ids")),
            _list(row.get("data_ids")), _list(row.get("tactics"), separator="; "),
            row.get("verification"), _feature_ids(row),
            row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("security_realizations", [])
    ]
    contracts = [
        [
            row.get("id"), row.get("obligation_id"),
            _list(row.get("relationship_ids")), _list(row.get("integration_ids")),
            _list(row.get("dynamic_scenario_ids")), _list(row.get("data_ids")),
            row.get("behavior"), row.get("failure_behavior"),
            row.get("compatibility"), row.get("verification"),
            _feature_ids(row), row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("contract_realizations", [])
    ]
    details = "\n\n".join(
        f"### {row.get('id')} — {row.get('name')}\n\n{_text(row.get('details'))}"
        for row in data.get("integration_flows", [])
    ) or "None recorded."
    return (
        f"# Data and Integrations: {data.get('project_slug')}\n\n"
        "## Data Ownership and Lifecycle\n\n"
        f"{_table(['Data', 'Durable noun / data set', 'Class', 'Source of truth', 'Writers', 'Readers', 'Retain / Export / Erase', 'Consistency', 'Storage', 'Residency', 'Backup / recovery', 'Transitions', 'Plan trace', 'Features', 'Evidence state', 'Evidence'], entities)}\n\n"
        "## Integration Flows\n\n"
        f"{_table(['Flow', 'Name', 'Producer', 'Consumer', 'Protocol / mode', 'Data', 'Data entities', 'Source of truth', 'Failure', 'Timeout / retry', 'Contract realizations', 'Security realizations', 'Plan trace', 'Features', 'Evidence state', 'Evidence'], flows)}\n\n"
        f"## Flow Details\n\n{details}\n\n"
        "## Consistency, Idempotency, and Concurrency\n\n"
        f"{_paragraphs(narrative.get('consistency_model'))}\n\n"
        "## Trust Boundaries\n\n"
        f"{_table(['Boundary', 'Name', 'Type', 'Description', 'Inside', 'Outside', 'Crossing flows', 'Residency', 'Features', 'Evidence state', 'Evidence'], boundaries)}\n\n"
        "## Security and Privacy Re-Projection\n\n"
        f"{_table(['Realization', 'Obligation', 'Boundaries', 'Actors', 'Components', 'Integrations', 'Data', 'Tactics', 'Verification', 'Features', 'Evidence state', 'Evidence'], security)}\n\n"
        "## Interaction Contract Realizations\n\n"
        f"{_table(['Realization', 'Obligation', 'Relationships', 'Integrations', 'Dynamic scenarios', 'Data', 'Behavior', 'Failure', 'Compatibility', 'Verification', 'Features', 'Evidence state', 'Evidence'], contracts)}\n\n"
        "## Security and Privacy Summary\n\n"
        f"{_paragraphs(narrative.get('security_privacy_summary'))}\n\n"
        "## Data and Integration Gaps\n\n"
        f"{_projection_gaps(data, {'data', 'integrations', 'security', 'contracts'})}\n"
    )


def _render_quality_v2(data: dict) -> str:
    narrative = data.get("narrative", {})
    quality = [
        [
            row.get("id"), row.get("name"), row.get("attribute"),
            row.get("source"), row.get("stimulus"), row.get("environment"),
            row.get("response"), row.get("target"), row.get("tactic"),
            row.get("verification"), _list(row.get("operation_ids")),
            _feature_ids(row), row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("quality_scenarios", [])
    ]
    operations = [
        [
            row.get("id"), row.get("name"), row.get("category"),
            row.get("responsibility"), row.get("owner"),
            _list(row.get("signals"), separator="; "), row.get("failure_domain"),
            row.get("target"), row.get("tactic"), row.get("runbook"),
            row.get("verification"),
            _slice(row, ("component_ids", "deployment_node_ids")),
            _list(row.get("quality_ids")), _feature_ids(row),
            row.get("evidence_state"), _evidence(row),
        ]
        for row in data.get("operations", [])
    ]
    details = "\n\n".join(
        f"## {row.get('id')} — {row.get('name')}\n\n{_text(row.get('details'))}"
        for row in data.get("quality_scenarios", [])
    ) or "None recorded."
    return (
        f"# Quality Attributes: {data.get('project_slug')}\n\n"
        "## Quality Scenarios\n\n"
        f"{_table(['Quality', 'Name', 'Attribute', 'Source', 'Stimulus', 'Environment', 'Response', 'Target', 'Tactic', 'Verification', 'Operations', 'Features', 'Evidence state', 'Evidence'], quality)}\n\n"
        f"{details}\n\n"
        "## Operations\n\n"
        f"{_table(['Operation', 'Name', 'Category', 'Responsibility', 'Owner', 'Signals', 'Failure domain', 'Target', 'Tactic', 'Runbook', 'Verification', 'Components / nodes', 'Quality', 'Features', 'Evidence state', 'Evidence'], operations)}\n\n"
        "## Operability and Observability\n\n"
        f"{_paragraphs(narrative.get('operability_summary'))}\n\n"
        "## Capacity, Resilience, and Recovery\n\n"
        f"{_paragraphs(narrative.get('capacity_resilience_recovery_summary'))}\n\n"
        "## Cost and Complexity Trade-Offs\n\n"
        f"{_paragraphs(narrative.get('cost_complexity_summary'))}\n\n"
        "## Quality and Operations Gaps\n\n"
        f"{_projection_gaps(data, {'quality_attributes', 'operability'})}\n"
    )


def render_documents(data: dict) -> dict[str, bytes]:
    if data.get("$schema") != SCHEMA_URN or data.get("schema_version") != SCHEMA_VERSION:
        raise RenderInputError(
            f"renderer requires $schema={SCHEMA_URN!r} and schema_version=2"
        )
    return {
        "solution-architecture.md": _render_solution_v2(data).encode("utf-8"),
        "views.md": _render_views_v2(data).encode("utf-8"),
        "data-and-integrations.md": _render_data_v2(data).encode("utf-8"),
        "quality-attributes.md": _render_quality_v2(data).encode("utf-8"),
    }


def projection_hashes(documents: dict[str, bytes]) -> dict[str, str]:
    return {path: _hash_bytes(documents[path]) for path in CORE_PATHS}


def finalize_review_manifest(data: dict) -> tuple[dict, dict[str, bytes]]:
    """Return a proposed manifest with projection and review-payload hashes set."""

    finalized = copy.deepcopy(data)
    if finalized.get("lifecycle_status") != "proposed":
        raise RenderInputError("only a proposed manifest can be finalized for review")
    finalized["approval"] = copy.deepcopy(PENDING_APPROVAL)
    documents = render_documents(finalized)
    hashes = projection_hashes(documents)
    projections = finalized.get("projections")
    if not isinstance(projections, list):
        raise RenderInputError("projections must be an array")
    for projection in projections:
        if not isinstance(projection, dict):
            raise RenderInputError("every projection must be an object")
        path = projection.get("path")
        if path not in hashes:
            raise RenderInputError(
                f"only the four core projections are supported in v2: {path!r}"
            )
        projection["sha256"] = hashes[path]
    documents = render_documents(finalized)
    finalized["approval"]["review_payload_sha256"] = review_payload_sha256(
        finalized, documents
    )
    return finalized, documents


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise OSError(f"output target must be absent or a regular file: {path}")
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_documents(
    manifest_path: Path,
    output_dir: Path,
    *,
    finalize_review: bool,
) -> dict:
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise OSError("manifest must be a regular non-symlink file")
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise OSError("output directory must be an existing non-symlink directory")
    loaded = _strict_json_loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RenderInputError("manifest must contain an object")
    if finalize_review:
        manifest, documents = finalize_review_manifest(loaded)
    else:
        manifest = loaded
        documents = render_documents(manifest)
    for path, payload in documents.items():
        _atomic_write(output_dir / path, payload)
    if finalize_review:
        _atomic_write(
            output_dir / "architecture.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    return {
        "schema_version": 1,
        "status": "rendered",
        "output_dir": str(output_dir),
        "projection_hashes": projection_hashes(documents),
        "review_payload_sha256": (
            manifest.get("approval", {}).get("review_payload_sha256")
            if finalize_review
            else review_payload_sha256(manifest, documents)
        ),
    }


def check_package(package: Path) -> tuple[dict, int]:
    result = {
        "schema_version": 1,
        "status": "error",
        "mismatches": [],
        "projection_hashes": {},
        "review_payload_sha256": None,
        "receipt_sha256": None,
        "message": None,
    }
    try:
        if package.is_symlink() or not package.is_dir():
            raise OSError("package must be an existing non-symlink directory")
        manifest_path = package / "architecture.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise OSError("architecture.json must be a regular file")
        data = _strict_json_loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RenderInputError("architecture.json must contain an object")
        documents = render_documents(data)
        hashes = projection_hashes(documents)
        result["projection_hashes"] = hashes
        projections = data.get("projections")
        if not isinstance(projections, list):
            raise RenderInputError("projections must be an array")
        registered = {
            row.get("path"): row
            for row in projections
            if isinstance(row, dict) and isinstance(row.get("path"), str)
        }
        expected_paths = set(CORE_PATHS)
        if set(registered) != expected_paths:
            result["mismatches"].append(
                "projections must register exactly the four core Markdown paths"
            )
        for path, expected_bytes in documents.items():
            target = package / path
            if target.is_symlink() or not target.is_file():
                result["mismatches"].append(f"missing/non-regular projection: {path}")
                continue
            actual = target.read_bytes()
            if actual != expected_bytes:
                result["mismatches"].append(
                    f"deterministic projection differs from architecture.json: {path}"
                )
            row = registered.get(path, {})
            if row.get("sha256") != hashes[path]:
                result["mismatches"].append(
                    f"registered projection sha256 is stale: {path}"
                )

        expected_review = review_payload_sha256(data, documents)
        result["review_payload_sha256"] = expected_review
        approval = data.get("approval")
        if not isinstance(approval, dict):
            result["mismatches"].append("approval must be an object")
        else:
            if approval.get("review_payload_sha256") != expected_review:
                result["mismatches"].append(
                    "approval.review_payload_sha256 does not match the deterministic review payload"
                )
            lifecycle = data.get("lifecycle_status")
            if lifecycle == "published":
                expected_receipt = receipt_sha256(data, documents)
                result["receipt_sha256"] = expected_receipt
                if approval.get("receipt_sha256") != expected_receipt:
                    result["mismatches"].append(
                        "approval.receipt_sha256 does not match the published package"
                    )
            elif approval.get("receipt_sha256") is not None:
                result["mismatches"].append(
                    "proposed package approval.receipt_sha256 must be null"
                )
        if result["mismatches"]:
            result.update(
                {
                    "status": "mismatch",
                    "message": "deterministic render check failed",
                }
            )
            return result, 1
        result.update({"status": "pass", "message": "all projections and digests match"})
        return result, 0
    except (OSError, UnicodeError, json.JSONDecodeError, RenderInputError) as exc:
        result["message"] = str(exc)
        return result, 2


def _check_cli(package: Path, json_output: bool) -> int:
    result, code = check_package(package)
    if json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"architecture-render: {result['status'].upper()} — {result['message']}")
        for mismatch in result.get("mismatches", []):
            print(f"MISMATCH: {mismatch}")
    return code


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--check":
        legacy_parser = argparse.ArgumentParser(
            description="Check deterministic ce-architecture v2 projections"
        )
        legacy_parser.add_argument(
            "--check", dest="package", type=Path, required=True
        )
        legacy_parser.add_argument("--json", action="store_true")
        legacy_args = legacy_parser.parse_args(argv)
        return _check_cli(legacy_args.package, legacy_args.json)

    parser = argparse.ArgumentParser(
        description="Render deterministic ce-architecture v2 projections"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("manifest", type=Path)
    render_parser.add_argument("--output-dir", type=Path, required=True)
    render_parser.add_argument("--finalize-review", action="store_true")
    render_parser.add_argument("--json", action="store_true")
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("package", type=Path)
    check_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "check":
        return _check_cli(args.package, args.json)
    try:
        result = write_documents(
            args.manifest,
            args.output_dir,
            finalize_review=args.finalize_review,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RenderInputError) as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "error",
                        "message": str(exc),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"architecture-render: ERROR — {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "architecture-render: RENDERED — "
            + ", ".join(sorted(result["projection_hashes"]))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
