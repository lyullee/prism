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


def _coarsen_steps(
    steps: list[dict[str, Any]],
    *,
    duration_s: float,
    max_steps: int = 100,
) -> list[dict[str, Any]]:
    """Compress a long provider history without changing its mass ledger.

    The external solver may need thousands of small internal intervals to
    reach a declared inventory threshold, while the PRISM boundary contract
    deliberately bounds retained history to 100 intervals.  Each output row
    is a time-bin average; mass and static enthalpy are integrated over the
    original intervals before the averaged row is emitted.
    """
    if len(steps) <= max_steps:
        return steps
    group_size = math.ceil(len(steps) / max_steps)
    result: list[dict[str, Any]] = []

    def _interval_end(index: int) -> float:
        return (
            float(steps[index + 1]["time_s"])
            if index + 1 < len(steps)
            else float(duration_s)
        )

    def _time_average(rows: list[dict[str, Any]], field: str, widths: list[float]) -> float:
        total = sum(widths)
        return sum(float(row[field]) * width for row, width in zip(rows, widths)) / total

    for start in range(0, len(steps), group_size):
        rows = steps[start:start + group_size]
        widths = [_interval_end(start + offset) - float(row["time_s"])
                  for offset, row in enumerate(rows)]
        width = sum(widths)
        mass = sum(float(row["total_mass_flow_kg_s"]) * dt for row, dt in zip(rows, widths))
        gas_mass = sum(float(row["gas_mass_flow_kg_s"]) * dt for row, dt in zip(rows, widths))
        ground_mass = sum(
            float(row["ground_liquid_mass_flow_kg_s"]) * dt
            for row, dt in zip(rows, widths)
        )
        airborne_mass = sum(
            float(row["airborne_liquid_mass_flow_kg_s"]) * dt
            for row, dt in zip(rows, widths)
        )
        energy = sum(
            float(row["total_mass_flow_kg_s"])
            * float(row["specific_enthalpy_j_kg"])
            * dt
            for row, dt in zip(rows, widths)
        )
        enthalpy = energy / mass if mass > 0.0 else _time_average(rows, "specific_enthalpy_j_kg", widths)
        pressure = _time_average(rows, "gas_pressure_pa_abs", widths)
        temperature = _time_average(rows, "gas_temperature_k", widths)
        density = _time_average(rows, "gas_density_kg_m3", widths)
        area = _time_average(rows, "gas_effective_area_m2", widths)
        gas_flow = gas_mass / width
        ground_flow = ground_mass / width
        airborne_flow = airborne_mass / width
        total_flow = mass / width
        gas_velocity = gas_flow / (density * area) if gas_flow > 0.0 else 0.0
        impact = rows[0]["droplet_class_outcomes"][0].get("impact_position_m", [0.0, 0.0, 0.0])
        result.append({
            "time_s": float(rows[0]["time_s"]),
            "total_mass_flow_kg_s": total_flow,
            "gas_mass_flow_kg_s": gas_flow,
            "ground_liquid_mass_flow_kg_s": ground_flow,
            "airborne_liquid_mass_flow_kg_s": airborne_flow,
            "specific_enthalpy_j_kg": enthalpy,
            "gas_pressure_pa_abs": pressure,
            "gas_temperature_k": temperature,
            "gas_density_kg_m3": density,
            "gas_effective_area_m2": area,
            "gas_velocity_m_s": gas_velocity,
            "gas_velocity_origin": "mass_continuity_from_declared_area",
            "droplet_class_outcomes": [{
                "ground_liquid_mass_flow_kg_s": ground_flow,
                "airborne_liquid_mass_flow_kg_s": airborne_flow,
                "flight_time_s": 0.0,
                "impact_position_m": impact,
                "droplet_diameter_m": 0.001,
            }],
        })
    return result


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
        termination_threshold_kg: float | None = None,
        inlet_isolation_time_s: float | None = None,
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
        self.termination_threshold_kg = (
            float(termination_threshold_kg)
            if termination_threshold_kg is not None
            else None
        )
        if self.termination_threshold_kg is not None and self.termination_threshold_kg <= 0.0:
            raise ValueError("provider termination threshold must be positive")
        self.inlet_isolation_time_s = (
            float(inlet_isolation_time_s)
            if inlet_isolation_time_s is not None
            else None
        )
        if self.inlet_isolation_time_s is not None and self.inlet_isolation_time_s < 0.0:
            raise ValueError("provider inlet isolation time must be non-negative")
        if (
            self.inlet_isolation_time_s is not None
            and self.inlet_isolation_time_s > self.duration_s
        ):
            raise ValueError("provider inlet isolation time cannot exceed the horizon")

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
        terminated_by_threshold = False
        for index in range(intervals):
            inlet_state = (
                pipe.thermo(state)
                if (
                    self.inlet_isolation_time_s is not None
                    and time_s >= self.inlet_isolation_time_s
                )
                else inlet
            )
            result = pipe.step(state, inlet_state, outlet, self.time_step_s)
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
            if (
                self.termination_threshold_kg is not None
                and state.mass_kg <= self.termination_threshold_kg
            ):
                terminated_by_threshold = True
                break
        if (
            not terminated_by_threshold
            and not math.isclose(time_s, self.duration_s, rel_tol=0.0, abs_tol=1.0e-10)
        ):
            raise ValueError("DynamicHEMPipe provider clock disagrees with duration")
        actual_duration_s = time_s
        if actual_duration_s <= 0.0:
            raise ValueError("DynamicHEMPipe provider produced no positive release duration")
        packet_steps = _coarsen_steps(
            steps,
            duration_s=actual_duration_s,
        )
        termination_basis = (
            "inventory_depletion"
            if terminated_by_threshold
            else "synthetic_diagnostic_horizon"
        )
        termination_provenance = (
            "external DynamicHEMPipe isolated-inlet positive inventory threshold; residual pipe inventory retained"
            if terminated_by_threshold
            else "external DynamicHEMPipe fixed diagnostic horizon; residual pipe inventory retained"
        )
        data = {
            "event_kind": "accidental_leak",
            "event_id": request["event_id"],
            "component_id": request["component_id"],
            "port_id": request["port_id"],
            "duration_s": actual_duration_s,
            "available_mass_kg": initial_mass,
            "cumulative_mass_out_kg": cumulative_mass,
            "termination_provenance": termination_provenance,
            "termination_basis": termination_basis,
            "upstream_service": "LH2",
            "fluid": "Hydrogen",
            "phase_basis": "two_phase",
            "reference_area_m2": area,
            "reference_area_provenance": "external DynamicHEMPipe inner full-bore area",
            "cumulative_specific_enthalpy_out_j": cumulative_enthalpy,
            "droplet_partition_provenance": "provider atmospheric liquid partition; airborne liquid set to zero",
            "steps": packet_steps,
            "provider_meta": {
                "initial_mass_kg": initial_mass,
                "final_mass_kg": state.mass_kg,
                "residual_mass_kg": initial_mass - state.mass_kg - cumulative_mass,
                "duration_s": actual_duration_s,
                "time_step_s": self.time_step_s,
                "model_class": "lh2dt.DynamicHEMPipe",
                "termination_basis": (
                    "inventory_depletion_positive_threshold"
                    if terminated_by_threshold
                    else "synthetic_diagnostic_horizon"
                ),
                "depletion_threshold_kg": self.termination_threshold_kg,
                "remaining_mass_kg": float(state.mass_kg),
                "max_abs_mass_residual_kg": abs(
                    initial_mass - state.mass_kg - cumulative_mass
                ),
                "terminated_by_threshold": terminated_by_threshold,
                "inlet_isolation_time_s": self.inlet_isolation_time_s,
                "isolation_success": self.inlet_isolation_time_s is not None,
            },
        }
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_state_snapshot_digest": request["state_snapshot_digest"],
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
    position_enu_m = (
        [float(value) for value in args.position_enu_m]
        if args.position_enu_m is not None
        else [0.0, 0.0, float(args.nozzle_height_m)]
    )
    snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": component_id,
        "captured_at_s": 0.0,
        "origin": "model_prediction",
        "pressure_pa_abs": args.inlet_pressure_pa,
        "temperature_k": args.inlet_temperature_k,
        "position_enu_m": position_enu_m,
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
        position_enu_m=position_enu_m,
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
        termination_threshold_kg=args.termination_threshold_kg,
        inlet_isolation_time_s=args.inlet_isolation_time_s,
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
                result.request.state_snapshot.schema_version
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
    parser.add_argument(
        "--termination-threshold-kg",
        type=float,
        default=None,
        help="optional positive provider inventory threshold for natural termination",
    )
    parser.add_argument(
        "--inlet-isolation-time-s",
        type=float,
        default=None,
        help="optional provider inlet isolation time; after this time the pipe inlet is held at its state",
    )
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    parser.add_argument(
        "--position-enu-m", type=float, nargs=3, default=None,
        help="absolute ENU release position; defaults to the origin with nozzle height",
    )
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
