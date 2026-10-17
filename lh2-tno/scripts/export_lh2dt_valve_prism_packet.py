"""Export one explicit ``lh2dt.Valve`` liquid/two-phase outlet as PRISM.

The valve model owns the hydraulic outlet calculation.  This diagnostic
adapter supplies an explicit liquid state and atmospheric boundary.  When an
isolation command and observation interval are supplied, the external
stroke-limited actuator is advanced to zero opening and the zero-flow interval
is checked explicitly; the upstream inventory remains a caller-owned ledger.
The packet remains diagnostic and does not infer field failure frequency or
site isolation reliability.
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


def _request(*, source_digest: str, component_id: str, opening_diameter_m: float,
             state_snapshot: EquipmentStateSnapshot, height_m: float,
             position_enu_m: list[float], model_revision: str,
             event_id: str | None, port_id: str | None, horizon_s: float,
             isolation_time_s: float | None,
             post_isolation_observation_s: float | None) -> AccidentReleaseExportRequest:
    port_id = port_id or f"{component_id}.accident-out"
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id or f"{component_id}/{port_id}/{opening_diameter_m:.12g}m",
        "failure_mode": "explicit_valve_atmospheric_outlet",
        "failure_opening_diameter_m": opening_diameter_m,
        "horizon_s": horizon_s,
        "position_enu_m": position_enu_m,
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "lh2dt Valve explicit atmospheric outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "Valve",
        "model_revision": model_revision,
        "state_snapshot_digest": state_snapshot.digest(),
        "state_snapshot": state_snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit external Valve liquid/two-phase diagnostic; not site-calibrated",
        "provider_termination_required": True,
        **({"isolation_time_s": isolation_time_s} if isolation_time_s is not None else {}),
        **(
            {"post_isolation_observation_s": post_isolation_observation_s}
            if post_isolation_observation_s is not None else {}
        ),
    })


class ValveAccidentProvider:
    """Evaluate one explicit full-open liquid valve boundary."""

    def __init__(self, root: Path, *, duration_s: float, time_step_s: float,
                 inlet_pressure_pa: float, inlet_temperature_k: float,
                 opening_diameter_m: float, discharge_coefficient: float,
                 isolation_time_s: float | None = None,
                 post_isolation_observation_s: float | None = None,
                 stroke_time_s: float = 0.05,
                 available_mass_kg: float | None = None) -> None:
        self.root = root.resolve()
        self.duration_s = float(duration_s)
        self.time_step_s = float(time_step_s)
        self.inlet_pressure_pa = float(inlet_pressure_pa)
        self.inlet_temperature_k = float(inlet_temperature_k)
        self.opening_diameter_m = float(opening_diameter_m)
        self.discharge_coefficient = float(discharge_coefficient)
        self.isolation_time_s = (
            None if isolation_time_s is None else float(isolation_time_s)
        )
        self.post_isolation_observation_s = (
            None
            if post_isolation_observation_s is None
            else float(post_isolation_observation_s)
        )
        self.stroke_time_s = float(stroke_time_s)
        self.available_mass_kg = (
            None if available_mass_kg is None else float(available_mass_kg)
        )

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.duration_s <= 0.0 or self.time_step_s <= 0.0:
            raise ValueError("valve diagnostic duration and time step must be positive")
        if self.isolation_time_s is not None:
            if self.isolation_time_s < 0.0 or self.isolation_time_s > self.duration_s:
                raise ValueError("isolation_time_s must lie in [0, duration_s]")
            if self.post_isolation_observation_s is None:
                raise ValueError("post_isolation_observation_s is required with isolation_time_s")
            if self.post_isolation_observation_s < 0.0:
                raise ValueError("post_isolation_observation_s must be non-negative")
            total_duration = self.isolation_time_s + self.post_isolation_observation_s
            if total_duration > self.duration_s + 1.0e-12:
                raise ValueError("isolation plus observation must fit duration_s")
            if self.stroke_time_s <= 0.0:
                raise ValueError("stroke_time_s must be positive")
        else:
            total_duration = self.duration_s
        if not math.isclose(total_duration / self.time_step_s, round(total_duration / self.time_step_s), rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("duration must be an integer number of time steps")
        if self.opening_diameter_m <= 0.0 or not 0.0 < self.discharge_coefficient <= 1.0:
            raise ValueError("valve opening diameter and discharge coefficient are invalid")

        sys.path.insert(0, str(self.root / "src"))
        from lh2dt.properties import HydrogenProperties
        from lh2dt.valve import StrokeLimitedCommandedValve, Valve

        properties = HydrogenProperties("Hydrogen")
        inlet = properties.from_pT(self.inlet_pressure_pa, self.inlet_temperature_k)
        if "liquid" not in str(inlet.phase).lower() or "gas" in str(inlet.phase).lower():
            raise ValueError("Valve diagnostic inlet must be liquid")
        ambient_pressure = float(request["ambient_pressure_pa_abs"])
        ambient = properties.saturated_vapor(ambient_pressure)
        area = math.pi * self.opening_diameter_m**2 / 4.0
        valve = Valve(area, self.discharge_coefficient, properties=properties, allow_reverse=False)
        actuator = StrokeLimitedCommandedValve(
            valve, stroke_time_s=self.stroke_time_s, initial_opening=1.0
        )
        actuator.set_target_opening(1.0)
        result = valve.evaluate(inlet, ambient, opening=1.0)
        flow = float(result.mass_flow_kg_s)
        if not math.isfinite(flow) or flow <= 0.0:
            raise ValueError("Valve diagnostic did not produce a positive outward flow")
        outlet = properties.from_ph(ambient_pressure, result.outlet_specific_enthalpy_J_kg)
        quality = outlet.quality
        if quality is None:
            if "liquid" not in str(outlet.phase).lower() or "gas" in str(outlet.phase).lower():
                raise ValueError("Valve outlet is outside the liquid/two-phase atmospheric contract")
            gas_fraction = 0.0
        elif not 0.0 <= float(quality) <= 1.0:
            raise ValueError("Valve outlet quality is outside the liquid/two-phase atmospheric contract")
        else:
            gas_fraction = float(quality)
        intervals = int(round(total_duration / self.time_step_s))
        enthalpy = float(result.outlet_specific_enthalpy_J_kg)
        steps: list[dict[str, Any]] = []
        cumulative_mass = 0.0
        cumulative_enthalpy = 0.0
        elapsed = 0.0
        zero_flow_after_isolation = True
        for index in range(intervals):
            dt = self.time_step_s
            if (
                self.isolation_time_s is not None
                and elapsed < self.isolation_time_s < elapsed + dt
            ):
                dt = self.isolation_time_s - elapsed
            if self.isolation_time_s is not None and elapsed >= self.isolation_time_s - 1.0e-12:
                actuator.set_target_opening(0.0)
            opening = actuator.advance(dt)
            hydraulic = actuator.evaluate(inlet, ambient)
            interval_flow = float(hydraulic.mass_flow_kg_s)
            if not math.isfinite(interval_flow) or interval_flow < 0.0:
                raise ValueError("StrokeLimitedCommandedValve returned invalid mass flow")
            interval_outlet = properties.from_ph(
                ambient_pressure, float(hydraulic.outlet_specific_enthalpy_J_kg)
            )
            interval_quality = interval_outlet.quality
            if interval_quality is None:
                interval_gas_fraction = 0.0
            else:
                interval_gas_fraction = min(1.0, max(0.0, float(interval_quality)))
            gas_flow = interval_flow * interval_gas_fraction
            ground_flow = interval_flow - gas_flow
            cumulative_mass += interval_flow * dt
            cumulative_enthalpy += interval_flow * dt * enthalpy
            closed_observation_start = (
                None
                if self.isolation_time_s is None
                else self.isolation_time_s + self.stroke_time_s
            )
            if (
                closed_observation_start is not None
                and elapsed >= closed_observation_start - 1.0e-12
                and interval_flow > 1.0e-12
            ):
                zero_flow_after_isolation = False
            steps.append({
                "time_s": elapsed,
                "total_mass_flow_kg_s": interval_flow,
                "gas_mass_flow_kg_s": gas_flow,
                "ground_liquid_mass_flow_kg_s": ground_flow,
                "airborne_liquid_mass_flow_kg_s": 0.0,
                "specific_enthalpy_j_kg": float(hydraulic.outlet_specific_enthalpy_J_kg),
                "droplet_class_outcomes": [{
                    "ground_liquid_mass_flow_kg_s": ground_flow,
                    "airborne_liquid_mass_flow_kg_s": 0.0,
                    "flight_time_s": 0.0,
                    "impact_position_m": [float(request["position_enu_m"][0]), float(request["position_enu_m"][1]), 0.0],
                    "droplet_diameter_m": 0.001,
                }],
            })
            elapsed += dt
        isolation_success = (
            self.isolation_time_s is not None
            and self.post_isolation_observation_s is not None
            and self.isolation_time_s + self.post_isolation_observation_s
            > self.isolation_time_s + self.stroke_time_s + 1.0e-12
            and actuator.opening <= 1.0e-12
            and zero_flow_after_isolation
        )
        if self.isolation_time_s is not None and not isolation_success:
            raise ValueError("declared isolation observation did not confirm zero flow")
        available_mass = self.available_mass_kg
        if available_mass is None:
            available_mass = cumulative_mass * 1.2
        if available_mass <= 0.0 or cumulative_mass > available_mass + 1.0e-12:
            raise ValueError("available mass must exceed the provider cumulative release")
        termination_basis = (
            "reviewed_isolation_success" if isolation_success else "synthetic_diagnostic_horizon"
        )
        termination_provenance = (
            "external StrokeLimitedCommandedValve reached zero opening at the declared "
            "isolation command and remained at zero flow through the observation interval"
            if isolation_success
            else "external Valve bounded full-open diagnostic horizon; reserve is explicit feed-through bookkeeping"
        )
        provider_meta = {
            "model_class": "lh2dt.StrokeLimitedCommandedValve",
            "mass_flow_kg_s": flow,
            "gas_quality": gas_fraction,
            "choked": bool(result.choked),
            "throat_pressure_pa": float(result.throat_pressure_Pa),
            "mass_flux_kg_m2_s": float(result.mass_flux_kg_m2_s),
            "initial_mass_kg": available_mass,
            "final_mass_kg": available_mass - cumulative_mass,
            "residual_mass_kg": available_mass - cumulative_mass,
            "final_opening": float(actuator.opening),
            "post_isolation_zero_flow": zero_flow_after_isolation,
        }
        if self.isolation_time_s is not None:
            provider_meta.update({
                "isolation_time_s": self.isolation_time_s,
                "post_isolation_observation_s": self.post_isolation_observation_s,
                "isolation_success": isolation_success,
            })
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_state_snapshot_digest": request["state_snapshot_digest"],
            "provider_model": "lh2dt.StrokeLimitedCommandedValve",
            "provider_source_digest": request["provider_source_digest"],
            "data": {
                "event_kind": "accidental_leak",
                "event_id": request["event_id"],
                "component_id": request["component_id"],
                "port_id": request["port_id"],
                "duration_s": elapsed,
                "available_mass_kg": available_mass,
                "cumulative_mass_out_kg": cumulative_mass,
                "cumulative_specific_enthalpy_out_j": cumulative_enthalpy,
                "termination_provenance": termination_provenance,
                "termination_basis": termination_basis,
                "upstream_service": "LH2",
                "fluid": "Hydrogen",
                "phase_basis": "two_phase" if gas_fraction > 0.0 and gas_fraction < 1.0 else "liquid",
                "reference_area_m2": area,
                "reference_area_provenance": "external StrokeLimitedCommandedValve full-open bore",
                "droplet_partition_provenance": "provider atmospheric liquid partition; airborne liquid explicitly zero",
                "steps": steps,
                "provider_meta": provider_meta,
            },
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
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
        "phase": "liquid",
        "position_enu_m": position_enu_m,
        "source_digest": source_digest,
    })
    request = _request(
        source_digest=source_digest,
        component_id=args.component_id,
        opening_diameter_m=args.opening_diameter_m,
        state_snapshot=state_snapshot,
        height_m=args.nozzle_height_m,
        position_enu_m=position_enu_m,
        model_revision=args.model_revision,
        event_id=args.event_id,
        port_id=args.port_id,
        horizon_s=args.duration_s,
        isolation_time_s=args.isolation_time_s,
        post_isolation_observation_s=args.post_isolation_observation_s,
    )
    provider = ValveAccidentProvider(
        root,
        duration_s=args.duration_s,
        time_step_s=args.time_step_s,
        inlet_pressure_pa=args.inlet_pressure_pa,
        inlet_temperature_k=args.inlet_temperature_k,
        opening_diameter_m=args.opening_diameter_m,
        discharge_coefficient=args.discharge_coefficient,
        isolation_time_s=args.isolation_time_s,
        post_isolation_observation_s=args.post_isolation_observation_s,
        stroke_time_s=args.stroke_time_s,
        available_mass_kg=args.available_mass_kg,
    )
    result = export_equipment_liquid_accident_history(provider, request)
    release = result.release.model_dump(mode="json")
    verification = {
        "status": "EXTERNAL_LH2DT_VALVE_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "provider_model": result.provider_response.get("provider_model"),
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
        "strict_packet_energy_residual_j": result.release.cumulative_specific_enthalpy_out_j - result.release.integrated_specific_enthalpy_out_j,
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
            "synthetic liquid state and explicit external valve boundary",
            "valve owns no inventory; available mass is explicit feed-through reserve",
            "actuator closure is a diagnostic command contract, not field isolation reliability",
            "no field frequency or independent physical validation",
        ],
    }
    _save(args.output_dir / "provider_response.json", result.provider_response)
    _save(args.output_dir / "resolved_release.json", release)
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a Valve diagnostic liquid outlet into PRISM")
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=0.2)
    parser.add_argument("--time-step-s", type=float, default=0.02)
    parser.add_argument("--inlet-pressure-pa", type=float, default=250000.0)
    parser.add_argument("--inlet-temperature-k", type=float, default=20.0)
    parser.add_argument("--opening-diameter-m", type=float, default=0.0025)
    parser.add_argument("--discharge-coefficient", type=float, default=0.7)
    parser.add_argument("--isolation-time-s", type=float, default=None)
    parser.add_argument("--post-isolation-observation-s", type=float, default=None)
    parser.add_argument("--stroke-time-s", type=float, default=0.05)
    parser.add_argument("--available-mass-kg", type=float, default=None)
    parser.add_argument("--nozzle-height-m", type=float, default=0.5)
    parser.add_argument(
        "--position-enu-m", type=float, nargs=3, default=None,
        help="absolute ENU release position; defaults to the origin with nozzle height",
    )
    parser.add_argument("--component-id", default="transfer-valve-diagnostic")
    parser.add_argument("--event-id", default=None, help="optional exact worklist event id")
    parser.add_argument("--port-id", default=None, help="optional exact facility accident port id")
    parser.add_argument("--model-revision", default="external-library-valve-0.1.1")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(f"Valve PRISM accident export failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
