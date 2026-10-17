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

import CoolProp.CoolProp as CP

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.equipment_accident_export import (  # noqa: E402
    EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
    InventoryReleaseExportRequest,
    export_equipment_inventory_release_history,
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
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _coarsen_steps(steps: list[dict[str, Any]], *, duration_s: float, maximum_steps: int = 96) -> list[dict[str, Any]]:
    """Bound a long provider clock without changing its integrated mass/energy."""
    if len(steps) <= maximum_steps:
        return steps
    if not steps or duration_s <= 0.0:
        raise ValueError("cannot coarsen an empty or non-positive provider clock")
    chunk = int(math.ceil(len(steps) / maximum_steps))
    numeric = (
        "mass_flow_kg_s", "pressure_pa_abs", "specific_enthalpy_j_kg",
        "temperature_k", "density_kg_m3", "effective_area_m2", "velocity_m_s",
    )
    compact: list[dict[str, Any]] = []
    for start in range(0, len(steps), chunk):
        group = steps[start:start + chunk]
        weighted: dict[str, float] = {key: 0.0 for key in numeric}
        total_dt = 0.0
        for offset, row in enumerate(group):
            index = start + offset
            end = steps[index + 1]["time_s"] if index + 1 < len(steps) else duration_s
            dt = float(end) - float(row["time_s"])
            if dt <= 0.0:
                raise ValueError("provider clock contains a non-positive interval")
            total_dt += dt
            for key in numeric:
                weighted[key] += float(row[key]) * dt
        first = dict(group[0])
        first["time_s"] = float(group[0]["time_s"])
        for key in numeric:
            first[key] = weighted[key] / total_dt
        # Pressure and static enthalpy are the conserved thermodynamic
        # boundary quantities.  Averaging temperature and density
        # independently can create a state that is not on the declared EOS
        # (the first 600 s interval exposed this at the 1e-4 level).  Rebuild
        # those derived fields from the averaged P/H pair before the packet
        # reaches the strict gas worker.
        first["temperature_k"] = float(CP.PropsSI(
            "T", "P", first["pressure_pa_abs"], "Hmass",
            first["specific_enthalpy_j_kg"], "Hydrogen"
        ))
        first["density_kg_m3"] = float(CP.PropsSI(
            "Dmass", "P", first["pressure_pa_abs"], "Hmass",
            first["specific_enthalpy_j_kg"], "Hydrogen"
        ))
        if first["effective_area_m2"] > 0.0 and first["density_kg_m3"] > 0.0:
            # Preserve the strict mass/area/density/velocity closure after
            # averaging a variable-opening provider trace.
            first["velocity_m_s"] = first["mass_flow_kg_s"] / (
                first["density_kg_m3"] * first["effective_area_m2"]
            )
        compact.append(first)
    if len(compact) > maximum_steps or compact[-1]["time_s"] >= duration_s:
        raise ValueError("coarsened provider clock is outside the bounded packet contract")
    return compact


def _pressure_equalization_metadata(
    steps: list[dict[str, Any]],
    *,
    duration_s: float,
    ambient_pressure_pa_abs: float,
    minimum_zero_flow_intervals: int = 2,
) -> dict[str, Any]:
    """Return explicit provider-owned natural-stop evidence for a coarse packet.

    The provider history is already coarsened with mass-preserving interval
    averages.  This check therefore uses the packet rows that PRISM will
    consume, rather than reconstructing a stop from a bounded clock.  It
    requires a positive-flow row immediately before the first non-outward
    zero-flow row and a non-zero observation tail.
    """
    if len(steps) < minimum_zero_flow_intervals + 1:
        raise ValueError("pressure_equalization requires a provider observation tail")
    candidate_index = None
    for index, row in enumerate(steps):
        if index == 0:
            continue
        flow = float(row["mass_flow_kg_s"])
        previous_flow = float(steps[index - 1]["mass_flow_kg_s"])
        source = row.get("provider_source_state")
        pressure = (
            float(source["source_pressure_pa_abs"])
            if isinstance(source, Mapping) and source.get("source_pressure_pa_abs") is not None
            else None
        )
        if (
            pressure is not None
            and flow <= 1.0e-12
            and previous_flow > 1.0e-12
            and pressure <= ambient_pressure_pa_abs + 1.0e-3
        ):
            candidate_index = index
            break
    if candidate_index is None:
        raise ValueError(
            "pressure_equalization requires positive flow followed by non-outward zero flow"
        )
    tail = steps[candidate_index : candidate_index + minimum_zero_flow_intervals]
    if len(tail) < minimum_zero_flow_intervals or any(
        float(row["mass_flow_kg_s"]) > 1.0e-12 for row in tail
    ):
        raise ValueError("pressure_equalization requires a complete zero-flow observation tail")
    first = tail[0]
    last = tail[-1]
    first_source = first.get("provider_source_state")
    last_source = last.get("provider_source_state")
    if not isinstance(first_source, Mapping) or not isinstance(last_source, Mapping):
        raise ValueError("pressure_equalization requires provider source-state metadata")
    pressure = float(last_source["source_pressure_pa_abs"])
    if pressure > ambient_pressure_pa_abs + 1.0e-3:
        raise ValueError("pressure_equalization terminal source pressure remains outward")
    time_s = float(first["time_s"])
    observation_s = max(0.0, float(last["time_s"]) - time_s)
    if observation_s <= 0.0:
        raise ValueError("pressure_equalization observation interval must be positive")
    return {
        "pressure_equalization_time_s": time_s,
        "post_pressure_equalization_observation_s": observation_s,
        "pressure_equalization_success": True,
        "terminal_source_pressure_pa_abs": pressure,
        "ambient_pressure_pa_abs": float(ambient_pressure_pa_abs),
        "max_post_pressure_equalization_flow_kg_s": max(
            float(row["mass_flow_kg_s"]) for row in tail
        ),
        "pressure_equalization_observation_intervals": len(tail),
        "pressure_equalization_clock_duration_s": float(duration_s),
    }


def _request(*, source_digest: str, component_id: str, event_id: str | None,
             port_id: str | None, mode: str, state_snapshot: EquipmentStateSnapshot,
             height_m: float, position_enu_m: list[float], model_class: str, revision: str,
             failure_opening_diameter_m: float | None = None) -> InventoryReleaseExportRequest:
    port_id = port_id or f"{component_id}.accident-out"
    return InventoryReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_inventory_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id or f"{component_id}/{port_id}/{mode}",
        "release_mode": mode,
        "horizon_s": 600.0,
        "position_enu_m": position_enu_m,
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": f"{model_class} explicit inventory outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": model_class,
        "model_revision": revision,
        "failure_opening_diameter_m": failure_opening_diameter_m,
        "state_snapshot_digest": state_snapshot.digest(),
        "state_snapshot": state_snapshot.to_mapping(),
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
        if self.release_mode not in {
            "instantaneous_inventory",
            "inventory_over_600s",
            "pressure_equalization",
        }:
            raise ValueError("unsupported inventory release mode")
        if self.duration_s <= 0.0 or self.time_step_s <= 0.0 or self.fluid_volume_m3 <= 0.0:
            raise ValueError("inventory diagnostic inputs must be positive")
        if self.release_mode in {"inventory_over_600s", "pressure_equalization"} and not math.isclose(self.duration_s, 600.0, rel_tol=0.0, abs_tol=1.0e-9):
            raise ValueError("bounded 600 s inventory provider duration must be exactly 600 s")
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
        from lh2dt.dynamic_state_closure import build_dynamic_state_closure
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
        state_history: list[dict[str, Any]] = []
        cumulative_mass = 0.0
        cumulative_enthalpy = 0.0
        time_s = 0.0
        intervals = int(math.ceil(self.duration_s / self.time_step_s)) if self.release_mode == "instantaneous_inventory" else int(round(self.duration_s / self.time_step_s))
        terminated = False

        def record_state(time_value: float, current_state: Any, mass_out: float) -> None:
            fluid_state = model.thermo(current_state)
            state_history.append({
                "time_s": float(time_value),
                "mass_kg": float(current_state.mass_kg),
                "internal_energy_j": float(current_state.internal_energy_J),
                "wall_temperature_k": float(current_state.wall_temperature_K),
                "pressure_pa_abs": float(fluid_state.pressure_Pa),
                "cumulative_mass_out_kg": float(mass_out),
            })

        record_state(0.0, state, 0.0)
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
                if self.release_mode == "instantaneous_inventory":
                    # Atmospheric pressure equilibrium can stop the outlet
                    # while a substantial provider inventory is still inside
                    # the unit.  That is not depletion; fail closed instead
                    # of turning the residual inventory into a false
                    # inventory_depletion termination.
                    if state.mass_kg > 1.0e-10:
                        raise ValueError(
                            "instantaneous inventory provider reached zero flow before inventory depletion; "
                            "use an explicit bounded horizon or a provider depletion mechanism"
                        )
                    terminated = True
                    break
                # A 600 s inventory-over-time history may include provider
                # pressure-equilibrium intervals with zero outward flow.
                mass_flow = 0.0
            if self.release_mode == "instantaneous_inventory":
                dt = min(dt, max((state.mass_kg - 1.0e-10) / mass_flow, 1.0e-8))
            exit_state = properties.from_ph(ambient_pressure, float(hydraulic.outlet_specific_enthalpy_J_kg))
            if exit_state.phase not in {"gas", "supercritical_gas"}:
                raise ValueError("inventory gas-unit outlet is outside gas contract")
            # Keep the upstream and throat states in the provider response.
            # These are required inputs for any optional compressible-plane
            # adapter; the atmospheric packet's continuity velocity is not a
            # substitute for a near-field solution.
            throat_state = properties.from_ps(
                float(hydraulic.throat_pressure_Pa),
                float(fluid.specific_entropy_J_kgK),
    )
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
                "provider_source_state": {
                    "source_pressure_pa_abs": float(fluid.pressure_Pa),
                    "source_temperature_k": float(fluid.temperature_K),
                    "source_density_kg_m3": float(fluid.density_kg_m3),
                    "source_specific_enthalpy_j_kg": float(fluid.specific_enthalpy_J_kg),
                    "source_specific_entropy_j_kgk": float(fluid.specific_entropy_J_kgK),
                    "throat_pressure_pa_abs": float(hydraulic.throat_pressure_Pa),
                    "throat_temperature_k": float(throat_state.temperature_K),
                    "throat_density_kg_m3": float(throat_state.density_kg_m3),
                    "throat_specific_enthalpy_j_kg": float(throat_state.specific_enthalpy_J_kg),
                    "throat_mass_flux_kg_m2_s": float(hydraulic.mass_flux_kg_m2_s),
                    "choked": bool(hydraulic.choked),
                    "provider_source_state_provenance": (
                        "lh2dt provider fluid state before Valve.evaluate; throat state "
                        "resolved from provider entropy at provider throat pressure"
                    ),
                },
            })
            state = result.state
            time_s += dt
            record_state(time_s, state, cumulative_mass)
            if self.release_mode == "instantaneous_inventory" and state.mass_kg <= 1.0e-10:
                terminated = True
                break
            if self.release_mode in {"inventory_over_600s", "pressure_equalization"} and state.mass_kg <= 1.0e-10:
                raise ValueError("bounded inventory provider depleted before 600 s")
        if self.release_mode == "instantaneous_inventory" and not terminated:
            raise ValueError("instantaneous inventory provider did not deplete within diagnostic horizon")
        if self.release_mode in {"inventory_over_600s", "pressure_equalization"} and not math.isclose(time_s, 600.0, rel_tol=0.0, abs_tol=1.0e-8):
            raise ValueError("bounded inventory provider clock disagrees with 600 s")
        basis = (
            "inventory_depletion"
            if self.release_mode == "instantaneous_inventory"
            else "model_pressure_equalization"
            if self.release_mode == "pressure_equalization"
            else "inventory_over_600s"
        )
        declared_duration = 600.0 if self.release_mode in {"inventory_over_600s", "pressure_equalization"} else time_s
        packet_steps = _coarsen_steps(steps, duration_s=declared_duration)
        pressure_equalization = (
            _pressure_equalization_metadata(
                packet_steps,
                duration_s=declared_duration,
                ambient_pressure_pa_abs=ambient_pressure,
            )
            if self.release_mode == "pressure_equalization"
            else {}
        )
        packet_mass = sum(
            float(row["mass_flow_kg_s"]) * (
                float(packet_steps[index + 1]["time_s"]) if index + 1 < len(packet_steps) else declared_duration
            ) - float(row["mass_flow_kg_s"]) * float(row["time_s"])
            for index, row in enumerate(packet_steps)
        )
        packet_enthalpy = sum(
            float(row["mass_flow_kg_s"]) * float(row["specific_enthalpy_j_kg"]) * (
                (float(packet_steps[index + 1]["time_s"]) if index + 1 < len(packet_steps) else declared_duration)
                - float(row["time_s"])
            )
            for index, row in enumerate(packet_steps)
        )
        maximum_inventory_residual = max(
            abs(initial_mass - row["cumulative_mass_out_kg"] - row["mass_kg"])
            for row in state_history
        )
        maximum_pressure_residual = max(
            abs(
                float(model.thermo(type(state)(
                    mass_kg=float(row["mass_kg"]),
                    internal_energy_J=float(row["internal_energy_j"]),
                    wall_temperature_K=float(row["wall_temperature_k"]),
                )).pressure_Pa) - row["pressure_pa_abs"]
            )
            for row in state_history
        )
        dynamic_closure = build_dynamic_state_closure(
            state_history,
            max_abs_inventory_residual_kg=maximum_inventory_residual,
            inventory_tolerance_kg=max(1.0e-10, initial_mass * 1.0e-9),
            max_abs_pressure_residual_pa=maximum_pressure_residual,
            pressure_tolerance_pa=max(1.0e-6, self.inlet_pressure_pa * 1.0e-10),
            provenance=(
                f"{model_class} recomputed pressure from its finite-volume mass, "
                "internal-energy, and wall-temperature state before each inventory "
                "outlet evaluation; the digest covers the complete provider history."
            ),
        )
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_state_snapshot_digest": request["state_snapshot_digest"],
            "provider_model": model_class,
            "provider_source_digest": request["provider_source_digest"],
            "data": {
                "event_kind": "accidental_leak",
                "event_id": request["event_id"],
                "component_id": request["component_id"],
                "port_id": request["port_id"],
                "duration_s": declared_duration,
                # Available mass is the initial provider inventory for both
                # release modes.  Reporting only released mass here would
                # hide an open residual inventory from downstream audits.
                "available_mass_kg": initial_mass,
                "cumulative_mass_out_kg": packet_mass,
                "cumulative_static_enthalpy_out_j": packet_enthalpy,
                "termination_provenance": (
                    f"external {model_class} finite-volume releasable-inventory ledger; "
                    "atmospheric-pressure equilibrium residual is retained"
                    if self.release_mode == "instantaneous_inventory"
                    else f"external {model_class} source pressure reached the non-outward atmospheric boundary and remained at zero flow through the provider observation tail"
                    if self.release_mode == "pressure_equalization"
                    else f"external {model_class} finite-volume inventory ledger over declared 600 s horizon"
                ),
                "termination_basis": basis,
                "fluid": "Hydrogen",
                "steps": packet_steps,
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
                    "raw_interval_count": len(steps),
                    "packet_interval_count": len(packet_steps),
                    "dynamic_state_closure": dynamic_closure,
                    **pressure_equalization,
                },
            },
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    model_class = "lh2dt.DynamicVaporizer" if args.mode == "vaporizer" else "lh2dt.DynamicReliquefier"
    position_enu_m = (
        [float(value) for value in args.position_enu_m]
        if args.position_enu_m is not None
        else [0.0, 0.0, float(args.nozzle_height_m)]
    )
    state_snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": args.component_id,
        "captured_at_s": 0.0,
        "origin": "synthetic",
        "pressure_pa_abs": args.inlet_pressure_pa,
        "temperature_k": args.inlet_temperature_k,
        "phase": "vapour",
        "position_enu_m": position_enu_m,
        "source_digest": source_digest,
    })
    request = _request(source_digest=source_digest, component_id=args.component_id, event_id=args.event_id,
                       port_id=args.port_id, mode=args.release_mode, state_snapshot=state_snapshot,
                       height_m=args.nozzle_height_m, position_enu_m=position_enu_m,
                       model_class=model_class, revision=args.model_revision,
                       failure_opening_diameter_m=args.failure_opening_diameter_m)
    provider = DynamicGasInventoryProvider(root, mode=args.mode, release_mode=args.release_mode,
        duration_s=args.duration_s, time_step_s=args.time_step_s, fluid_volume_m3=args.fluid_volume_m3,
        wall_heat_capacity_j_k=args.wall_heat_capacity_j_k, fluid_wall_ua_w_k=args.fluid_wall_ua_w_k,
        boundary_ua_w_k=args.boundary_ua_w_k, boundary_temperature_k=args.boundary_temperature_k,
        maximum_heat_w=args.maximum_heat_w, inlet_pressure_pa=args.inlet_pressure_pa,
        inlet_temperature_k=args.inlet_temperature_k, opening_diameter_m=args.opening_diameter_m,
        discharge_coefficient=args.discharge_coefficient, stroke_time_s=args.stroke_time_s)
    result = export_equipment_inventory_release_history(provider, request, release_kind="gas")
    release = result.release.model_dump(mode="json")
    closure_audit = dynamic_state_closure_status(release)
    verification = {
        "status": (
            "EXTERNAL_LH2DT_DYNAMIC_GAS_INVENTORY_PRISM_PACKET_EXECUTED_DIAGNOSTIC"
            if closure_audit.get("ready") is True
            else "EXTERNAL_LH2DT_DYNAMIC_GAS_INVENTORY_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED"
        ),
        "provider_model": model_class,
        "release_mode": args.release_mode,
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
        "dynamic_state_closure": {
            "ready": closure_audit.get("ready"),
            "blocking_reasons": closure_audit.get("blocking_reasons", []),
            "provider_record_present": closure_audit.get("checks", {}).get("record_present", False),
        },
        "limitations": [
            "synthetic dynamic gas-unit inventory and diagnostic valve area",
            (
                "explicit frequency-event opening is attached; it is not inferred from the diagnostic valve area"
                if args.failure_opening_diameter_m is not None
                else "no failure opening is attached"
            ),
            "no site calibration, isolation reliability or independent validation",
        ],
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
    parser.add_argument(
        "--release-mode",
        choices=("instantaneous_inventory", "inventory_over_600s", "pressure_equalization"),
        required=True,
    )
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
    parser.add_argument(
        "--failure-opening-diameter-m", type=float, default=None,
        help="optional explicit frequency-event opening; never inferred from the diagnostic valve area",
    )
    parser.add_argument("--discharge-coefficient", type=float, default=0.7)
    parser.add_argument("--stroke-time-s", type=float, default=0.2)
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    parser.add_argument(
        "--position-enu-m", type=float, nargs=3, default=None,
        help="absolute ENU release position; defaults to the origin with nozzle height",
    )
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
