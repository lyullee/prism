"""Export an inventory-defined dynamic gas-unit accident packet.

This adapter is separate from the fixed-opening hole adapter.  The packet
contains no random failure diameter; the external finite-volume model owns the
inventory ledger and the termination basis.
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
    InventoryReleaseExportRequest,
    export_equipment_inventory_release_history,
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


def _request(*, source_digest: str, component_id: str, event_id: str | None,
             port_id: str | None, mode: str, state_digest: str,
             height_m: float, model_class: str, revision: str) -> InventoryReleaseExportRequest:
    port_id = port_id or f"{component_id}.accident-out"
    return InventoryReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_inventory_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id or f"{component_id}/{port_id}/{mode}",
        "release_mode": mode,
        "horizon_s": 600.0,
        "position_enu_m": [0.0, 0.0, height_m],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": f"{model_class} explicit inventory outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": model_class,
        "model_revision": revision,
        "state_snapshot_digest": state_digest,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": f"explicit external {model_class} inventory-defined diagnostic ({mode}); not site-calibrated",
        "provider_termination_required": True,
    })


class DynamicGasInventoryProvider:
    def __init__(self, root: Path, *, mode: str, release_mode: str,
                 duration_s: float, time_step_s: float, fluid_volume_m3: float,
                 wall_heat_capacity_j_k: float, fluid_wall_ua_w_k: float,
                 boundary_ua_w_k: float, boundary_temperature_k: float,
                 maximum_heat_w: float, inlet_pressure_pa: float,
                 inlet_temperature_k: float, opening_diameter_m: float,
                 discharge_coefficient: float, stroke_time_s: float) -> None:
        self.root = root.resolve()
        self.mode = mode
        self.release_mode = release_mode
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
        if self.release_mode not in {"instantaneous_inventory", "inventory_over_600s"}:
            raise ValueError("unsupported inventory release mode")
        if self.duration_s <= 0.0 or self.time_step_s <= 0.0 or self.fluid_volume_m3 <= 0.0:
            raise ValueError("inventory diagnostic inputs must be positive")
        if self.release_mode == "inventory_over_600s" and not math.isclose(self.duration_s, 600.0, rel_tol=0.0, abs_tol=1.0e-9):
            raise ValueError("inventory_over_600s provider duration must be exactly 600 s")
        sys.path.insert(0, str(self.root / "src"))
        from lh2dt.properties import HydrogenProperties
        from lh2dt.valve import StrokeLimitedCommandedValve, Valve
        if self.mode == "vaporizer":
            from lh2dt.dynamic_vaporizer import DynamicVaporizer
            model_class = "lh2dt.DynamicVaporizer"
            model = DynamicVaporizer(self.fluid_volume_m3, self.wall_heat_capacity_j_k, self.fluid_wall_ua_w_k,
                                     self.boundary_temperature_k, self.boundary_ua_w_k, self.maximum_heat_w,
                                     properties=HydrogenProperties("Hydrogen"))
        elif self.mode == "reliquefier":
            from lh2dt.dynamic_reliquefier import DynamicReliquefier
            model_class = "lh2dt.DynamicReliquefier"
            model = DynamicReliquefier(self.fluid_volume_m3, self.wall_heat_capacity_j_k, self.fluid_wall_ua_w_k,
                                       self.boundary_temperature_k, self.boundary_ua_w_k, self.maximum_heat_w,
                                       properties=HydrogenProperties("Hydrogen"))
        else:
            raise ValueError("mode must be vaporizer or reliquefier")
        properties = model.properties
        inlet = properties.from_pT(self.inlet_pressure_pa, self.inlet_temperature_k)
        if inlet.phase not in {"gas", "supercritical_gas"}:
            raise ValueError("dynamic gas-unit inventory state must be gas-like")
        state = model.initialize(inlet)
        initial_mass = float(state.mass_kg)
        ambient_pressure = float(request["ambient_pressure_pa_abs"])
        ambient_temperature = float(request["ambient_temperature_k"])
        outlet_boundary = properties.from_pT(ambient_pressure, ambient_temperature)
        area = math.pi * self.opening_diameter_m**2 / 4.0
        valve = StrokeLimitedCommandedValve(Valve(area, self.discharge_coefficient, properties=properties, allow_reverse=False),
                                            stroke_time_s=self.stroke_time_s, initial_opening=0.0)
        valve.set_target_opening(1.0)
        steps: list[dict[str, Any]] = []
        cumulative_mass = 0.0
        cumulative_enthalpy = 0.0
        time_s = 0.0
        intervals = int(math.ceil(self.duration_s / self.time_step_s)) if self.release_mode == "instantaneous_inventory" else int(round(self.duration_s / self.time_step_s))
        terminated = False
        for index in range(intervals):
            fluid = model.thermo(state)
            dt = self.time_step_s
            if self.release_mode == "instantaneous_inventory":
                dt = min(dt, self.duration_s - time_s)
            opening = valve.advance(dt)
            hydraulic = valve.evaluate(fluid, outlet_boundary)
            mass_flow = float(hydraulic.mass_flow_kg_s)
            if not math.isfinite(mass_flow) or mass_flow < 0.0:
                raise ValueError(f"inventory gas unit returned invalid outward flow at interval {index}")
            if mass_flow <= 0.0:
                if self.release_mode == "instantaneous_inventory" and cumulative_mass > 0.0:
                    terminated = True
                    break
                if self.release_mode == "instantaneous_inventory":
                    raise ValueError("inventory gas unit produced no outward flow before any inventory was released")
                # A 600 s inventory-over-time history may include provider
                # pressure-equilibrium intervals with zero outward flow.
                mass_flow = 0.0
            if self.release_mode == "instantaneous_inventory":
                dt = min(dt, max((state.mass_kg - 1.0e-10) / mass_flow, 1.0e-8))
            exit_state = properties.from_ph(ambient_pressure, float(hydraulic.outlet_specific_enthalpy_J_kg))
            if exit_state.phase not in {"gas", "supercritical_gas"}:
                raise ValueError("inventory gas-unit outlet is outside gas contract")
            result = model.step(state, fluid, 0.0, mass_flow, dt)
            enthalpy = float(hydraulic.outlet_specific_enthalpy_J_kg)
            cumulative_mass += mass_flow * dt
            cumulative_enthalpy += mass_flow * dt * enthalpy
            effective_area = area * opening
            steps.append({
                "time_s": time_s,
                "mass_flow_kg_s": mass_flow,
                "pressure_pa_abs": ambient_pressure,
                "specific_enthalpy_j_kg": enthalpy,
                "temperature_k": float(exit_state.temperature_K),
                "density_kg_m3": float(exit_state.density_kg_m3),
                "effective_area_m2": effective_area,
                "velocity_m_s": mass_flow / (float(exit_state.density_kg_m3) * effective_area) if effective_area > 0.0 else 0.0,
                "area_provenance": "explicit atmospheric valve area; inventory event does not promote this as failure opening",
                "velocity_origin": "mass_continuity_from_declared_area",
            })
            state = result.state
            time_s += dt
            if self.release_mode == "instantaneous_inventory" and state.mass_kg <= 1.0e-10:
                terminated = True
                break
            if self.release_mode == "inventory_over_600s" and state.mass_kg <= 1.0e-10:
                raise ValueError("inventory_over_600s provider depleted before 600 s")
        if self.release_mode == "instantaneous_inventory" and not terminated:
            raise ValueError("instantaneous inventory provider did not deplete within diagnostic horizon")
        if self.release_mode == "inventory_over_600s" and not math.isclose(time_s, 600.0, rel_tol=0.0, abs_tol=1.0e-8):
            raise ValueError("inventory_over_600s provider clock disagrees with 600 s")
        basis = "inventory_depletion" if self.release_mode == "instantaneous_inventory" else "inventory_over_600s"
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_model": model_class,
            "provider_source_digest": request["provider_source_digest"],
            "data": {
                "event_kind": "accidental_leak",
                "event_id": request["event_id"],
                "component_id": request["component_id"],
                "port_id": request["port_id"],
                "duration_s": time_s,
                "available_mass_kg": cumulative_mass if self.release_mode == "instantaneous_inventory" else initial_mass,
                "cumulative_mass_out_kg": cumulative_mass,
                "cumulative_static_enthalpy_out_j": cumulative_enthalpy,
                "termination_provenance": (
                    f"external {model_class} finite-volume releasable-inventory ledger; "
                    "atmospheric-pressure equilibrium residual is retained"
                    if self.release_mode == "instantaneous_inventory"
                    else f"external {model_class} finite-volume inventory ledger over declared 600 s horizon"
                ),
                "termination_basis": basis,
                "fluid": "Hydrogen",
                "steps": steps,
                "provider_meta": {
                    "model_class": model_class,
                    "release_mode": self.release_mode,
                    "initial_mass_kg": initial_mass,
                    "final_mass_kg": float(state.mass_kg),
                    "residual_mass_kg": initial_mass - float(state.mass_kg) - cumulative_mass,
                    "available_mass_definition": (
                        "cumulative releasable mass until atmospheric-pressure equilibrium"
                        if self.release_mode == "instantaneous_inventory"
                        else "initial finite-volume inventory"
                    ),
                    "diagnostic_valve_area_m2": area,
                    "diagnostic_valve_area_is_not_failure_opening": True,
                },
            },
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    model_class = "lh2dt.DynamicVaporizer" if args.mode == "vaporizer" else "lh2dt.DynamicReliquefier"
    state_payload = vars(args).copy()
    state_payload.pop("lh2dt_root", None)
    state_payload.pop("output_dir", None)
    request = _request(source_digest=source_digest, component_id=args.component_id, event_id=args.event_id,
                       port_id=args.port_id, mode=args.release_mode, state_digest=canonical_digest(state_payload),
                       height_m=args.nozzle_height_m, model_class=model_class, revision=args.model_revision)
    provider = DynamicGasInventoryProvider(root, mode=args.mode, release_mode=args.release_mode,
        duration_s=args.duration_s, time_step_s=args.time_step_s, fluid_volume_m3=args.fluid_volume_m3,
        wall_heat_capacity_j_k=args.wall_heat_capacity_j_k, fluid_wall_ua_w_k=args.fluid_wall_ua_w_k,
        boundary_ua_w_k=args.boundary_ua_w_k, boundary_temperature_k=args.boundary_temperature_k,
        maximum_heat_w=args.maximum_heat_w, inlet_pressure_pa=args.inlet_pressure_pa,
        inlet_temperature_k=args.inlet_temperature_k, opening_diameter_m=args.opening_diameter_m,
        discharge_coefficient=args.discharge_coefficient, stroke_time_s=args.stroke_time_s)
    result = export_equipment_inventory_release_history(provider, request, release_kind="gas")
    release = result.release.model_dump(mode="json")
    verification = {
        "status": "EXTERNAL_LH2DT_DYNAMIC_GAS_INVENTORY_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "provider_model": model_class,
        "release_mode": args.release_mode,
        "provider_result_digest": result.provider_result_digest,
        "strict_packet_duration_s": result.release.duration_s,
        "strict_packet_interval_count": len(result.release.steps),
        "strict_packet_mass_residual_kg": result.release.cumulative_mass_out_kg - result.release.integrated_mass_kg,
        "strict_packet_energy_residual_j": result.release.cumulative_static_enthalpy_out_j - result.release.integrated_static_enthalpy_j,
        "provider_packet_promoted": result.provider_packet_promoted,
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "limitations": ["synthetic dynamic gas-unit inventory and diagnostic valve area", "no failure opening is attached", "no site calibration, isolation reliability or independent validation"],
    }
    _save(args.output_dir / "provider_response.json", result.provider_response)
    _save(args.output_dir / "resolved_release.json", release)
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an inventory-defined dynamic LH2 gas-unit packet into PRISM")
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("vaporizer", "reliquefier"), default="vaporizer")
    parser.add_argument("--release-mode", choices=("instantaneous_inventory", "inventory_over_600s"), required=True)
    parser.add_argument("--duration-s", type=float, default=0.5)
    parser.add_argument("--time-step-s", type=float, default=0.1)
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
    parser.add_argument("--event-id", default=None)
    parser.add_argument("--port-id", default=None)
    parser.add_argument("--model-revision", default="external-library-dynamic-gas-inventory-0.1.1")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(f"dynamic LH2 inventory export failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
