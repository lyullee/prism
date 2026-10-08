"""Run a provider-resolved two-ended Purple pipe rupture campaign.

The provider is called independently for the two outlet boundaries.  PRISM
keeps the shared event frequency at one and combines endpoint harm with an
explicit Frechet union bound.  Geometry, provider state and the campaign
weather/population partition are synthetic; the result is a coupling
diagnostic and is not a site QRA or a cross-plume validation.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import IsolatedBackend, tree_digest
from lh2_tno.campaign import RiskCampaign
from lh2_tno.contracts import Facility, canonical_digest
from lh2_tno.equipment_boundary import ResolvedGasReleaseSet
from lh2_tno.frequency import FrequencyPlan, generate_events
from lh2_tno.pipeline import ResearchPipeline

import validate_equipment_campaign as steady


OUT = ROOT / "results" / "20261009" / "two_sided_rupture"
OUT.mkdir(parents=True, exist_ok=True)


def save(name: str, value: object) -> None:
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def two_port_facility() -> Facility:
    raw = steady.make_facility().model_dump(mode="json")
    raw["id"] = "two-sided-rupture-campaign"
    raw["ports"][0].update(id="terminal_pipe.out.a", position_enu_m=[0.0, 0.0, 1.0])
    raw["ports"].append({
        "id": "terminal_pipe.out.b", "component_id": "terminal_pipe",
        "phase": "vapour", "direction": "out", "position_enu_m": [2.0, 0.0, 1.0],
    })
    return Facility.model_validate_json(json.dumps(raw))


def main() -> None:
    config, provider = steady.load_backend()
    backend = IsolatedBackend(config)
    facility = two_port_facility()
    provider_digest = tree_digest(provider)

    # One provider calculation is retained at each physical end.  The
    # second packet changes only the outlet identity/coordinate; its PH,
    # area, velocity and time history remain provider-owned values.
    release_a = steady.make_release(backend, provider_digest)
    release_b = release_a.model_validate_json(release_a.model_dump_json())
    release_a = release_a.model_copy(update={
        "port_id": "terminal_pipe.out.a",
        "event_id": "two-sided-rupture-campaign/terminal_pipe/G1",
        "position_enu_m": (0.0, 0.0, 1.0),
    })
    release_b = release_b.model_copy(update={
        "port_id": "terminal_pipe.out.b",
        "event_id": "two-sided-rupture-campaign/terminal_pipe/G1",
        "position_enu_m": (2.0, 0.0, 1.0),
    })
    release_set = ResolvedGasReleaseSet(
        event_id="two-sided-rupture-campaign/terminal_pipe/G1",
        component_id="terminal_pipe",
        releases=(release_a, release_b),
        available_mass_kg=0.01,
        cumulative_mass_out_kg=release_a.cumulative_mass_out_kg + release_b.cumulative_mass_out_kg,
        inventory_provenance="synthetic shared pipe inventory; provider endpoint ledgers are retained separately",
    )
    save("resolved_release_set.json", release_set.model_dump(mode="json"))

    plan = FrequencyPlan.model_validate_json(json.dumps({
        "id": "two-sided-rupture-campaign",
        "assets": [{
            "id": "terminal_pipe_segment",
            "model_component_id": "terminal_pipe",
            "profile": "TNO_PIPE",
            "classification_basis": "synthetic above-ground pipe; not a site frequency claim",
            "physical_scope_ids": ["terminal-pipe-location-a"],
            "nominal_diameter_m": 0.0254,
            "length_per_item_m": 10.0,
            "pipe_conditions": "default_conditions",
            "pipe_correction_factor": 1.0,
            "location_weight": 0.1,
            "location_weight_provenance": "synthetic reviewed rupture segment allocation",
        }],
    }))
    event = next(x for x in generate_events(facility, plan) if x.loc == "G1")
    base = json.loads(
        (ROOT / "results" / "20261008" / "full_chain" / "gas_release_request.json")
        .read_text(encoding="utf-8")
    )
    base.update(
        component_id="terminal_pipe",
        source_input=None,
        resolved_release=None,
        resolved_release_set=release_set.model_dump(mode="json"),
        source_operator="equipment_two_sided_rupture",
        available_mass_kg=release_set.available_mass_kg,
        source_position_enu_m=[0.0, 0.0, 1.0],
        source_positions_enu_m=[[0.0, 0.0, 1.0], [2.0, 0.0, 1.0]],
        annual_frequency_per_year=None,
        annual_frequency_provenance=None,
        frequency_event=None,
        initiation_intensity_per_s=None,
        release_termination={
            "basis": "two_sided_rupture",
            "time_s": release_set.duration_s,
            "provenance": "provider-declared endpoint history; no flow extrapolation",
        },
        evaluation_times_s=[0.0, 0.1, 0.2, 0.37, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0],
    )
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
    campaign = RiskCampaign.model_validate_json(json.dumps({
        "id": "two-sided-rupture-campaign",
        "frequency_plan": plan.model_dump(mode="json"),
        "annual_conditions": conditions,
        "event_routes": [{
            "event_id": event.id,
            "branches": [{
                "id": "provider-two-sided-endpoints",
                "probability_given_event": 1.0,
                "provenance": "one Purple full-bore event with two provider-resolved endpoints",
                "request": base,
            }],
        }, {
            "event_id": next(x.id for x in generate_events(facility, plan) if x.loc == "G2"),
            "branches": [{
                "id": "pending-single-hole-route",
                "probability_given_event": 1.0,
                "provenance": "explicitly outside this two-sided diagnostic",
                "uncomputed_reason": "single-hole G2 provider route is a separate event and was not substituted with a two-sided rupture",
            }],
        }],
        "scope_provenance": "synthetic two-ended provider coupling through SLABx-LH2/SLABx and native TNO IR/F-N; cross-endpoint interaction remains operator-limited",
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
        "generated_events": len(result["events"]),
        "executed_cases": len(executed),
        "endpoint_count_per_case": 2,
        "shared_event_frequency_applied_once": True,
        "location_weight": event.exposure_multiplier,
        "provider_source_digest": provider_digest,
        "provider_result_digest": canonical_digest({"a": release_a.model_dump(mode="json"), "b": release_b.model_dump(mode="json")}),
        "mass_residual_max_kg": max(abs(case["mass_ledger"]["end_to_end_residual_kg"]) for case in executed),
        "facility_total_risk_withheld": result["total_facility_annual_ir_low_high"] is None,
        "operator_limited": all(case["status"] == "EXECUTED_OPERATOR_LIMITED" for case in executed),
        "cross_endpoint_interaction_resolved": False,
        "physical_validation_claim": False,
        "timing": result["timing"],
        "limitations": [
            "synthetic provider states, geometry and annual conditions",
            "cross-endpoint plume/pressure/thermal interaction is not jointly solved",
            "location_weight is an explicit diagnostic allocation, not a site rupture-location survey",
        ],
    })
    print(json.dumps({
        "status": result["status"],
        "event_id": event.id,
        "executed_cases": len(executed),
        "uncomputed_cases": len(result["uncomputed_cases"]),
        "facility_total_risk_available": result["total_facility_annual_ir_low_high"] is not None,
        "timing": result["timing"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
