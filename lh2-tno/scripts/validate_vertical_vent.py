"""Run a provider-resolved vertical gas-vent handoff diagnostic.

The equipment provider supplies a horizontal SLAB-equivalent handoff section
after the vertical exit.  PRISM consumes that section without rotating the
original nozzle or recalculating its discharge.  The input is synthetic and
operator-limited until a validated vertical free-jet adapter is available.
"""
from __future__ import annotations

import copy
import json
import argparse
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


OUT = ROOT / "results" / "20261009" / "vertical_vent"
OUT.mkdir(parents=True, exist_ok=True)


def save(name: str, value: object) -> None:
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def make_facility() -> Facility:
    raw = steady.make_facility().model_dump(mode="json")
    raw["id"] = "vertical-vent-campaign"
    raw["ports"][0]["position_enu_m"] = [0.0, 0.0, 1.0]
    return Facility.model_validate_json(json.dumps(raw))


def make_vertical_release(
    backend: IsolatedBackend,
    provider_digest: str,
    opening_diameter_m: float = 0.0254,
    event_id: str = "vertical-vent-campaign/terminal_pipe/AREA_100%",
) -> ResolvedGasRelease:
    raw = steady.make_release(
        backend,
        provider_digest,
        opening_diameter_m=opening_diameter_m,
        event_id=event_id,
    ).model_dump(mode="json")
    raw.update(
        port_id="terminal_pipe.out",
        event_id=event_id,
        position_enu_m=[0.0, 0.0, 1.0],
        direction_enu=[0.0, 0.0, 1.0],
    )
    # Keep the provider release history intact and declare one handoff state
    # per release interval.  The changing carrier velocity/section exercises
    # the variable-state contract; it remains a synthetic adapter input, not a
    # measured vertical transient.
    first = copy.deepcopy(raw["steps"][0])
    second = copy.deepcopy(first)
    second["time_s"] = 0.2
    raw["steps"] = [first, second]
    ends = [0.2, raw["duration_s"]]
    mass = sum(step["mass_flow_kg_s"] * (end - step["time_s"])
               for step, end in zip(raw["steps"], ends))
    energy = sum(step["mass_flow_kg_s"] * step["specific_enthalpy_j_kg"] * (end - step["time_s"])
                 for step, end in zip(raw["steps"], ends))
    h2_fraction = 0.9
    width = 0.02
    velocities = [5.0, 6.0]
    states = []
    for step, velocity in zip(raw["steps"], velocities):
        depth = (step["mass_flow_kg_s"] / h2_fraction) / (step["density_kg_m3"] * velocity * 2.0 * width)
        states.append({
            "time_s": step["time_s"],
            "direction_enu": [1.0, 0.0, 0.0],
            "velocity_m_s": velocity,
            "density_kg_m3": step["density_kg_m3"],
            "temperature_k": step["temperature_k"],
            "h2_mass_fraction": h2_fraction,
            "half_width_m": width,
            "depth_m": depth,
            "provenance": "synthetic provider variable vertical-to-horizontal handoff; not independently validated",
        })
    raw.update(
        cumulative_mass_out_kg=mass,
        cumulative_static_enthalpy_out_j=energy,
        vertical_handoff={
            "position_enu_m": [0.0, 0.0, 2.0],
            "direction_enu": [1.0, 0.0, 0.0],
            "velocity_m_s": velocities[0],
            "density_kg_m3": first["density_kg_m3"],
            "temperature_k": first["temperature_k"],
            "h2_mass_fraction": h2_fraction,
            "half_width_m": width,
            "depth_m": states[0]["depth_m"],
            "provenance": "synthetic provider vertical-to-horizontal handoff; not independently validated",
            "states": states,
        },
    )
    return ResolvedGasRelease.model_validate_json(json.dumps(raw))


