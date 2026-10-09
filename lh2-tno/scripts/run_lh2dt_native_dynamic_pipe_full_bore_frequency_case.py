"""Run a native finite-inventory full-bore DynamicHEMPipe frequency diagnostic.

The provider owns the finite pipe state and stops at pressure equalization or
inventory depletion.  PRISM binds the exact ``LH2_PIPE AREA_100%`` literature
event to that provider packet and runs one consequence chain.  This is still a
single synthetic equipment diagnostic; it does not promote a facility QRA or
turn a literature rate into a site-calibrated frequency.
"""
from __future__ import annotations

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
from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_accident_export import (  # noqa: E402
    AccidentReleaseExportRequest,
    export_equipment_liquid_accident_history,
)
from lh2_tno.equipment_manifest import EquipmentManifest  # noqa: E402
from lh2_tno.frequency import FrequencyPlan, bind_event, generate_events  # noqa: E402
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
        "failure_opening_diameter_m": 0.025,
        "horizon_s": 60.0,
        "position_enu_m": [5.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "native lh2dt DynamicHEMPipe finite full-bore accidental outlet; LH2_PIPE AREA_100%",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "lh2dt.dynamic_pipe.DynamicHEMPipe",
        "model_revision": "native-export-3d9b982",
        "state_snapshot_digest": state_digest,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit native full-bore finite-inventory diagnostic; literature frequency binding; not site-calibrated",
        "provider_termination_required": True,
    })


def _defaults() -> dict[str, Any]:
    value = json.loads((ROOT / "examples" / "equipment_consequence_template.json").read_text(encoding="utf-8"))
    for key in (
        "component_id", "available_mass_kg", "source_position_enu_m",
        "source_positions_enu_m", "resolved_release", "resolved_release_set",
        "resolved_liquid_release",
    ):
        value.pop(key, None)
    value.update({
        "source_input": None,
        "source_operator": "equipment_liquid_release",
        "source_duration_mode": "model_natural",
        "annual_frequency_per_year": None,
        "annual_frequency_provenance": None,
        "frequency_event": None,
        "initiation_intensity_per_s": None,
        "release_termination": {
            "basis": "provider_declared",
            "time_s": "provider_duration",
            "provenance": "native DynamicHEMPipe finite full-bore provider clock",
        },
        "pool": {
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
        },
    })
    return value


