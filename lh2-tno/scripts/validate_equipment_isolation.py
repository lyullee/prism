"""Validate transient tank-to-isolation-to-facility coupling.

The external ``lh2dt`` provider owns the layered tank, commanded valve and
network flow. PRISM converts each provider interval history into its
resolved atmospheric-gas contract, then runs all reviewed LH2 pipe LOCs
through the normal SLABx-LH2/SLABx/TNO facility chain. The geometry, barrier
probability and weather partition are synthetic.
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

# The synthetic facility keeps one declared nominal pipe bore.  Each
# literature LH2_PIPE area bin is then represented by a provider-owned valve
# area on that same component, so the frequency hole diameter and the
# transient equipment boundary remain tied to one physical source.
FULL_OPEN_AREA_M2 = 1.0e-6
NOMINAL_PIPE_DIAMETER_M = math.sqrt(4.0 * FULL_OPEN_AREA_M2 / math.pi)


def save(name: str, value: object) -> None:
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def dynamic_input(outcome: str = "success", valve_area_m2: float = FULL_OPEN_AREA_M2) -> dict:
    close_time = 0.25 if outcome == "success" else 0.5
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
            "full_open_area_m2": valve_area_m2,
            "discharge_coefficient": 0.8,
            "pressure_samples": 16,
            "allow_reverse": False,
            "closed_leakage_CdA_m2": 0.0,
        },
        "isolation": {"close_time_s": close_time, "outcome": outcome},
        "duration_s": 0.5,
        "time_step_s": 0.01,
    }


def make_release(
    backend: IsolatedBackend,
    provider_digest: str,
    outcome: str,
    loc: str,
    area_fraction: float,
) -> tuple[ResolvedGasRelease, dict, dict]:
    valve_area_m2 = FULL_OPEN_AREA_M2 * area_fraction
    request = dynamic_input(outcome, valve_area_m2)
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
        "event_id": f"equipment-isolation-campaign/terminal_pipe/{loc}/{outcome}",
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
        "termination_provenance": (
            "provider commanded isolation at 0.25 s; zero closed-seat leakage and zero post-close flow confirmed"
            if outcome == "success"
            else "provider isolation command failed; valve remained open through the 0.5 s diagnostic horizon"
        ),
        "failure_opening_diameter_m": math.sqrt(4.0 * valve_area_m2 / math.pi),
    }
    return ResolvedGasRelease.model_validate_json(json.dumps(packet)), request, response


def make_dynamic_facility() -> Facility:
    """Keep the synthetic facility bore consistent with the valve area."""
    raw = steady.make_facility().model_dump(mode="json")
    raw["id"] = "equipment-isolation-campaign"
    raw["components"][0]["parameters_si"]["diameter_m"] = NOMINAL_PIPE_DIAMETER_M
    return Facility.model_validate_json(json.dumps(raw))


def main() -> None:
    config, provider = steady.load_backend()
    backend = IsolatedBackend(config)
    facility: Facility = make_dynamic_facility()
    provider_digest = tree_digest(provider)
    # Generate the reviewed catalogue events first.  The provider is then run
    # independently for every area bin; no result is scaled or reused across
    # hole sizes.
    plan_raw = {
        "id": "equipment-isolation-campaign",
        "assets": [{
            "id": "terminal_pipe_asset",
            "model_component_id": "terminal_pipe",
            "profile": "LH2_PIPE",
            "classification_basis": "synthetic one-metre LH2-service pipe boundary; not a site frequency claim",
            "physical_scope_ids": ["terminal-pipe-1m"],
            "nominal_diameter_m": NOMINAL_PIPE_DIAMETER_M,
            "length_per_item_m": 1.0,
            "vessel_external_impact_or_operating_error": None,
        }],
    }
    frequency_plan = FrequencyPlan.model_validate_json(json.dumps(plan_raw))
    events = generate_events(facility, frequency_plan)
    provider_request = {}
    provider_response = {}
    releases = {}
    for event in events:
        area_fraction = float(event.release.area_fraction)
        success_release, success_request, success_response = make_release(
            backend, provider_digest, "success", event.loc, area_fraction
        )
        failure_release, failure_request, failure_response = make_release(
            backend, provider_digest, "failure", event.loc, area_fraction
        )
        provider_request[event.loc] = {"success": success_request, "failure": failure_request}
        provider_response[event.loc] = {"success": success_response, "failure": failure_response}
        releases[event.loc] = {
            "success": success_release,
            "failure": failure_release,
            "success_response": success_response,
            "failure_response": failure_response,
        }
    save("provider_input.json", provider_request)
    save("provider_response.json", provider_response)
    save("facility.json", facility.model_dump(mode="json"))
    save("resolved_release.json", {
        loc: {
            "success": source["success"].model_dump(mode="json"),
            "failure": source["failure"].model_dump(mode="json"),
        }
        for loc, source in releases.items()
    })

    base_template = json.loads(
        (ROOT / "results" / "20261008" / "full_chain" / "gas_release_request.json")
        .read_text(encoding="utf-8")
    )
    def consequence_template(release: ResolvedGasRelease, response: dict) -> dict:
        data = response["data"]
        template = copy.deepcopy(base_template)
        template.update(
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
                "basis": data["termination_basis"],
                "time_s": release.duration_s,
                "provenance": release.termination_provenance,
            },
            evaluation_times_s=sorted({
                *[row["time_s"] for row in data["steps"]],
                0.25, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0,
            }),
        )
        return template
    barrier_success_probability = 0.99
    routes = []
    for event in events:
        source = releases[event.loc]
        routes.append({
            "event_id": event.id,
            "branches": [
                {
                    "id": "provider-isolation-success",
                    "probability_given_event": barrier_success_probability,
                    "provenance": "synthetic barrier branch; native commanded-valve provider export; PRISM does not re-solve provider flow",
                    "request": copy.deepcopy(consequence_template(source["success"], source["success_response"])),
                },
                {
                    "id": "provider-isolation-failure",
                    "probability_given_event": 1.0 - barrier_success_probability,
                    "provenance": "synthetic barrier branch; valve remains open through declared diagnostic horizon",
                    "request": copy.deepcopy(consequence_template(source["failure"], source["failure_response"])),
                },
            ],
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
        "scope_provenance": "all five reviewed LH2_PIPE area bins use independent native transient equipment-twin runs with explicit isolation-success and isolation-failure branches through PH validation, SLABx-LH2/SLABx consequence chain and native TNO IR/F-N; barrier probability and geometry are synthetic",
    }))
    save("campaign.json", campaign.model_dump(mode="json"))
    save("backend_config.json", config.model_dump(mode="json"))
    result = ResearchPipeline(facility, backend).facility_risk(campaign)
    save("campaign_result.json", result)
    executed = [case for case in result["cases"] if case["status"] == "EXECUTED"]
    uncomputed = [case for case in result["uncomputed_cases"] if case["status"] == "UNCOMPUTED"]
    provider_checks = {
        loc: {
            "success": source["success_response"]["data"],
            "failure": source["failure_response"]["data"],
        }
        for loc, source in releases.items()
    }
    assert len(executed) == 20, result["cases"]
    assert len(uncomputed) == 0, result["cases"]
    assert result["total_facility_annual_ir_low_high"] is None
    assert all(data["success"]["isolation_flow_zero_confirmed"] is True for data in provider_checks.values())
    assert all(data["success"]["post_close_max_flow_kg_s"] == 0.0 for data in provider_checks.values())
    assert all(data["failure"]["isolation_flow_zero_confirmed"] is False for data in provider_checks.values())
    assert all(data["failure"]["post_close_observation_available"] is False for data in provider_checks.values())
    assert all(data["failure"]["pre_close_max_flow_kg_s"] > 0.0 for data in provider_checks.values())
    assert all(abs(case["mass_ledger"]["end_to_end_residual_kg"]) < 1e-8 for case in executed)
    save("verification.json", {
        "equipment_provider_cases": len(events) * 2,
        "facility_executed_cases": len(executed),
        "uncomputed_other_pipe_locs": 0,
        "executed_pipe_locs": [event.loc for event in events],
        "provider_flow_owned_by_equipment_twin": True,
        "provider_transient_tank_valve_network_executed": True,
        "provider_isolation_success_command_confirmed": True,
        "provider_isolation_failure_horizon_executed": True,
        "provider_success_post_close_max_flow_kg_s": {
            loc: data["success"]["post_close_max_flow_kg_s"] for loc, data in provider_checks.items()
        },
        "provider_failure_pre_close_max_flow_kg_s": {
            loc: data["failure"]["pre_close_max_flow_kg_s"] for loc, data in provider_checks.items()
        },
        "provider_success_mass_residual_max_kg": {
            loc: data["success"]["max_total_mass_residual_kg"] for loc, data in provider_checks.items()
        },
        "provider_failure_mass_residual_max_kg": {
            loc: data["failure"]["max_total_mass_residual_kg"] for loc, data in provider_checks.items()
        },
        "provider_success_energy_residual_max_j": {
            loc: data["success"]["max_total_energy_residual_j"] for loc, data in provider_checks.items()
        },
        "provider_failure_energy_residual_max_j": {
            loc: data["failure"]["max_total_energy_residual_j"] for loc, data in provider_checks.items()
        },
        "synthetic_barrier_success_probability": barrier_success_probability,
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
            "isolation success/failure branch probability is synthetic and not a plant barrier reliability estimate",
            "isolation success is qualified only for the supplied command and zero closed-seat leakage",
            "isolation failure is held only to the 0.5 s diagnostic horizon; inventory depletion is not claimed",
            "no actuator delay, failure-on-demand probability, liquid two-phase release or site data calibration",
            "all five pipe LOCs are executed, but the route remains a synthetic one-component diagnostic rather than a site equipment inventory",
        ],
    })
    print(json.dumps({
        "status": result["status"],
        "executed": len(executed),
        "uncomputed": len(uncomputed),
        "total_facility_risk_available": result["total_facility_annual_ir_low_high"] is not None,
        "provider_isolation_success_flow_zero_confirmed": all(data["success"]["isolation_flow_zero_confirmed"] for data in provider_checks.values()),
        "provider_isolation_failure_flow_nonzero_before_horizon": all(data["failure"]["pre_close_max_flow_kg_s"] > 0.0 for data in provider_checks.values()),
        "provider_success_mass_out_kg": {
            loc: data["success"]["cumulative_mass_out_kg"] for loc, data in provider_checks.items()
        },
        "provider_failure_mass_out_kg": {
            loc: data["failure"]["cumulative_mass_out_kg"] for loc, data in provider_checks.items()
        },
        "timing": result["timing"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
