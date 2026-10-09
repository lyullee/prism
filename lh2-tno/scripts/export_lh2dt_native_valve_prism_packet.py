"""Export a native ``lh2dt.StrokeLimitedCommandedValve`` history into PRISM.

The external valve owns the gas-orifice calculation and the finite actuator
stroke.  This adapter supplies an explicit upstream inventory ledger and a
bounded diagnostic horizon, then sends the native history through PRISM's
strict gas-release boundary.  A valve has no inventory or isolation model of
its own, so the default termination remains ``synthetic_diagnostic_horizon``.
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
    export_equipment_gas_accident_history,
)
from lh2_tno.contracts import canonical_digest  # noqa: E402
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


class NativeStrokeValveProvider:
    """Delegate one native valve response without recalculating its history."""

    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = dict(response)

    def _strict_response(self) -> dict[str, Any]:
        """Adapt the native helper's optional source trace to PRISM's schema.

        The current external fixed-source helper records a compact source trace
        (including ``opening`` and ``choked``) but does not yet provide the
        complete ``ProviderSourceState`` record required by PRISM.  Preserve
        the untouched native response on disk and remove only that optional
        trace from the strict handoff until the external schema is expanded.
        """
        response = json.loads(json.dumps(self.response, allow_nan=False))
        data = response.get("data", {})
        for step in data.get("steps", []):
            if isinstance(step, dict):
                step.pop("provider_source_state", None)
        return response

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if request.get("event_id") != self.response.get("data", {}).get("event_id"):
            raise ValueError("native provider event_id does not match PRISM request")
        if request.get("component_id") != self.response.get("data", {}).get("component_id"):
            raise ValueError("native provider component_id does not match PRISM request")
        if request.get("port_id") != self.response.get("data", {}).get("port_id"):
            raise ValueError("native provider port_id does not match PRISM request")
        return self._strict_response()


def _native_valve(
    lh2dt_root: Path,
    *,
    opening_diameter_m: float,
    discharge_coefficient: float,
    stroke_time_s: float,
) -> tuple[Any, Any]:
    sys.path.insert(0, str(lh2dt_root / "src"))
    module = importlib.import_module("lh2dt")
    properties = module.HydrogenProperties("Hydrogen")
    area = 3.141592653589793 * opening_diameter_m**2 / 4.0
    valve = module.Valve(
        area,
        discharge_coefficient,
        properties=properties,
        allow_reverse=False,
    )
    actuator = module.StrokeLimitedCommandedValve(
        valve,
        stroke_time_s=stroke_time_s,
        initial_opening=0.0,
    )
    actuator.set_target_opening(1.0)
    return actuator, properties


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    if args.time_step_s <= 0.0 or args.horizon_s <= 0.0:
        raise ValueError("horizon and time step must be positive")
    if args.time_step_s > args.horizon_s:
        raise ValueError("time step must not exceed horizon")
    source_digest = _tree_digest(root)
    valve, properties = _native_valve(
        root,
        opening_diameter_m=args.failure_opening_diameter_m,
        discharge_coefficient=args.discharge_coefficient,
        stroke_time_s=args.stroke_time_s,
    )
    source_state = properties.from_pT(args.source_pressure_pa_abs, args.source_temperature_k)
    phase = str(source_state.phase).lower()
    if "gas" not in phase and "vapour" not in phase and "supercritical" not in phase:
        raise ValueError("native StrokeLimitedCommandedValve diagnostic requires a gas-like source state")
    snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": args.component_id,
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": args.source_pressure_pa_abs,
        "temperature_k": args.source_temperature_k,
        "mass_kg": args.available_mass_kg,
        "phase": "vapour",
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "measurements": {
            "upstream_pressure": {
                "quantity": "pressure",
                "value_si": args.source_pressure_pa_abs,
                "sensor_location": f"{args.component_id}.upstream",
            },
            "upstream_temperature": {
                "quantity": "temperature",
                "value_si": args.source_temperature_k,
                "sensor_location": f"{args.component_id}.upstream",
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
        "provider_boundary_reference": "lh2dt.StrokeLimitedCommandedValve.export_accident_history native gas outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "StrokeLimitedCommandedValve",
        "model_revision": args.model_revision,
        "state_snapshot_digest": snapshot.digest(),
        "state_snapshot": snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "native external StrokeLimitedCommandedValve gas export; synthetic upstream state and reserve",
        "provider_termination_required": True,
    })
    native_request: dict[str, Any] = {
        "event_id": args.event_id,
        "component_id": args.component_id,
        "port_id": args.port_id,
        "failure_mode": "explicit_failed_opening",
        "source_pressure_pa_abs": args.source_pressure_pa_abs,
        "source_temperature_k": args.source_temperature_k,
        "ambient_pressure_pa_abs": args.ambient_pressure_pa_abs,
        "ambient_temperature_k": args.ambient_temperature_k,
        "failure_opening_diameter_m": args.failure_opening_diameter_m,
        "horizon_s": args.horizon_s,
        "time_step_s": args.time_step_s,
        "available_mass_kg": args.available_mass_kg,
        "termination_basis": "synthetic_diagnostic_horizon",
        "termination_provenance": "operator-declared bounded valve horizon; upstream reserve remains explicit",
        "provider_source_digest": source_digest,
        "state_snapshot_digest": snapshot.digest(),
    }
    native_response = valve.export_accident_history(native_request)
    result = export_equipment_gas_accident_history(
        NativeStrokeValveProvider(native_response), request
    )
    data = native_response["data"]
    provider_meta = data.get("provider_meta") if isinstance(data.get("provider_meta"), Mapping) else {}
    verification = {
        "schema_version": "prism.native_lh2dt_stroke_valve_packet_verification.v1",
        "status": "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC",
        "provider_model": native_response.get("provider_model"),
        "provider_export_schema": native_response.get("provider_export_schema"),
        "provider_method": result.provider_method,
        "provider_source_digest": source_digest,
        "provider_result_digest": result.provider_result_digest,
        "native_provider_result_digest": canonical_digest(native_response),
        "native_source_trace_preserved_out_of_band": True,
        "provider_packet_promoted": result.provider_packet_promoted,
        "phase_basis": data.get("provider_meta", {}).get("initial_source_phase") if isinstance(data.get("provider_meta"), Mapping) else None,
        "termination_basis": data.get("termination_basis"),
        "duration_s": data.get("duration_s"),
        "available_mass_kg": data.get("available_mass_kg"),
        "cumulative_mass_out_kg": data.get("cumulative_mass_out_kg"),
        "upstream_reserve_remaining_kg": float(data.get("available_mass_kg", 0.0)) - float(data.get("cumulative_mass_out_kg", 0.0)),
        "final_opening": provider_meta.get("valve", {}).get("final_opening") if isinstance(provider_meta.get("valve"), Mapping) else None,
        "choked_intervals": provider_meta.get("valve", {}).get("choked_intervals") if isinstance(provider_meta.get("valve"), Mapping) else None,
        "state_snapshot_digest_match": native_response.get("provider_state_snapshot_digest") == snapshot.digest(),
        "physical_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic gas source state, valve geometry and upstream reserve",
            "StrokeLimitedCommandedValve owns no upstream inventory or isolation reliability",
            "native compact source trace is preserved in provider_response.json but is not promoted into the strict packet until its schema is expanded",
            "bounded diagnostic horizon leaves explicit reserve and is not a qualified facility frequency case",
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
    parser.add_argument("--component-id", default="native-stroke-valve-diagnostic")
    parser.add_argument("--port-id", default="native-stroke-valve-gas-out")
    parser.add_argument("--event-id", default="native-stroke-valve/accidental-leak-001")
    parser.add_argument("--model-revision", default="external-library-native-export-0.1.2")
    parser.add_argument("--source-pressure-pa-abs", type=float, default=500000.0)
    parser.add_argument("--source-temperature-k", type=float, default=300.0)
    parser.add_argument("--ambient-pressure-pa-abs", type=float, default=101325.0)
    parser.add_argument("--ambient-temperature-k", type=float, default=288.15)
    parser.add_argument("--failure-opening-diameter-m", type=float, default=0.0025)
    parser.add_argument("--discharge-coefficient", type=float, default=0.8)
    parser.add_argument("--stroke-time-s", type=float, default=0.05)
    parser.add_argument("--horizon-s", type=float, default=0.1)
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--available-mass-kg", type=float, default=100.0)
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    args = parser.parse_args()
    try:
        result = run(args)
    except (ImportError, KeyError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"native StrokeLimitedCommandedValve PRISM export failed: {error}") from error
    print(json.dumps({
        "status": result["status"],
        "phase_basis": result["phase_basis"],
        "termination_basis": result["termination_basis"],
        "duration_s": result["duration_s"],
        "output": str(args.output_dir.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