def run(args: Any) -> dict[str, Any]:
    external_root = args.lh2dt_root.resolve()
    sys.path.insert(0, str(external_root / "src"))
    from lh2dt.dynamic_pipe import DynamicHEMPipe
    from lh2dt.properties import HydrogenProperties

    source_digest = _tree_digest(external_root)
    state_digest = canonical_digest({
        "source": "native-dynamic-pipe-full-bore-case",
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
    provider = NativeDynamicPipeProvider(model, {
        "initial_pressure_pa_abs": 500000.0,
        "initial_temperature_k": 27.0,
        "initial_quality": 0.1,
        "time_step_s": 0.01,
        "discharge_coefficient": 0.8,
        "impact_position_m": [5.0, 0.0, 0.001],
        "direction_enu": [1.0, 0.0, 0.0],
        "droplet_diameter_m": 1.0e-3,
        "droplet_flight_time_s": 0.0,
    })
    started = time.perf_counter()
    adapted = export_equipment_liquid_accident_history(provider, _request(source_digest, state_digest))
    export_elapsed_ms = (time.perf_counter() - started) * 1000.0
    release = adapted.release
    request = build_consequence_request_from_provider_release(release, _defaults())
    plan_raw = json.loads(args.frequency_plan.read_text(encoding="utf-8"))
    for asset in plan_raw.get("assets", []):
        if asset.get("id") == "transfer-line":
            # The catalogue rate is length based.  Allocate the 10 m catalogue
            # exposure to this one reviewed outlet so the bound event has an
            # exact single-location multiplier of one.
            asset["location_weight"] = 0.1
            asset["location_weight_provenance"] = (
                "single reviewed full-bore outlet used for native DynamicHEMPipe diagnostic"
            )
    plan = FrequencyPlan.model_validate_json(
        json.dumps(plan_raw, ensure_ascii=False, allow_nan=False)
    )
    manifest = EquipmentManifest.from_json(args.manifest)
    events = generate_events(manifest.to_facility(), plan)
    event_id = "generic-lh2-full-scope-frequency-example/transfer-line/AREA_100%"
    event = next((row for row in events if row.id == event_id), None)
    if event is None:
        raise ValueError("frequency plan did not generate the LH2_PIPE AREA_100% event")
    if event.release.hole_diameter_m != 0.025 or event.exposure_multiplier != 1:
        raise ValueError("LH2_PIPE AREA_100% event is not an exact single-location full-bore match")
    request = bind_event(request, event)
    config_raw = json.loads(args.backend_config.read_text(encoding="utf-8"))
    for pin in config_raw.get("packages", []):
        pin["sha256"] = tree_digest(Path(pin["root"]))
    config = BackendConfig.model_validate_json(json.dumps(config_raw, ensure_ascii=False, allow_nan=False))
    chain_started = time.perf_counter()
    consequence = ResearchPipeline(manifest.to_facility(), IsolatedBackend(config)).consequences(request)
    chain_elapsed_ms = (time.perf_counter() - chain_started) * 1000.0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _save(args.output_dir / "provider_response.json", adapted.provider_response)
    _save(args.output_dir / "resolved_release.json", release.model_dump(mode="json"))
    _save(args.output_dir / "consequence_result.json", consequence)
    data = consequence.get("data", {})
    provider_data = adapted.provider_response.get("data", {})
    final_pressure = provider_data.get("provider_meta", {}).get("final_pressure_pa_abs")
    pressure_equalized = provider_data.get("provider_meta", {}).get("pressure_equalized")
    pressure_matches_ambient = (
        isinstance(final_pressure, (int, float))
        and math.isclose(float(final_pressure), 101325.0, rel_tol=0.0, abs_tol=1.0e-3)
    )
    if pressure_equalized is True and not pressure_matches_ambient:
        raise ValueError("provider pressure-equalization result does not match the declared ambient pressure")
    verification = {
        "schema_version": "prism.native_lh2dt_dynamic_pipe_full_bore_frequency_case.v1",
        "status": data.get("status"),
        "event_id": release.event_id,
        "component_id": release.component_id,
        "opening_diameter_m": release.failure_opening_diameter_m,
        "full_bore_match": release.failure_opening_diameter_m == 0.025,
        "phase_basis": release.phase_basis,
        "provider_source_digest": release.provider_source_digest,
        "provider_result_digest": adapted.provider_result_digest,
        "provider_termination_basis": release.termination_basis,
        "provider_duration_s": release.duration_s,
        "provider_available_mass_kg": release.available_mass_kg,
        "provider_cumulative_mass_out_kg": release.cumulative_mass_out_kg,
        "provider_mass_residual_kg": release.cumulative_mass_out_kg - release.integrated_mass_kg,
        "provider_final_pressure_pa_abs": final_pressure,
        "provider_pressure_equalized": pressure_equalized,
        "provider_final_pressure_matches_ambient": pressure_matches_ambient,
        "provider_export_elapsed_ms": export_elapsed_ms,
        "consequence_chain_elapsed_ms": chain_elapsed_ms,
        "consequence_chain_executed": data.get("full_chain_executed") is True,
        "frequency_applied": request.frequency_event is not None,
        "frequency_event_id": request.frequency_event.id if request.frequency_event is not None else None,
        "annual_frequency_per_year": request.annual_frequency_per_year,
        "annual_frequency_provenance": request.annual_frequency_provenance,
        "frequency_exact_opening_match": (
            request.frequency_event is not None
            and request.frequency_event.release.hole_diameter_m == release.failure_opening_diameter_m
        ),
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "limitations": [
            "synthetic 1 m pipe, initial state, full-bore opening and atmospheric boundary",
            "provider pressure-equalization termination is finite-state evidence, not field isolation reliability",
            "literature frequency is a diagnostic initiating-event input and not site-calibrated",
            "declared-sensitivity pool footprint remains operator-limited",
            "airborne liquid remains zero pending independent droplet validation",
        ],
    }
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--backend-config", type=Path, required=True)
    parser.add_argument("--frequency-plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    verification = run(args)
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
