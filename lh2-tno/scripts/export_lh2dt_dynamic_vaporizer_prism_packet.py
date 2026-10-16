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

from lh2_tno.equipment_accident_export import (  # noqa: E402
    EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
    AccidentReleaseExportRequest,
    InventoryReleaseExportRequest,
    export_equipment_gas_accident_history,
    export_equipment_inventory_release_history,
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
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _annotate_inventory_depletion_response(
    response: Mapping[str, Any], *, initial_mass_kg: float
) -> dict[str, Any]:
    """Expose the native positive-threshold stop without repairing the packet.

    ``lh2dt`` owns the stop decision.  PRISM records the exact threshold,
    final inventory and accounting residual so the release-boundary audit can
    distinguish a real provider stop from a finite diagnostic horizon.
    """

    if not isinstance(response, Mapping) or not isinstance(response.get("data"), Mapping):
        raise ValueError("native inventory response must contain an object data field")
    data = dict(response["data"])
    if not isinstance(data.get("provider_meta"), Mapping):
        raise ValueError("native inventory response must contain provider_meta")
    metadata = dict(data["provider_meta"])
    try:
        initial = float(initial_mass_kg)
        final_mass = float(metadata["final_mass_kg"])
        cumulative_mass = float(data["cumulative_mass_out_kg"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("native inventory response lacks finite mass ledger fields") from error
    if (
        not math.isfinite(initial)
        or not math.isfinite(final_mass)
        or not math.isfinite(cumulative_mass)
        or initial <= 0.0
        or final_mass < 0.0
        or cumulative_mass < 0.0
    ):
        raise ValueError("native inventory response contains invalid mass ledger fields")
    threshold_mass = max(initial * 1.0e-9, 1.0e-12)
    metadata.update({
        "available_mass_definition": (
            "initial finite-volume inventory with explicit positive depletion threshold"
        ),
        "depletion_threshold_kg": threshold_mass,
        "remaining_inventory_kg": final_mass,
        "max_total_mass_residual_kg": abs(
            initial - cumulative_mass - final_mass
        ),
        "termination_rule": "state.mass_kg <= max(initial_mass_kg*1e-9, 1e-12)",
    })
    data["provider_meta"] = metadata
    result = dict(response)
    result["data"] = data
    return result


def _request(*, source_digest: str, component_id: str, opening_diameter_m: float,
             state_snapshot: EquipmentStateSnapshot, height_m: float, model_class: str,
             event_id: str | None, port_id: str | None,
             model_revision: str, mode: str, horizon_s: float = 600.0,
             isolation_time_s: float | None = None,
             post_isolation_observation_s: float | None = None) -> AccidentReleaseExportRequest:
    port_id = port_id or f"{component_id}.accident-out"
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id or f"{component_id}/{port_id}/{opening_diameter_m:.12g}m",
        "failure_mode": "explicit_atmospheric_outlet_valve",
        "failure_opening_diameter_m": opening_diameter_m,
        "horizon_s": horizon_s,
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
        "state_snapshot_digest": state_snapshot.digest(),
        "state_snapshot": state_snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": (
            f"explicit external {model_class} bounded valve diagnostic ({mode}); not site-calibrated"
        ),
        "provider_termination_required": True,
        **({"isolation_time_s": isolation_time_s} if isolation_time_s is not None else {}),
        **(
            {"post_isolation_observation_s": post_isolation_observation_s}
            if post_isolation_observation_s is not None else {}
        ),
    })