def main() -> None:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all-area-bins",
        action="store_true",
        help="run a separate provider boundary calculation for every generated area bin",
    )
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.output_dir
    OUT.mkdir(parents=True, exist_ok=True)
    config, provider = steady.load_backend()
    backend = IsolatedBackend(config)
    facility = make_facility()
    provider_digest = tree_digest(provider)

    plan = FrequencyPlan.model_validate_json(json.dumps({
        "id": "vertical-vent-campaign",
        "assets": [{
            "id": "terminal-valve",
            "model_component_id": "terminal_pipe",
            "profile": "LH2_VALVE",
            "classification_basis": "synthetic LH2-service vent boundary; not a site frequency claim",
            "physical_scope_ids": ["terminal-vent-1"],
            "nominal_diameter_m": 0.0254,
        }],
    }))
    events = generate_events(facility, plan)
    selected = next(event for event in events if event.loc == "AREA_100%")
    if args.all_area_bins:
        releases = {
            event.id: make_vertical_release(
                backend,
                provider_digest,
                opening_diameter_m=event.release.hole_diameter_m,
                event_id=event.id,
            )
            for event in events
        }
        release = releases[selected.id]
        save("resolved_release_catalog.json", {
            event_id: value.model_dump(mode="json")
            for event_id, value in releases.items()
        })
    else:
        release = make_vertical_release(backend, provider_digest)
        releases = {selected.id: release}
    save("resolved_release.json", release.model_dump(mode="json"))
    base = json.loads(
        (ROOT / "results" / "20261008" / "full_chain" / "gas_release_request.json")
        .read_text(encoding="utf-8")
    )
    def request_for(release_for_event: ResolvedGasRelease) -> dict:
        request = copy.deepcopy(base)
        request.update(
            component_id="terminal_pipe",
            source_input=None,
            resolved_release=release_for_event.model_dump(mode="json"),
            resolved_release_set=None,
            source_operator="integrated_transient",
            available_mass_kg=release_for_event.available_mass_kg,
            source_position_enu_m=[0.0, 0.0, 1.0],
            source_positions_enu_m=None,
            annual_frequency_per_year=None,
            annual_frequency_provenance=None,
            frequency_event=None,
            initiation_intensity_per_s=None,
            release_termination={
                "basis": "synthetic_diagnostic_horizon",
                "time_s": release_for_event.duration_s,
                "provenance": "synthetic vertical provider history; no flow extrapolation",
            },
            evaluation_times_s=[0.0, 0.1, 0.2, 0.37, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0],
        )
        return request
    population = [{
        "receptor_id": receptor.id,
        "persons": 20.0 if index == 0 else 10.0,
        "presence_probability": 0.5,
        "provenance": "synthetic disjoint outdoor groups; not field population",
    } for index, receptor in enumerate(facility.receptors)]
    conditions = []
    for condition_id, probability, speed in [("D-3ms-west", 0.4, 3.0), ("D-4ms-west", 0.6, 4.0)]:
        weather = copy.deepcopy(base["weather"])
        weather["wind_speed_m_s"] = speed
        conditions.append({
            "id": condition_id, "annual_probability": probability,
            "weather": weather, "population": population,
            "provenance": "synthetic annual condition partition; no site weather qualification",
        })
    routes = []
    for event in events:
        if args.all_area_bins or event.id == selected.id:
            routes.append({
                "event_id": event.id,
                "branches": [{
                    "id": "provider-vertical-handoff",
                    "probability_given_event": 1.0,
                    "provenance": "provider vertical exit plus declared horizontal handoff",
                    "request": request_for(releases[event.id]),
                }],
            })
        else:
            routes.append({
                "event_id": event.id,
                "branches": [{
                    "id": "pending-vertical-area-bin",
                    "probability_given_event": 1.0,
                    "provenance": "explicitly outside this vertical handoff diagnostic",
                    "uncomputed_reason": "only AREA_100% was assigned a provider vertical handoff in this diagnostic",
                }],
            })
    campaign = RiskCampaign.model_validate_json(json.dumps({
        "id": "vertical-vent-campaign",
        "frequency_plan": plan.model_dump(mode="json"),
        "annual_conditions": conditions,
        "event_routes": routes,
        "scope_provenance": "synthetic vertical provider handoff through SLABx-LH2/SLABx and native TNO IR/F-N; handoff physics remains operator-limited",
    }))
    save("facility.json", facility.model_dump(mode="json"))
    save("frequency_plan.json", plan.model_dump(mode="json"))
    save("campaign.json", campaign.model_dump(mode="json"))
    save("backend_config.json", config.model_dump(mode="json"))
    result = ResearchPipeline(facility, backend).facility_risk(campaign)
    save("campaign_result.json", result)
    executed = [case for case in result["cases"] if case["status"].startswith("EXECUTED")]
    save("verification.json", {
        "status": result["status"],
        "generated_events": len(events),
        "executed_cases": len(executed),
        "provider_vertical_handoff_consumed": True,
        "provider_source_digest": provider_digest,
        "provider_result_digest": canonical_digest(release.model_dump(mode="json")),
        "mass_residual_max_kg": max(abs(case["mass_ledger"]["end_to_end_residual_kg"]) for case in executed),
        "operator_limited": all(case["status"] == "EXECUTED_OPERATOR_LIMITED" for case in executed),
        "facility_total_risk_withheld": result["total_facility_annual_ir_low_high"] is None,
        "physical_validation_claim": False,
        "timing": result["timing"],
        "limitations": [
            "synthetic variable-state vertical release history and horizontal handoff",
            "vertical free-jet and handoff state are not independently validated",
            "all generated area bins use separate provider calculations" if args.all_area_bins else
            "only AREA_100% route is executed; other area bins remain explicit UNCOMPUTED cases",
        ],
    })
    print(json.dumps({
        "status": result["status"],
        "event_id": selected.id,
        "executed_cases": len(executed),
        "uncomputed_cases": len(result["uncomputed_cases"]),
        "facility_total_risk_available": result["total_facility_annual_ir_low_high"] is not None,
        "timing": result["timing"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
