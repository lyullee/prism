"""Audit the reconstructed inspection-centre HAZOP consequence artifact.

The audit verifies the explicit identity handoff and the presence of the full
diagnostic consequence stage ledger.  It is deliberately a diagnostic audit:
model-prediction packets, provider qualification, independent validation, and
facility QRA promotion remain separate gates.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "prism.reconstructed_hazop_chain_audit.v1"
RUNTIME_SCHEMA = "prism.observed_hazop_runtime_audit.v1"
BINDING_SCHEMA = "prism.observed_hazop_provider_event_binding.v1"
CHAIN_SCHEMA = "prism.observed_hazop_provider_consequence_chain.v1"

REQUIRED_STAGES = (
    "equipment_resolved_gas_exit",
    "rainout_and_dynamic_pool",
    "vector_cryogenic_near_field",
    "SLABx_dispersion",
    "finite_inventory_cloud",
    "ignition_branches",
    "fire_radiation",
    "multi_energy_blast_zones",
    "TNO_human_damage",
    "conditional_risk",
)


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def _text(value: Any) -> str:
    return str(value or "").strip()


def _selected_scenarios(runtime: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    for row in _rows(runtime.get("rows"), "runtime.rows"):
        selected.extend(_rows(row.get("selected_scenarios"), "selected_scenarios"))
    return selected


def audit_reconstructed_hazop_chain(
    runtime_audit: Mapping[str, Any],
    binding_audit: Mapping[str, Any],
    chain: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a fail-closed audit of one reconstructed diagnostic chain."""
    if runtime_audit.get("schema_version") != RUNTIME_SCHEMA:
        raise ValueError(f"runtime_audit schema_version must be {RUNTIME_SCHEMA}")
    if binding_audit.get("schema_version") != BINDING_SCHEMA:
        raise ValueError(f"binding_audit schema_version must be {BINDING_SCHEMA}")
    if chain.get("schema_version") != CHAIN_SCHEMA:
        raise ValueError(f"chain schema_version must be {CHAIN_SCHEMA}")

    selected = _selected_scenarios(runtime_audit)
    binding_rows = _rows(binding_audit.get("rows"), "binding_audit.rows")
    chain_rows = _rows(chain.get("rows"), "chain.rows")
    selected_ids = {_text(row.get("scenario_id")) for row in selected}
    binding_ids = {_text(row.get("scenario_id")) for row in binding_rows}
    chain_ids = {_text(row.get("scenario_id")) for row in chain_rows}

    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, reason: str, evidence: Mapping[str, Any]) -> None:
        checks.append({
            "name": name,
            "status": "PASS" if passed else "BLOCKED",
            "reason": None if passed else reason,
            "evidence": dict(evidence),
        })

    check(
        "selected_scenario_identity",
        bool(selected_ids) and selected_ids == binding_ids == chain_ids,
        "runtime, binding, and chain scenario IDs do not match exactly",
        {
            "runtime_ids": sorted(selected_ids),
            "binding_ids": sorted(binding_ids),
            "chain_ids": sorted(chain_ids),
        },
    )
    check(
        "provider_event_binding",
        binding_audit.get("status") == "OBSERVED_HAZOP_PROVIDER_EVENT_BINDINGS_DIAGNOSTIC"
        and all(row.get("status") == "EXPLICIT_PROVIDER_EVENT_BOUND" for row in binding_rows),
        "explicit provider event identity binding is not a diagnostic pass",
        {
            "binding_status": binding_audit.get("status"),
            "bound_count": sum(row.get("status") == "EXPLICIT_PROVIDER_EVENT_BOUND" for row in binding_rows),
            "binding_count": len(binding_rows),
        },
    )
    executed = [row for row in chain_rows if row.get("status") == "EXECUTED"]
    check(
        "provider_consequence_execution",
        chain.get("status") == "OBSERVED_HAZOP_PROVIDER_CHAIN_EXECUTED"
        and len(executed) == len(chain_rows) == len(selected)
        and all(row.get("gate_status") == "CONSEQUENCE_EVALUATED" for row in executed),
        "one or more selected scenarios did not execute the consequence gate",
        {
            "chain_status": chain.get("status"),
            "selected_count": len(selected),
            "executed_count": len(executed),
            "gate_statuses": sorted({_text(row.get("gate_status")) for row in chain_rows}),
        },
    )

    stage_sets: list[list[str]] = []
    for row in executed:
        consequence = row.get("consequence")
        data = consequence.get("data") if isinstance(consequence, Mapping) else None
        stages = data.get("stages") if isinstance(data, Mapping) else None
        stage_sets.append([str(stage) for stage in stages] if isinstance(stages, list) else [])
    stages_ok = bool(stage_sets) and all(set(REQUIRED_STAGES).issubset(set(stages)) for stages in stage_sets)
    check(
        "full_consequence_stage_ledger",
        stages_ok and all(
            isinstance(row.get("consequence"), Mapping)
            and row["consequence"].get("data", {}).get("full_chain_executed") is True
            and row["consequence"].get("data", {}).get("status") == "END_TO_END_DIAGNOSTIC_EXECUTED"
            for row in executed
        ),
        "consequence payload does not expose the required end-to-end diagnostic stages",
        {
            "required_stages": list(REQUIRED_STAGES),
            "observed_stages": stage_sets,
        },
    )
    check(
        "diagnostic_promotion_boundary",
        chain.get("policy", {}).get("provider_packets_are_qualified") is False
        and chain.get("policy", {}).get("facility_qra_claim") is False
        and all(row.get("provider_qualification") == "UNQUALIFIED_DIAGNOSTIC" for row in executed),
        "diagnostic chain incorrectly advertises provider qualification or facility QRA",
        {
            "provider_packets_are_qualified": chain.get("policy", {}).get("provider_packets_are_qualified"),
            "facility_qra_claim": chain.get("policy", {}).get("facility_qra_claim"),
            "provider_qualifications": sorted({_text(row.get("provider_qualification")) for row in chain_rows}),
        },
    )

    blocked = [row for row in checks if row["status"] != "PASS"]
    return {
        "schema_version": SCHEMA,
        "status": "RECONSTRUCTED_DIAGNOSTIC_CHAIN_VERIFIED" if not blocked else "RECONSTRUCTED_DIAGNOSTIC_CHAIN_BLOCKED",
        "check_count": len(checks),
        "passed_count": len(checks) - len(blocked),
        "blocked_count": len(blocked),
        "checks": checks,
        "required_stages": list(REQUIRED_STAGES),
        "policy": {
            "diagnostic_only": True,
            "provider_qualification_claim": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
        },
        "interpretation": (
            "The reconstructed state-to-HAZOP-to-provider-to-consequence chain is "
            "structurally verified as a diagnostic execution. This audit does not "
            "qualify a provider packet, validate facility geometry, or promote a "
            "facility IR/F-N result."
        ),
    }


__all__ = ["CHAIN_SCHEMA", "REQUIRED_STAGES", "SCHEMA", "audit_reconstructed_hazop_chain"]
