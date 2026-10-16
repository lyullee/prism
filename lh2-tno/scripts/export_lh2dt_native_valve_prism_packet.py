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
from lh2_tno.compressible_handoff import attach_compressible_plane_handoff  # noqa: E402
from lh2_tno.compressible_source_adapter import build_compressible_plane_handoff  # noqa: E402
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
        """Pass the native source/throat state through without recalculation."""
        response = json.loads(json.dumps(self.response, allow_nan=False))
        # ``opening`` is a native actuator diagnostic, not part of PRISM's
        # ProviderSourceState contract.  Keep it in provider_response.json but
        # remove only this extra key before strict Pydantic validation.
        for step in response.get("data", {}).get("steps", []):
            if isinstance(step, dict) and isinstance(step.get("provider_source_state"), dict):
                step["provider_source_state"].pop("opening", None)
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
    strict_provider_response = NativeStrokeValveProvider(native_response)._strict_response()
    result = export_equipment_gas_accident_history(
        NativeStrokeValveProvider(native_response), request
    )
    data = native_response["data"]
    provider_meta = data.get("provider_meta") if isinstance(data.get("provider_meta"), Mapping) else {}
    source_states = [
        step.get("provider_source_state")
        for step in data.get("steps", [])
        if isinstance(step, Mapping)
    ]
    native_source_state_complete = bool(source_states) and all(
        isinstance(state, Mapping)
        and all(
            state.get(field) is not None
            for field in (
                "source_specific_entropy_j_kgk",
                "throat_pressure_pa_abs",
                "throat_density_kg_m3",
                "throat_specific_enthalpy_j_kg",
            )
        )
        for state in source_states
    )
    verification = {
        "schema_version": "prism.native_lh2dt_stroke_valve_packet_verification.v1",
        "status": "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC",
        "provider_model": native_response.get("provider_model"),
        "provider_export_schema": native_response.get("provider_export_schema"),
        "provider_method": result.provider_method,
        "provider_source_digest": source_digest,
        "provider_result_digest": result.provider_result_digest,
        "native_provider_result_digest": canonical_digest(native_response),
        "strict_provider_result_digest": canonical_digest(strict_provider_response),
        "native_source_trace_preserved_in_packet": True,
        "source_state_completion": {
            "status": (
                "PROVIDER_NATIVE_SOURCE_THROAT_FIELDS"
                if native_source_state_complete else "INCOMPLETE"
            ),
            "interval_count": len(source_states),
            "inference_performed": False,
            "provenance": "external native ValveResult throat pressure and provider property state",
        },
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
        "compressible_handoff_requested": args.compressible_handoff,
        "compressible_handoff_generated": False,
        "limitations": [
            "synthetic gas source state, valve geometry and upstream reserve",
            "StrokeLimitedCommandedValve owns no upstream inventory or isolation reliability",
            "native source entropy and hydraulic throat state are preserved in the strict packet; this is not an expansion/mixing solution",
            "bounded diagnostic horizon leaves explicit reserve and is not a qualified facility frequency case",
        ],
    }
    _save(args.output_dir / "provider_response.json", native_response)
    _save(args.output_dir / "provider_response_strict.json", strict_provider_response)
    _save(args.output_dir / "resolved_release.json", result.release.model_dump(mode="json"))
    if args.compressible_handoff:
        handoff_source_digest = canonical_digest({
            "prism_adapter": "export_lh2dt_native_valve_prism_packet",
            "adapter_revision": args.model_revision,
            "lh2dt_source_digest": source_digest,
        })
        handoff_result = build_compressible_plane_handoff(
            result.release,
            strict_provider_response,
            properties=properties,
            algorithm=args.handoff_algorithm,
            adapter_source_digest=handoff_source_digest,
            evidence_status="synthetic_diagnostic",
        )
        attached_packet, handoff_audit = attach_compressible_plane_handoff(
            result.release.model_dump(mode="json"),
            handoff_result.export,
        )
        _save(args.output_dir / "compressible_handoff.json", handoff_result.export)
        _save(args.output_dir / "compressible_handoff_audit.json", handoff_result.audit)
        _save(args.output_dir / "resolved_release_with_handoff.json", attached_packet)
        _save(args.output_dir / "handoff_attach_audit.json", handoff_audit)
        verification["compressible_handoff_generated"] = True
        verification["compressible_handoff_algorithm"] = args.handoff_algorithm
        verification["compressible_handoff_state_count"] = handoff_audit["handoff_state_count"]
        verification["compressible_handoff_provider_qualified"] = False
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
    parser.add_argument(
        "--compressible-handoff",
        action="store_true",
        help=(
            "also build and attach a source-state-bound compressible plane handoff; "
            "the result remains synthetic diagnostic evidence"
        ),
    )
    parser.add_argument(
        "--handoff-algorithm",
        choices=("birch_momentum_energy", "birch_momentum_isentropic"),
        default="birch_momentum_energy",
    )
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
