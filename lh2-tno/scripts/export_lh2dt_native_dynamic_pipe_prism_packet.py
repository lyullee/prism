"""Export a native ``lh2dt.DynamicHEMPipe`` accident history into PRISM.

The adapter calls the external model's own ``export_accident_history`` method
and sends the returned gas/two-phase history through PRISM's strict release
boundary.  It is a synthetic diagnostic by default; no frequency or facility
qualification is inferred from the native response.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_accident_export import (  # noqa: E402
    AccidentReleaseExportRequest,
    export_equipment_liquid_accident_history,
)
from lh2_tno.state_snapshot import (  # noqa: E402
    EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
    EquipmentStateSnapshot,
)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


class NativeDynamicPipeProvider:
    """Delegate one already-computed native response to PRISM."""

    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = dict(response)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if request.get("event_id") != self.response.get("data", {}).get("event_id"):
            raise ValueError("native provider event_id does not match PRISM request")
        return self.response


def _native_pipe(lh2dt_root: Path, *, length_m: float, diameter_m: float, roughness_m: float) -> Any:
    sys.path.insert(0, str(lh2dt_root / "src"))
    module = importlib.import_module("lh2dt")
    properties = module.HydrogenProperties("Hydrogen")
    return module.DynamicHEMPipe(
        length_m=length_m,
        inner_diameter_m=diameter_m,
        roughness_m=roughness_m,
        wall_heat_capacity_J_K=1.0e5,
        properties=properties,
        ambient_temperature_K=288.15,
    ), properties


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    if args.isolation_time_s is not None and args.isolation_time_s > args.horizon_s:
        raise ValueError("isolation time must not exceed horizon")
    source_digest = _tree_digest(root)
    pipe, properties = _native_pipe(
        root,
        length_m=args.length_m,
        diameter_m=args.pipe_diameter_m,
        roughness_m=args.roughness_m,
    )
    source = properties.saturated_liquid(args.initial_pressure_pa_abs)
    vapor = properties.saturated_vapor(args.initial_pressure_pa_abs)
    source_enthalpy = source.specific_enthalpy_J_kg + args.initial_quality * (
        vapor.specific_enthalpy_J_kg - source.specific_enthalpy_J_kg
    )
    source_state = properties.from_ph(args.initial_pressure_pa_abs, source_enthalpy)
    initial_state = pipe.initialize(source_state, wall_temperature_K=args.wall_temperature_k)
    snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": args.component_id,
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": args.initial_pressure_pa_abs,
        "temperature_k": float(source_state.temperature_K),
        "mass_kg": float(initial_state.mass_kg),
        "phase": "two_phase",
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "measurements": {
            "initial_pressure": {
                "quantity": "pressure",
                "value_si": args.initial_pressure_pa_abs,
                "sensor_location": f"{args.component_id}.fluid_volume",
            },
            "initial_quality": {
                "quantity": "level_fraction",
                "value_si": args.initial_quality,
                "sensor_location": f"{args.component_id}.fluid_volume",
            },
        },
    })
    request = AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": args.component_id,
        "port_id": args.port_id,
        "event_id": args.event_id,
        "failure_mode": "explicit_failed_opening",
        "failure_opening_diameter_m": args.failure_opening_diameter_m,
        "horizon_s": args.horizon_s,
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "lh2dt.DynamicHEMPipe.export_accident_history native outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "DynamicHEMPipe",
        "model_revision": args.model_revision,
        "state_snapshot_digest": snapshot.digest(),
        "state_snapshot": snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "native external DynamicHEMPipe accident export; synthetic geometry and state",
        "provider_termination_required": True,
    })
    native_request: dict[str, Any] = {
        "event_id": args.event_id,
        "component_id": args.component_id,
        "port_id": args.port_id,
        "failure_mode": "explicit_failed_opening",
        "initial_pressure_pa_abs": args.initial_pressure_pa_abs,
        "initial_temperature_k": args.initial_temperature_k,
        "initial_quality": args.initial_quality,
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "failure_opening_diameter_m": args.failure_opening_diameter_m,
        "discharge_coefficient": args.discharge_coefficient,
        "horizon_s": args.horizon_s,
        "time_step_s": args.time_step_s,
        "wall_temperature_k": args.wall_temperature_k,
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "direction_enu": [1.0, 0.0, 0.0],
        "provider_source_digest": source_digest,
        "state_snapshot_digest": snapshot.digest(),
    }
    if args.isolation_time_s is not None:
        native_request["isolation_time_s"] = args.isolation_time_s
        native_request["post_isolation_observation_s"] = args.post_isolation_observation_s
    native_response = pipe.export_accident_history(native_request)
    result = export_equipment_liquid_accident_history(
        NativeDynamicPipeProvider(native_response), request
    )
    data = native_response["data"]
    provider_meta = data.get("provider_meta") if isinstance(data.get("provider_meta"), Mapping) else {}
    verification = {
        "schema_version": "prism.native_lh2dt_dynamic_pipe_packet_verification.v1",
        "status": "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC",
        "provider_model": native_response.get("provider_model"),
        "provider_export_schema": native_response.get("provider_export_schema"),
        "provider_method": result.provider_method,
        "provider_source_digest": source_digest,
        "provider_result_digest": result.provider_result_digest,
        "provider_packet_promoted": result.provider_packet_promoted,
        "phase_basis": data.get("phase_basis"),
        "termination_basis": data.get("termination_basis"),
        "duration_s": data.get("duration_s"),
        "available_mass_kg": data.get("available_mass_kg"),
        "cumulative_mass_out_kg": data.get("cumulative_mass_out_kg"),
        "mass_residual_kg": provider_meta.get("residual_mass_kg"),
        "isolation_time_s": provider_meta.get("isolation_time_s"),
        "post_isolation_observation_s": provider_meta.get("post_isolation_observation_s"),
        "isolation_success": provider_meta.get("isolation_success"),
        "state_snapshot_digest_match": native_response.get("provider_state_snapshot_digest") == snapshot.digest(),
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic pipe geometry, initial two-phase state and atmospheric boundary",
            "native provider history remains diagnostic until independent qualification is supplied",
            "airborne liquid remains zero under the native provider contract",
        ],
    }
    _save(args.output_dir / "provider_response.json", native_response)
    _save(args.output_dir / "resolved_release.json", result.release.model_dump(mode="json"))
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--component-id", default="native-dynamic-pipe-diagnostic")
    parser.add_argument("--port-id", default="native-dynamic-pipe-out")
    parser.add_argument("--event-id", default="native-dynamic-pipe/accidental-leak-001")
    parser.add_argument("--model-revision", default="external-library-native-export-0.1.1")
    parser.add_argument("--length-m", type=float, default=10.0)
    parser.add_argument("--pipe-diameter-m", type=float, default=0.1)
    parser.add_argument("--roughness-m", type=float, default=1.0e-6)
    parser.add_argument("--initial-pressure-pa-abs", type=float, default=500000.0)
    parser.add_argument("--initial-temperature-k", type=float, default=27.0)
    parser.add_argument("--initial-quality", type=float, default=0.1)
    parser.add_argument("--wall-temperature-k", type=float, default=27.0)
    parser.add_argument("--ambient-pressure-pa-abs", type=float, default=101325.0)
    parser.add_argument("--ambient-temperature-k", type=float, default=288.15)
    parser.add_argument("--failure-opening-diameter-m", type=float, default=0.01)
    parser.add_argument("--discharge-coefficient", type=float, default=0.8)
    parser.add_argument("--horizon-s", type=float, default=0.1)
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--isolation-time-s", type=float, default=0.05)
    parser.add_argument("--post-isolation-observation-s", type=float, default=0.01)
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    args = parser.parse_args()
    try:
        result = run(args)
    except (ImportError, KeyError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"native DynamicHEMPipe PRISM export failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "phase_basis": result["phase_basis"],
        "termination_basis": result["termination_basis"],
        "duration_s": result["duration_s"],
        "isolation_success": result["isolation_success"],
        "output": str(args.output_dir.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
