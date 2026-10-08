"""Export a bounded ``lh2dt.MappedPump`` liquid outlet as PRISM.

``MappedPump`` is a two-port hydraulic model and owns no tank inventory.  The
adapter therefore requires an explicit liquid feed state, a downstream design
pressure, an H-Q-N map, and a separate atmospheric valve.  It only exports a
packet when the mapped pump flow and the declared outlet valve flow agree
within a configured tolerance.  A feed reserve is a diagnostic bookkeeping
input, never an inferred facility inventory or accident frequency.
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

from lh2_tno.contracts import canonical_digest  # noqa: E402
from lh2_tno.equipment_accident_export import (  # noqa: E402
    EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
    AccidentReleaseExportRequest,
    export_equipment_liquid_accident_history,
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


def _request(*, source_digest: str, component_id: str, opening_diameter_m: float,
             state_digest: str, height_m: float, model_revision: str,
             event_id: str | None, port_id: str | None) -> AccidentReleaseExportRequest:
    port_id = port_id or f"{component_id}.accident-out"
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id or f"{component_id}/{port_id}/{opening_diameter_m:.12g}m",
        "failure_mode": "explicit_pump_downstream_atmospheric_outlet",
        "failure_opening_diameter_m": opening_diameter_m,
        "horizon_s": 600.0,
        "position_enu_m": [0.0, 0.0, height_m],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "lh2dt MappedPump liquid feed plus explicit atmospheric valve",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "MappedPump",
        "model_revision": model_revision,
        "state_snapshot_digest": state_digest,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit external MappedPump H-Q-N plus valve diagnostic; no pump inventory inferred",
        "provider_termination_required": True,
    })


class MappedPumpAccidentProvider:
    """Evaluate a mapped pump and an explicit matching atmospheric valve."""

    def __init__(self, root: Path, *, duration_s: float, time_step_s: float,
                 inlet_pressure_pa: float, inlet_temperature_k: float,
                 downstream_pressure_pa: float, downstream_temperature_k: float,
                 head_curve_points: list[list[float]], reference_speed_rpm: float,
                 speed_rpm: float, isentropic_efficiency: float,
                 opening_diameter_m: float, discharge_coefficient: float,
                 flow_match_tolerance: float) -> None:
        self.root = root.resolve()
        self.duration_s = float(duration_s)
        self.time_step_s = float(time_step_s)
        self.inlet_pressure_pa = float(inlet_pressure_pa)
        self.inlet_temperature_k = float(inlet_temperature_k)
        self.downstream_pressure_pa = float(downstream_pressure_pa)
        self.downstream_temperature_k = float(downstream_temperature_k)
        self.head_curve_points = head_curve_points
        self.reference_speed_rpm = float(reference_speed_rpm)
        self.speed_rpm = float(speed_rpm)
        self.isentropic_efficiency = float(isentropic_efficiency)
        self.opening_diameter_m = float(opening_diameter_m)
        self.discharge_coefficient = float(discharge_coefficient)
        self.flow_match_tolerance = float(flow_match_tolerance)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.duration_s <= 0.0 or self.time_step_s <= 0.0:
            raise ValueError("pump diagnostic duration and time step must be positive")
        if not math.isclose(self.duration_s / self.time_step_s, round(self.duration_s / self.time_step_s), rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("duration must be an integer number of time steps")
        if self.opening_diameter_m <= 0.0 or not 0.0 < self.flow_match_tolerance < 1.0:
            raise ValueError("opening diameter and flow match tolerance are invalid")

        sys.path.insert(0, str(self.root / "src"))
        from lh2dt.properties import HydrogenProperties
        from lh2dt.pump import MappedPump
        from lh2dt.valve import Valve

        properties = HydrogenProperties("Hydrogen")
        inlet = properties.from_pT(self.inlet_pressure_pa, self.inlet_temperature_k)
        downstream = properties.from_pT(self.downstream_pressure_pa, self.downstream_temperature_k)
        if "liquid" not in str(inlet.phase).lower() or "gas" in str(inlet.phase).lower():
            raise ValueError("MappedPump diagnostic inlet must be liquid")
        pump = MappedPump(
            self.head_curve_points,
            reference_speed_rpm=self.reference_speed_rpm,
            speed_rpm=self.speed_rpm,
            isentropic_efficiency=self.isentropic_efficiency,
            properties=properties,
        )
        pump_result = pump.evaluate(inlet, downstream)
        if pump_result.mass_flow_kg_s <= 0.0:
            raise ValueError("MappedPump map produced no positive flow")
        pump_outlet = properties.from_ph(
            downstream.pressure_Pa, pump_result.outlet_specific_enthalpy_J_kg
        )
        ambient_pressure = float(request["ambient_pressure_pa_abs"])
        ambient_temperature = float(request["ambient_temperature_k"])
        ambient = properties.from_pT(ambient_pressure, ambient_temperature)
        area = math.pi * self.opening_diameter_m**2 / 4.0
        valve = Valve(area, self.discharge_coefficient, properties=properties, allow_reverse=False)
        valve_result = valve.evaluate(pump_outlet, ambient, opening=1.0)
        valve_flow = float(valve_result.mass_flow_kg_s)
        relative_error = abs(valve_flow - pump_result.mass_flow_kg_s) / pump_result.mass_flow_kg_s
        if relative_error > self.flow_match_tolerance:
            raise ValueError(
                f"pump and atmospheric valve flows disagree: relative error {relative_error:.6g} "
                f"> tolerance {self.flow_match_tolerance:.6g}"
            )
        outlet = properties.from_ph(ambient_pressure, valve_result.outlet_specific_enthalpy_J_kg)
        if "liquid" not in str(outlet.phase).lower() or "gas" in str(outlet.phase).lower():
            raise ValueError("MappedPump outlet is outside the liquid atmospheric contract")
        intervals = int(round(self.duration_s / self.time_step_s))
        cumulative_mass = 0.0
        cumulative_enthalpy = 0.0
        steps: list[dict[str, Any]] = []
        time_s = 0.0
        for _ in range(intervals):
            mass_flow = pump_result.mass_flow_kg_s
            enthalpy = float(valve_result.outlet_specific_enthalpy_J_kg)
            cumulative_mass += mass_flow * self.time_step_s
            cumulative_enthalpy += mass_flow * self.time_step_s * enthalpy
            steps.append({
                "time_s": time_s,
                "total_mass_flow_kg_s": mass_flow,
                "gas_mass_flow_kg_s": 0.0,
                "ground_liquid_mass_flow_kg_s": mass_flow,
                "airborne_liquid_mass_flow_kg_s": 0.0,
                "specific_enthalpy_j_kg": enthalpy,
                "droplet_class_outcomes": [{
                    "ground_liquid_mass_flow_kg_s": mass_flow,
                    "airborne_liquid_mass_flow_kg_s": 0.0,
                    "flight_time_s": 0.0,
                    "impact_position_m": [float(request["position_enu_m"][0]), float(request["position_enu_m"][1]), 0.0],
                    "droplet_diameter_m": 0.001,
                }],
            })
            time_s += self.time_step_s
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_model": "lh2dt.MappedPump",
            "provider_source_digest": request["provider_source_digest"],
            "data": {
                "event_kind": "accidental_leak",
                "event_id": request["event_id"],
                "component_id": request["component_id"],
                "port_id": request["port_id"],
                "duration_s": self.duration_s,
                "available_mass_kg": cumulative_mass * 1.2,
                "cumulative_mass_out_kg": cumulative_mass,
                "cumulative_specific_enthalpy_out_j": cumulative_enthalpy,
                "termination_provenance": "external MappedPump H-Q-N point and matched atmospheric valve over bounded feed-through horizon",
                "termination_basis": "synthetic_diagnostic_horizon",
                "upstream_service": "LH2",
                "fluid": "Hydrogen",
                "phase_basis": "liquid",
                "reference_area_m2": area,
                "reference_area_provenance": "explicit downstream atmospheric valve bore",
                "droplet_partition_provenance": "provider liquid outlet; airborne liquid explicitly zero",
                "steps": steps,
                "provider_meta": {
                    "model_class": "lh2dt.MappedPump",
                    "mass_flow_kg_s": pump_result.mass_flow_kg_s,
                    "valve_flow_kg_s": valve_flow,
                    "flow_relative_error": relative_error,
                    "pressure_rise_pa": pump_result.pressure_rise_Pa,
                    "map_head_pressure_rise_pa": pump_result.map_head_pressure_rise_Pa,
                    "map_limited": pump_result.map_limited,
                    "npsh_available_m": pump_result.npsh_available_m,
                    "cavitation_margin_m": pump_result.cavitation_margin_m,
                },
            },
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    state_payload = vars(args).copy()
    state_payload.pop("lh2dt_root", None)
    state_payload.pop("output_dir", None)
    component_id = args.component_id
    request = _request(
        source_digest=source_digest, component_id=component_id,
        opening_diameter_m=args.opening_diameter_m,
        state_digest=canonical_digest(state_payload),
        height_m=args.nozzle_height_m, model_revision=args.model_revision,
        event_id=args.event_id,
        port_id=args.port_id,
    )
    provider = MappedPumpAccidentProvider(
        root, duration_s=args.duration_s, time_step_s=args.time_step_s,
        inlet_pressure_pa=args.inlet_pressure_pa, inlet_temperature_k=args.inlet_temperature_k,
        downstream_pressure_pa=args.downstream_pressure_pa, downstream_temperature_k=args.downstream_temperature_k,
        head_curve_points=args.head_curve_points, reference_speed_rpm=args.reference_speed_rpm,
        speed_rpm=args.speed_rpm, isentropic_efficiency=args.isentropic_efficiency,
        opening_diameter_m=args.opening_diameter_m, discharge_coefficient=args.discharge_coefficient,
        flow_match_tolerance=args.flow_match_tolerance,
    )
    result = export_equipment_liquid_accident_history(provider, request)
    release = result.release.model_dump(mode="json")
    verification = {
        "status": "EXTERNAL_LH2DT_MAPPED_PUMP_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "provider_model": "lh2dt.MappedPump",
        "provider_result_digest": result.provider_result_digest,
        "strict_packet_duration_s": result.release.duration_s,
        "strict_packet_interval_count": len(result.release.steps),
        "strict_packet_mass_residual_kg": result.release.cumulative_mass_out_kg - result.release.integrated_mass_kg,
        "strict_packet_energy_residual_j": result.release.cumulative_specific_enthalpy_out_j - result.release.integrated_specific_enthalpy_out_j,
        "provider_packet_promoted": result.provider_packet_promoted,
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "limitations": [
            "MappedPump owns no tank inventory; available mass is an explicit feed-through diagnostic reserve",
            "synthetic H-Q-N map, liquid states, downstream pressure and atmospheric valve geometry",
            "no pump seal failure mode, isolation logic, field frequency or independent physical validation",
        ],
    }
    _save(args.output_dir / "provider_response.json", result.provider_response)
    _save(args.output_dir / "resolved_release.json", release)
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a MappedPump diagnostic liquid outlet into PRISM")
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=0.2)
    parser.add_argument("--time-step-s", type=float, default=0.02)
    parser.add_argument("--inlet-pressure-pa", type=float, default=120000.0)
    parser.add_argument("--inlet-temperature-k", type=float, default=20.0)
    parser.add_argument("--downstream-pressure-pa", type=float, default=250000.0)
    parser.add_argument("--downstream-temperature-k", type=float, default=22.0)
    parser.add_argument("--head-curve-points", type=lambda text: json.loads(text), default=[[0.0, 250000.0], [0.0001, 200000.0], [0.001, 100000.0], [0.002, 0.0]])
    parser.add_argument("--reference-speed-rpm", type=float, default=3600.0)
    parser.add_argument("--speed-rpm", type=float, default=3600.0)
    parser.add_argument("--isentropic-efficiency", type=float, default=0.7)
    parser.add_argument("--opening-diameter-m", type=float, default=0.000538)
    parser.add_argument("--discharge-coefficient", type=float, default=0.7)
    parser.add_argument("--flow-match-tolerance", type=float, default=0.02)
    parser.add_argument("--nozzle-height-m", type=float, default=0.5)
    parser.add_argument("--component-id", default="mapped-pump-diagnostic")
    parser.add_argument("--event-id", default=None, help="optional exact worklist event id for a structural diagnostic")
    parser.add_argument("--port-id", default=None, help="optional exact facility accident port id")
    parser.add_argument("--model-revision", default="external-library-mapped-pump-0.1.1")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(f"MappedPump PRISM accident export failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
