"""Export native ``DynamicVaporizer`` or ``DynamicReliquefier`` history.

The external finite-volume model owns the transient mass/energy state and its
native accident outlet.  PRISM validates the returned gas history and
completes omitted source-state thermodynamic fields from the same provider
property backend.  This does not create a near-field jet solution; the raw
native result digest and the deterministic completion audit remain separate.
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

from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_accident_export import (  # noqa: E402
    AccidentReleaseExportRequest,
    export_equipment_gas_accident_history,
)
from lh2_tno.native_source_state import (  # noqa: E402
    complete_isentropic_throat_source_states,
)
from lh2_tno.state_snapshot import (  # noqa: E402
    EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
    EquipmentStateSnapshot,
)
from lh2_tno.resolved_liquid_worker import dynamic_state_closure_status  # noqa: E402


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


class NativeDynamicThermalProvider:
    """Keep exact event identity after deterministic source-state completion."""

    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = dict(response)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        data = self.response.get("data", {})
        for key in ("event_id", "component_id", "port_id"):
            if request.get(key) != data.get(key):
                raise ValueError(f"native provider {key} does not match PRISM request")
        return json.loads(json.dumps(self.response, allow_nan=False))


def _native_model(root: Path, *, mode: str, fluid_volume_m3: float, wall_heat_capacity_j_k: float,
                  fluid_wall_ua_w_k: float, ambient_temperature_k: float,
                  ambient_ua_w_k: float, maximum_heat_w: float) -> tuple[Any, Any, str]:
    sys.path.insert(0, str(root / "src"))
    module = importlib.import_module("lh2dt")
    properties = module.HydrogenProperties("Hydrogen")
    if mode == "vaporizer":
        model = module.DynamicVaporizer(
            fluid_volume_m3=fluid_volume_m3,
            wall_heat_capacity_J_K=wall_heat_capacity_j_k,
            fluid_wall_UA_W_K=fluid_wall_ua_w_k,
            ambient_temperature_K=ambient_temperature_k,
            ambient_UA_W_K=ambient_ua_w_k,
            maximum_heat_W=maximum_heat_w,
            properties=properties,
        )
        return model, properties, "DynamicVaporizer"
    if mode == "reliquefier":
        model = module.DynamicReliquefier(
            fluid_volume_m3=fluid_volume_m3,
            wall_heat_capacity_J_K=wall_heat_capacity_j_k,
            fluid_wall_UA_W_K=fluid_wall_ua_w_k,
            cold_side_temperature_K=ambient_temperature_k,
            cold_side_UA_W_K=ambient_ua_w_k,
            maximum_cooling_W=maximum_heat_w,
            properties=properties,
        )
        return model, properties, "DynamicReliquefier"
    raise ValueError("mode must be vaporizer or reliquefier")


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    if args.time_step_s <= 0.0 or args.horizon_s <= 0.0:
        raise ValueError("horizon and time step must be positive")
    if args.time_step_s > args.horizon_s:
        raise ValueError("time step must not exceed horizon")
    source_digest = _tree_digest(root)
    position_enu_m = (
        [float(value) for value in args.position_enu_m]
        if args.position_enu_m is not None
        else [0.0, 0.0, args.nozzle_height_m]
    )
    model, properties, model_class = _native_model(
        root, mode=args.mode, fluid_volume_m3=args.fluid_volume_m3,
        wall_heat_capacity_j_k=args.wall_heat_capacity_j_k,
        fluid_wall_ua_w_k=args.fluid_wall_ua_w_k,
        ambient_temperature_k=args.thermal_boundary_temperature_k,
        ambient_ua_w_k=args.thermal_boundary_ua_w_k,
        maximum_heat_w=args.maximum_heat_w,
    )
    source_state = properties.from_pT(args.source_pressure_pa_abs, args.source_temperature_k)
    phase = str(source_state.phase).lower()
    if phase not in {"gas", "supercritical_gas", "supercritical"}:
        raise ValueError("native dynamic thermal export requires a gas-like source state")
    initial_state = model.initialize(source_state, wall_temperature_K=args.wall_temperature_k)
    snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": args.component_id,
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": args.source_pressure_pa_abs,
        "temperature_k": args.source_temperature_k,
        "mass_kg": float(initial_state.mass_kg),
        "phase": "vapour",
        "position_enu_m": position_enu_m,
        "measurements": {
            "initial_pressure": {"quantity": "pressure", "value_si": args.source_pressure_pa_abs, "sensor_location": f"{args.component_id}.fluid_volume"},
            "initial_temperature": {"quantity": "temperature", "value_si": args.source_temperature_k, "sensor_location": f"{args.component_id}.fluid_volume"},
        },
    })
    event_id = args.event_id
    request_payload: dict[str, Any] = {
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": args.component_id,
        "port_id": args.port_id,
        "event_id": event_id,
        "failure_mode": "explicit_failed_atmospheric_outlet",
        "failure_opening_diameter_m": args.failure_opening_diameter_m,
        "horizon_s": args.horizon_s,
        "position_enu_m": position_enu_m,
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": f"lh2dt.{model_class}.export_accident_history native gas outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": model_class,
        "model_revision": args.model_revision,
        "state_snapshot_digest": snapshot.digest(),
        "state_snapshot": snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": f"native external {model_class} finite-volume accident export; synthetic geometry and state",
        "provider_termination_required": True,
    }
    if args.isolation_time_s is not None:
        request_payload["isolation_time_s"] = args.isolation_time_s
        request_payload["post_isolation_observation_s"] = args.post_isolation_observation_s
    request = AccidentReleaseExportRequest.from_mapping(request_payload)
    native_request = {
        "event_id": event_id,
        "component_id": args.component_id,
        "port_id": args.port_id,
        "failure_mode": "explicit_failed_atmospheric_outlet",
        "source_pressure_pa_abs": args.source_pressure_pa_abs,
        "source_temperature_k": args.source_temperature_k,
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "failure_opening_diameter_m": args.failure_opening_diameter_m,
        "discharge_coefficient": args.discharge_coefficient,
        "stroke_time_s": args.stroke_time_s,
        "horizon_s": args.horizon_s,
        "time_step_s": args.time_step_s,
        "wall_temperature_k": args.wall_temperature_k,
        "provider_source_digest": source_digest,
        "state_snapshot_digest": snapshot.digest(),
    }
    if request.isolation_time_s is not None:
        native_request["isolation_time_s"] = request.isolation_time_s
        native_request["post_isolation_observation_s"] = request.post_isolation_observation_s
    native_response_raw = model.export_accident_history(native_request)
    native_response, source_state_completion = complete_isentropic_throat_source_states(
        native_response_raw,
        properties=properties,
    )
    result = export_equipment_gas_accident_history(NativeDynamicThermalProvider(native_response), request)
    data = native_response["data"]
    meta = data.get("provider_meta") if isinstance(data.get("provider_meta"), Mapping) else {}
    closure_audit = dynamic_state_closure_status(result.release.model_dump(mode="json"))
    declared_closure = meta.get("dynamic_state_closure")
    verification = {
        "schema_version": "prism.native_lh2dt_dynamic_thermal_packet_verification.v1",
        "status": "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC",
        "mode": args.mode,
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
        "provider_mass_residual_kg": meta.get("residual_mass_kg"),
        "dynamic_state_closure": {
            "declared_by_provider": isinstance(declared_closure, Mapping),
            "prism_source_dynamics_status": (
                "READY" if closure_audit.get("ready") is True else "BLOCKED"
            ),
            "ready": closure_audit.get("ready"),
            "blocking_reasons": closure_audit.get("blocking_reasons", []),
            "state_history_digest": (
                declared_closure.get("state_history_digest")
                if isinstance(declared_closure, Mapping)
                else None
            ),
        },
        "final_mass_kg": meta.get("final_mass_kg"),
        "state_snapshot_digest_match": native_response.get("provider_state_snapshot_digest") == snapshot.digest(),
        "native_result_digest": canonical_digest(native_response),
        "native_provider_result_digest": canonical_digest(native_response_raw),
        "native_source_trace_completed_in_packet": True,
        "source_state_completion": source_state_completion,
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic finite-volume geometry, thermal boundary, gas state and atmospheric opening",
            "source entropy and throat thermodynamic fields are completed from the native source pressure/temperature/throat pressure using the same provider property backend",
            "this deterministic completion is not an independent near-field calculation; high-speed output still requires the separate compressible-plane handoff",
            "provider packet remains diagnostic and has no field frequency or independent physical validation",
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
    parser.add_argument("--mode", choices=("vaporizer", "reliquefier"), default="vaporizer")
    parser.add_argument("--component-id", default=None)
    parser.add_argument("--port-id", default=None)
    parser.add_argument("--event-id", default=None)
    parser.add_argument("--model-revision", default="external-library-native-export-0.1.2")
    parser.add_argument("--source-pressure-pa-abs", type=float, default=101500.0)
    parser.add_argument("--source-temperature-k", type=float, default=300.0)
    parser.add_argument("--ambient-pressure-pa-abs", type=float, default=101325.0)
    parser.add_argument("--ambient-temperature-k", type=float, default=288.15)
    parser.add_argument("--failure-opening-diameter-m", type=float, default=0.0025)
    parser.add_argument("--discharge-coefficient", type=float, default=0.8)
    parser.add_argument("--stroke-time-s", type=float, default=0.05)
    parser.add_argument("--horizon-s", type=float, default=0.1)
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--isolation-time-s", type=float, default=None)
    parser.add_argument("--post-isolation-observation-s", type=float, default=0.0)
    parser.add_argument("--wall-temperature-k", type=float, default=300.0)
    parser.add_argument("--thermal-boundary-temperature-k", type=float, default=300.0)
    parser.add_argument("--thermal-boundary-ua-w-k", type=float, default=5.0)
    parser.add_argument("--fluid-volume-m3", type=float, default=0.01)
    parser.add_argument("--wall-heat-capacity-j-k", type=float, default=10000.0)
    parser.add_argument("--fluid-wall-ua-w-k", type=float, default=10.0)
    parser.add_argument("--maximum-heat-w", type=float, default=1000.0)
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    parser.add_argument(
        "--position-enu-m",
        type=float,
        nargs=3,
        metavar=("EAST_M", "NORTH_M", "UP_M"),
        default=None,
        help="equipment outlet position; defaults to [0, 0, nozzle-height]",
    )
    args = parser.parse_args()
    if args.component_id is None:
        args.component_id = f"native-{args.mode}-diagnostic"
    if args.port_id is None:
        args.port_id = f"native-{args.mode}-gas-out"
    if args.event_id is None:
        args.event_id = f"native-{args.mode}/accidental-leak-001"
    try:
        result = run(args)
    except (ImportError, KeyError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"native dynamic thermal PRISM export failed: {error}") from error
    print(json.dumps({"status": result["status"], "mode": result["mode"], "termination_basis": result["termination_basis"], "duration_s": result["duration_s"], "output": str(args.output_dir.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
