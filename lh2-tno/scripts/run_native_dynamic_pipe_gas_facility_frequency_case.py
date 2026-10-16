"""Run one native external gas or liquid packet through the facility risk ledger.

Gas packets must already contain the provider-resolved compressible plane;
liquid/two-phase packets carry the provider-resolved liquid boundary and use a
declared pool-footprint sensitivity.  The runner binds the exact opening to
one literature frequency event, evaluates the declared outdoor
weather/population conditions with the normal PRISM campaign engine, and
writes a conditional facility IR/F-N assessment.  Unmatched opening bins
remain explicit ``UNCOMPUTED`` cases.  Provider qualification, independent
physical validation, and the complete-facility QRA gate remain closed for
synthetic or operator-limited evidence.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import time
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.facility_assessment import build_facility_assessment  # noqa: E402
from lh2_tno.frequency import FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.equipment_boundary import ResolvedLiquidRelease  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    build_consequence_request_from_provider_release,
    load_provider_release,
)
from lh2_tno.uncertainty import LiteratureFrequencyScenario  # noqa: E402


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{path} must contain an array of objects")
    return value


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _request_defaults(
    context: dict[str, Any],
    packet: Any,
) -> dict[str, Any]:
    defaults = copy.deepcopy(context)
    for key in (
        "component_id",
        "available_mass_kg",
        "source_position_enu_m",
        "source_positions_enu_m",
        "source_input",
        "resolved_release",
        "resolved_release_set",
        "resolved_liquid_release",
        "annual_frequency_per_year",
        "annual_frequency_provenance",
        "frequency_event",
        "initiation_intensity_per_s",
    ):
        defaults.pop(key, None)
    is_liquid = isinstance(packet, ResolvedLiquidRelease)
    defaults["source_operator"] = "equipment_liquid_release" if is_liquid else "integrated_transient"
    defaults["source_duration_mode"] = "declared"
    defaults["release_termination"] = {
        "basis": "reviewed_isolation_success",
        "time_s": "provider_duration",
        "provenance": (
            "native external provider packet; provider isolation clock retained "
            "for facility campaign diagnostic"
        ),
    }
    if is_liquid:
        integrated_mass = float(packet.integrated_mass_kg)
        pool_radius = (
            0.0001 if integrated_mass < 1.0e-4
            else 0.005 if integrated_mass < 0.1
            else 0.05
        )
        pool_fluid = packet.property_basis.fluid
        translation = "none"
        provenance = None
        if pool_fluid == "ParaHydrogen":
            pool_fluid = "Hydrogen"
            translation = "para_hydrogen_to_hydrogen"
            provenance = (
                "explicit provider ParaHydrogen to native DynamicLH2PoolX Hydrogen "
                "compatibility boundary; synthetic diagnostic"
            )
        defaults["pool"] = {
            "footprint_origin": "declared_sensitivity",
            "fluid": pool_fluid,
            "fluid_translation": translation,
            "translation_provenance": provenance,
            "radius_m": pool_radius,
            "conductivity_w_mk": 0.6,
            "diffusivity_m2_s": 1.5e-7,
            "initial_temperature_k": packet.ambient_temperature_k,
            "domain_radius_m": max(0.005, 5.0 * pool_radius) if pool_radius < 0.001 else max(0.25, 5.0 * pool_radius),
            "radial_step_m": pool_radius / 20.0,
            "maximum_time_step_s": 0.01,
        }
    return defaults


def _default_scenarios(asset_id: str) -> tuple[LiteratureFrequencyScenario, ...]:
    return tuple(
        LiteratureFrequencyScenario(
            id=identifier,
            asset_quantiles={asset_id: quantile},
            provenance=provenance,
        )
        for identifier, quantile, provenance in (
            (
                "native-provider-published-central",
                "published",
                "published LH2 equipment catalogue central rate; diagnostic only",
            ),
            (
                "native-provider-literature-low",
                "p05",
                "published marginal p05 LH2 equipment rate; diagnostic sensitivity only",
            ),
            (
                "native-provider-literature-high",
                "p95",
                "published marginal p95 LH2 equipment rate; diagnostic sensitivity only",
            ),
        )
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    packet = load_provider_release(args.packet)
    is_liquid = isinstance(packet, ResolvedLiquidRelease)
    if not is_liquid and packet.compressible_plane_handoff is None:
        raise ValueError(
            "the selected gas packet must contain compressible_plane_handoff"
        )
    context = _object(args.request_context)
    manifest = EquipmentManifest.from_json(args.manifest)
    facility = manifest.to_facility()
    if packet.component_id not in {component.id for component in facility.components}:
        raise ValueError("facility manifest does not contain the provider component")
    plan = FrequencyPlan.model_validate_json(
        args.frequency_plan.read_text(encoding="utf-8")
    )
    events = generate_events(facility, plan)
    matching = [
        event
        for event in events
        if event.model_component_id == packet.component_id
        and event.release.mode == "hole"
        and event.release.hole_diameter_m is not None
        and math.isclose(
            event.release.hole_diameter_m,
            packet.failure_opening_diameter_m,
            rel_tol=1.0e-10,
            abs_tol=1.0e-12,
        )
    ]
    if len(matching) != 1:
        raise ValueError(
            "frequency plan must produce exactly one event matching the provider opening; "
            f"found {len(matching)}"
        )
    bound_event = matching[0]
    request = build_consequence_request_from_provider_release(
        packet, _request_defaults(context, packet)
    )
    branch = {
        "id": "native-provider-liquid-packet" if is_liquid else "native-provider-gas-packet",
        "probability_given_event": 1.0,
        "provenance": (
            (
                "native external liquid/two-phase history with declared pool sensitivity; "
                "exact opening match; diagnostic only"
                if is_liquid
                else "native external gas history with provider-resolved compressible "
                "plane; exact opening match; diagnostic only"
            )
        ),
        "request": request.model_dump(mode="json"),
    }
    routes = []
    for event in events:
        if event.id == bound_event.id:
            routes.append({"event_id": event.id, "branches": [branch]})
        else:
            routes.append(
                {
                    "event_id": event.id,
                    "branches": [
                        {
                            "id": "uncomputed-opening-bin",
                            "probability_given_event": 1.0,
                            "provenance": (
                                "native external packet covers only the exact provider opening; "
                                "other catalogue bins remain uncomputed"
                            ),
                            "uncomputed_reason": (
                                "no native external packet for this opening bin"
                            ),
                        }
                    ],
                }
            )
    conditions = _array(args.annual_conditions)
    campaign_raw = {
        "id": "native-provider-facility-frequency-campaign",
        "frequency_plan": plan.model_dump(mode="json"),
        "annual_conditions": conditions,
        "event_routes": routes,
        "scope_provenance": (
            "one native external packet bound to one literature frequency "
            "opening; declared outdoor weather/population conditions; other bins withheld"
        ),
        "maximum_physics_cases": args.maximum_physics_cases,
    }
    campaign = RiskCampaign.model_validate_json(
        json.dumps(campaign_raw, ensure_ascii=False, allow_nan=False)
    )
    config_raw = _object(args.backend_config)
    for pin in config_raw.get("packages", []):
        if isinstance(pin, dict) and isinstance(pin.get("root"), str):
            pin["sha256"] = tree_digest(Path(pin["root"]))
    config = BackendConfig.model_validate_json(
        json.dumps(config_raw, ensure_ascii=False, allow_nan=False)
    )
    started = time.perf_counter()
    result = ResearchPipeline(facility, IsolatedBackend(config)).facility_risk(campaign)
    campaign_elapsed_ms = (time.perf_counter() - started) * 1000.0
    assessment = build_facility_assessment(
        [result],
        expected_component_ids=(packet.component_id,),
        frequency_scenarios=_default_scenarios(bound_event.asset_id),
    )
    result_events = result.get("events", [])
    result_cases = result.get("cases", [])
    withheld_cases = result.get("uncomputed_cases", [])
    actual_uncomputed_case_count = sum(
        1 for case in withheld_cases if str(case.get("status", "")) == "UNCOMPUTED"
    )
    operator_limited_case_count = sum(
        1
        for case in withheld_cases
        if str(case.get("status", "")).startswith("EXECUTED_OPERATOR_LIMITED")
    )
    executed_cases = [
        case for case in result_cases if str(case.get("status", "")).startswith("EXECUTED")
    ]
    verification = {
        "schema_version": "prism.native_provider_facility_frequency_case.v1",
        "status": "NATIVE_PROVIDER_PACKET_FACILITY_CAMPAIGN_EXECUTED_DIAGNOSTIC",
        "campaign_status": result.get("status"),
        "facility_assessment_status": assessment.get("status"),
        "facility_id": facility.id,
        "component_id": packet.component_id,
        "provider_packet_event_id": packet.event_id,
        "campaign_frequency_event_id": bound_event.id,
        "provider_event_id_rebound": packet.event_id != bound_event.id,
        "provider_source_digest": packet.provider_source_digest,
        "provider_result_digest": packet.provider_result_digest,
        "provider_termination_basis": packet.termination_basis,
        "provider_duration_s": packet.duration_s,
        "provider_mass_residual_kg": packet.cumulative_mass_out_kg - packet.integrated_mass_kg,
        "release_kind": "liquid" if is_liquid else "gas",
        "compressible_plane_handoff_consumed": not is_liquid,
        "exact_opening_match": math.isclose(
            packet.failure_opening_diameter_m,
            bound_event.release.hole_diameter_m,
            rel_tol=1.0e-10,
            abs_tol=1.0e-12,
        ),
        "literature_frequency_applied": True,
        "frequency_source": bound_event.source,
        "frequency_annual_central_per_year": bound_event.annual_frequency_per_year,
        "frequency_p05_per_year": bound_event.marginal_p05_per_year,
        "frequency_p95_per_year": bound_event.marginal_p95_per_year,
        "frequency_from_provider_packet": False,
        "event_count": len(result_events),
        "case_count": len(result_cases),
        "executed_case_count": len(executed_cases),
        "uncomputed_case_count": actual_uncomputed_case_count,
        "operator_limited_case_count": operator_limited_case_count,
        "withheld_case_count": len(withheld_cases),
        "risk_atom_count": len(result.get("risk_atoms", [])),
        "conditional_diagnostic_facility_risk_available": assessment.get(
            "conditional_diagnostic_facility_risk_available"
        ),
        "conditional_diagnostic_facility_annual_ir_low_high": assessment.get(
            "conditional_diagnostic_facility_annual_ir_low_high"
        ),
        "conditional_diagnostic_facility_expected_death_fn_low_high": assessment.get(
            "conditional_diagnostic_facility_expected_death_fn_low_high"
        ),
        "frequency_scenario_count": len(assessment.get("frequency_uncertainty", {}).get("scenarios", [])),
        "facility_total_risk_available": assessment.get("facility_total_risk_available"),
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "provider_packet_promoted": False,
        "campaign_elapsed_ms": campaign_elapsed_ms,
        "fresh_physics_executed": assessment.get("fresh_physics_executed"),
        "limitations": [
            "provider packet, geometry, weather and population remain synthetic or diagnostic",
            "provider event identity is explicitly mapped to the matching frequency event; it is not silently rewritten",
            "unmatched opening bins remain UNCOMPUTED",
            (
                "declared liquid pool footprint and liquid/near-field provider boundary are not "
                "independent physical validation"
                if is_liquid
                else "operator-limited compressible-plane handoff is not independent physical validation"
            ),
            "literature frequency uncertainty is a conditional reweighting of saved atoms, not a facility credible interval",
            "facility IR/F-N promotion remains closed until qualified provider, complete scope and validation gates pass",
        ],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _save(args.output_dir / "facility.json", facility.model_dump(mode="json"))
    _save(args.output_dir / "frequency_plan.json", plan.model_dump(mode="json"))
    _save(args.output_dir / "campaign.json", campaign.model_dump(mode="json"))
    _save(args.output_dir / "campaign_result.json", result)
    _save(args.output_dir / "facility_assessment.json", assessment)
    _save(args.output_dir / "verification.json", verification)
    _save(
        args.output_dir / "binding_provenance.json",
        {
            "schema_version": "prism.native_provider_frequency_event_binding.v1",
            "provider_packet_digest": canonical_digest(packet.model_dump(mode="json")),
            "provider_event_id": packet.event_id,
            "frequency_event_id": bound_event.id,
            "component_id": packet.component_id,
            "opening_match": verification["exact_opening_match"],
            "frequency_from_provider_packet": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "release_kind": "liquid" if is_liquid else "gas",
            "interpretation": (
                "The native packet is consumed as the release history. The catalogue event "
                "supplies the initiating frequency after an explicit opening match; event-ID "
                "mapping is retained rather than mutating the provider packet."
            ),
        },
    )
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--request-context", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--annual-conditions", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--maximum-physics-cases", type=int, default=20)
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ImportError, TypeError, ValueError) as error:
        raise SystemExit(f"native provider facility campaign failed: {error}") from error
    print(
        json.dumps(
            {
                "status": result["status"],
                "campaign_status": result["campaign_status"],
                "facility_assessment_status": result["facility_assessment_status"],
                "exact_opening_match": result["exact_opening_match"],
                "executed_case_count": result["executed_case_count"],
                "uncomputed_case_count": result["uncomputed_case_count"],
                "risk_atom_count": result["risk_atom_count"],
                "conditional_diagnostic_facility_risk_available": result[
                    "conditional_diagnostic_facility_risk_available"
                ],
                "facility_total_risk_available": result["facility_total_risk_available"],
                "output": str(args.output_dir.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
