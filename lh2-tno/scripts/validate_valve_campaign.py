"""Bind external lh2dt Valve liquid packets to the PRISM facility campaign.

The Valve provider owns the liquid/two-phase outlet history.  This script
only binds five exact LH2_VALVE literature LOCs to those saved packets and
runs the normal two-weather consequence chain.  The packets are synthetic
diagnostic evidence; no valve failure frequency, inventory feedback or
provider qualification is inferred.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.contracts import Facility  # noqa: E402
from lh2_tno.frequency import FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402


PACKETS = {
    "AREA_0.01%": ROOT / "results/20261019/valve_worklist_AREA_0.01pct_chain_native/request.json",
    "AREA_0.1%": ROOT / "results/20261019/valve_worklist_AREA_0.1pct_chain_native/request.json",
    "AREA_1%": ROOT / "results/20261013/valve_worklist_AREA_1pct_chain/request.json",
    "AREA_10%": ROOT / "results/20261019/valve_worklist_AREA_10pct_chain_native/request.json",
    "AREA_100%": ROOT / "results/20261019/valve_worklist_AREA_100pct_chain_native/request.json",
}


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _backend() -> tuple[BackendConfig, Path]:
    raw = _load(ROOT / "results/20261009/backend_config_current.json")
    provider = Path(
        r"C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템"
        r"\06_액화수소_디지털트윈_물리모델\src\lh2dt"
    )
    raw["packages"] = [p for p in raw["packages"] if p["name"] != "lh2dt"]
    raw["packages"].append({"name": "lh2dt", "root": str(provider), "sha256": tree_digest(provider)})
    return BackendConfig.model_validate_json(json.dumps(raw)), provider


def _facility() -> Facility:
    return Facility.model_validate_json(json.dumps({
        "id": "generic-lh2-full-scope-example",
        "configuration_origin": "synthetic",
        "environment": "outdoor",
        "components": [{
            "id": "transfer-valve-01",
            "kind": "valve",
            "position_enu_m": [0.0, 0.0, 0.5],
            "property_basis": {
                "fluid": "Hydrogen",
                "backend": "CoolProp-HEOS",
                "energy_reference": "CoolProp-HEOS:Hydrogen:native",
            },
            "parameters_si": {"diameter_m": 0.025},
        }],
        "ports": [{
            "id": "valve-accident-out",
            "component_id": "transfer-valve-01",
            "phase": "any",
            "direction": "out",
            "position_enu_m": [0.0, 0.0, 0.5],
        }],
        "edges": [],
        "receptors": [{"id": "worker-01", "position_enu_m": [2.0, 0.0, 1.0]}],
    }))


def _frequency_plan() -> FrequencyPlan:
    source = _load(ROOT / "examples/generic_lh2_full_scope_frequency_plan.json")
    valve = next(asset for asset in source["assets"] if asset["id"] == "transfer-valve")
    return FrequencyPlan.model_validate_json(json.dumps({
        "id": source["id"],
        "assets": (valve,),
        "excluded_model_components": {},
    }))


def _request(packet: dict, event_id: str, condition_weather: dict) -> dict:
    request = copy.deepcopy(packet)
    release = request.get("resolved_liquid_release")
    if not isinstance(release, dict):
        raise ValueError(f"packet for {event_id} has no resolved_liquid_release")
    if release.get("event_id") != event_id:
        raise ValueError(f"packet event mismatch: {release.get('event_id')} != {event_id}")
    request.update({
        "component_id": "transfer-valve-01",
        "source_input": None,
        "resolved_release": None,
        "resolved_release_set": None,
        "resolved_liquid_release": release,
        "available_mass_kg": release["available_mass_kg"],
        "source_position_enu_m": release["position_enu_m"],
        "weather": condition_weather,
        "annual_frequency_per_year": None,
        "annual_frequency_provenance": None,
        "frequency_event": None,
        "initiation_intensity_per_s": None,
        "source_operator": "equipment_liquid_release",
        "source_duration_mode": "declared",
        "release_termination": {
            "basis": release["termination_basis"],
            "time_s": release["duration_s"],
            "provenance": release["termination_provenance"],
        },
        "evaluation_times_s": sorted({
            0.0,
            release["duration_s"],
            1.0,
            2.0,
            3.0,
            5.0,
            10.0,
            20.0,
            *[step["time_s"] for step in release["steps"]],
        }),
    })
    return request


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    facility = _facility()
    plan = _frequency_plan()
    events = generate_events(facility, plan)
    if {event.loc for event in events} != set(PACKETS):
        raise AssertionError("the valve frequency plan did not generate all five area bins")

    conditions = []
    for condition_id, probability, speed in [("D-3ms-west", 0.4, 3.0), ("D-4ms-west", 0.6, 4.0)]:
        conditions.append({
            "id": condition_id,
            "annual_probability": probability,
            "weather": {
                "wind_speed_m_s": speed,
                "wind_from_bearing_deg": 270.0,
                "measurement_height_m": 10.0,
                "roughness_m": 0.03,
                "stability": "D",
                "relative_humidity": 0.5,
            },
            "population": [{
                "receptor_id": "worker-01",
                "persons": 1.0,
                "presence_probability": 1.0,
                "provenance": "synthetic diagnostic receptor; not site population",
            }],
            "provenance": "synthetic annual outdoor weather partition; no site weather qualification",
        })

    routes = []
    packet_records = {}
    for event in events:
        packet = _load(PACKETS[event.loc])
        packet_records[event.id] = packet
        routes.append({
            "event_id": event.id,
            "branches": [{
                "id": "external-valve-provider-liquid-boundary",
                "probability_given_event": 1.0,
                "provenance": "external lh2dt.Valve packet; PRISM does not re-solve the provider outlet",
                "request": _request(packet, event.id, conditions[0]["weather"]),
            }],
        })

    campaign = RiskCampaign.model_validate_json(json.dumps({
        "id": "generic-lh2-valve-provider-campaign",
        "frequency_plan": plan.model_dump(mode="json"),
        "annual_conditions": conditions,
        "event_routes": routes,
        "scope_provenance": "five exact LH2_VALVE literature area bins use saved external lh2dt.Valve liquid/two-phase packets through the SLABx-LH2/SLABx and native TNO IR/F-N chain; provider horizon and facility context remain synthetic diagnostic evidence",
    }))
    config, provider = _backend()
    result = ResearchPipeline(facility, IsolatedBackend(config)).facility_risk(campaign)
    _save(args.output_dir / "campaign_result_debug.json", result)
    executed = [case for case in result["cases"] if case["status"].startswith("EXECUTED")]
    failed = [case for case in result["cases"] if case["status"] == "FAILED"]
    # The external provider packets are diagnostic evidence.  Operator-limited
    # cases remain usable for a conditional chain, while backend failures stay
    # explicitly withheld and are never converted to zero risk.
    if len(result["events"]) != 5 or len(executed) + len(failed) != 10:
        raise AssertionError({"events": len(result["events"]), "executed": len(executed), "failed": len(failed), "uncomputed": len(result["uncomputed_cases"])})
    if any(abs(case["mass_ledger"]["end_to_end_residual_kg"]) > 1e-8 for case in executed):
        raise AssertionError("valve packet mass ledger did not close")
    _save(args.output_dir / "facility.json", facility.model_dump(mode="json"))
    _save(args.output_dir / "frequency_plan.json", plan.model_dump(mode="json"))
    _save(args.output_dir / "campaign.json", campaign.model_dump(mode="json"))
    _save(args.output_dir / "packet_sources.json", {event_id: str(PACKETS[event.loc]) for event in events for event_id in [event.id]})
    _save(args.output_dir / "provider_packets.json", packet_records)
    _save(args.output_dir / "backend_config.json", config.model_dump(mode="json"))
    _save(args.output_dir / "campaign_result.json", result)
    _save(args.output_dir / "verification.json", {
        "status": result["status"],
        "generated_events": len(result["events"]),
        "executed_cases": len(executed),
        "failed_cases": len(failed),
        "uncomputed_cases": len(result["uncomputed_cases"]),
        "provider_packet_case_count": result["provider_packet_case_count"],
        "qualified_provider_packet_case_count": result["qualified_provider_packet_case_count"],
        "frequency_inference": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "provider_source_digest": tree_digest(provider),
        "max_mass_residual_kg": max(abs(case["mass_ledger"]["end_to_end_residual_kg"]) for case in executed),
        "timing": result["timing"],
        "limitations": [
            "external Valve packets use synthetic liquid state and bounded diagnostic horizon",
            "valve inventory feedback and isolation reliability are not modeled in this campaign",
            "facility geometry, receptors and weather are synthetic",
            "provider packet qualification and independent physical validation remain false",
        ],
    })
    print(json.dumps({
        "status": result["status"],
        "generated_events": len(result["events"]),
        "executed_cases": len(executed),
        "uncomputed_cases": len(result["uncomputed_cases"]),
        "risk_atoms": len(result["risk_atoms"]),
        "facility_total_risk_available": result["total_facility_annual_ir_low_high"] is not None,
        "timing": result["timing"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
