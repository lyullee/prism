"""Export a bounded ``lh2dt.DynamicVaporizer``/``DynamicReliquefier`` outlet.

The dynamic unit owns the finite gas inventory, wall energy and pressure
history.  PRISM adds only an explicit atmospheric valve boundary and the
strict external accident-history envelope.  The outlet area, discharge
coefficient, horizon and initial state are declared inputs; none is learned
from a normal operating snapshot.  The result is therefore a synthetic
diagnostic packet until a site-calibrated accident export and independent
evidence exist.
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
    export_equipment_gas_accident_history,
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


def _request(*, source_digest: str, component_id: str, opening_diameter_m: float,
             state_digest: str, height_m: float, model_class: str,
             model_revision: str, mode: str) -> AccidentReleaseExportRequest:
    port_id = f"{component_id}.accident-out"
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": f"{component_id}/{port_id}/{opening_diameter_m:.12g}m",
        "failure_mode": "explicit_atmospheric_outlet_valve",
        "failure_opening_diameter_m": opening_diameter_m,
        "horizon_s": 600.0,
        "position_enu_m": [0.0, 0.0, height_m],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": (
            f"lh2dt {model_class} finite-volume inventory with explicit atmospheric valve"
        ),
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": model_class,
        "model_revision": model_revision,
        "state_snapshot_digest": state_digest,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": (
            f"explicit external {model_class} bounded valve diagnostic ({mode}); not site-calibrated"
        ),
        "provider_termination_required": True,
    })


class DynamicVaporizerAccidentProvider:
    """Run one finite-volume gas unit against an explicit atmospheric valve."""

    def __init__(self, root: Path, *, mode: str, duration_s: float,
                 time_step_s: float, fluid_volume_m3: float,
                 wall_heat_capacity_j_k: float, fluid_wall_ua_w_k: float,
                 boundary_ua_w_k: float, boundary_temperature_k: float,
                 maximum_heat_w: float, inlet_pressure_pa: float,
                 inlet_temperature_k: float, opening_diameter_m: float,
                 discharge_coefficient: float, stroke_time_s: float) -> None:
        self.root = root.resolve()
        self.mode = mode
        self.duration_s = float(duration_s)
        self.time_step_s = float(time_step_s)
        self.fluid_volume_m3 = float(fluid_volume_m3)
        self.wall_heat_capacity_j_k = float(wall_heat_capacity_j_k)
        self.fluid_wall_ua_w_k = float(fluid_wall_ua_w_k)
        self.boundary_ua_w_k = float(boundary_ua_w_k)
        self.boundary_temperature_k = float(boundary_temperature_k)
        self.maximum_heat_w = float(maximum_heat_w)
        self.inlet_pressure_pa = float(inlet_pressure_pa)
        self.inlet_temperature_k = float(inlet_temperature_k)
        self.opening_diameter_m = float(opening_diameter_m)
        self.discharge_coefficient = float(discharge_coefficient)
        self.stroke_time_s = float(stroke_time_s)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        values = {
            "duration_s": self.duration_s,
            "time_step_s": self.time_step_s,
            "fluid_volume_m3": self.fluid_volume_m3,
            "wall_heat_capacity_j_k": self.wall_heat_capacity_j_k,
            "fluid_wall_ua_w_k": self.fluid_wall_ua_w_k,
            "boundary_ua_w_k": self.boundary_ua_w_k,
            "boundary_temperature_k": self.boundary_temperature_k,
            "maximum_heat_w": self.maximum_heat_w,
            "inlet_pressure_pa": self.inlet_pressure_pa,
            "inlet_temperature_k": self.inlet_temperature_k,
            "opening_diameter_m": self.opening_diameter_m,
            "discharge_coefficient": self.discharge_coefficient,
            "stroke_time_s": self.stroke_time_s,
        }
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError("dynamic vaporizer diagnostic inputs must be finite")
        if self.mode not in {"vaporizer", "reliquefier"}:
            raise ValueError("mode must be vaporizer or reliquefier")
        if self.duration_s <= 0.0 or self.time_step_s <= 0.0:
            raise ValueError("diagnostic duration and time step must be positive")
        if not math.isclose(self.duration_s / self.time_step_s,
                            round(self.duration_s / self.time_step_s),
                            rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("duration must be an integer number of time steps")
        if self.opening_diameter_m <= 0.0 or self.fluid_volume_m3 <= 0.0:
            raise ValueError("opening diameter and fluid volume must be positive")

        sys.path.insert(0, str(self.root / "src"))
        from lh2dt.properties import HydrogenProperties
        from lh2dt.valve import StrokeLimitedCommandedValve, Valve
        if self.mode == "vaporizer":
            from lh2dt.dynamic_vaporizer import DynamicVaporizer
            model_class = "lh2dt.DynamicVaporizer"
            model = DynamicVaporizer(
                self.fluid_volume_m3, self.wall_heat_capacity_j_k,
                self.fluid_wall_ua_w_k, self.boundary_temperature_k,
                self.boundary_ua_w_k, self.maximum_heat_w,
                properties=HydrogenProperties("Hydrogen"),
            )
        else:
            from lh2dt.dynamic_reliquefier import DynamicReliquefier
            model_class = "lh2dt.DynamicReliquefier"
            model = DynamicReliquefier(
                self.fluid_volume_m3, self.wall_heat_capacity_j_k,
                self.fluid_wall_ua_w_k, self.boundary_temperature_k,
                self.boundary_ua_w_k, self.maximum_heat_w,
                properties=HydrogenProperties("Hydrogen"),
            )
        properties = model.properties
        ambient_pressure = float(request["ambient_pressure_pa_abs"])
        ambient_temperature = float(request["ambient_temperature_k"])
        inlet = properties.from_pT(self.inlet_pressure_pa, self.inlet_temperature_k)
        if inlet.phase not in {"gas", "supercritical_gas"}:
            raise ValueError("dynamic gas-unit initial state must be gas-like")
        state = model.initialize(inlet)
        initial_mass = float(state.mass_kg)
        area = math.pi * self.opening_diameter_m**2 / 4.0
        outlet_boundary = properties.from_pT(ambient_pressure, ambient_temperature)
        valve = StrokeLimitedCommandedValve(
            Valve(area, self.discharge_coefficient, properties=properties,
                  allow_reverse=False),
            stroke_time_s=self.stroke_time_s,
            initial_opening=0.0,
        )
        valve.set_target_opening(1.0)
        intervals = int(round(self.duration_s / self.time_step_s))
        steps: list[dict[str, Any]] = []
        cumulative_mass = 0.0
        cumulative_enthalpy = 0.0
        choked_count = 0
        time_s = 0.0
        for index in range(intervals):
            fluid = model.thermo(state)
            opening = valve.advance(self.time_step_s)
            hydraulic = valve.evaluate(fluid, outlet_boundary)
            mass_flow = float(hydraulic.mass_flow_kg_s)
            if not math.isfinite(mass_flow) or mass_flow < 0.0:
                raise ValueError(f"dynamic gas unit returned invalid outward flow at interval {index}")
            exit_state = properties.from_ph(
                ambient_pressure, float(hydraulic.outlet_specific_enthalpy_J_kg)
            )
            if hydraulic.choked:
                choked_count += 1
            if exit_state.phase not in {"gas", "supercritical_gas"}:
                raise ValueError("dynamic gas unit outlet is outside the gas contract")
            result = model.step(state, fluid, 0.0, mass_flow, self.time_step_s)
            enthalpy = float(hydraulic.outlet_specific_enthalpy_J_kg)
            density = float(exit_state.density_kg_m3)
            effective_area = area * opening
            cumulative_mass += mass_flow * self.time_step_s
            cumulative_enthalpy += mass_flow * self.time_step_s * enthalpy
            steps.append({
                "time_s": time_s,
                "mass_flow_kg_s": mass_flow,
                "pressure_pa_abs": ambient_pressure,
                "specific_enthalpy_j_kg": enthalpy,
                "temperature_k": float(exit_state.temperature_K),
                "density_kg_m3": density,
                "effective_area_m2": effective_area,
                "velocity_m_s": mass_flow / (density * effective_area) if mass_flow > 0.0 and effective_area > 0.0 else 0.0,
                "area_provenance": "explicit atmospheric valve full-bore area scaled by stroke state",
                "velocity_origin": "mass_continuity_from_declared_area",
            })
            state = result.state
            time_s += self.time_step_s
            if state.mass_kg <= 0.0:
                raise ValueError("dynamic gas unit inventory depleted before diagnostic horizon")
        if not math.isclose(time_s, self.duration_s, rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("provider clock disagrees with duration")
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_model": model_class,
            "provider_source_digest": request["provider_source_digest"],
            "data": {
                "event_kind": "accidental_leak",
                "event_id": request["event_id"],
                "component_id": request["component_id"],
                "port_id": request["port_id"],
                "duration_s": self.duration_s,
                "available_mass_kg": initial_mass,
                "cumulative_mass_out_kg": cumulative_mass,
                "cumulative_static_enthalpy_out_j": cumulative_enthalpy,
                "termination_provenance": (
                    f"external {model_class} finite-volume state with explicit valve; "
                    "residual inventory retained at synthetic horizon"
                ),
                "termination_basis": "synthetic_diagnostic_horizon",
                "fluid": "Hydrogen",
                "steps": steps,
                "provider_meta": {
                    "model_class": model_class,
                    "mode": self.mode,
                    "initial_mass_kg": initial_mass,
                    "final_mass_kg": float(state.mass_kg),
                    "residual_mass_kg": initial_mass - float(state.mass_kg) - cumulative_mass,
                    "time_step_s": self.time_step_s,
                    "valve": {
                        "area_m2": area,
                        "discharge_coefficient": self.discharge_coefficient,
                        "stroke_time_s": self.stroke_time_s,
                        "final_opening": valve.opening,
                        "choked_intervals": choked_count,
                    },
                },
            },
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    model_class = (
        "lh2dt.DynamicVaporizer" if args.mode == "vaporizer"
        else "lh2dt.DynamicReliquefier"
    )
    state_payload = vars(args).copy()
    state_payload.pop("lh2dt_root", None)
    state_payload.pop("output_dir", None)
    component_id = args.component_id
    port_id = f"{component_id}.accident-out"
    request = _request(
        source_digest=source_digest, component_id=component_id,
        opening_diameter_m=args.opening_diameter_m,
        state_digest=canonical_digest(state_payload),
        height_m=args.nozzle_height_m, model_class=model_class,
        model_revision=args.model_revision, mode=args.mode,
    )
    provider = DynamicVaporizerAccidentProvider(
        root, mode=args.mode, duration_s=args.duration_s,
        time_step_s=args.time_step_s, fluid_volume_m3=args.fluid_volume_m3,
        wall_heat_capacity_j_k=args.wall_heat_capacity_j_k,
        fluid_wall_ua_w_k=args.fluid_wall_ua_w_k,
        boundary_ua_w_k=args.boundary_ua_w_k,
        boundary_temperature_k=args.boundary_temperature_k,
        maximum_heat_w=args.maximum_heat_w,
        inlet_pressure_pa=args.inlet_pressure_pa,
        inlet_temperature_k=args.inlet_temperature_k,
        opening_diameter_m=args.opening_diameter_m,
        discharge_coefficient=args.discharge_coefficient,
        stroke_time_s=args.stroke_time_s,
    )
    result = export_equipment_gas_accident_history(provider, request)
    release = result.release.model_dump(mode="json")
    verification = {
        "status": "EXTERNAL_LH2DT_DYNAMIC_GAS_UNIT_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "provider_model": model_class,
        "mode": args.mode,
        "provider_result_digest": result.provider_result_digest,
        "strict_packet_duration_s": result.release.duration_s,
        "strict_packet_interval_count": len(result.release.steps),
        "strict_packet_mass_residual_kg": result.release.cumulative_mass_out_kg - result.release.integrated_mass_kg,
        "strict_packet_energy_residual_j": result.release.cumulative_static_enthalpy_out_j - result.release.integrated_static_enthalpy_j,
        "provider_packet_promoted": result.provider_packet_promoted,
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic dynamic gas-unit geometry, initial state, valve opening and atmospheric boundary",
            "short fixed diagnostic horizon retains residual inventory",
            "no site calibration, failure frequency, isolation logic or independent physical validation",
        ],
    }
    _save(args.output_dir / "provider_response.json", result.provider_response)
    _save(args.output_dir / "resolved_release.json", release)
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a dynamic LH2 gas unit diagnostic outlet into PRISM")
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("vaporizer", "reliquefier"), default="vaporizer")
    parser.add_argument("--duration-s", type=float, default=0.5)
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--fluid-volume-m3", type=float, default=0.01)
    parser.add_argument("--wall-heat-capacity-j-k", type=float, default=1000.0)
    parser.add_argument("--fluid-wall-ua-w-k", type=float, default=100.0)
    parser.add_argument("--boundary-ua-w-k", type=float, default=10.0)
    parser.add_argument("--boundary-temperature-k", type=float, default=288.15)
    parser.add_argument("--maximum-heat-w", type=float, default=10000.0)
    parser.add_argument("--inlet-pressure-pa", type=float, default=102000.0)
    parser.add_argument("--inlet-temperature-k", type=float, default=300.0)
    parser.add_argument("--opening-diameter-m", type=float, default=0.001)
    parser.add_argument("--discharge-coefficient", type=float, default=0.7)
    parser.add_argument("--stroke-time-s", type=float, default=0.2)
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    parser.add_argument("--component-id", default="dynamic-vaporizer-diagnostic")
    parser.add_argument("--model-revision", default="external-library-dynamic-gas-unit-0.1.1")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(f"dynamic LH2 gas-unit PRISM accident export failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
