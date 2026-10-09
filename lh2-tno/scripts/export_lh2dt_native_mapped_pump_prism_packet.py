"""Export a native ``lh2dt.MappedPump`` accident history into PRISM.

``MappedPump`` supplies the H-Q-N operating point and its native atmospheric
outlet history.  The pump is not an inventory owner, so the caller must pass
an explicit upstream reserve and a provider termination basis.  This script
keeps that boundary explicit and never converts normal pump flow into a
qualified accident frequency.
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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


class NativeMappedPumpProvider:
    """Delegate one native pump response while checking exact identity."""

    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = dict(response)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        data = self.response.get("data", {})
        for key in ("event_id", "component_id", "port_id"):
            if request.get(key) != data.get(key):
                raise ValueError(f"native provider {key} does not match PRISM request")
        return self.response


def _native_pump(
    lh2dt_root: Path,
    *,
    head_curve_points: list[list[float]],
    reference_speed_rpm: float,
    speed_rpm: float,
    isentropic_efficiency: float,
) -> Any:
    sys.path.insert(0, str(lh2dt_root / "src"))
    module = importlib.import_module("lh2dt")
    properties = module.HydrogenProperties("Hydrogen")
    pump = module.MappedPump(
        head_curve_points,
        reference_speed_rpm=reference_speed_rpm,
        speed_rpm=speed_rpm,
        isentropic_efficiency=isentropic_efficiency,
        properties=properties,
    )
    return pump, properties


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    if args.time_step_s <= 0.0 or args.horizon_s <= 0.0:
        raise ValueError("horizon and time step must be positive")
    if args.time_step_s > args.horizon_s:
        raise ValueError("time step must not exceed horizon")
    source_digest = _tree_digest(root)
    pump, properties = _native_pump(
        root,
        head_curve_points=args.head_curve_points,
        reference_speed_rpm=args.reference_speed_rpm,
        speed_rpm=args.speed_rpm,
        isentropic_efficiency=args.isentropic_efficiency,
    )
    source_state = properties.from_pT(args.source_pressure_pa_abs, args.source_temperature_k)
    phase = str(source_state.phase).lower()
    if "liquid" not in phase or "gas" in phase or (source_state.quality is not None and source_state.quality > 1.0e-7):
        raise ValueError("native MappedPump diagnostic requires a liquid source state")
    snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": args.component_id,
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": args.source_pressure_pa_abs,
        "temperature_k": args.source_temperature_k,
        "mass_kg": args.available_mass_kg,
        "phase": "liquid",
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "measurements": {
            "upstream_pressure": {
                "quantity": "pressure",
                "value_si": args.source_pressure_pa_abs,
                "sensor_location": f"{args.component_id}.suction",
            },
            "upstream_temperature": {
                "quantity": "temperature",
                "value_si": args.source_temperature_k,
                "sensor_location": f"{args.component_id}.suction",
            },
        },
    })
    request = AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": args.component_id,
        "port_id": args.port_id,
        "event_id": args.event_id,
        "failure_mode": "explicit_failed_pump_atmospheric_outlet",
        "failure_opening_diameter_m": args.failure_opening_diameter_m,
        "horizon_s": args.horizon_s,
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "lh2dt.MappedPump.export_accident_history native liquid/two-phase outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "MappedPump",
        "model_revision": args.model_revision,
        "state_snapshot_digest": snapshot.digest(),
        "state_snapshot": snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "native external MappedPump H-Q-N accident export; synthetic source state and reserve",
        "provider_termination_required": True,
    })
    native_request = {
        "event_id": args.event_id,
        "component_id": args.component_id,
        "port_id": args.port_id,
        "failure_mode": "explicit_failed_pump_atmospheric_outlet",
        "source_pressure_pa_abs": args.source_pressure_pa_abs,
        "source_temperature_k": args.source_temperature_k,
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "failure_opening_diameter_m": args.failure_opening_diameter_m,
        "discharge_coefficient": args.discharge_coefficient,
        "horizon_s": args.horizon_s,
        "time_step_s": args.time_step_s,
        "available_mass_kg": args.available_mass_kg,
        "termination_basis": "synthetic_diagnostic_horizon",
        "termination_provenance": "operator-declared bounded pump feed-through horizon; upstream reserve remains explicit",
        "pump_pressure_rise_pa": args.pump_pressure_rise_pa,
        "provider_source_digest": source_digest,
        "state_snapshot_digest": snapshot.digest(),
        "droplet_diameter_m": args.droplet_diameter_m,
        "droplet_flight_time_s": args.droplet_flight_time_s,
        "impact_position_m": [0.0, 0.0, 0.001],
    }
    native_response = pump.export_accident_history(native_request)
    result = export_equipment_liquid_accident_history(NativeMappedPumpProvider(native_response), request)
    data = native_response["data"]
    meta = data.get("provider_meta") if isinstance(data.get("provider_meta"), Mapping) else {}
    point = meta.get("pump_operating_point") if isinstance(meta.get("pump_operating_point"), Mapping) else {}
    verification = {
        "schema_version": "prism.native_lh2dt_mapped_pump_packet_verification.v1",
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
        "upstream_reserve_remaining_kg": float(data.get("available_mass_kg", 0.0)) - float(data.get("cumulative_mass_out_kg", 0.0)),
        "pump_operating_point": {
            "mass_flow_kg_s": point.get("mass_flow_kg_s"),
            "pressure_rise_pa": point.get("pressure_rise_pa"),
            "map_head_pressure_rise_pa": point.get("map_head_pressure_rise_pa"),
            "map_limited": point.get("map_limited"),
            "cavitation_margin_m": point.get("cavitation_margin_m"),
        },
        "state_snapshot_digest_match": native_response.get("provider_state_snapshot_digest") == snapshot.digest(),
        "strict_packet_mass_residual_kg": result.release.cumulative_mass_out_kg - result.release.integrated_mass_kg,
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic liquid source state, H-Q-N map, atmospheric opening and upstream reserve",
            "MappedPump owns no finite inventory, seal failure model or isolation reliability",
            "airborne liquid remains zero under the native provider contract",
            "bounded feed-through horizon is diagnostic and not a qualified facility frequency case",
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
    parser.add_argument("--component-id", default="native-mapped-pump-diagnostic")
    parser.add_argument("--port-id", default="native-mapped-pump-liquid-out")
    parser.add_argument("--event-id", default="native-mapped-pump/accidental-leak-001")
    parser.add_argument("--model-revision", default="external-library-native-export-0.1.2")
    parser.add_argument("--source-pressure-pa-abs", type=float, default=120000.0)
    parser.add_argument("--source-temperature-k", type=float, default=20.0)
    parser.add_argument("--ambient-pressure-pa-abs", type=float, default=101325.0)
    parser.add_argument("--ambient-temperature-k", type=float, default=288.15)
    parser.add_argument("--failure-opening-diameter-m", type=float, default=0.000538)
    parser.add_argument("--discharge-coefficient", type=float, default=0.7)
    parser.add_argument("--pump-pressure-rise-pa", type=float, default=100000.0)
    parser.add_argument("--horizon-s", type=float, default=0.2)
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--available-mass-kg", type=float, default=1.0)
    parser.add_argument("--droplet-diameter-m", type=float, default=0.001)
    parser.add_argument("--droplet-flight-time-s", type=float, default=0.0)
    parser.add_argument("--nozzle-height-m", type=float, default=0.5)
    parser.add_argument("--reference-speed-rpm", type=float, default=3000.0)
    parser.add_argument("--speed-rpm", type=float, default=3000.0)
    parser.add_argument("--isentropic-efficiency", type=float, default=0.7)
    parser.add_argument("--head-curve-points", type=json.loads, default=[[0.0, 300000.0], [0.01, 150000.0], [0.02, 0.0]])
    args = parser.parse_args()
    try:
        result = run(args)
    except (ImportError, KeyError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"native MappedPump PRISM export failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "phase_basis": result["phase_basis"],
        "termination_basis": result["termination_basis"],
        "duration_s": result["duration_s"],
        "pump_operating_point": result["pump_operating_point"],
        "output": str(args.output_dir.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
