"""Export native ``lh2dt.VentStack`` accident history into PRISM."""
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
    export_equipment_gas_accident_history,
)
from lh2_tno.state_snapshot import EQUIPMENT_STATE_SNAPSHOT_SCHEMA, EquipmentStateSnapshot  # noqa: E402


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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


class NativeVentStackProvider:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = dict(response)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        data = self.response.get("data", {})
        for key in ("event_id", "component_id", "port_id"):
            if request.get(key) != data.get(key):
                raise ValueError(f"native provider {key} does not match PRISM request")
        strict = json.loads(json.dumps(self.response, allow_nan=False))
        for step in strict.get("data", {}).get("steps", []):
            if isinstance(step, dict):
                step.pop("provider_source_state", None)
        return strict


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    if args.time_step_s <= 0.0 or args.horizon_s <= 0.0 or args.time_step_s > args.horizon_s:
        raise ValueError("horizon and time step must be positive and ordered")
    source_digest = _tree_digest(root)
    sys.path.insert(0, str(root / "src"))
    module = importlib.import_module("lh2dt")
    properties = module.HydrogenProperties("Hydrogen")
    stack = module.VentStack(
        length_m=args.length_m,
        inner_diameter_m=args.inner_diameter_m,
        roughness_m=args.roughness_m,
        local_loss_coefficient=args.local_loss_coefficient,
        elevation_change_m=args.elevation_change_m,
        ambient_UA_W_K=args.ambient_ua_w_k,
        integration_segments=args.integration_segments,
        ambient_temperature_K=args.ambient_temperature_k,
        properties=properties,
    )
    source_state = properties.from_pT(args.source_pressure_pa_abs, args.source_temperature_k)
    phase = str(source_state.phase).lower()
    if phase not in {"gas", "supercritical_gas", "supercritical"}:
        raise ValueError("native VentStack export requires a gas-like source state")
    snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": args.component_id,
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": args.source_pressure_pa_abs,
        "temperature_k": args.source_temperature_k,
        "phase": "vapour",
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "measurements": {
            "upstream_pressure": {"quantity": "pressure", "value_si": args.source_pressure_pa_abs, "sensor_location": f"{args.component_id}.upstream"},
            "upstream_temperature": {"quantity": "temperature", "value_si": args.source_temperature_k, "sensor_location": f"{args.component_id}.upstream"},
        },
    })
    request = AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": args.component_id,
        "port_id": args.port_id,
        "event_id": args.event_id,
        "failure_mode": "explicit_failed_vent_outlet",
        "failure_opening_diameter_m": args.inner_diameter_m,
        "horizon_s": args.horizon_s,
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "lh2dt.VentStack.export_accident_history native gas outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "VentStack",
        "model_revision": args.model_revision,
        "state_snapshot_digest": snapshot.digest(),
        "state_snapshot": snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "native external VentStack accident export; synthetic upstream state and geometry",
        "provider_termination_required": True,
    })
    native_response = stack.export_accident_history({
        "event_id": args.event_id,
        "component_id": args.component_id,
        "port_id": args.port_id,
        "source_pressure_pa_abs": args.source_pressure_pa_abs,
        "source_temperature_k": args.source_temperature_k,
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "failure_opening_diameter_m": args.inner_diameter_m,
        "horizon_s": args.horizon_s,
        "time_step_s": args.time_step_s,
        "available_mass_kg": args.available_mass_kg,
        "termination_basis": "synthetic_diagnostic_horizon",
        "termination_provenance": "operator-declared bounded VentStack horizon; upstream reserve remains explicit",
        "provider_source_digest": source_digest,
        "state_snapshot_digest": snapshot.digest(),
    })
    result = export_equipment_gas_accident_history(NativeVentStackProvider(native_response), request)
    data = native_response["data"]
    meta = data.get("provider_meta") if isinstance(data.get("provider_meta"), Mapping) else {}
    hydraulic = meta.get("hydraulic") if isinstance(meta.get("hydraulic"), Mapping) else {}
    verification = {
        "schema_version": "prism.native_lh2dt_vent_stack_packet_verification.v1",
        "status": "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC",
        "provider_model": native_response.get("provider_model"),
        "provider_export_schema": native_response.get("provider_export_schema"),
        "provider_method": result.provider_method,
        "provider_source_digest": source_digest,
        "provider_result_digest": result.provider_result_digest,
        "provider_packet_promoted": result.provider_packet_promoted,
        "termination_basis": data.get("termination_basis"),
        "duration_s": data.get("duration_s"),
        "available_mass_kg": data.get("available_mass_kg"),
        "cumulative_mass_out_kg": data.get("cumulative_mass_out_kg"),
        "mass_reserve_remaining_kg": float(data.get("available_mass_kg", 0.0)) - float(data.get("cumulative_mass_out_kg", 0.0)),
        "hydraulic": {"mass_flow_kg_s": hydraulic.get("mass_flow_kg_s"), "reynolds_number": hydraulic.get("reynolds_number"), "pressure_drop_pa": hydraulic.get("pressure_drop_pa")},
        "state_snapshot_digest_match": native_response.get("provider_state_snapshot_digest") == snapshot.digest(),
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic upstream gas state, stack geometry and bounded horizon",
            "VentStack owns no upstream inventory, relief setpoint or isolation reliability",
            "native compact source trace is preserved in provider_response.json but not promoted to the incomplete strict source-state schema",
            "diagnostic only; no field frequency or independent physical validation",
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
    parser.add_argument("--component-id", default="native-vent-stack-diagnostic")
    parser.add_argument("--port-id", default="native-vent-stack-gas-out")
    parser.add_argument("--event-id", default="native-vent-stack/accidental-leak-001")
    parser.add_argument("--model-revision", default="external-library-native-export-0.1.2")
    parser.add_argument("--source-pressure-pa-abs", type=float, default=102000.0)
    parser.add_argument("--source-temperature-k", type=float, default=300.0)
    parser.add_argument("--ambient-pressure-pa-abs", type=float, default=101325.0)
    parser.add_argument("--ambient-temperature-k", type=float, default=288.15)
    parser.add_argument("--length-m", type=float, default=1.0)
    parser.add_argument("--inner-diameter-m", type=float, default=0.01)
    parser.add_argument("--roughness-m", type=float, default=1.0e-6)
    parser.add_argument("--local-loss-coefficient", type=float, default=1.0)
    parser.add_argument("--elevation-change-m", type=float, default=0.0)
    parser.add_argument("--ambient-ua-w-k", type=float, default=0.0)
    parser.add_argument("--integration-segments", type=int, default=64)
    parser.add_argument("--horizon-s", type=float, default=0.1)
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--available-mass-kg", type=float, default=1.0)
    parser.add_argument("--nozzle-height-m", type=float, default=2.0)
    args = parser.parse_args()
    try:
        result = run(args)
    except (ImportError, KeyError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"native VentStack PRISM export failed: {error}") from error
    print(json.dumps({"status": result["status"], "termination_basis": result["termination_basis"], "duration_s": result["duration_s"], "output": str(args.output_dir.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
