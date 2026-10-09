"""Export an explicit ``lh2dt.VentStack`` atmospheric gas outlet as PRISM.

``VentStack.evaluate`` is a steady two-port calculation.  This adapter only
uses it inside an explicitly bounded diagnostic horizon and repeats the
provider result as a left-held gas history.  The horizon is therefore
declared as synthetic; PRISM never treats the steady result as an inventory
depletion or as a field vent frequency.
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

from lh2_tno.equipment_accident_export import (  # noqa: E402
    EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
    EmergencyReliefExportRequest,
    export_equipment_emergency_relief_history,
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


def _request(*, source_digest: str, component_id: str, port_id: str | None, event_id: str | None, state_snapshot: EquipmentStateSnapshot, height_m: float, revision: str) -> EmergencyReliefExportRequest:
    port_id = port_id or f"{component_id}.accident-out"
    return EmergencyReliefExportRequest.from_mapping({
        "schema_version": "prism.equipment_emergency_relief_export_request.v1",
        "event_kind": "emergency_relief",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id or f"{component_id}/{port_id}/maximum-relief-discharge",
        "horizon_s": 600.0,
        "position_enu_m": [0.0, 0.0, height_m],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "lh2dt VentStack explicit atmospheric outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "VentStack",
        "model_revision": revision,
        "state_snapshot_digest": state_snapshot.digest(),
        "state_snapshot": state_snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit external VentStack maximum-relief-discharge diagnostic over bounded horizon; not site-calibrated",
        "provider_termination_required": True,
    })


class VentStackAccidentProvider:
    """Run one explicit VentStack two-port state over a bounded clock."""

    def __init__(self, root: Path, *, duration_s: float, time_step_s: float, stack: dict[str, Any], upstream: dict[str, float], ambient_temperature_k: float) -> None:
        self.root = root.resolve()
        self.duration_s = float(duration_s)
        self.time_step_s = float(time_step_s)
        self.stack = dict(stack)
        self.upstream = dict(upstream)
        self.ambient_temperature_k = float(ambient_temperature_k)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.duration_s <= 0.0 or self.time_step_s <= 0.0:
            raise ValueError("VentStack diagnostic duration and time step must be positive")
        if not math.isclose(self.duration_s / self.time_step_s, round(self.duration_s / self.time_step_s), rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("VentStack duration must be an integer number of time steps")
        sys.path.insert(0, str(self.root / "src"))
        from lh2dt.properties import HydrogenProperties
        from lh2dt.vent_stack import VentStack

        properties = HydrogenProperties("Hydrogen")
        ambient_pressure = float(request["ambient_pressure_pa_abs"])
        upstream = properties.from_pT(float(self.upstream["pressure_pa"]), float(self.upstream["temperature_k"]))
        downstream = properties.saturated_vapor(ambient_pressure)
        stack = VentStack(**self.stack, ambient_temperature_K=self.ambient_temperature_k, properties=properties)
        hydraulic = stack.evaluate(upstream, downstream)
        flow = float(hydraulic.mass_flow_kg_s)
        if not math.isfinite(flow) or flow <= 0.0:
            raise ValueError("VentStack diagnostic did not produce a positive outward flow")
        outlet = properties.from_ph(ambient_pressure, float(hydraulic.outlet_specific_enthalpy_J_kg))
        area = math.pi * float(self.stack["inner_diameter_m"])**2 / 4.0
        density = float(outlet.density_kg_m3)
        velocity = flow / (density * area)
        intervals = int(round(self.duration_s / self.time_step_s))
        steps = [{
            "time_s": index * self.time_step_s,
            "mass_flow_kg_s": flow,
            "pressure_pa_abs": ambient_pressure,
            "specific_enthalpy_j_kg": float(outlet.specific_enthalpy_J_kg),
            "temperature_k": float(outlet.temperature_K),
            "density_kg_m3": density,
            "effective_area_m2": area,
            "velocity_m_s": velocity,
            "area_provenance": "external VentStack inner bore",
            "velocity_origin": "mass_continuity_from_declared_area",
        } for index in range(intervals)]
        cumulative_mass = flow * self.duration_s
        cumulative_enthalpy = cumulative_mass * float(outlet.specific_enthalpy_J_kg)
        data = {
            "event_kind": "emergency_relief",
            "event_id": request["event_id"],
            "component_id": request["component_id"],
            "port_id": request["port_id"],
            "duration_s": self.duration_s,
            "available_mass_kg": cumulative_mass * 1.2,
            "cumulative_mass_out_kg": cumulative_mass,
            "cumulative_static_enthalpy_out_j": cumulative_enthalpy,
            "termination_provenance": "external VentStack bounded diagnostic horizon; steady two-port inventory is not depleted",
            "termination_basis": "emergency_relief_discharge",
            "fluid": "Hydrogen",
            "steps": steps,
            "provider_meta": {
                "hydraulic": {
                    "mass_flow_kg_s": flow,
                    "reynolds_number": float(hydraulic.reynolds_number),
                    "pressure_drop_pa": float(hydraulic.pressure_drop_Pa),
                },
                "upstream": dict(self.upstream),
                "downstream_pressure_pa": ambient_pressure,
                "model_class": "lh2dt.VentStack",
            },
        }
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_state_snapshot_digest": request["state_snapshot_digest"],
            "provider_model": "lh2dt.VentStack",
            "provider_source_digest": request["provider_source_digest"],
            "data": data,
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    component_id = args.component_id
    stack = {
        "length_m": args.length_m,
        "inner_diameter_m": args.inner_diameter_m,
        "roughness_m": args.roughness_m,
        "local_loss_coefficient": args.local_loss_coefficient,
        "elevation_change_m": args.elevation_change_m,
        "ambient_UA_W_K": args.ambient_ua_w_k,
        "integration_segments": args.integration_segments,
    }
    upstream = {"pressure_pa": args.inlet_pressure_pa, "temperature_k": args.inlet_temperature_k}
    state_snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": component_id,
        "captured_at_s": 0.0,
        "origin": "synthetic",
        "pressure_pa_abs": args.inlet_pressure_pa,
        "temperature_k": args.inlet_temperature_k,
        "phase": "vapour",
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "source_digest": source_digest,
    })
    request = _request(source_digest=source_digest, component_id=component_id, port_id=args.port_id, event_id=args.event_id, state_snapshot=state_snapshot, height_m=args.nozzle_height_m, revision=args.model_revision)
    provider = VentStackAccidentProvider(root, duration_s=args.duration_s, time_step_s=args.time_step_s, stack=stack, upstream=upstream, ambient_temperature_k=args.ambient_temperature_k)
    result = export_equipment_emergency_relief_history(provider, request)
    release = result.release.model_dump(mode="json")
    verification = {
        "status": "EXTERNAL_LH2DT_VENT_STACK_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "provider_model": "lh2dt.VentStack",
        "provider_result_digest": result.provider_result_digest,
        "state_snapshot": result.request.state_snapshot.to_mapping() if result.request.state_snapshot else None,
        "state_snapshot_handoff": {
            "present": result.request.state_snapshot is not None,
            "digest": result.request.state_snapshot_digest,
            "provider_echo_digest": result.provider_response.get("provider_state_snapshot_digest"),
            "digest_match": result.provider_response.get("provider_state_snapshot_digest") == result.request.state_snapshot_digest,
        },
        "strict_packet_duration_s": result.release.duration_s,
        "strict_packet_interval_count": len(result.release.steps),
        "strict_packet_mass_residual_kg": result.release.cumulative_mass_out_kg - result.release.integrated_mass_kg,
        "strict_packet_energy_residual_j": result.release.cumulative_static_enthalpy_out_j - result.release.integrated_static_enthalpy_j,
        "provider_packet_promoted": result.provider_packet_promoted,
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "limitations": [
            "steady VentStack two-port result repeated over a synthetic diagnostic horizon",
            "synthetic upstream pressure/temperature, geometry and atmospheric boundary",
            "no tank inventory feedback, relief setpoint or site calibration",
        ],
    }
    _save(args.output_dir / "provider_response.json", result.provider_response)
    _save(args.output_dir / "resolved_release.json", release)
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a VentStack diagnostic outlet into PRISM")
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=0.5)
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--length-m", type=float, default=1.0)
    parser.add_argument("--inner-diameter-m", type=float, default=0.01)
    parser.add_argument("--roughness-m", type=float, default=1.0e-6)
    parser.add_argument("--local-loss-coefficient", type=float, default=1.0)
    parser.add_argument("--elevation-change-m", type=float, default=0.0)
    parser.add_argument("--ambient-ua-w-k", type=float, default=0.0)
    parser.add_argument("--integration-segments", type=int, default=64)
    parser.add_argument("--inlet-pressure-pa", type=float, default=102000.0)
    parser.add_argument("--inlet-temperature-k", type=float, default=40.0)
    parser.add_argument("--ambient-temperature-k", type=float, default=288.15)
    parser.add_argument("--nozzle-height-m", type=float, default=2.0)
    parser.add_argument("--component-id", default="vent-stack-diagnostic")
    parser.add_argument("--event-id", default=None, help="optional exact worklist event id for a structural diagnostic")
    parser.add_argument("--port-id", default=None, help="optional exact facility accident port id")
    parser.add_argument("--model-revision", default="external-library-vent-stack-0.1.1")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(f"VentStack PRISM accident export failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
