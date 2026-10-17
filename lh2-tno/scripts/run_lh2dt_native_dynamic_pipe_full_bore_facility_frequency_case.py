"""Run a native DynamicHEMPipe full-bore packet through a facility campaign.

The external HEM pipe owns the finite-volume state, atmospheric flash and
inventory ledger.  PRISM validates the returned packet, applies the exact
``LH2_PIPE AREA_100%`` literature frequency, and sends that one event through
the facility risk ledger.  Uncomputed opening bins remain explicit, so this is
conditional campaign evidence and never a qualified facility QRA.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest  # noqa: E402
from lh2_tno.campaign import RiskCampaign  # noqa: E402
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_accident_export import (  # noqa: E402
    AccidentReleaseExportRequest,
    export_equipment_liquid_accident_history,
)
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.frequency import FrequencyPlan, generate_events  # noqa: E402
from lh2_tno.pipeline import ResearchPipeline  # noqa: E402
from lh2_tno.provider_release import build_consequence_request_from_provider_release  # noqa: E402


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


class NativeDynamicPipeProvider:
    def __init__(self, model: Any, parameters: dict[str, Any]) -> None:
        self.model = model
        self.parameters = dict(parameters)

    def export_accident_history(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = dict(request)
        payload.update(self.parameters)
        return dict(self.model.export_accident_history(payload))


def _request(source_digest: str, state_digest: str) -> AccidentReleaseExportRequest:
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": "liquid-transfer-line-01",
        "port_id": "line-accident-out",
        "event_id": "generic-lh2-full-scope-frequency-example/transfer-line/AREA_100%",
        "failure_mode": "explicit_failed_opening",
        # Exact LH2_PIPE AREA_100% catalogue opening.
        "failure_opening_diameter_m": 0.025,
        "horizon_s": 60.0,
        "position_enu_m": [5.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "post_pressure_equalization_observation_s": 0.2,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "native lh2dt DynamicHEMPipe finite full-bore atmospheric accidental outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "lh2dt.dynamic_pipe.DynamicHEMPipe",
        "model_revision": "native-export-3d9b982",
        "state_snapshot_digest": state_digest,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit native DynamicHEMPipe full-bore diagnostic with literature frequency; not site-calibrated",
        "provider_termination_required": True,
    })


def _defaults(request: dict[str, Any]) -> dict[str, Any]:
    defaults = copy.deepcopy(request)
    for key in (
        "component_id", "available_mass_kg", "source_position_enu_m",
        "source_positions_enu_m", "source_input", "resolved_release",
        "resolved_release_set", "resolved_liquid_release",
        "annual_frequency_per_year", "annual_frequency_provenance",
        "frequency_event", "initiation_intensity_per_s",
    ):
        defaults.pop(key, None)
    defaults["release_termination"] = {
        "basis": "provider_declared",
        "time_s": "provider_duration",
        "provenance": "native DynamicHEMPipe finite full-bore pressure-equalization clock",
    }
    defaults["source_operator"] = "equipment_liquid_release"
    defaults["source_duration_mode"] = "model_natural"
    defaults["pool"] = {
        "footprint_origin": "declared_sensitivity",
        "fluid": "Hydrogen",
        "fluid_translation": "none",
        "radius_m": 0.0001,
        "conductivity_w_mk": 0.6,
        "diffusivity_m2_s": 1.5e-7,
        "initial_temperature_k": 288.15,
        "domain_radius_m": 0.005,
        "radial_step_m": 0.000005,
        "maximum_time_step_s": 0.01,
    }
    return defaults


def run(args: argparse.Namespace) -> dict[str, Any]:
    external_root = args.lh2dt_root.resolve()
    sys.path.insert(0, str(external_root / "src"))
    from lh2dt.dynamic_pipe import DynamicHEMPipe
    from lh2dt.properties import HydrogenProperties

    compiled = json.loads(args.compiled_campaign.read_text(encoding="utf-8"))
    event_id = "generic-lh2-full-scope-frequency-example/transfer-line/AREA_100%"
    storage_event_id = "generic-lh2-full-scope-frequency-example/storage-shell/AREA_0.01%"
    routes = compiled.get("event_routes")
    if not isinstance(routes, list):
        raise ValueError("compiled campaign has no event_routes")
    source_route = next((row for row in routes if row.get("event_id") == storage_event_id), None)
    pipe_route = next((row for row in routes if row.get("event_id") == event_id), None)
    if not isinstance(source_route, dict) or not isinstance(pipe_route, dict):
        raise ValueError("compiled campaign lacks storage and transfer-line routes")
    source_branches = [
        row for row in source_route.get("branches", [])
        if isinstance(row, dict) and isinstance(row.get("request"), dict)
    ]
    if not source_branches:
        raise ValueError("storage route must provide at least one request template")
    # The storage route can legitimately contain success and failure branch
    # requests.  This diagnostic needs only a request-shaped consequence
    # template for the independent transfer-line packet; it must not merge,
    # select by probability, or infer a storage failure outcome.  Keep the
    # deterministic first request and record that choice in the provenance
    # below so the branch is auditable and cannot be mistaken for a storage
    # campaign result.
    current_request = source_branches[0]["request"]
    source_branch_template_id = source_branches[0].get("id")

    source_digest = _tree_digest(external_root)
    state_digest = canonical_digest({
        "source": "native-dynamic-pipe-full-bore-facility-frequency-case",
        "pressure_pa_abs": 500000.0,
        "initial_quality": 0.1,
        "length_m": 1.0,
        "inner_diameter_m": 0.025,
    })
    model = DynamicHEMPipe(
        1.0,
        0.025,
        1.0e-6,
        1.0e5,
        ambient_temperature_K=288.15,
        properties=HydrogenProperties("Hydrogen"),
    )
    provider = NativeDynamicPipeProvider(
        model,
        {
            "initial_pressure_pa_abs": 500000.0,
            "initial_temperature_k": 27.0,
            "initial_quality": 0.1,
            "time_step_s": 0.01,
            "post_pressure_equalization_observation_s": 0.2,
            "minimum_step_s": 0.0005,
            "discharge_coefficient": 0.8,
            "impact_position_m": [5.0, 0.0, 1.0],
            "direction_enu": [1.0, 0.0, 0.0],
            "droplet_diameter_m": 1.0e-3,
        },
    )
    started = time.perf_counter()
    adapted = export_equipment_liquid_accident_history(provider, _request(source_digest, state_digest))
    export_elapsed_ms = (time.perf_counter() - started) * 1000.0
    release = adapted.release
    payload = release.model_dump(mode="json")
    payload["position_enu_m"] = [5.0, 0.0, 1.0]
    release = type(release).model_validate_json(json.dumps(payload, allow_nan=False))
    defaults = _defaults(current_request)
    request = build_consequence_request_from_provider_release(release, defaults)
    branch = {
        "id": "native-provider-request",
        "probability_given_event": 1.0,
        "provenance": "native DynamicHEMPipe HEM liquid/two-phase packet; exact LH2_PIPE AREA_100% opening; diagnostic only",
        "request": request.model_dump(mode="json"),
    }
    manifest = EquipmentManifest.from_json(args.manifest)
    campaign_raw = copy.deepcopy(compiled)
    selected_assets = [
        asset for asset in campaign_raw["frequency_plan"].get("assets", [])
        if asset.get("id") == "transfer-line"
    ]
    campaign_raw["frequency_plan"]["assets"] = selected_assets
    # The full compiled catalogue may carry precomputed rows for every
    # equipment family.  Once this diagnostic narrows the selected frequency
    # scope to the transfer line, retain only rows owned by that selected
    # component.  Dropping rows for excluded components is explicit scope
    # filtering; it is not a substitution or a frequency inference.
    selected_component_ids = {
        asset.get("model_component_id")
        for asset in selected_assets
        if isinstance(asset, dict) and isinstance(asset.get("model_component_id"), str)
    }
    frequency_plan = campaign_raw["frequency_plan"]
    precomputed_events = frequency_plan.get("precomputed_events")
    precomputed_event_count_before_scope_filter = (
        len(precomputed_events) if isinstance(precomputed_events, list) else None
    )
    precomputed_event_count_after_scope_filter = precomputed_event_count_before_scope_filter
    if isinstance(precomputed_events, list):
        frequency_plan["precomputed_events"] = [
            event for event in precomputed_events
            if isinstance(event, dict)
            and event.get("model_component_id") in selected_component_ids
        ]
        precomputed_event_count_after_scope_filter = len(frequency_plan["precomputed_events"])
        if not frequency_plan["precomputed_events"]:
            frequency_plan.pop("precomputed_events", None)
            frequency_plan.pop("precomputed_events_provenance", None)
            precomputed_event_count_after_scope_filter = 0
    for asset in campaign_raw["frequency_plan"]["assets"]:
        # LH2_PIPE is a length-based catalogue.  Allocate the 10 m segment to
        # one reviewed outlet so the bound event is not silently assigned to
        # the whole line.
        asset["location_weight"] = 0.1
        asset["location_weight_provenance"] = (
            "single reviewed transfer-line outlet used for native DynamicHEMPipe diagnostic"
        )
    campaign_raw["event_routes"] = [{
        "event_id": event_id,
        "branches": [branch],
    }]
    manifest_raw = json.loads(args.manifest.read_text(encoding="utf-8"))
    known_component_ids = {
        component.get("id")
        for component in manifest_raw.get("components", [])
        if isinstance(component, dict) and isinstance(component.get("id"), str)
    }
    excluded = campaign_raw["frequency_plan"].setdefault("excluded_model_components", {})
    # Remove exclusions inherited from the full-facility catalogue when the
    # supplied diagnostic manifest intentionally contains only one component.
    # An exclusion for a component absent from the live manifest is itself an
    # invalid frequency-plan reference.
    campaign_raw["frequency_plan"]["excluded_model_components"] = {
        component_id: reason
        for component_id, reason in excluded.items()
        if component_id in known_component_ids and component_id not in selected_component_ids
    }
    excluded = campaign_raw["frequency_plan"]["excluded_model_components"]
    for component in manifest_raw.get("components", []):
        component_id = component.get("id")
        if component_id and component_id != "liquid-transfer-line-01":
            excluded.setdefault(
                component_id,
                "excluded from this single native DynamicHEMPipe frequency diagnostic; no packet executed",
            )
    frequency_plan = FrequencyPlan.model_validate_json(
        json.dumps(campaign_raw["frequency_plan"], ensure_ascii=False, allow_nan=False)
    )
    generated_events = generate_events(manifest.to_facility(), frequency_plan)
    campaign_raw["event_routes"] = [
        {"event_id": event_id, "branches": [branch]},
        *[
            {
                "event_id": event.id,
                "branches": [{
                    "id": "uncomputed-native-pipe-scope",
                    "probability_given_event": 1.0,
                    "provenance": "native DynamicHEMPipe diagnostic executes only AREA_100%; no packet for this LOC",
                    "uncomputed_reason": "native DynamicHEMPipe full-bore packet not executed for this opening bin",
                }],
            }
            for event in generated_events
            if event.id != event_id
        ],
    ]
    campaign_raw["scope_provenance"] = (
        "single native DynamicHEMPipe liquid/two-phase LH2_PIPE frequency diagnostic; "
        "synthetic geometry and declared sensitivity pool footprint; "
        f"request template copied from storage route branch {source_branch_template_id!r}; "
        "storage branch outcome is not evaluated or merged"
    )
    campaign = RiskCampaign.model_validate_json(json.dumps(campaign_raw, ensure_ascii=False, allow_nan=False))

    config_raw = json.loads(args.backend_config.read_text(encoding="utf-8"))
    for pin in config_raw.get("packages", []):
        pin["sha256"] = tree_digest(Path(pin["root"]))
    config = BackendConfig.model_validate_json(json.dumps(config_raw, ensure_ascii=False, allow_nan=False))
    chain_started = time.perf_counter()
    result = ResearchPipeline(manifest.to_facility(), IsolatedBackend(config)).facility_risk(campaign)
    chain_elapsed_ms = (time.perf_counter() - chain_started) * 1000.0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _save(args.output_dir / "provider_response.json", adapted.provider_response)
    _save(args.output_dir / "resolved_release.json", release.model_dump(mode="json"))
    _save(args.output_dir / "campaign.json", campaign.model_dump(mode="json"))
    _save(args.output_dir / "campaign_result.json", result)
    provider_meta = adapted.provider_response.get("data", {}).get("provider_meta", {})
    bound_event = next(
        (event for event in result.get("events", []) if event.get("id") == event_id),
        {},
    )
    final_pressure = provider_meta.get("final_pressure_pa_abs")
    pressure_equalized = provider_meta.get("pressure_equalized")
    pressure_matches_ambient = (
        isinstance(final_pressure, (int, float))
        and math.isclose(float(final_pressure), 101325.0, rel_tol=0.0, abs_tol=1.0e-3)
    )
    campaign_cases = result.get("cases", [])
    executed_campaign_cases = [
        case for case in campaign_cases
        if str(case.get("status", "")).startswith("EXECUTED")
    ]
    uncomputed_campaign_cases = [
        case for case in campaign_cases
        if str(case.get("status", "")) == "UNCOMPUTED"
    ]
    verification = {
        "schema_version": "prism.native_lh2dt_dynamic_pipe_full_bore_facility_frequency_case.v1",
        "status": result.get("status"),
        "event_id": event_id,
        "component_id": release.component_id,
        "catalogue_opening_diameter_m": 0.025,
        "provider_opening_diameter_m": release.failure_opening_diameter_m,
        "exact_opening_match": release.failure_opening_diameter_m == 0.025,
        "full_bore_match": release.failure_opening_diameter_m == 0.025,
        "phase_basis": release.phase_basis,
        "provider_source_digest": release.provider_source_digest,
        "provider_result_digest": adapted.provider_result_digest,
        "provider_duration_s": release.duration_s,
        "provider_mass_residual_kg": release.cumulative_mass_out_kg - release.integrated_mass_kg,
        "provider_termination_basis": release.termination_basis,
        "provider_final_pressure_pa_abs": final_pressure,
        "provider_pressure_equalized": pressure_equalized,
        "provider_final_pressure_matches_ambient": pressure_matches_ambient,
        "pressure_equalization_time_s": provider_meta.get("pressure_equalization_time_s"),
        "post_pressure_equalization_observation_s": provider_meta.get(
            "post_pressure_equalization_observation_s"
        ),
        "pressure_equalization_success": provider_meta.get("pressure_equalization_success"),
        "terminal_source_pressure_pa_abs": provider_meta.get(
            "terminal_source_pressure_pa_abs"
        ),
        "ambient_pressure_pa_abs": provider_meta.get("ambient_pressure_pa_abs"),
        "max_post_pressure_equalization_flow_kg_s": provider_meta.get(
            "max_post_pressure_equalization_flow_kg_s"
        ),
        "provider_energy_residual_j": release.cumulative_specific_enthalpy_out_j - release.integrated_specific_enthalpy_out_j,
        "literature_frequency_bound": True,
        "frequency_source": "compiled campaign LH2_PIPE AREA_100% literature row",
        "frequency_from_provider_packet": False,
        "frequency_event_id": event_id,
        "annual_frequency_per_year": bound_event.get("annual_frequency_per_year"),
        "annual_frequency_provenance": (
            f"{event_id}; {bound_event.get('source')}; {bound_event.get('source_sha256')}"
            if bound_event.get("source") and bound_event.get("source_sha256")
            else None
        ),
        "frequency_applied": True,
        "frequency_exact_opening_match": release.failure_opening_diameter_m == 0.025,
        "request_template_source_branch_id": source_branch_template_id,
        "frequency_scope_filtering": {
            "selected_component_ids": sorted(selected_component_ids),
            "precomputed_event_count_before": precomputed_event_count_before_scope_filter,
            "precomputed_event_count_after": precomputed_event_count_after_scope_filter,
            "excluded_components_outside_manifest_removed": True,
            "storage_branch_outcome_evaluated": False,
        },
        "provider_packet_promoted": adapted.provider_packet_promoted,
        "qualified_provider_packet_count": 0,
        "native_export_elapsed_ms": export_elapsed_ms,
        "consequence_chain_elapsed_ms": chain_elapsed_ms,
        "consequence_chain_executed": any(str(case.get("status", "")).startswith("EXECUTED") for case in result.get("cases", [])),
        "facility_campaign_executed": True,
        "facility_campaign_status": result.get("status"),
        "facility_campaign_event_count": len(result.get("events", [])),
        "facility_campaign_case_count": len(campaign_cases),
        "facility_campaign_executed_case_count": len(executed_campaign_cases),
        "facility_campaign_uncomputed_case_count": len(uncomputed_campaign_cases),
        "facility_campaign_risk_atom_count": len(result.get("risk_atoms", [])),
        "facility_campaign_conditional_risk_available": result.get("known_contribution_annual_ir_low_high") is not None,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "facility_total_risk_available": result.get("total_facility_annual_ir_low_high") is not None,
        "limitations": [
            "synthetic DynamicHEMPipe geometry, initial quality, opening and atmospheric boundary",
            "bounded horizon retains residual pipe inventory",
            "airborne liquid remains explicitly zero pending independent droplet validation",
            "literature frequency is diagnostic input and not site-calibrated",
            "four other LH2_PIPE opening bins remain UNCOMPUTED in the facility campaign",
            "facility total IR/F-N is withheld while the declared scope is partial",
        ],
    }
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--compiled-campaign", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        verification = run(args)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        raise SystemExit(f"native LH2 DynamicHEMPipe frequency case failed: {error}") from error
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
