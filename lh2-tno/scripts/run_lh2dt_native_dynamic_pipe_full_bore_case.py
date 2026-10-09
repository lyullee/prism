"""Run a native finite-inventory full-bore DynamicHEMPipe diagnostic.

The provider owns the finite pipe state and stops at pressure equalization or
inventory depletion.  PRISM validates the packet and runs one direct
consequence chain, but does not assign a field frequency or promote facility
QRA from this synthetic geometry.
"""
from __future__ import annotations

import copy
import hashlib
import json
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
        "event_id": "generic-lh2-full-bore-diagnostic/transfer-line/full-bore",
        "failure_mode": "explicit_failed_opening",
        "failure_opening_diameter_m": 0.01,
        "horizon_s": 60.0,
        "position_enu_m": [5.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "native lh2dt DynamicHEMPipe finite full-bore accidental outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "lh2dt.dynamic_pipe.DynamicHEMPipe",
        "model_revision": "native-export-4cedec3",
        "state_snapshot_digest": state_digest,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit native full-bore finite-inventory diagnostic; not site-calibrated",
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
        "inner_diameter_m": 0.01,
    })
    model = DynamicHEMPipe(
        1.0,
        0.01,
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
    manifest = EquipmentManifest.from_json(args.manifest)
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
    verification = {
        "schema_version": "prism.native_lh2dt_dynamic_pipe_full_bore_case.v1",
        "status": data.get("status"),
        "event_id": release.event_id,
        "component_id": release.component_id,
        "opening_diameter_m": release.failure_opening_diameter_m,
        "full_bore_match": release.failure_opening_diameter_m == 0.01,
        "phase_basis": release.phase_basis,
        "provider_source_digest": release.provider_source_digest,
        "provider_result_digest": adapted.provider_result_digest,
        "provider_termination_basis": release.termination_basis,
        "provider_duration_s": release.duration_s,
        "provider_available_mass_kg": release.available_mass_kg,
        "provider_cumulative_mass_out_kg": release.cumulative_mass_out_kg,
        "provider_mass_residual_kg": release.cumulative_mass_out_kg - release.integrated_mass_kg,
        "provider_final_pressure_pa_abs": provider_data.get("provider_meta", {}).get("final_pressure_pa_abs"),
        "provider_pressure_equalized": provider_data.get("provider_meta", {}).get("pressure_equalized"),
        "provider_export_elapsed_ms": export_elapsed_ms,
        "consequence_chain_elapsed_ms": chain_elapsed_ms,
        "consequence_chain_executed": data.get("full_chain_executed") is True,
        "frequency_applied": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
        "limitations": [
            "synthetic 1 m pipe, initial state, full-bore opening and atmospheric boundary",
            "provider pressure-equalization termination is finite-state evidence, not field isolation reliability",
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
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    verification = run(args)
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
