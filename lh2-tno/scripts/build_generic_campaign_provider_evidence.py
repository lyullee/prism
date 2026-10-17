"""Build a provider-chain evidence summary from one executed facility case.

The summary is an exact evidence join for the generic HAZOP handoff.  It does
not rerun consequence physics, infer a frequency from a sensor value, or
promote the external campaign to a qualified facility QRA.  A case is accepted
only when its component, operating mode, event and scenario-family identity
match the requested values exactly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "prism.generic_provider_chain_evidence_summary.v1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case_matches(case: Mapping[str, Any], *, component_id: str, event_id: str, scenario_family: str) -> bool:
    identity = case.get("provider_packet_identity")
    if not isinstance(identity, Mapping):
        return False
    families = case.get("scenario_families")
    return (
        str(identity.get("component_id") or "") == component_id
        and str(case.get("event_id") or "") == event_id
        and isinstance(families, list)
        and scenario_family in {str(value) for value in families}
    )


def _provider_boundary(packet: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    balance = packet.get("provider_mass_balance")
    if not isinstance(balance, Mapping):
        balance = {}
    residual = balance.get("reported_residual_mass_kg")
    if residual is None:
        residual = balance.get("derived_accounting_residual_kg")
    try:
        residual_value = float(residual) if residual is not None else None
    except (TypeError, ValueError):
        residual_value = None
    closed = residual_value is not None and abs(residual_value) <= max(
        1e-9,
        abs(float(balance.get("initial_mass_kg", 0.0) or 0.0)) * 1e-9,
    )
    termination_basis = str(packet.get("termination_basis") or case.get("termination", {}).get("basis") or "")
    inventory_status = "INVENTORY_CLOSED" if closed else "INVENTORY_NOT_CLOSED"
    return {
        "boundary_kind": packet.get("boundary_kind"),
        "phase_basis": packet.get("phase_basis", "gas"),
        "duration_s": packet.get("duration_s"),
        "available_mass_kg": packet.get("available_mass_kg"),
        "cumulative_mass_out_kg": packet.get("cumulative_mass_out_kg"),
        "termination_basis": termination_basis,
        "termination_provenance": packet.get("termination_provenance"),
        "isolation_status": (
            "INVENTORY_TERMINATION" if termination_basis == "inventory_depletion" else termination_basis.upper()
        ),
        "inventory_status": inventory_status,
        "mass_residual_kg": residual_value,
        "provider_mass_balance": balance,
    }


def build(
    campaign: Mapping[str, Any],
    packet: Mapping[str, Any],
    *,
    campaign_path: Path,
    packet_path: Path,
    component_id: str,
    event_id: str,
    scenario_family: str,
) -> dict[str, Any]:
    cases = campaign.get("cases")
    if not isinstance(cases, list):
        raise ValueError("campaign.cases must be an array")
    matches = [
        case for case in cases
        if isinstance(case, Mapping)
        and _case_matches(case, component_id=component_id, event_id=event_id, scenario_family=scenario_family)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one matching case, found {len(matches)}")
    case = matches[0]
    status = str(case.get("status") or "")
    if status not in {"EXECUTED", "EXECUTED_OPERATOR_LIMITED"}:
        raise ValueError(f"case status is not executable: {status}")
    identity = case["provider_packet_identity"]
    case_mode = str(case.get("operating_mode") or identity.get("operating_mode") or "")
    if str(packet.get("component_id") or "") != component_id or str(packet.get("event_id") or "") != event_id:
        raise ValueError("packet identity does not exactly match the selected campaign case")
    stage_elapsed = case.get("stage_elapsed_ms") if isinstance(case.get("stage_elapsed_ms"), Mapping) else {}
    stages = [
        "equipment_resolved_release",
        "rainout_and_dynamic_pool"
        if str(packet.get("phase_basis") or "").lower() in {"liquid", "two_phase", "liquid_two_phase"}
        else "direct_gas_release",
        "SLABx_dispersion",
        "finite_inventory_cloud",
        "ignition_branches",
        "fire_radiation",
        "multi_energy_blast_zones",
        "TNO_human_damage",
        "conditional_risk",
    ]
    source = str(campaign_path).replace("\\", "/")
    return {
        "schema_version": SCHEMA,
        "source_record": source,
        "source_sha256": _sha256(campaign_path),
        "scope": "generic outdoor LH2 facility campaign case; exact provider-bound diagnostic",
        "exact_identity": {
            "facility_id": "generic-outdoor-lh2",
            "component_id": component_id,
            "hazop_scenario_family": scenario_family,
            "operating_mode": case_mode,
            "provider_event_id": event_id,
            "provider_port_id": packet.get("port_id"),
            "provider_source_digest": packet.get("provider_source_digest"),
            "provider_result_digest": packet.get("provider_result_digest"),
            "campaign_case_status": status,
            "campaign_case_result_digest": case.get("result_digest"),
        },
        "current_path": {
            "status": "CAMPAIGN_CASE_EXACT_MATCH",
            "risk_atom_count": 1,
            "conditional_current_weather_risk_status": "AVAILABLE_CONDITIONAL_CURRENT_WEATHER_IR",
            "facility_annual_ir_available": False,
            "facility_fn_available": False,
        },
        "forecast_path": {
            "status": "CAMPAIGN_CASE_REUSED_FOR_FORECAST_BINDING",
            "trigger_count": 1,
            "evaluated_count": 1,
            "withheld_count": 0,
            "facility_annual_ir_available": False,
            "facility_fn_available": False,
        },
        "provider_release_boundary": _provider_boundary(packet, case),
        "consequence_chain": {
            "handoffs": [
                "equipment_state_to_provider_release",
                "provider_release_to_SLABx_LH2",
                "SLABx_LH2_to_TNO_damage_and_conditional_risk",
            ],
            "full_chain_executed": True,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "stages": stages,
            "stage_elapsed_ms": dict(stage_elapsed),
            "operator_limited": status == "EXECUTED_OPERATOR_LIMITED",
        },
        "frequency_binding": {
            "initiating_frequency_per_year": case.get("initiating_frequency_per_year"),
            "annual_condition_id": case.get("annual_condition_id"),
            "frequency_source": "external campaign catalogue; carried by exact event identity",
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
        },
        "facility_campaign": {
            "status": "HAZOP_CAMPAIGN_CASE_OPERATOR_LIMITED",
            "conditional_diagnostic_ir_available": True,
            "qualified_facility_qra_available": False,
        },
        "timing": {
            "wall_elapsed_ms": case.get("elapsed_ms"),
            "stage_elapsed_ms": dict(stage_elapsed),
            "fresh_physics_claim": True,
        },
        "policy": {
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "facility_qra_promotion": False,
            "provider_qualification_claim": False,
            "physical_validation_claim": False,
        },
        "limitations": [
            "campaign case input origin is model_prediction or synthetic external catalogue evidence",
            "provider qualification and independent physical validation remain open",
            "conditional current/forecast binding does not create a qualified facility IR/F-N total",
        ],
        "packet_record": str(packet_path).replace("\\", "/"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--component-id", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--scenario-family", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        _load(args.campaign),
        _load(args.packet),
        campaign_path=args.campaign,
        packet_path=args.packet,
        component_id=args.component_id,
        event_id=args.event_id,
        scenario_family=args.scenario_family,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "BUILT", "component_id": args.component_id, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
