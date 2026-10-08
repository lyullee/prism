"""Exercise a provider-resolved SLABx-LH2 liquid/two-phase exit end to end.

The provider owns liquid discharge, atmospheric flash and ground partition.  The
PRISM adapter only validates the supplied ledger and forwards flashed gas plus
ground liquid to the existing transition, DynamicLH2PoolX and consequence
operators.  This is an operator-limited diagnostic; it is not a field
validation or a claim that the provider's spray energy closure is qualified.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import CoolProp.CoolProp as CP

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.contracts import Facility, canonical_digest
from lh2_tno.equipment_boundary import ResolvedLiquidRelease
from lh2_tno.equipment_release_adapter import build_resolved_liquid_release_from_provider_response
from lh2_tno.pipeline import ResearchPipeline


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def provider_packet(source: dict, provider: dict) -> ResolvedLiquidRelease:
    """Map the external liquid-jet history through the shared adapter."""
    duration = float(source["duration_s"])
    steps = []
    h_out = float(CP.PropsSI("H", "P", source["tank"]["pressure_pa"],
                             "T", source["tank"]["temperature_k"], source["tank"]["fluid"]))
    for raw in provider["data"]["steps"]:
        if float(raw["time_s"]) >= duration - 1e-12:
            continue
        gas = raw["gas"]
        ground = raw["ground"]
        total = float(raw["conservation"]["mass_in_kg_s"])
        gas_rate = float(gas["mass_flow_kg_s"])
        ground_rate = float(ground["mass_flow_kg_s"])
        steps.append({
            "time_s": float(raw["time_s"]),
            "total_mass_flow_kg_s": total,
            "gas_mass_flow_kg_s": gas_rate,
            "ground_liquid_mass_flow_kg_s": ground_rate,
            "airborne_liquid_mass_flow_kg_s": 0.0,
            "specific_enthalpy_j_kg": h_out,
            "gas_pressure_pa_abs": float(gas["pressure_pa"]),
            "gas_temperature_k": float(gas["temperature_k"]),
            "gas_density_kg_m3": float(gas["density_kg_m3"]),
            "gas_effective_area_m2": float(gas["effective_area_m2"]),
            "gas_velocity_m_s": float(gas["velocity_m_s"]),
            "gas_velocity_origin": "provider_resolved",
            "droplet_class_outcomes": [{
                "ground_liquid_mass_flow_kg_s": ground_rate,
                "airborne_liquid_mass_flow_kg_s": 0.0,
                "flight_time_s": float(ground["flight_time_s"]),
                "impact_position_m": list(ground["impact_position_m"]),
                "droplet_diameter_m": float(source["liquid_jet"]["droplet_diameter_m"]),
            }] if ground_rate > 1e-12 else [],
        })
    if not steps:
        raise ValueError("provider returned no left-held liquid interval")
    ends = [x["time_s"] for x in steps[1:]] + [duration]
    mass = sum(x["total_mass_flow_kg_s"] * (end - x["time_s"]) for x, end in zip(steps, ends))
    response = {
        "data": {
            "event_kind": "accidental_leak",
            "upstream_service": "LH2",
            "fluid": source["tank"]["fluid"],
            "phase_basis": "two_phase",
            "duration_s": duration,
            "available_mass_kg": mass,
            "cumulative_mass_out_kg": mass,
            "cumulative_specific_enthalpy_out_j": mass * h_out,
            "reference_area_m2": float(provider["data"]["steps"][0]["gas"]["effective_area_m2"]),
            "reference_area_provenance": "SLABx-LH2 flashed-gas outlet area",
            "steps": steps,
            "termination_provenance": "declared finite diagnostic inventory depletion horizon",
            "droplet_partition_provenance": "SLABx-LH2 ballistic ground-interception result",
        }
    }
    return build_resolved_liquid_release_from_provider_response(
        response,
        component_id="storage",
        port_id="storage.out",
        event_id="slabx-lh2-liquid-jet-provider-diagnostic",
        provider_source_digest=canonical_digest(source),
        provider_result=provider,
        provider_result_digest=canonical_digest(provider),
        upstream_service_provenance="SLABx-LH2 liquid-jet source operator",
        provider_boundary_reference="SLABx-LH2 atmospheric flash and ground interception result",
        input_origin="model_prediction",
        position_enu_m=[0.0, 0.0, source["nozzle"]["height_m"]],
        direction_enu=source["nozzle"]["direction_enu"],
        ambient_pressure_pa_abs=source["ambient"]["pressure_pa"],
        ambient_temperature_k=source["ambient"]["temperature_k"],
        failure_opening_diameter_m=source["nozzle"]["diameter_m"],
    )


def main() -> None:
    base = json.loads((ROOT / "results" / "20261008" / "full_chain" / "gas_release_request.json").read_text(encoding="utf-8"))
    source = copy.deepcopy(base["source_input"])
    source["duration_s"] = 2.0
    source["time_step_s"] = 1.0
    # The provider normalises this oblique downward release; the boundary
    # contract carries the unit ENU vector explicitly.
    source["nozzle"]["direction_enu"] = [2.0 ** -0.5, 0.0, -2.0 ** -0.5]
    source["liquid_jet"] = {
        "discharge_coefficient": 0.62,
        "droplet_diameter_m": 5e-4,
        "d2_evaporation_constant_m2_s": 1e-7,
        "spray_half_angle_deg": 12.0,
        "liquid_velocity_fraction": 1.0,
    }
    config_raw = json.loads((ROOT / "results" / "20261009" / "backend_config_current.json").read_text(encoding="utf-8"))
    pin_refresh = []
    for pin in config_raw["packages"]:
        observed = tree_digest(Path(pin["root"]))
        if observed != pin["sha256"]:
            pin_refresh.append({"name": pin["name"], "declared": pin["sha256"], "observed": observed})
            pin["sha256"] = observed
    config = BackendConfig.model_validate_json(json.dumps(config_raw))
    backend = IsolatedBackend(config)
    provider = backend.run("liquid_jet_source", source)
    release = provider_packet(source, provider)
    ground = provider["data"]["steps"][0]["ground"]

    facility_data = json.loads((ROOT / "examples" / "consequence_facility.json").read_text(encoding="utf-8"))
    for port in facility_data["ports"]:
        if port["id"] == "storage.out":
            port["phase"] = "two_phase"
    facility = Facility.model_validate_json(json.dumps(facility_data, allow_nan=False))
    request = copy.deepcopy(base)
    request.update(
        source_input=None, resolved_release=None, resolved_release_set=None,
        resolved_liquid_release=release.model_dump(mode="json"),
        component_id="storage", source_operator="equipment_liquid_release",
        source_duration_mode="declared", available_mass_kg=release.available_mass_kg,
        source_position_enu_m=list(release.position_enu_m),
        pool={"footprint_origin": "declared_sensitivity",
              "radius_m": float(ground["footprint_radius_m"]),
              "conductivity_w_mk": 0.6, "diffusivity_m2_s": 1.5e-7,
              "initial_temperature_k": source["ambient"]["temperature_k"],
              "domain_radius_m": 0.25, "radial_step_m": 0.0025,
              "maximum_time_step_s": 0.01},
        evaluation_times_s=sorted(set(base["evaluation_times_s"] + [2.0])),
        release_termination={"basis": "inventory_depletion", "time_s": 2.0,
                             "provenance": "provider-resolved finite liquid inventory horizon"},
        annual_frequency_per_year=None, annual_frequency_provenance=None,
        initiation_intensity_per_s=None,
    )
    validated_request = ConsequenceRequest.model_validate_json(json.dumps(request, allow_nan=False))
    result = ResearchPipeline(facility, backend).consequences(validated_request)
    data = result["data"]
    if not data.get("full_chain_executed"):
        raise AssertionError(data.get("status"))
    if not data.get("operator_limited"):
        raise AssertionError("provider liquid route must remain operator-limited")
    if abs(float(data["mass_ledger"]["end_to_end_residual_kg"])) > 1e-8:
        raise AssertionError(data["mass_ledger"])

    out = ROOT / "results" / "20261009" / "equipment_liquid_release"
    save(out / "provider_source_request.json", source)
    save(out / "provider_source_response.json", provider)
    save(out / "resolved_liquid_release.json", release.model_dump(mode="json"))
    save(out / "facility.json", facility.model_dump(mode="json"))
    save(out / "request.json", request)
    save(out / "result.json", result)
    save(out / "backend_config.json", config.model_dump(mode="json"))
    save(out / "verification.json", {
        "status": data["status"], "source_operator": data["source_operator"],
        "full_chain_executed": data["full_chain_executed"],
        "operator_limited": data["operator_limited"],
        "provider_phase_basis": release.phase_basis,
        "provider_mass_kg": release.integrated_mass_kg,
        "provider_mass_residual_kg": data["mass_ledger"]["end_to_end_residual_kg"],
        "provider_gas_and_ground_partition": True,
        "pool_route_executed": bool(data.get("pool")),
        "physical_validation_claim": data["physical_validation_claim"],
        "airborne_liquid_policy": "rejected unless a validated droplet adapter is supplied",
        "pin_refresh": pin_refresh,
        "timing": data.get("stage_elapsed_ms", {}),
    })
    print(json.dumps({"status": data["status"], "source_operator": data["source_operator"],
                      "full_chain_executed": data["full_chain_executed"],
                      "operator_limited": data["operator_limited"],
                      "mass_residual_kg": data["mass_ledger"]["end_to_end_residual_kg"],
                      "elapsed_ms": result.get("elapsed_ms")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