class DynamicVaporizerAccidentProvider:
    """Run one finite-volume gas unit against an explicit atmospheric valve."""

    def __init__(self, root: Path, *, mode: str, duration_s: float,
                 time_step_s: float, fluid_volume_m3: float,
                 wall_heat_capacity_j_k: float, fluid_wall_ua_w_k: float,
                 boundary_ua_w_k: float, boundary_temperature_k: float,
                 maximum_heat_w: float, inlet_pressure_pa: float,
                 inlet_temperature_k: float, opening_diameter_m: float,
                 discharge_coefficient: float, stroke_time_s: float,
                 termination_mode: str = "synthetic_horizon",
                 isolation_time_s: float | None = None,
                 post_isolation_observation_s: float | None = None) -> None:
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
        self.termination_mode = termination_mode
        self.isolation_time_s = (
            None if isolation_time_s is None else float(isolation_time_s)
        )
        self.post_isolation_observation_s = (
            None
            if post_isolation_observation_s is None
            else float(post_isolation_observation_s)
        )

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
        if self.termination_mode not in {"synthetic_horizon", "inventory_depletion"}:
            raise ValueError(
                "termination_mode must be synthetic_horizon or inventory_depletion"
            )
        if self.duration_s <= 0.0 or self.time_step_s <= 0.0:
            raise ValueError("diagnostic duration and time step must be positive")
        if self.isolation_time_s is None:
            total_duration = self.duration_s
        else:
            if self.isolation_time_s < 0.0 or self.isolation_time_s >= self.duration_s:
                raise ValueError("isolation_time_s must be in [0, duration_s)")
            if self.post_isolation_observation_s is None:
                raise ValueError(
                    "post_isolation_observation_s is required with isolation_time_s"
                )
            if self.post_isolation_observation_s < 0.0:
                raise ValueError("post_isolation_observation_s must be non-negative")
            if self.stroke_time_s <= 0.0:
                raise ValueError("stroke_time_s must be positive")
            total_duration = (
                self.isolation_time_s
                + self.stroke_time_s
                + self.post_isolation_observation_s
            )
            if total_duration > self.duration_s + 1.0e-12:
                raise ValueError(
                    "isolation plus stroke plus observation must fit duration_s"
                )
            for name, value in {
                "isolation_time_s": self.isolation_time_s,
                "stroke_time_s": self.stroke_time_s,
                "post_isolation_observation_s": self.post_isolation_observation_s,
            }.items():
                if not math.isclose(value / self.time_step_s,
                                    round(value / self.time_step_s),
                                    rel_tol=0.0, abs_tol=1.0e-10):
                    raise ValueError(f"{name} must be an integer number of time steps")
        if not math.isclose(total_duration / self.time_step_s,
                            round(total_duration / self.time_step_s),
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

        if self.termination_mode == "inventory_depletion":
            if self.isolation_time_s is not None:
                raise ValueError(
                    "inventory_depletion cannot be combined with an isolation command"
                )
            # Use the native finite-volume accident exporter.  The adapter
            # below does not reinterpret its stopping rule; it only makes the
            # provider's positive threshold and residual ledger explicit for
            # PRISM's release-boundary audit.
            native_response = model.export_accident_history({
                "event_id": request["event_id"],
                "component_id": request["component_id"],
                "port_id": request["port_id"],
                "source_pressure_pa_abs": self.inlet_pressure_pa,
                "source_temperature_k": self.inlet_temperature_k,
                "ambient_pressure_pa_abs": ambient_pressure,
                "ambient_temperature_k": ambient_temperature,
                "failure_opening_diameter_m": self.opening_diameter_m,
                "horizon_s": self.duration_s,
                "time_step_s": self.time_step_s,
                "discharge_coefficient": self.discharge_coefficient,
                "stroke_time_s": self.stroke_time_s,
                "wall_temperature_k": self.inlet_temperature_k,
                "provider_source_digest": request["provider_source_digest"],
                "state_snapshot_digest": request["state_snapshot_digest"],
            })
            # These fields are a direct serialization of the stopping rule in
            # lh2dt.DynamicVaporizer.export_accident_history.  Without this
            # explicit declaration, PRISM must keep the packet unclosed.
            response = _annotate_inventory_depletion_response(
                native_response, initial_mass_kg=initial_mass
            )
            response["provider_state_snapshot_digest"] = request[
                "state_snapshot_digest"
            ]
            response["provider_source_digest"] = request["provider_source_digest"]
            return response

        area = math.pi * self.opening_diameter_m**2 / 4.0
        outlet_boundary = properties.from_pT(ambient_pressure, ambient_temperature)
        valve = StrokeLimitedCommandedValve(
            Valve(area, self.discharge_coefficient, properties=properties,
                  allow_reverse=False),
            stroke_time_s=self.stroke_time_s,
            initial_opening=0.0,
        )
        valve.set_target_opening(1.0)
        intervals = int(round(total_duration / self.time_step_s))
        steps: list[dict[str, Any]] = []
        cumulative_mass = 0.0
        cumulative_enthalpy = 0.0
        choked_count = 0
        time_s = 0.0
        zero_flow_after_isolation = True
        for index in range(intervals):
            fluid = model.thermo(state)
            if (
                self.isolation_time_s is not None
                and time_s >= self.isolation_time_s - 1.0e-12
            ):
                valve.set_target_opening(0.0)
            opening = valve.advance(self.time_step_s)
            hydraulic = valve.evaluate(fluid, outlet_boundary)
            mass_flow = float(hydraulic.mass_flow_kg_s)
            if not math.isfinite(mass_flow) or mass_flow < 0.0:
                raise ValueError(f"dynamic gas unit returned invalid outward flow at interval {index}")
            exit_state = properties.from_ph(
                ambient_pressure, float(hydraulic.outlet_specific_enthalpy_J_kg)
            )
            # Preserve the provider-native upstream and throat states.  The
            # strict PRISM gas packet intentionally carries only the resolved
            # atmospheric boundary; a later compressible near-field adapter
            # must bind to these states instead of inferring pressure from an
            # atmospheric mass-continuity velocity.
            throat_state = properties.from_ps(
                float(hydraulic.throat_pressure_Pa),
                float(fluid.specific_entropy_J_kgK),
            )
            if hydraulic.choked:
                choked_count += 1
            if exit_state.phase not in {"gas", "supercritical_gas"}:
                raise ValueError("dynamic gas unit outlet is outside the gas contract")
            result = model.step(state, fluid, 0.0, mass_flow, self.time_step_s)
            enthalpy = float(hydraulic.outlet_specific_enthalpy_J_kg)
            density = float(exit_state.density_kg_m3)
            # The strict packet schema requires a positive representative
            # area even during a fully closed, zero-flow observation row.
            # Keep a numerical lower bound that cannot create mass flow; the
            # provider's valve state and zero-flow flag carry the closure.
            effective_area = area * max(opening, 1.0e-12)
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
                "area_provenance": (
                    "explicit atmospheric valve full-bore area scaled by stroke state; "
                    "closed rows retain a positive numerical area floor"
                ),
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
            closed_observation_start = (
                None
                if self.isolation_time_s is None
                else self.isolation_time_s + self.stroke_time_s
            )
            if (
                closed_observation_start is not None
                and time_s >= closed_observation_start - 1.0e-12
                and mass_flow > 1.0e-12
            ):
                zero_flow_after_isolation = False
            state = result.state
            time_s += self.time_step_s
            if state.mass_kg <= 0.0:
                raise ValueError("dynamic gas unit inventory depleted before diagnostic horizon")
        if not math.isclose(time_s, total_duration, rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("provider clock disagrees with duration")
        isolation_success = (
            self.isolation_time_s is not None
            and self.post_isolation_observation_s is not None
            and total_duration
            > self.isolation_time_s + self.stroke_time_s + 1.0e-12
            and valve.opening <= 1.0e-12
            and zero_flow_after_isolation
        )
        if self.isolation_time_s is not None and not isolation_success:
            raise ValueError("declared isolation observation did not confirm zero flow")
        termination_basis = (
            "reviewed_isolation_success"
            if isolation_success
            else "synthetic_diagnostic_horizon"
        )
        termination_provenance = (
            "external StrokeLimitedCommandedValve reached zero opening at the declared "
            "isolation command and remained at zero flow through the observation interval"
            if isolation_success
            else (
                f"external {model_class} finite-volume state with explicit valve; "
                "residual inventory retained at synthetic horizon"
            )
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
                "duration_s": total_duration,
                "available_mass_kg": initial_mass,
                "cumulative_mass_out_kg": cumulative_mass,
                "cumulative_static_enthalpy_out_j": cumulative_enthalpy,
                "termination_provenance": termination_provenance,
                "termination_basis": termination_basis,
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
                    "isolation_time_s": self.isolation_time_s,
                    "post_isolation_observation_s": self.post_isolation_observation_s,
                    "isolation_success": isolation_success,
                    "post_isolation_zero_flow": zero_flow_after_isolation,
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
    component_id = args.component_id
    port_id = f"{component_id}.accident-out"
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
    if args.termination_mode == "inventory_depletion":
        request = InventoryReleaseExportRequest.from_mapping({
            "schema_version": "prism.equipment_inventory_export_request.v1",
            "event_kind": "accidental_leak",
            "component_id": component_id,
            "port_id": args.port_id or f"{component_id}.accident-out",
            "event_id": args.event_id or f"{component_id}/inventory-depletion",
            "release_mode": "instantaneous_inventory",
            "horizon_s": args.duration_s,
            "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
            "direction_enu": [1.0, 0.0, 0.0],
            "ambient_pressure_pa_abs": 101325.0,
            "ambient_temperature_k": 288.15,
            "provider_source_digest": source_digest,
            "provider_boundary_reference": (
                f"lh2dt {model_class} native finite-volume inventory outlet"
            ),
            "input_origin": "model_prediction",
            "model_package": "lh2dt_models",
            "model_class": model_class,
            "model_revision": args.model_revision,
            "state_snapshot_digest": state_snapshot.digest(),
            "state_snapshot": state_snapshot.to_mapping(),
            "evidence_status": "synthetic_diagnostic",
            "scenario_provenance": (
                f"explicit external {model_class} inventory-depletion diagnostic; not site-calibrated"
            ),
            "provider_termination_required": True,
        })
    else:
        request = _request(
            source_digest=source_digest, component_id=component_id,
            opening_diameter_m=args.opening_diameter_m,
            state_snapshot=state_snapshot,
            height_m=args.nozzle_height_m, model_class=model_class,
            model_revision=args.model_revision, mode=args.mode, event_id=args.event_id,
            port_id=args.port_id,
            horizon_s=args.duration_s if args.isolation_time_s is not None else 600.0,
            isolation_time_s=args.isolation_time_s,
            post_isolation_observation_s=args.post_isolation_observation_s,
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
        termination_mode=args.termination_mode,
        isolation_time_s=args.isolation_time_s,
        post_isolation_observation_s=args.post_isolation_observation_s,
    )
    if args.termination_mode == "inventory_depletion":
        result = export_equipment_inventory_release_history(provider, request)
    else:
        result = export_equipment_gas_accident_history(provider, request)
    release = result.release.model_dump(mode="json")
    verification = {
        "status": "EXTERNAL_LH2DT_DYNAMIC_GAS_UNIT_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "provider_model": model_class,
        "mode": args.mode,
        "termination_mode": args.termination_mode,
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
        "termination_basis": result.release.termination_basis,
        "isolation": {
            "requested": args.isolation_time_s is not None,
            "isolation_time_s": args.isolation_time_s,
            "post_isolation_observation_s": args.post_isolation_observation_s,
            "provider_isolation_success": (
                result.provider_response.get("data", {})
                .get("provider_meta", {})
                .get("isolation_success")
            ),
        },
        "limitations": [
            "synthetic dynamic gas-unit geometry, initial state, valve opening and atmospheric boundary",
            "isolation command is a diagnostic provider contract, not field isolation reliability",
            "no site calibration, failure frequency or independent physical validation",
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
    parser.add_argument(
        "--termination-mode", choices=("synthetic_horizon", "inventory_depletion"),
        default="synthetic_horizon",
        help="use the native positive-threshold inventory stop instead of a bounded diagnostic horizon",
    )
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
    parser.add_argument(
        "--isolation-time-s", type=float, default=None,
        help="optional explicit isolation command time; requires post-isolation observation",
    )
    parser.add_argument(
        "--post-isolation-observation-s", type=float, default=None,
        help="optional zero-flow observation after valve stroke completion",
    )
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    parser.add_argument("--component-id", default="dynamic-vaporizer-diagnostic")
    parser.add_argument("--event-id", default=None, help="optional exact worklist event id for a structural diagnostic")
    parser.add_argument("--port-id", default=None, help="optional exact facility accident port id")
    parser.add_argument("--model-revision", default="external-library-dynamic-gas-unit-0.1.1")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(f"dynamic LH2 gas-unit PRISM accident export failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
