"""Validate transient tank-to-isolation-to-facility coupling.

The external ``lh2dt`` provider owns the layered tank, commanded valve and
network flow. PRISM converts the provider's interval history into its
resolved atmospheric-gas contract, then runs the selected pipe LOC through
the normal SLABx-LH2/SLABx/TNO facility chain. The geometry is synthetic and
the other pipe LOCs remain explicitly uncomputed.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import IsolatedBackend, tree_digest
from lh2_tno.campaign import RiskCampaign
from lh2_tno.contracts import Facility, canonical_digest
from lh2_tno.equipment_boundary import ResolvedGasRelease
from lh2_tno.frequency import FrequencyPlan, generate_events
from lh2_tno.pipeline import ResearchPipeline

import validate_equipment_campaign as steady


OUT = ROOT / "results" / "20261009" / "equipment_isolation_campaign"
OUT.mkdir(parents=True, exist_ok=True)


def save(name: str, value: object) -> None:
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def dynamic_input() -> dict:
    return {
        "fluid": "ParaHydrogen",
        "geometry": {
            "inner_diameter_m": 1.0,
            "straight_length_m": 2.0,
            "head_depth_m": 0.25,
            "quadrature_order": 40,
        },
        "tank_parameters": {
            "liquid_cell_count": 2,
            "vapor_cell_count": 2,
            "wall_node_count": 4,
            "wall_heat_capacity_J_K": 1.0e6,
        },
        "initial": {
            "pressure_pa": 103000.0,
            "liquid_fraction": 0.5,
            "vapor_enthalpy_offset_j_kg": 5000.0,
        },
        "ambient": {"pressure_pa": 100000.0, "temperature_k": 288.15, "wall_ambient_temperature_k": 20.0},
        "valve": {
            "full_open_area_m2": 1.0e-6,
            "discharge_coefficient": 0.8,
            "pressure_samples": 16,
            "allow_reverse": False,
            "closed_leakage_CdA_m2": 0.0,
        },
        "isolation": {"close_time_s": 0.25},
        "duration_s": 0.5,
        "time_step_s": 0.01,
    }


def make_release(backend: IsolatedBackend, provider_digest: str) -> tuple[ResolvedGasRelease, dict, dict]:
    request = dynamic_input()
    response = backend.run("equipment_dynamic_isolation", request)
    data = response["data"]
    steps = []
    for row in data["steps"]:
        steps.append(
            {
                key: row[key]
                for key in (
                    "time_s",
                    "mass_flow_kg_s",
                    "pressure_pa_abs",
                    "specific_enthalpy_j_kg",
                    "temperature_k",
                    "density_kg_m3",
                    "effective_area_m2",
                    "velocity_m_s",
                )
            }
            | {
                "area_provenance": "provider-declared commanded-valve area",
                "velocity_origin": "mass_continuity_from_declared_area",
            }
        )
    packet = {
        "component_id": "terminal_pipe",
        "port_id": "terminal_pipe.out",
        "event_id": "equipment-isolation-campaign/terminal_pipe/AREA_100%",
        "event_kind": "accidental_leak",
        "enthalpy_convention": "static_exit_enthalpy",
        "property_basis": {
            "fluid": "ParaHydrogen",
            "backend": "CoolProp-HEOS",
            "energy_reference": "CoolProp-HEOS:ParaHydrogen:native",
        },
        "upstream_service": "LH2",
        "upstream_service_provenance": "LH2 service boundary; layered tank and commanded isolation valve are provider-owned",
        "provider_source_digest": provider_digest,
        "provider_result_digest": canonical_digest(response),
        "provider_boundary_reference": "LayeredTankNetworkSimulator isolation_valve link to ambient sink",
        "input_origin": "synthetic",
        "position_enu_m": [0.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 100000.0,
        "ambient_temperature_k": 288.15,
        "duration_s": data["duration_s"],
        "available_mass_kg": data["available_mass_kg"],
        "cumulative_mass_out_kg": data["cumulative_mass_out_kg"],
        "cumulative_static_enthalpy_out_j": data["cumulative_static_enthalpy_out_j"],
        "steps": steps,
        "termination_provenance": "provider commanded isolation at 0.25 s; zero closed-seat leakage and zero post-close flow confirmed",
        "failure_opening_diameter_m": 0.0011283791670955126,
    }
    return ResolvedGasRelease.model_validate_json(json.dumps(packet)), request, response


def make_dynamic_facility() -> Facility:
    """Keep the synthetic facility bore consistent with the valve area."""
    raw = steady.make_facility().model_dump(mode="json")
    diameter = math.sqrt(4.0 * dynamic_input()["valve"]["full_open_area_m2"] / math.pi)
    raw["id"] = "equipment-isolation-campaign"
    raw["components"][0]["parameters_si"]["diameter_m"] = diameter
    return Facility.model_validate_json(json.dumps(raw))


def main() -> None:
    config, provider = steady.load_backend()
    backend = IsolatedBackend(config)
    facility: Facility = make_dynamic_facility()
    release, provider_request, provider_response = make_release(backend, tree_digest(provider))
    save("provider_input.json", provider_request)
    save("provider_response.json", provider_response)
    save("facility.json", facility.model_dump(mode="json"))
    save("resolved_release.json", release.model_dump(mode="json"))

    plan_raw = {
        "id": "equipment-isolation-campaign",
        "assets": [{
            "id": "terminal_pipe_asset",
            "model_component_id": "terminal_pipe",
            "profile": "LH2_PIPE",
            "classification_basis": "synthetic one-metre LH2-service pipe boundary; not a site frequency claim",
            "physical_scope_ids": ["terminal-pipe-1m"],
            "nominal_diameter_m": math.sqrt(4.0 * dynamic_input()["valve"]["full_open_area_m2"] / math.pi),
            "length_per_item_m": 1.0,
            "vessel_external_impact_or_operating_error": None,
        }],
    }
    frequency_plan = FrequencyPlan.model_validate_json(json.dumps(plan_raw))
    events = generate_events(facility, frequency_plan)
    selected = next(event for event in events if event.loc == "AREA_100%")
    base_request = json.loads(
        (ROOT / "results" / "20261008" / "full_chain" / "gas_release_request.json")
        .read_text(encoding="utf-8")
    )
    base_request.update(
        component_id="terminal_pipe",
        source_input=None,
        resolved_release=release.model_dump(mode="json"),
        available_mass_kg=release.available_mass_kg,
        source_position_enu_m=[0.0, 0.0, 1.0],
        annual_frequency_per_year=None,
        annual_frequency_provenance=None,
        frequency_event=None,
        initiation_intensity_per_s=None,
        release_termination={
            "basis": "reviewed_isolation_success",
            "time_s": release.duration_s,
            "provenance": release.termination_provenance,
        },
        evaluation_times_s=sorted({
            *[row["time_s"] for row in provider_response["data"]["steps"]],
            0.25, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0,
        }),
    )
    routes = []
    for event in events:
        if event.id == selected.id:
            routes.append({
                "event_id": event.id,
                "branches": [{
                    "id": "provider-dynamic-isolation-gas-exit",
                    "probability_given_event": 1.0,
                    "provenance": "native layered-tank/commanded-valve provider export; PRISM does not re-solve provider flow",
                    "request": copy.deepcopy(base_request),
                }],
            })
        else:
            routes.append({
                "event_id": event.id,
                "branches": [{
                    "id": "pending-equipment-route",
                    "probability_given_event": 1.0,
                    "provenance": "explicitly outside this coupling diagnostic",
                    "uncomputed_reason": "equipment transient route was only qualified for the selected AREA_100% gas exit",
                }],
            })
    population = [
        {
            "receptor_id": receptor.id,
            "persons": 20.0 if i == 0 else 10.0,
            "presence_probability": 0.5,
            "provenance": "synthetic disjoint outdoor groups; not field population",
        }
        for i, receptor in enumerate(facility.receptors)
    ]
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
            "population": population,
            "provenance": "synthetic annual condition partition; no site weather qualification",
        })
    campaign = RiskCampaign.model_validate_json(json.dumps({
        "id": "equipment-isolation-campaign",
        "frequency_plan": frequency_plan.model_dump(mode="json"),
        "annual_conditions": conditions,
        "event_routes": routes,
        "scope_provenance": "one native transient equipment-twin LH2 pipe gas exit with explicit valve closure through PH validation, SLABx-LH2/SLABx consequence chain and native TNO IR/F-N; other LOCs explicitly withheld",
    }))
    save("campaign.json", campaign.model_dump(mode="json"))
    save("backend_config.json", config.model_dump(mode="json"))
    result = ResearchPipeline(facility, backend).facility_risk(campaign)
    save("campaign_result.json", result)
    executed = [case for case in result["cases"] if case["status"] == "EXECUTED"]
    uncomputed = [case for case in result["uncomputed_cases"] if case["status"] == "UNCOMPUTED"]
    data = provider_response["data"]
    assert len(executed) == 2, result["cases"]
    assert len(uncomputed) == 8, result["cases"]
    assert result["total_facility_annual_ir_low_high"] is None
    assert data["isolation_flow_zero_confirmed"] is True
    assert data["post_close_max_flow_kg_s"] == 0.0
    assert all(abs(case["mass_ledger"]["end_to_end_residual_kg"]) < 1e-8 for case in executed)
    save("verification.json", {
        "equipment_provider_cases": 2,
        "uncomputed_other_pipe_locs": 8,
        "provider_flow_owned_by_equipment_twin": True,
        "provider_transient_tank_valve_network_executed": True,
        "provider_isolation_command_confirmed": True,
        "provider_post_close_max_flow_kg_s": data["post_close_max_flow_kg_s"],
        "provider_mass_residual_max_kg": data["max_total_mass_residual_kg"],
        "provider_energy_residual_max_j": data["max_total_energy_residual_j"],
        "resolved_gas_to_final_harm_executed": True,
        "native_tno_ir_fn_aggregation_executed": True,
        "facility_total_risk_withheld": True,
        "physical_validation_claim": False,
        "campaign_timing": result["timing"],
        "provider_source_digest": tree_digest(provider),
        "backend_config_digest": config.digest(),
        "campaign_digest": campaign.digest(),
        "limitations": [
            "synthetic layered tank geometry, initial state, valve area and weather/population",
            "isolation success is qualified only for the supplied command and zero closed-seat leakage",
            "no actuator delay, failure-on-demand probability, liquid two-phase release or site data calibration",
            "only AREA_100% selected route executed; other pipe LOCs remain uncomputed",
        ],
    })
    print(json.dumps({
        "status": result["status"],
        "executed": len(executed),
        "uncomputed": len(uncomputed),
        "total_facility_risk_available": result["total_facility_annual_ir_low_high"] is not None,
        "provider_isolation_flow_zero_confirmed": data["isolation_flow_zero_confirmed"],
        "provider_mass_out_kg": data["cumulative_mass_out_kg"],
        "provider_max_mass_residual_kg": data["max_total_mass_residual_kg"],
        "timing": result["timing"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
