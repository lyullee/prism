"""Connect one provider-owned inventory-depletion release to the facility chain.

The external ``lh2dt`` homogeneous finite-storage model owns the tank state,
valve flow and positive-mass depletion threshold.  PRISM only converts the
provider interval-average boundary history into ``ResolvedGasRelease`` and
runs every generated literature LH2 pipe LOC through the ordinary consequence
and native TNO IR/F-N path.  The facility and provider inputs remain synthetic
diagnostic values, so this is declared-scope coverage rather than site QRA
validation.
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
from lh2_tno.contracts import Facility
from lh2_tno.equipment_boundary import ResolvedGasRelease
from lh2_tno.equipment_release_adapter import build_resolved_gas_release_from_provider_response
from lh2_tno.frequency import FrequencyPlan, generate_events
from lh2_tno.pipeline import ResearchPipeline

import validate_equipment_campaign as steady


OUT = ROOT / "results" / "20261009" / "equipment_inventory_campaign"
OUT.mkdir(parents=True, exist_ok=True)
FULL_OPEN_AREA_M2 = 1.0e-5
NOMINAL_PIPE_DIAMETER_M = math.sqrt(4.0 * FULL_OPEN_AREA_M2 / math.pi)


def save(name: str, value: object) -> None:
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def provider_input(area_m2: float) -> dict:
    return {
        "fluid": "ParaHydrogen",
        "tank_geometry": {
            "volume_m3": 1.0e-4,
            "wall_heat_capacity_J_K": 100.0,
            "ambient_UA_W_K": 0.1,
            "fluid_wall_UA_W_K": 0.1,
        },
        "initial": {
            "pressure_pa": 101000.0,
            "liquid_fraction": 0.0001,
            "hydrogen_internal_energy_offset_j_kg": 5000.0,
        },
        "ambient": {"pressure_pa": 100000.0, "temperature_k": 288.15},
        "valve": {
            "full_open_area_m2": area_m2,
            "discharge_coefficient": 0.8,
            "pressure_samples": 16,
        },
        "depletion": {"threshold_mass_kg": 1.3405e-4},
        "duration_s": 40.0,
        "time_step_s": 0.5,
    }


def make_facility() -> Facility:
    raw = steady.make_facility().model_dump(mode="json")
    raw["id"] = "equipment-inventory-campaign"
    raw["components"][0]["parameters_si"]["diameter_m"] = NOMINAL_PIPE_DIAMETER_M
    return Facility.model_validate_json(json.dumps(raw))


def make_release(
    backend: IsolatedBackend,
    provider_digest: str,
    event_id: str,
    area_m2: float,
) -> tuple[ResolvedGasRelease, dict, dict]:
    request = provider_input(area_m2)
    response = backend.run("equipment_dynamic_inventory", request)
    data = response["data"]
    release = build_resolved_gas_release_from_provider_response(
        response,
        component_id="terminal_pipe",
        port_id="terminal_pipe.out",
        event_id=event_id,
        provider_source_digest=provider_digest,
        upstream_service_provenance=(
            "provider-owned homogeneous finite-storage tank and inventory valve"
        ),
        provider_boundary_reference=(
            "DynamicNetworkSimulator homogeneous tank to ambient inventory valve"
        ),
        input_origin="synthetic",
        position_enu_m=[0.0, 0.0, 1.0],
        direction_enu=[1.0, 0.0, 0.0],
        ambient_pressure_pa_abs=100000.0,
        ambient_temperature_k=288.15,
        failure_opening_diameter_m=math.sqrt(4.0 * area_m2 / math.pi),
    )
    return release, request, response


def main() -> None:
    config, provider = steady.load_backend()
    backend = IsolatedBackend(config)
    facility = make_facility()
    provider_digest = tree_digest(provider)
    plan_raw = {
        "id": "equipment-inventory-campaign",
        "assets": [
            {
                "id": "terminal_pipe_asset",
                "model_component_id": "terminal_pipe",
                "profile": "LH2_PIPE",
                "classification_basis": "synthetic one-metre LH2-service pipe boundary; not a site frequency claim",
                "physical_scope_ids": ["terminal-pipe-1m"],
                "nominal_diameter_m": NOMINAL_PIPE_DIAMETER_M,
                "length_per_item_m": 1.0,
                "vessel_external_impact_or_operating_error": None,
            }
        ],
    }
    frequency_plan = FrequencyPlan.model_validate_json(json.dumps(plan_raw))
    events = generate_events(facility, frequency_plan)
    releases = {}
    provider_requests = {}
    provider_responses = {}
    for event in events:
        area_m2 = FULL_OPEN_AREA_M2 * event.release.area_fraction
        release, provider_request, provider_response = make_release(
            backend, provider_digest, event.id, area_m2
        )
        data = provider_response["data"]
        if not data["inventory_depletion_detected"]:
            raise AssertionError(f"inventory threshold not reached for {event.loc}")
        releases[event.id] = release
        provider_requests[event.id] = provider_request
        provider_responses[event.id] = provider_response
    save("provider_inputs.json", provider_requests)
    save("provider_responses.json", provider_responses)
    save("facility.json", facility.model_dump(mode="json"))
    save("resolved_releases.json", {event_id: release.model_dump(mode="json") for event_id, release in releases.items()})

    base_template = json.loads(
        (ROOT / "results" / "20261008" / "full_chain" / "gas_release_request.json")
        .read_text(encoding="utf-8")
    )
    templates = {}
    for event in events:
        release = releases[event.id]
        data = provider_responses[event.id]["data"]
        evaluation_times = sorted(
            {
                0.0,
                data["duration_s"],
                1.0,
                2.0,
                3.0,
                5.0,
                10.0,
                20.0,
                40.0,
                60.0,
            }
            | {row["time_s"] for row in data["steps"]}
        )
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
            source_operator="equipment_inventory_depletion",
            release_termination={
                "basis": data["termination_basis"],
                "time_s": release.duration_s,
                "provenance": release.termination_provenance,
            },
            evaluation_times_s=evaluation_times,
        )
        templates[event.id] = template

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
    for condition_id, probability, speed in [
        ("D-3ms-west", 0.4, 3.0),
        ("D-4ms-west", 0.6, 4.0),
    ]:
        conditions.append(
            {
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
            }
        )

    routes = []
    for event in events:
        routes.append(
            {
                "event_id": event.id,
                "branches": [
                    {
                        "id": "provider-inventory-depletion",
                        "probability_given_event": 1.0,
                        "provenance": "provider-owned positive-mass inventory threshold; no frequency or flow extrapolation",
                        "request": copy.deepcopy(templates[event.id]),
                    }
                ],
            }
        )
    campaign = RiskCampaign.model_validate_json(
        json.dumps(
            {
                "id": "equipment-inventory-campaign",
                "frequency_plan": frequency_plan.model_dump(mode="json"),
                "annual_conditions": conditions,
                "event_routes": routes,
                "scope_provenance": "all five LH2_PIPE area-bin events use independent provider-owned homogeneous finite-storage inventory-depletion thresholds and resolved gas histories through SLABx-LH2/SLABx and native TNO IR/F-N; facility geometry, weather and population remain synthetic diagnostics",
            }
        )
    )
    save("campaign.json", campaign.model_dump(mode="json"))
    save("backend_config.json", config.model_dump(mode="json"))
    result = ResearchPipeline(facility, backend).facility_risk(campaign)
    save("campaign_result.json", result)
    executed = [case for case in result["cases"] if case["status"] == "EXECUTED"]
    uncomputed = [case for case in result["uncomputed_cases"] if case["status"] == "UNCOMPUTED"]
    provider_data = {event_id: response["data"] for event_id, response in provider_responses.items()}
    assert len(executed) == len(events) * len(conditions), result["cases"]
    assert len(uncomputed) == 0, result["cases"]
    assert result["total_facility_annual_ir_low_high"] is not None
    assert result["synthetic_release_horizon_present"] is False
    assert all(data["inventory_depletion_detected"] is True for data in provider_data.values())
    assert all(data["remaining_inventory_kg"] <= data["depletion_threshold_kg"] for data in provider_data.values())
    assert max(data["max_total_mass_residual_kg"] for data in provider_data.values()) < 1e-10
    assert max(data["max_total_energy_residual_j"] for data in provider_data.values()) < 1e-8
    assert all(abs(case["mass_ledger"]["end_to_end_residual_kg"]) < 1e-8 for case in executed)
    save(
        "verification.json",
        {
            "equipment_provider_cases": len(events),
            "facility_executed_cases": len(executed),
            "uncomputed_cases": len(uncomputed),
            "provider_inventory_depletion_detected": all(data["inventory_depletion_detected"] for data in provider_data.values()),
            "provider_available_mass_kg": {event_id: data["available_mass_kg"] for event_id, data in provider_data.items()},
            "provider_remaining_inventory_kg": {event_id: data["remaining_inventory_kg"] for event_id, data in provider_data.items()},
            "provider_depletion_threshold_kg": {event_id: data["depletion_threshold_kg"] for event_id, data in provider_data.items()},
            "provider_cumulative_mass_out_kg": {event_id: data["cumulative_mass_out_kg"] for event_id, data in provider_data.items()},
            "provider_mass_residual_max_kg": max(data["max_total_mass_residual_kg"] for data in provider_data.values()),
            "provider_energy_residual_max_j": max(data["max_total_energy_residual_j"] for data in provider_data.values()),
            "resolved_gas_to_final_harm_executed": True,
            "native_tno_ir_fn_aggregation_executed": True,
            "declared_scope_total_risk_computed": True,
            "facility_total_risk_withheld": False,
            "physical_validation_claim": False,
            "campaign_timing": result["timing"],
            "provider_source_digest": provider_digest,
            "backend_config_digest": config.digest(),
            "campaign_digest": campaign.digest(),
            "limitations": [
                "synthetic homogeneous tank geometry, initial state, all valve areas and weather/population",
                "positive-mass threshold is an event-safe provider stopping rule; it does not claim a zero-mass EOS state",
                "provider model is not independently validated against a depletion experiment",
                "declared-scope total risk is for this synthetic five-bin diagnostic, not a site facility QRA",
                "no plant actuator reliability, liquid two-phase outlet, or site calibration",
            ],
        },
    )
    provider_summary = {
        event_id: {
            "duration_s": data["duration_s"],
            "available_mass_kg": data["available_mass_kg"],
            "remaining_inventory_kg": data["remaining_inventory_kg"],
            "threshold_mass_kg": data["depletion_threshold_kg"],
            "cumulative_mass_out_kg": data["cumulative_mass_out_kg"],
            "mass_residual_max_kg": data["max_total_mass_residual_kg"],
            "energy_residual_max_j": data["max_total_energy_residual_j"],
        }
        for event_id, data in provider_data.items()
    }
    print(
        json.dumps(
            {
                "status": result["status"],
                "executed": len(executed),
                "uncomputed": len(uncomputed),
                "inventory_depletion_detected": all(data["inventory_depletion_detected"] for data in provider_data.values()),
                "provider_summary": provider_summary,
                "timing": result["timing"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
