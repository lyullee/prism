"""Connect one LH2 equipment-twin gas exit to the facility campaign.

The provider owns the PH/network flow calculation. PRISM only validates the
resolved atmospheric gas boundary, sends it through the consequence chain,
and aggregates the selected LOC with native TNO IR/F-N. The other pipe LOCs
remain explicit uncomputed cases; this is a coupling diagnostic, not a full
facility QRA or a physical validation claim.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import sys

import CoolProp.CoolProp as CP

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest
from lh2_tno.campaign import RiskCampaign
from lh2_tno.contracts import Facility, canonical_digest
from lh2_tno.equipment_boundary import ResolvedGasRelease
from lh2_tno.equipment_release_adapter import build_resolved_gas_release_from_provider_response
from lh2_tno.frequency import generate_events
from lh2_tno.pipeline import ResearchPipeline


OUT = ROOT / "results" / "20261009" / "equipment_campaign"
OUT.mkdir(parents=True, exist_ok=True)


def save(name: str, value: object) -> None:
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def load_backend() -> tuple[BackendConfig, Path]:
    raw = json.loads(
        (ROOT / "results" / "20261009" / "backend_config_current.json")
        .read_text(encoding="utf-8")
    )
    for pin in raw["packages"]:
        if pin["name"] == "tno":
            pin["sha256"] = tree_digest(Path(pin["root"]))
    provider = Path(
        r"C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템"
        r"\06_액화수소_디지털트윈_물리모델\src\lh2dt"
    )
    raw["packages"] = [p for p in raw["packages"] if p["name"] != "lh2dt"]
    raw["packages"].append(
        {"name": "lh2dt", "root": str(provider), "sha256": tree_digest(provider)}
    )
    return BackendConfig.model_validate_json(json.dumps(raw)), provider


def ph_state(pressure_pa: float, temperature_k: float) -> dict[str, float]:
    return {
        "pressure_pa_abs": pressure_pa,
        "specific_enthalpy_j_kg": CP.PropsSI(
            "H", "P", pressure_pa, "T", temperature_k, "ParaHydrogen"
        ),
    }


def provider_input(temperature_k: float) -> dict:
    return {
        "fluid": "ParaHydrogen",
        "provider_link_id": "TERMINAL_FULL_BORE_LEAK",
        "upstream": ph_state(101525.0, temperature_k),
        "downstream": ph_state(101325.0, 288.15),
        "stack": {
            "length_m": 6.0,
            "inner_diameter_m": 0.0254,
            "roughness_m": 1.5e-6,
            "local_loss_coefficient": 2.0,
            "elevation_change_m": 0.0,
            "ambient_temperature_K": 288.15,
            "ambient_UA_W_K": 5.0,
            "integration_segments": 64,
        },
    }


def make_facility() -> Facility:
    basis = {
        "fluid": "ParaHydrogen",
        "backend": "CoolProp-HEOS",
        "energy_reference": "CoolProp-HEOS:ParaHydrogen:native",
    }
    raw = {
        "id": "equipment-coupling-campaign",
        "configuration_origin": "synthetic",
        "environment": "outdoor",
        "components": [
            {
                "id": "terminal_pipe",
                "kind": "pipe",
                "position_enu_m": [0.0, 0.0, 1.0],
                "property_basis": basis,
                "parameters_si": {"length_m": 1.0, "diameter_m": 0.0254},
            }
        ],
        "ports": [
            {
                "id": "terminal_pipe.out",
                "component_id": "terminal_pipe",
                "phase": "vapour",
                "direction": "out",
            }
        ],
        "edges": [],
        "receptors": [
            {"id": "near_worker", "position_enu_m": [2.0, 0.0, 1.0]},
            {"id": "downwind_worker", "position_enu_m": [10.0, 0.0, 0.1]},
            {"id": "side_worker", "position_enu_m": [25.0, 4.0, 1.8]},
            {"id": "distant_worker", "position_enu_m": [60.0, 0.0, 1.8]},
        ],
    }
    return Facility.model_validate_json(json.dumps(raw))


def make_release(backend: IsolatedBackend, provider_digest: str) -> ResolvedGasRelease:
    inputs = [provider_input(20.5), provider_input(21.0)]
    exports = [backend.run("equipment_network_exit", item) for item in inputs]
    steps = []
    for time_s, response in zip((0.0, 0.2), exports):
        data = response["data"]
        outlet = data["outlet"]
        steps.append(
            {
                "time_s": time_s,
                "mass_flow_kg_s": data["flow"]["mass_flow_kg_s"],
                "pressure_pa_abs": outlet["pressure_Pa"],
                "specific_enthalpy_j_kg": outlet["specific_enthalpy_J_kg"],
                "temperature_k": outlet["temperature_K"],
                "density_kg_m3": outlet["density_kg_m3"],
                "effective_area_m2": data["effective_area_m2"],
                "velocity_m_s": data["velocity_m_s"],
                "area_provenance": "native terminal bore from equipment-twin network export",
                "velocity_origin": data["velocity_origin"],
            }
        )
    duration_s = 0.37
    ends = [step["time_s"] for step in steps[1:]] + [duration_s]
    mass = sum(step["mass_flow_kg_s"] * (end - step["time_s"]) for step, end in zip(steps, ends))
    energy = sum(
        step["mass_flow_kg_s"] * step["specific_enthalpy_j_kg"] * (end - step["time_s"])
        for step, end in zip(steps, ends)
    )
    save("provider_inputs.json", inputs)
    save("provider_exports.json", exports)
    provider_response = {
        "data": {
            "event_kind": "accidental_leak",
            "duration_s": duration_s,
            "available_mass_kg": 0.01,
            "cumulative_mass_out_kg": mass,
            "cumulative_static_enthalpy_out_j": energy,
            "steps": steps,
            "termination_provenance": (
                "synthetic 0.37 s command closure; provider transient feedback not qualified"
            ),
        }
    }
    return build_resolved_gas_release_from_provider_response(
        provider_response,
        component_id="terminal_pipe",
        port_id="terminal_pipe.out",
        event_id="equipment-coupling-campaign/terminal_pipe/AREA_100%",
        provider_source_digest=provider_digest,
        provider_result=exports,
        provider_result_digest=canonical_digest(exports),
        upstream_service_provenance=(
            "LH2 service boundary; native equipment model flashes the outlet to atmospheric gas"
        ),
        provider_boundary_reference=(
            "SteadyNetwork terminal link to atmosphere; native terminal bore"
        ),
        input_origin="synthetic",
        position_enu_m=[0.0, 0.0, 1.0],
        direction_enu=[1.0, 0.0, 0.0],
        ambient_pressure_pa_abs=101325.0,
        ambient_temperature_k=288.15,
        failure_opening_diameter_m=0.0254,
    )


def main() -> None:
    config, provider = load_backend()
    backend = IsolatedBackend(config)
    facility = make_facility()
    release = make_release(backend, tree_digest(provider))
    save("facility.json", facility.model_dump(mode="json"))
    save("resolved_release.json", release.model_dump(mode="json"))

    plan = {
        "id": "equipment-coupling-campaign",
        "assets": [
            {
                "id": "terminal_pipe_asset",
                "model_component_id": "terminal_pipe",
                "profile": "LH2_PIPE",
                "classification_basis": "synthetic one-metre LH2-service pipe boundary; not a site frequency claim",
                "physical_scope_ids": ["terminal-pipe-1m"],
                "nominal_diameter_m": 0.0254,
                "length_per_item_m": 1.0,
                "vessel_external_impact_or_operating_error": None,
            }
        ],
    }
    from lh2_tno.frequency import FrequencyPlan

    frequency_plan = FrequencyPlan.model_validate_json(json.dumps(plan))
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
        available_mass_kg=0.01,
        source_position_enu_m=[0.0, 0.0, 1.0],
        annual_frequency_per_year=None,
        annual_frequency_provenance=None,
        frequency_event=None,
        initiation_intensity_per_s=None,
        release_termination={
            "basis": "synthetic_diagnostic_horizon",
            "time_s": 0.37,
            "provenance": release.termination_provenance,
        },
        evaluation_times_s=[0.0, 0.1, 0.2, 0.37, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0],
    )
    routes = []
    for event in events:
        if event.id == selected.id:
            routes.append(
                {
                    "event_id": event.id,
                    "branches": [
                        {
                            "id": "provider-resolved-gas-exit",
                            "probability_given_event": 1.0,
                            "provenance": "native equipment-twin PH/network export; provider flow is not recomputed by PRISM",
                            "request": copy.deepcopy(base_request),
                        }
                    ],
                }
            )
        else:
            routes.append(
                {
                    "event_id": event.id,
                    "branches": [
                        {
                            "id": "pending-equipment-route",
                            "probability_given_event": 1.0,
                            "provenance": "explicitly outside this coupling diagnostic",
                            "uncomputed_reason": "equipment provider route was only qualified for the selected AREA_100% gas exit",
                        }
                    ],
                }
            )
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
    campaign = RiskCampaign.model_validate_json(
        json.dumps(
            {
                "id": "equipment-coupling-campaign",
                "frequency_plan": frequency_plan.model_dump(mode="json"),
                "annual_conditions": conditions,
                "event_routes": routes,
                "scope_provenance": "one native equipment-twin LH2 pipe gas exit through PH validation, SLABx-LH2/SLABx consequence chain and native TNO IR/F-N; other LOCs explicitly withheld",
            }
        )
    )
    save("campaign.json", campaign.model_dump(mode="json"))
    save("backend_config.json", config.model_dump(mode="json"))
    result = ResearchPipeline(facility, backend).facility_risk(campaign)
    save("campaign_result.json", result)
    executed = [case for case in result["cases"] if case["status"] == "EXECUTED"]
    uncomputed = [case for case in result["uncomputed_cases"] if case["status"] == "UNCOMPUTED"]
    assert len(executed) == 2, result["cases"]
    assert len(uncomputed) == 8, result["cases"]
    assert result["total_facility_annual_ir_low_high"] is None
    assert all(abs(case["mass_ledger"]["end_to_end_residual_kg"]) < 1e-8 for case in executed)
    assert all(case["request_digest"] for case in executed)
    save(
        "verification.json",
        {
            "equipment_provider_cases": 2,
            "uncomputed_other_pipe_locs": 8,
            "provider_flow_owned_by_equipment_twin": True,
            "provider_ph_and_continuity_checked": True,
            "resolved_gas_to_final_harm_executed": True,
            "native_tno_ir_fn_aggregation_executed": True,
            "facility_total_risk_withheld": True,
            "physical_validation_claim": False,
            "campaign_timing": result["timing"],
            "provider_source_digest": tree_digest(provider),
            "backend_config_digest": config.digest(),
            "campaign_digest": campaign.digest(),
            "mass_residual_max_kg": max(abs(case["mass_ledger"]["end_to_end_residual_kg"]) for case in executed),
            "limitations": [
                "synthetic equipment boundary and weather/population conditions",
                "provider is steady PH/network export; transient tank/valve feedback is not qualified",
                "only AREA_100% selected route executed; other pipe LOCs remain uncomputed",
            ],
        },
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "executed": len(executed),
                "uncomputed": len(uncomputed),
                "total_facility_risk_available": result["total_facility_annual_ir_low_high"] is not None,
                "timing": result["timing"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
