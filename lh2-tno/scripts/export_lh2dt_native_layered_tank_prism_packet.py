"""Export the external ``lh2dt.LayeredTank`` native accident history.

This adapter is intentionally separate from the older PRISM-side diagnostic
wrapper.  It calls the external model's own ``export_accident_history``
method, preserves its termination/isolation ledger, and then sends the
response through PRISM's strict liquid-release boundary.  The default input
is synthetic and therefore remains diagnostic evidence; the adapter never
promotes a packet to a qualified facility release.
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
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


class NativeLayeredTankProvider:
    """Small provider object that delegates the accident calculation natively."""

    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = dict(response)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if request.get("event_id") != self.response.get("data", {}).get("event_id"):
            raise ValueError("native provider event_id does not match PRISM request")
        return self.response


def _native_tank(
    lh2dt_root: Path,
    *,
    distributed_boiling_model: str = "phase_change_complementarity",
) -> Any:
    sys.path.insert(0, str(lh2dt_root / "src"))
    module = importlib.import_module("lh2dt")
    geometry = module.HorizontalVesselGeometry(
        inner_diameter_m=2.0,
        straight_length_m=4.0,
        head_depth_m=0.5,
        quadrature_order=48,
    )
    parameters = module.LayeredTankParameters(
        liquid_cell_count=3,
        vapor_cell_count=3,
        wall_node_count=6,
        wall_heat_capacity_J_K=3.0e6,
        # A depressurising liquid outlet can move a labelled vapor cell into
        # the saturation band.  The current lh2dt API requires that phase
        # transfer be closed by its explicit complementarity model; leaving
        # the model at the historical ``off`` default makes the native
        # accident export fail before a provider packet is produced.
        distributed_boiling_model=distributed_boiling_model,
    )
    return module.LayeredTank(geometry, parameters)


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    if args.isolation_time_s is not None and args.isolation_time_s > args.horizon_s:
        raise ValueError("isolation time must not exceed horizon")
    tank = _native_tank(
        root,
        distributed_boiling_model=args.distributed_boiling_model,
    )
    component_id = args.component_id
    port_id = args.port_id
    event_id = args.event_id
    position_enu_m = (
        [float(value) for value in args.position_enu_m]
        if args.position_enu_m is not None
        else [0.0, 0.0, float(args.nozzle_height_m)]
    )
    initial_native_state = tank.initialize_saturated(
        args.initial_pressure_pa_abs,
        args.liquid_volume_fraction,
    )
    initial_native_thermo = tank.thermo(initial_native_state)
    initial_native_liquid = initial_native_thermo.liquid[0]
    state_payload = {
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": component_id,
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": args.initial_pressure_pa_abs,
        "temperature_k": float(initial_native_liquid.temperature_K),
        "mass_kg": float(tank.total_mass_kg(initial_native_state)),
        "phase": "liquid",
        "position_enu_m": position_enu_m,
        "measurements": {
            "initial_pressure": {
                "quantity": "pressure",
                "value_si": args.initial_pressure_pa_abs,
                "sensor_location": f"{component_id}.liquid_inventory",
            },
            "liquid_volume_fraction": {
                "quantity": "level_fraction",
                "value_si": args.liquid_volume_fraction,
                "sensor_location": f"{component_id}.liquid_inventory",
            },
        },
    }
    snapshot = EquipmentStateSnapshot.from_mapping(state_payload)
    request_payload: dict[str, Any] = {
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id,
        "failure_mode": "explicit_failed_opening",
        "failure_opening_diameter_m": args.failure_opening_diameter_m,
        "horizon_s": args.horizon_s,
        "position_enu_m": position_enu_m,
        # Use a horizontal side outlet for the generic outdoor consequence
        # chain.  A downward/vertical outlet requires an explicit provider
        # vertical-handoff packet and is intentionally not inferred here.
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "lh2dt.LayeredTank.export_accident_history native liquid outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "LayeredTank",
        "model_revision": args.model_revision,
        "state_snapshot_digest": snapshot.digest(),
        "state_snapshot": snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "native external LayeredTank accident export; synthetic geometry and state",
        "provider_termination_required": True,
    }
    if args.isolation_time_s is not None:
        request_payload["isolation_time_s"] = args.isolation_time_s
        request_payload["post_isolation_observation_s"] = args.post_isolation_observation_s
    request = AccidentReleaseExportRequest.from_mapping(request_payload)
    native_request = {
        "event_id": event_id,
        "component_id": component_id,
        "port_id": port_id,
        "initial_pressure_pa_abs": args.initial_pressure_pa_abs,
        "liquid_volume_fraction": args.liquid_volume_fraction,
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "failure_opening_diameter_m": args.failure_opening_diameter_m,
        "discharge_coefficient": args.discharge_coefficient,
        "horizon_s": args.horizon_s,
        "time_step_s": args.time_step_s,
        "minimum_step_s": args.minimum_step_s,
        "impact_position_m": position_enu_m,
        "direction_enu": [1.0, 0.0, 0.0],
        "provider_source_digest": source_digest,
        "state_snapshot_digest": snapshot.digest(),
    }
    if request.isolation_time_s is not None:
        # Use the validated request values so the provider receives exactly
        # the controls that PRISM will later require it to echo.
        native_request["isolation_time_s"] = request.isolation_time_s
        native_request["post_isolation_observation_s"] = request.post_isolation_observation_s
    native_response = tank.export_accident_history(native_request)
    provider = NativeLayeredTankProvider(native_response)
    result = export_equipment_liquid_accident_history(provider, request)
    release = result.release.model_dump(mode="json")
    data = native_response["data"]
    provider_meta = data.get("provider_meta") if isinstance(data.get("provider_meta"), Mapping) else {}
    closure_audit = dynamic_state_closure_status(release)
    declared_closure = provider_meta.get("dynamic_state_closure")
    verification = {
        "schema_version": "prism.native_lh2dt_layered_tank_packet_verification.v1",
        "status": "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC",
        "provider_model": native_response.get("provider_model"),
        "provider_export_schema": native_response.get("provider_export_schema"),
        "provider_source_digest": source_digest,
        "provider_result_digest": result.provider_result_digest,
        "provider_method": result.provider_method,
        "provider_packet_promoted": result.provider_packet_promoted,
        "termination_basis": data.get("termination_basis"),
        "duration_s": data.get("duration_s"),
        "available_mass_kg": data.get("available_mass_kg"),
        "cumulative_mass_out_kg": data.get("cumulative_mass_out_kg"),
        "mass_residual_kg": provider_meta.get("residual_mass_kg"),
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
        "distributed_boiling_model": args.distributed_boiling_model,
        "isolation_time_s": provider_meta.get("isolation_time_s"),
        "post_isolation_observation_s": provider_meta.get("post_isolation_observation_s"),
        "isolation_success": provider_meta.get("isolation_success"),
        "state_snapshot_digest_match": native_response.get("provider_state_snapshot_digest") == snapshot.digest(),
        # Keep the canonical process-state payload beside the provider packet.
        # The generic scope catalog consumes this verification record to bind
        # the release back to the exact initial tank state.  A digest alone is
        # deliberately insufficient for that audit, so the payload and the
        # provider echo are both persisted here.
        "state_snapshot": snapshot.to_mapping(),
        "state_snapshot_handoff": {
            "present": True,
            "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
            "digest": snapshot.digest(),
            "provider_echo_digest": native_response.get("provider_state_snapshot_digest"),
            "digest_match": native_response.get("provider_state_snapshot_digest") == snapshot.digest(),
        },
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic geometry, inventory and atmospheric boundary",
            "native provider history is diagnostic evidence until independent qualification is supplied",
            "state snapshot mass is a handoff metadata value; native provider owns the exact inventory ledger",
        ],
    }
    _save(args.output_dir / "provider_response.json", native_response)
    _save(args.output_dir / "resolved_release.json", release)
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--component-id", default="native-layered-tank-diagnostic")
    parser.add_argument("--port-id", default="native-layered-tank-liquid-out")
    parser.add_argument("--event-id", default="native-layered-tank/accidental-leak-001")
    parser.add_argument("--model-revision", default="external-library-native-export-0.1.2")
    parser.add_argument(
        "--distributed-boiling-model",
        choices=("phase_change_complementarity", "saturated_liquid_complementarity", "off"),
        default="phase_change_complementarity",
        help=(
            "lh2dt phase-transfer closure used while depressurising the tank; "
            "the explicit complementarity default prevents a vapor cell from "
            "crossing into the saturation band without a phase-transfer ledger"
        ),
    )
    parser.add_argument("--initial-pressure-pa-abs", type=float, default=500000.0)
    parser.add_argument("--liquid-volume-fraction", type=float, default=0.43)
    parser.add_argument("--ambient-pressure-pa-abs", type=float, default=101325.0)
    parser.add_argument("--ambient-temperature-k", type=float, default=288.15)
    parser.add_argument("--failure-opening-diameter-m", type=float, default=1.0e-3)
    parser.add_argument("--discharge-coefficient", type=float, default=0.7)
    parser.add_argument("--horizon-s", type=float, default=0.05)
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--minimum-step-s", type=float, default=None)
    parser.add_argument("--isolation-time-s", type=float, default=None)
    parser.add_argument("--post-isolation-observation-s", type=float, default=0.0)
    parser.add_argument("--nozzle-height-m", type=float, default=0.5)
    parser.add_argument(
        "--position-enu-m", type=float, nargs=3, default=None,
        help="absolute ENU release position; defaults to the origin with nozzle height",
    )
    args = parser.parse_args()
    try:
        result = run(args)
    except (ImportError, KeyError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"native LayeredTank PRISM export failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "termination_basis": result["termination_basis"],
        "duration_s": result["duration_s"],
        "isolation_success": result["isolation_success"],
        "output": str(args.output_dir.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
