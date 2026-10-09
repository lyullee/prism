"""Export one explicit ``lh2dt.DynamicHEMPipe`` full-bore outlet as a PRISM packet.

The external pipe model owns the finite-volume state, outlet flow and short
diagnostic clock.  This adapter adds only the explicit atmospheric boundary
and the strict ``prism.external_accident_history.v1`` envelope.  It never
turns a normal pipe snapshot into an accident or extends a provider history to
the requested horizon.
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


def _request(
    *,
    provider_source_digest: str,
    component_id: str,
    port_id: str,
    event_id: str,
    opening_diameter_m: float,
    position_enu_m: list[float],
    model_revision: str,
    state_snapshot: EquipmentStateSnapshot,
) -> AccidentReleaseExportRequest:
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id,
        "failure_mode": "explicit_full_bore_outlet",
        "failure_opening_diameter_m": opening_diameter_m,
        "horizon_s": 600.0,
        "position_enu_m": position_enu_m,
        "direction_enu": [0.9701425001453319, 0.0, -0.24253562503633297],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": provider_source_digest,
        "provider_boundary_reference": "lh2dt DynamicHEMPipe explicit full-bore atmospheric outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "DynamicHEMPipe",
        "model_revision": model_revision,
        "state_snapshot_digest": state_snapshot.digest(),
        "state_snapshot": state_snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit external DynamicHEMPipe full-bore diagnostic; not site-calibrated",
        "provider_termination_required": True,
    })


class DynamicPipeAccidentProvider:
    """Run the external finite-volume pipe for one explicit outlet scenario."""

    def __init__(
        self,
        lh2dt_root: Path,
        *,
        duration_s: float,
        time_step_s: float,
        length_m: float,
        inner_diameter_m: float,
        roughness_m: float,
        inlet_pressure_pa: float,
        inlet_temperature_k: float,
        wall_heat_capacity_j_k: float,
    ) -> None:
        self.lh2dt_root = lh2dt_root.resolve()
        self.duration_s = float(duration_s)
        self.time_step_s = float(time_step_s)
        self.length_m = float(length_m)
        self.inner_diameter_m = float(inner_diameter_m)
        self.roughness_m = float(roughness_m)
        self.inlet_pressure_pa = float(inlet_pressure_pa)
        self.inlet_temperature_k = float(inlet_temperature_k)
        self.wall_heat_capacity_j_k = float(wall_heat_capacity_j_k)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        opening = float(request["failure_opening_diameter_m"])
        if not math.isclose(opening, self.inner_diameter_m, rel_tol=0.0, abs_tol=1.0e-12):
            raise ValueError("provider full-bore diameter disagrees with accident request")
        if self.duration_s <= 0.0 or self.time_step_s <= 0.0:
            raise ValueError("provider diagnostic duration and time step must be positive")
        if not math.isclose(self.duration_s / self.time_step_s, round(self.duration_s / self.time_step_s), rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("provider duration must be an integer number of time steps")

        sys.path.insert(0, str(self.lh2dt_root / "src"))
        from lh2dt.dynamic_pipe import DynamicHEMPipe
        from lh2dt.properties import HydrogenProperties

        properties = HydrogenProperties("Hydrogen")
        pipe = DynamicHEMPipe(
            self.length_m,
            self.inner_diameter_m,
            self.roughness_m,
            self.wall_heat_capacity_j_k,
            properties=properties,
        )
        ambient_pressure = float(request["ambient_pressure_pa_abs"])
        ambient_temperature = float(request["ambient_temperature_k"])
        inlet = properties.from_pT(self.inlet_pressure_pa, self.inlet_temperature_k)
        outlet = properties.saturated_vapor(ambient_pressure)
        state = pipe.initialize(inlet)
        initial_mass = state.mass_kg
        area = math.pi * self.inner_diameter_m**2 / 4.0
        vapor = properties.saturated_vapor(ambient_pressure)
        steps: list[dict[str, Any]] = []
        cumulative_mass = 0.0
        cumulative_enthalpy = 0.0
        intervals = int(round(self.duration_s / self.time_step_s))
        time_s = 0.0
        for index in range(intervals):
            result = pipe.step(state, inlet, outlet, self.time_step_s)
            mass_flow = float(result.derivative.mass_flow_out_kg_s)
            if not math.isfinite(mass_flow) or mass_flow < 0.0:
                raise ValueError(f"DynamicHEMPipe returned invalid outward flow at interval {index}")
            enthalpy = float(result.fluid.specific_enthalpy_J_kg)
            exit_state = properties.from_ph(ambient_pressure, enthalpy)
            quality = exit_state.quality
            if quality is None or not 0.0 <= quality <= 1.0:
                raise ValueError("DynamicHEMPipe outlet is outside the liquid/two-phase atmospheric contract")
            gas_flow = mass_flow * float(quality)
            ground_flow = mass_flow - gas_flow
            cumulative_mass += mass_flow * self.time_step_s
            cumulative_enthalpy += mass_flow * self.time_step_s * enthalpy
            steps.append({
                "time_s": time_s,
                "total_mass_flow_kg_s": mass_flow,
                "gas_mass_flow_kg_s": gas_flow,
                "ground_liquid_mass_flow_kg_s": ground_flow,
                "airborne_liquid_mass_flow_kg_s": 0.0,
                "specific_enthalpy_j_kg": enthalpy,
                "gas_pressure_pa_abs": ambient_pressure,
                "gas_temperature_k": float(vapor.temperature_K),
                "gas_density_kg_m3": float(vapor.density_kg_m3),
                "gas_effective_area_m2": area,
                "gas_velocity_m_s": gas_flow / (vapor.density_kg_m3 * area) if gas_flow > 0.0 else 0.0,
                "gas_velocity_origin": "mass_continuity_from_declared_area",
                "droplet_class_outcomes": [{
                    "ground_liquid_mass_flow_kg_s": ground_flow,
                    "airborne_liquid_mass_flow_kg_s": 0.0,
                    "flight_time_s": 0.0,
                    "impact_position_m": [float(request["position_enu_m"][0]), float(request["position_enu_m"][1]), 0.0],
                    "droplet_diameter_m": 0.001,
                }],
            })
            state = result.state
            time_s += self.time_step_s
        if not math.isclose(time_s, self.duration_s, rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("DynamicHEMPipe provider clock disagrees with duration")
        data = {
            "event_kind": "accidental_leak",
            "event_id": request["event_id"],
            "component_id": request["component_id"],
            "port_id": request["port_id"],
            "duration_s": self.duration_s,
            "available_mass_kg": initial_mass,
            "cumulative_mass_out_kg": cumulative_mass,
            "termination_provenance": "external DynamicHEMPipe fixed diagnostic horizon; residual pipe inventory retained",
            "termination_basis": "synthetic_diagnostic_horizon",
            "upstream_service": "LH2",
            "fluid": "Hydrogen",
            "phase_basis": "two_phase",
            "reference_area_m2": area,
            "reference_area_provenance": "external DynamicHEMPipe inner full-bore area",
            "cumulative_specific_enthalpy_out_j": cumulative_enthalpy,
            "droplet_partition_provenance": "provider atmospheric liquid partition; airborne liquid set to zero",
            "steps": steps,
            "provider_meta": {
                "initial_mass_kg": initial_mass,
                "final_mass_kg": state.mass_kg,
                "residual_mass_kg": initial_mass - state.mass_kg - cumulative_mass,
                "duration_s": self.duration_s,
                "time_step_s": self.time_step_s,
                "model_class": "lh2dt.DynamicHEMPipe",
            },
        }
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_model": "lh2dt.DynamicHEMPipe",
            "provider_source_digest": request["provider_source_digest"],
            "data": data,
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    area = math.pi * args.inner_diameter_m**2 / 4.0
    component_id = args.component_id
    port_id = args.port_id or f"{component_id}.accident-out"
    event_id = args.event_id or f"{component_id}/{port_id}/{args.inner_diameter_m:.12g}m"
    snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": component_id,
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": args.inlet_pressure_pa,
        "temperature_k": args.inlet_temperature_k,
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "measurements": {
            "inlet_pressure": {
                "quantity": "pressure",
                "value_si": args.inlet_pressure_pa,
                "sensor_location": f"{component_id}.fluid_volume",
            },
            "inlet_temperature": {
                "quantity": "temperature",
                "value_si": args.inlet_temperature_k,
                "sensor_location": f"{component_id}.fluid_volume",
            },
        },
    })
    request = _request(
        provider_source_digest=source_digest,
        component_id=component_id,
        port_id=port_id,
        event_id=event_id,
        opening_diameter_m=args.inner_diameter_m,
        position_enu_m=[0.0, 0.0, args.nozzle_height_m],
        model_revision=args.model_revision,
        state_snapshot=snapshot,
    )
    provider = DynamicPipeAccidentProvider(
        root,
        duration_s=args.duration_s,
        time_step_s=args.time_step_s,
        length_m=args.length_m,
        inner_diameter_m=args.inner_diameter_m,
        roughness_m=args.roughness_m,
        inlet_pressure_pa=args.inlet_pressure_pa,
        inlet_temperature_k=args.inlet_temperature_k,
        wall_heat_capacity_j_k=args.wall_heat_capacity_j_k,
    )
    result = export_equipment_liquid_accident_history(provider, request)
    release = result.release.model_dump(mode="json")
    verification = {
        "status": "EXTERNAL_LH2DT_DYNAMIC_PIPE_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "provider_model": "lh2dt.DynamicHEMPipe",
        "provider_result_digest": result.provider_result_digest,
        "strict_packet_duration_s": result.release.duration_s,
        "strict_packet_interval_count": len(result.release.steps),
        "strict_packet_mass_residual_kg": result.release.cumulative_mass_out_kg - result.release.integrated_mass_kg,
        "strict_packet_energy_residual_j": result.release.cumulative_specific_enthalpy_out_j - result.release.integrated_specific_enthalpy_out_j,
        "state_snapshot": result.request.state_snapshot.to_mapping() if result.request.state_snapshot is not None else None,
        "state_snapshot_handoff": {
            "present": result.request.state_snapshot is not None,
            "schema_version": (
                result.request.state_snapshot.get("schema_version")
                if result.request.state_snapshot is not None
                else None
            ),
            "digest": result.request.state_snapshot_digest,
            "provider_echo_digest": result.provider_response.get("provider_state_snapshot_digest"),
            "digest_match": (
                result.request.state_snapshot is not None
                and result.provider_response.get("provider_state_snapshot_digest")
                == result.request.state_snapshot_digest
            ),
        },
        "provider_packet_promoted": result.provider_packet_promoted,
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic DynamicHEMPipe geometry, inlet state, full-bore opening and atmospheric boundary",
            "short fixed diagnostic horizon retains residual pipe inventory",
            "flash/airborne-liquid closure and site calibration are not supplied",
        ],
    }
    _save(args.output_dir / "provider_response.json", result.provider_response)
    _save(args.output_dir / "resolved_release.json", release)
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a DynamicHEMPipe diagnostic outlet into PRISM")
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=0.001)
    parser.add_argument("--time-step-s", type=float, default=1.0e-4)
    parser.add_argument("--length-m", type=float, default=1.0)
    parser.add_argument("--inner-diameter-m", type=float, default=0.002)
    parser.add_argument("--roughness-m", type=float, default=1.0e-7)
    parser.add_argument("--inlet-pressure-pa", type=float, default=250000.0)
    parser.add_argument("--inlet-temperature-k", type=float, default=20.5)
    parser.add_argument("--wall-heat-capacity-j-k", type=float, default=1000.0)
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    parser.add_argument("--component-id", default="dynamic-pipe-diagnostic")
    parser.add_argument("--event-id", default=None, help="optional exact worklist event id for a structural diagnostic")
    parser.add_argument("--port-id", default=None, help="optional exact facility accident port id")
    parser.add_argument("--model-revision", default="external-library-dynamic-pipe-0.1.1")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(f"DynamicHEMPipe PRISM accident export failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
