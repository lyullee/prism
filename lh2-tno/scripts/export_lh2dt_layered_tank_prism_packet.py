"""Export an explicit ``lh2dt.LayeredTank`` inventory accident as a PRISM packet.

The external layered-tank diagnostic already advances the tank state, solves a
commanded liquid outlet, and stops at a declared positive inventory threshold.
This wrapper changes only the transport envelope: its interval-average
provider ledger becomes the strict ``prism.external_accident_history.v1``
request/response consumed by PRISM.  It does not infer an opening, extend the
history, or turn the result into a qualified facility packet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lh2_tno.equipment_accident_export import (  # noqa: E402
    EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
    AccidentReleaseExportRequest,
    export_equipment_liquid_accident_history,
)
from lh2_tno.state_snapshot import (  # noqa: E402
    EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
    EquipmentStateSnapshot,
)
from validate_layered_tank_inventory_slabsx import _run_provider  # noqa: E402


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


def _request(
    *,
    provider_source_digest: str,
    component_id: str,
    port_id: str,
    event_id: str,
    opening_diameter_m: float,
    position_enu_m: list[float],
    direction_enu: list[float],
    model_revision: str,
    state_snapshot: EquipmentStateSnapshot,
) -> AccidentReleaseExportRequest:
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id,
        "failure_mode": "explicit_failed_opening",
        "failure_opening_diameter_m": opening_diameter_m,
        "horizon_s": 600.0,
        "position_enu_m": position_enu_m,
        "direction_enu": direction_enu,
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": provider_source_digest,
        "provider_boundary_reference": "lh2dt LayeredTank explicit liquid accidental outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "LayeredTankNetworkSimulator+CommandedValve",
        "model_revision": model_revision,
        "state_snapshot_digest": state_snapshot.digest(),
        "state_snapshot": state_snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit external LayeredTank inventory-threshold diagnostic; not site-calibrated",
        "provider_termination_required": True,
    })


class LayeredTankAccidentProvider:
    """Provider adapter that owns the LayeredTank state and termination clock."""

    def __init__(
        self,
        lh2dt_root: Path,
        *,
        time_step_s: float,
        target_release_kg: float,
        max_intervals: int,
        full_open_area_m2: float,
        request: AccidentReleaseExportRequest,
        provider_export: Mapping[str, Any],
    ) -> None:
        self.lh2dt_root = lh2dt_root.resolve()
        self.time_step_s = float(time_step_s)
        self.target_release_kg = float(target_release_kg)
        self.max_intervals = int(max_intervals)
        self.full_open_area_m2 = float(full_open_area_m2)
        self.request = request
        self.provider_export = dict(provider_export)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if request["event_id"] != self.request.event_id:
            raise ValueError("LayeredTank provider event does not match accident request")
        export = dict(self.provider_export)
        meta = {
            "status": "PRECOMPUTED_EXTERNAL_LAYERED_TANK_EXPORT",
            "source_state_snapshot_digest": request["state_snapshot_digest"],
        }
        raw_steps = export["steps"]
        if not raw_steps:
            raise ValueError("LayeredTank provider returned no accident intervals")
        steps: list[dict[str, Any]] = []
        previous_time = 0.0
        for raw in raw_steps:
            endpoint_time = float(raw["time_s"])
            if endpoint_time <= previous_time:
                raise ValueError("LayeredTank provider interval clock is not increasing")
            flow = raw["flow"]
            mass_flow = float(flow["mass_flow_kg_s"])
            enthalpy = float(flow["transmitted_specific_enthalpy_J_kg"])
            if mass_flow < 0.0 or not math.isfinite(mass_flow):
                raise ValueError("LayeredTank provider returned an invalid outward flow")
            steps.append({
                "time_s": previous_time,
                "total_mass_flow_kg_s": mass_flow,
                "gas_mass_flow_kg_s": 0.0,
                "ground_liquid_mass_flow_kg_s": mass_flow,
                "airborne_liquid_mass_flow_kg_s": 0.0,
                "specific_enthalpy_j_kg": enthalpy,
                "droplet_class_outcomes": [{
                    "ground_liquid_mass_flow_kg_s": mass_flow,
                    "airborne_liquid_mass_flow_kg_s": 0.0,
                    "flight_time_s": 0.0,
                    "impact_position_m": [0.0, 0.0, 0.0],
                    "droplet_diameter_m": 0.001,
                }],
            })
            previous_time = endpoint_time
        if not math.isclose(previous_time, float(export["duration_s"]), abs_tol=1.0e-10):
            raise ValueError("LayeredTank provider duration disagrees with interval clock")
        data = {
            "event_kind": "accidental_leak",
            "event_id": request["event_id"],
            "component_id": request["component_id"],
            "port_id": request["port_id"],
            "duration_s": float(export["duration_s"]),
            "available_mass_kg": float(export["available_mass_kg"]),
            "cumulative_mass_out_kg": float(export["cumulative_mass_out_kg"]),
            "termination_provenance": export["termination_provenance"],
            "termination_basis": export["termination_basis"],
            "upstream_service": "LH2",
            "fluid": "Hydrogen",
            "phase_basis": "liquid",
            "reference_area_m2": self.full_open_area_m2,
            "reference_area_provenance": "external LayeredTank commanded-valve full-opening area",
            "cumulative_specific_enthalpy_out_j": float(export["cumulative_specific_enthalpy_out_j"]),
            "droplet_partition_provenance": "provider liquid-port ground interception; no airborne-liquid promotion",
            "steps": steps,
            "provider_meta": meta,
        }
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_model": "lh2dt.LayeredTankNetworkSimulator+CommandedValve",
            "provider_source_digest": request["provider_source_digest"],
            "provider_state_snapshot_digest": request["state_snapshot_digest"],
            "data": data,
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    opening_diameter_m = math.sqrt(4.0 * args.full_open_area_m2 / math.pi)
    component_id = args.component_id
    port_id = args.port_id or f"{component_id}.accident-out"
    event_id = args.event_id or f"{component_id}/{port_id}/{opening_diameter_m:.12g}m"
    direction = [1.0 / math.sqrt(2.0), 0.0, -1.0 / math.sqrt(2.0)]
    provider_export, provider_meta = _run_provider(
        root,
        time_step_s=args.time_step_s,
        target_release_kg=args.target_release_kg,
        max_intervals=args.max_intervals,
        full_open_area_m2=args.full_open_area_m2,
    )
    initial_state = provider_export["initial_state"]
    state_snapshot = EquipmentStateSnapshot(
        schema_version=EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        component_id=component_id,
        captured_at_s=0.0,
        origin="model_prediction",
        pressure_pa_abs=float(initial_state["pressure_pa_abs"]),
        temperature_k=float(initial_state["temperature_k"]),
        mass_kg=float(initial_state["mass_kg"]),
        phase="liquid" if initial_state.get("phase") == "liquid" else "unknown",
        position_enu_m=(0.0, 0.0, float(args.nozzle_height_m)),
        measurements={
            "initial_pressure": {
                "quantity": "pressure",
                "value_si": float(initial_state["pressure_pa_abs"]),
                "sensor_location": f"{component_id}.liquid_cell_0",
            },
            "initial_temperature": {
                "quantity": "temperature",
                "value_si": float(initial_state["temperature_k"]),
                "sensor_location": f"{component_id}.liquid_cell_0",
            },
            "initial_mass": {
                "quantity": "mass",
                "value_si": float(initial_state["mass_kg"]),
                "sensor_location": f"{component_id}.inventory",
            },
        },
    )
    request = _request(
        provider_source_digest=source_digest,
        component_id=component_id,
        port_id=port_id,
        event_id=event_id,
        opening_diameter_m=opening_diameter_m,
        position_enu_m=[0.0, 0.0, args.nozzle_height_m],
        direction_enu=direction,
        model_revision=args.model_revision,
        state_snapshot=state_snapshot,
    )
    provider = LayeredTankAccidentProvider(
        root,
        time_step_s=args.time_step_s,
        target_release_kg=args.target_release_kg,
        max_intervals=args.max_intervals,
        full_open_area_m2=args.full_open_area_m2,
        request=request,
        provider_export=provider_export,
    )
    result = export_equipment_liquid_accident_history(provider, request)
    release = result.release.model_dump(mode="json")
    response = result.provider_response
    verification = {
        "status": "EXTERNAL_LH2DT_LAYERED_TANK_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "provider_model": "lh2dt.LayeredTankNetworkSimulator+CommandedValve",
        "provider_result_digest": result.provider_result_digest,
        "provider_run_meta": provider_meta,
        "strict_packet_duration_s": result.release.duration_s,
        "strict_packet_mass_residual_kg": result.release.cumulative_mass_out_kg - result.release.integrated_mass_kg,
        "strict_packet_energy_residual_j": result.release.cumulative_specific_enthalpy_out_j - result.release.integrated_specific_enthalpy_out_j,
        "provider_packet_promoted": result.provider_packet_promoted,
        "state_snapshot_handoff": {
            "present": result.request.state_snapshot is not None,
            "schema_version": (
                None if result.request.state_snapshot is None
                else result.request.state_snapshot.schema_version
            ),
            "digest": result.request.state_snapshot_digest,
            "provider_echo_digest": response.get("provider_state_snapshot_digest"),
            "digest_match": response.get("provider_state_snapshot_digest") == result.request.state_snapshot_digest,
        },
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic LayeredTank geometry, opening and atmospheric boundary",
            "liquid-port ground interception is explicit; flash and airborne-liquid physics are not supplied",
            "provider packet remains synthetic_diagnostic and is not a qualified facility release",
        ],
    }
    _save(args.output_dir / "provider_response.json", response)
    _save(args.output_dir / "resolved_release.json", release)
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a LayeredTank inventory accident into PRISM")
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--target-release-kg", type=float, default=1.0e-4)
    parser.add_argument("--max-intervals", type=int, default=64)
    parser.add_argument("--full-open-area-m2", type=float, default=1.0e-8)
    parser.add_argument("--component-id", default="layered-tank-diagnostic")
    parser.add_argument(
        "--port-id",
        help="Optional accident port identity to preserve when exporting a worklist item.",
    )
    parser.add_argument(
        "--event-id",
        help="Optional event identity to preserve when exporting a worklist item.",
    )
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    parser.add_argument("--model-revision", default="external-library-layered-tank-0.1.1")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(f"LayeredTank PRISM accident export failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
