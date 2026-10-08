"""Bind a LayeredTank/SLABx liquid history to reviewed LH2 frequencies.

The provider history is already resolved through SLABx-LH2.  This script
creates a deliberately small outdoor facility campaign around that history,
binds only the published LH2_VESSEL area bin whose physical opening matches,
and records the other bins as explicit uncomputed cases.  Frequency
uncertainty reweights the executed risk atoms and never reruns physics.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest
from lh2_tno.campaign import RiskCampaign
from lh2_tno.contracts import Facility
from lh2_tno.frequency import FrequencyPlan, generate_events
from lh2_tno.pipeline import ResearchPipeline
from lh2_tno.uncertainty import (
    LiteratureFrequencyDistributionScenario,
    LiteratureFrequencyScenario,
    literature_frequency_uncertainty,
    sample_literature_frequency_distributions,
)


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def build_frequency_plan(facility: Facility) -> FrequencyPlan:
    """Use one reviewed vessel exposure and exclude every other component."""

    excluded = {
        component.id: (
            "LayeredTank frequency campaign only resolves the storage vessel; "
            "no provider-resolved accident history was supplied for this component"
        )
        for component in facility.components
        if component.id != "storage"
    }
    return FrequencyPlan.model_validate_json(
        json.dumps({
            "id": "layered-tank-literature-frequency",
            "assets": [
                {
                    "id": "storage-vessel",
                    "model_component_id": "storage",
                    "profile": "LH2_VESSEL",
                    "physical_scope_ids": ["storage-vessel-shell"],
                    "classification_basis": (
                        "synthetic outdoor storage vessel campaign; 0.1 m is the reviewed "
                        "reference flow diameter for the selected literature bin"
                    ),
                    "nominal_diameter_m": 0.1,
                }
            ],
            "excluded_model_components": excluded,
        })
    )


def build_annual_conditions(facility: Facility, base_request: dict) -> list[dict]:
    population = [
        {
            "receptor_id": receptor.id,
            "persons": 20.0 if index == 0 else 10.0,
            "presence_probability": 0.5,
            "provenance": "synthetic disjoint outdoor groups at representative receptors",
        }
        for index, receptor in enumerate(facility.receptors)
    ]
    base_weather = base_request["weather"]
    return [
        {
            "id": "D-3ms-west",
            "annual_probability": 0.4,
            "weather": {**base_weather, "wind_speed_m_s": 3.0},
            "population": population,
            "provenance": "synthetic joint annual wind/population partition; no site weather qualification",
        },
        {
            "id": "D-4ms-west",
            "annual_probability": 0.6,
            "weather": {**base_weather, "wind_speed_m_s": 4.0},
            "population": population,
            "provenance": "synthetic joint annual wind/population partition; no site weather qualification",
        },
    ]


def build_event_routes(
    facility: Facility, plan: FrequencyPlan, base_request: dict
) -> tuple[list[dict], dict]:
    events = generate_events(facility, plan)
    provider_release = base_request["resolved_liquid_release"]
    provider_diameter = provider_release["failure_opening_diameter_m"]
    routes = []
    matching = []
    for event in events:
        if math.isclose(
            event.release.hole_diameter_m,
            provider_diameter,
            rel_tol=1e-10,
            abs_tol=1e-12,
        ):
            matching.append(event.id)
            request = copy.deepcopy(base_request)
            request.update(
                annual_frequency_per_year=None,
                annual_frequency_provenance=None,
                frequency_event=None,
                initiation_intensity_per_s=None,
            )
            branch = {
                "id": "provider-resolved-liquid-history",
                "probability_given_event": 1.0,
                "provenance": (
                    "LayeredTank state feedback plus SLABx-LH2 resolved liquid history; "
                    "operator-limited diagnostic"
                ),
                "request": request,
            }
        else:
            branch = {
                "id": "uncomputed-opening-mismatch",
                "probability_given_event": 1.0,
                "provenance": "explicitly uncomputed; no frequency interpolation or size substitution",
                "uncomputed_reason": (
                    f"provider opening {provider_diameter:.12g} m does not match "
                    f"catalogue opening {event.release.hole_diameter_m:.12g} m for {event.loc}; "
                    "a separate provider history is required"
                ),
            }
        routes.append({"event_id": event.id, "branches": [branch]})
    return routes, {"provider_failure_opening_diameter_m": provider_diameter, "matching_event_ids": matching}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider-dir",
        type=Path,
        required=True,
        help="directory produced by validate_layered_tank_inventory_slabsx.py",
    )
    parser.add_argument(
        "--backend-config",
        type=Path,
        default=ROOT / "results" / "20261009" / "backend_config_current.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results" / "20261009" / "layered_tank_frequency_campaign",
    )
    parser.add_argument("--distribution-draws", type=int, default=250)
    parser.add_argument(
        "--allow-pin-refresh",
        action="store_true",
        help="refresh stale source-tree pins and record the observed digests",
    )
    args = parser.parse_args()
    if args.distribution_draws < 100:
        raise ValueError("distribution-draws must be at least 100")

    out = args.output_dir
    provider_dir = args.provider_dir
    facility = Facility.model_validate_json(
        (ROOT / "examples" / "consequence_facility.json").read_text(encoding="utf-8")
    )
    base_request = json.loads((provider_dir / "request.json").read_text(encoding="utf-8"))
    plan = build_frequency_plan(facility)
    routes, matching = build_event_routes(facility, plan, base_request)
    campaign = RiskCampaign.model_validate_json(
        json.dumps({
            "id": "layered-tank-literature-frequency-campaign",
            "frequency_plan": plan.model_dump(mode="json"),
            "annual_conditions": build_annual_conditions(facility, base_request),
            "event_routes": routes,
            "scope_provenance": (
                "synthetic outdoor facility campaign using one LayeredTank/SLABx provider history; "
                "only the exact published LH2_VESSEL area bin is bound"
            ),
        })
    )
    config_raw = json.loads(args.backend_config.read_text(encoding="utf-8"))
    pin_refresh = []
    if args.allow_pin_refresh:
        for pin in config_raw["packages"]:
            observed = tree_digest(Path(pin["root"]))
            if observed != pin["sha256"]:
                pin_refresh.append(
                    {"name": pin["name"], "declared": pin["sha256"], "observed": observed}
                )
            pin["sha256"] = observed
    config = BackendConfig.model_validate_json(json.dumps(config_raw))
    started = time.perf_counter()
    result = ResearchPipeline(facility, IsolatedBackend(config)).facility_risk(campaign)
    result["layered_tank_provider_match"] = matching
    result["physical_validation_claim"] = False
    frequency_bounds = literature_frequency_uncertainty(
        result,
        (
            LiteratureFrequencyScenario(
                id="within-asset-p05",
                asset_quantiles={"storage-vessel": "p05"},
                provenance="published LH2_VESSEL p05 marginal bounds; shared within-asset direction",
            ),
            LiteratureFrequencyScenario(
                id="within-asset-published",
                asset_quantiles={"storage-vessel": "published"},
                provenance="published LH2_VESSEL median frequency",
            ),
            LiteratureFrequencyScenario(
                id="within-asset-p95",
                asset_quantiles={"storage-vessel": "p95"},
                provenance="published LH2_VESSEL p95 marginal bounds; shared within-asset direction",
            ),
        ),
    )
    events = generate_events(facility, plan)
    event_quantiles = {event.id: "p95" for event in events}
    frequency_bounds["scenarios"].append(
        literature_frequency_uncertainty(
            result,
            (
                LiteratureFrequencyScenario(
                    id="independent-event-p95",
                    event_quantiles=event_quantiles,
                    provenance="published event-wise p95 comparison for all generated area bins",
                    correlation_assumption="independent_event_bounds",
                ),
            ),
        )["scenarios"][0]
    )
    distribution = sample_literature_frequency_distributions(
        result,
        (
            LiteratureFrequencyDistributionScenario(
                id="within-asset-shared-normal",
                provenance="published LH2_VESSEL lognormal draws with one shared normal per asset",
                correlation_assumption="within_asset_shared_normal",
            ),
        ),
        draws=args.distribution_draws,
        seed=20261009,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    save(out / "facility.json", facility.model_dump(mode="json"))
    save(out / "frequency_plan.json", plan.model_dump(mode="json"))
    save(out / "campaign.json", campaign.model_dump(mode="json"))
    save(out / "campaign_result.json", result)
    save(out / "backend_config.json", config.model_dump(mode="json"))
    save(out / "frequency_uncertainty.json", frequency_bounds)
    save(out / "frequency_distribution.json", distribution)
    save(
        out / "verification.json",
        {
            "status": result["status"],
            "matching_event_ids": matching["matching_event_ids"],
            "generated_event_count": len(result["events"]),
            "executed_case_count": sum(
                case["status"].startswith("EXECUTED") for case in result["cases"]
            ),
            "operator_limited_case_count": sum(
                case["status"] == "EXECUTED_OPERATOR_LIMITED" for case in result["cases"]
            ),
            "uncomputed_case_count": len(result["uncomputed_cases"]),
            "total_facility_risk_withheld": result["total_facility_annual_ir_low_high"] is None,
            "frequency_uncertainty_reweighted_without_physics": frequency_bounds["fresh_physics_executed"] is False,
            "frequency_distribution_reweighted_without_physics": distribution["fresh_physics_executed"] is False,
            "provider_failure_opening_diameter_m": matching["provider_failure_opening_diameter_m"],
            "provider_frequency_size_match": len(matching["matching_event_ids"]) == 1,
            "elapsed_ms": elapsed_ms,
            "physical_validation_claim": False,
            "pin_refresh": pin_refresh,
        },
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "matching_event_ids": matching["matching_event_ids"],
                "executed_case_count": sum(case["status"].startswith("EXECUTED") for case in result["cases"]),
                "uncomputed_case_count": len(result["uncomputed_cases"]),
                "total_facility_risk_withheld": result["total_facility_annual_ir_low_high"] is None,
                "elapsed_ms": elapsed_ms,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
