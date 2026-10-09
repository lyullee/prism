"""Export one explicit ``lh2dt.Valve`` liquid/two-phase outlet as PRISM.

The valve model owns the hydraulic outlet calculation.  This diagnostic
adapter supplies an explicit liquid state, full-open atmospheric boundary and
bounded clock; it does not infer valve inventory, failure frequency or
isolation reliability.
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
             state_snapshot: EquipmentStateSnapshot, height_m: float, model_revision: str,
             event_id: str | None, port_id: str | None) -> AccidentReleaseExportRequest:
    port_id = port_id or f"{component_id}.accident-out"
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id or f"{component_id}/{port_id}/{opening_diameter_m:.12g}m",
        "failure_mode": "explicit_valve_atmospheric_outlet",
        "failure_opening_diameter_m": opening_diameter_m,
        "horizon_s": 600.0,
        "position_enu_m": [0.0, 0.0, height_m],
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
    })


class ValveAccidentProvider:
    """Evaluate one explicit full-open liquid valve boundary."""

    def __init__(self, root: Path, *, duration_s: float, time_step_s: float,
                 inlet_pressure_pa: float, inlet_temperature_k: float,
                 opening_diameter_m: float, discharge_coefficient: float) -> None:
        self.root = root.resolve()
        self.duration_s = float(duration_s)
        self.time_step_s = float(time_step_s)
        self.inlet_pressure_pa = float(inlet_pressure_pa)
        self.inlet_temperature_k = float(inlet_temperature_k)
        self.opening_diameter_m = float(opening_diameter_m)
        self.discharge_coefficient = float(discharge_coefficient)

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.duration_s <= 0.0 or self.time_step_s <= 0.0:
            raise ValueError("valve diagnostic duration and time step must be positive")
        if not math.isclose(self.duration_s / self.time_step_s, round(self.duration_s / self.time_step_s), rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("duration must be an integer number of time steps")
        if self.opening_diameter_m <= 0.0 or not 0.0 < self.discharge_coefficient <= 1.0:
            raise ValueError("valve opening diameter and discharge coefficient are invalid")

        sys.path.insert(0, str(self.root / "src"))
        from lh2dt.properties import HydrogenProperties
        from lh2dt.valve import Valve

        properties = HydrogenProperties("Hydrogen")
        inlet = properties.from_pT(self.inlet_pressure_pa, self.inlet_temperature_k)
        if "liquid" not in str(inlet.phase).lower() or "gas" in str(inlet.phase).lower():
            raise ValueError("Valve diagnostic inlet must be liquid")
        ambient_pressure = float(request["ambient_pressure_pa_abs"])
        ambient = properties.saturated_vapor(ambient_pressure)
        area = math.pi * self.opening_diameter_m**2 / 4.0
        valve = Valve(area, self.discharge_coefficient, properties=properties, allow_reverse=False)
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
        intervals = int(round(self.duration_s / self.time_step_s))
        enthalpy = float(result.outlet_specific_enthalpy_J_kg)
        steps: list[dict[str, Any]] = []
        cumulative_mass = 0.0
        cumulative_enthalpy = 0.0
        for index in range(intervals):
            gas_flow = flow * gas_fraction
            ground_flow = flow - gas_flow
            cumulative_mass += flow * self.time_step_s
            cumulative_enthalpy += flow * self.time_step_s * enthalpy
            steps.append({
                "time_s": index * self.time_step_s,
                "total_mass_flow_kg_s": flow,
                "gas_mass_flow_kg_s": gas_flow,
                "ground_liquid_mass_flow_kg_s": ground_flow,
                "airborne_liquid_mass_flow_kg_s": 0.0,
                "specific_enthalpy_j_kg": enthalpy,
                "droplet_class_outcomes": [{
                    "ground_liquid_mass_flow_kg_s": ground_flow,
                    "airborne_liquid_mass_flow_kg_s": 0.0,
                    "flight_time_s": 0.0,
                    "impact_position_m": [float(request["position_enu_m"][0]), float(request["position_enu_m"][1]), 0.0],
                    "droplet_diameter_m": 0.001,
                }],
            })
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_state_snapshot_digest": request["state_snapshot_digest"],
            "provider_model": "lh2dt.Valve",
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
                "termination_provenance": "external Valve bounded full-open diagnostic horizon; reserve is explicit feed-through bookkeeping",
                "termination_basis": "synthetic_diagnostic_horizon",
                "upstream_service": "LH2",
                "fluid": "Hydrogen",
                "phase_basis": "two_phase" if gas_fraction > 0.0 and gas_fraction < 1.0 else "liquid",
                "reference_area_m2": area,
                "reference_area_provenance": "external Valve full-open bore",
                "droplet_partition_provenance": "provider atmospheric liquid partition; airborne liquid explicitly zero",
                "steps": steps,
                "provider_meta": {
                    "model_class": "lh2dt.Valve",
                    "mass_flow_kg_s": flow,
                    "gas_quality": gas_fraction,
                    "choked": bool(result.choked),
                    "throat_pressure_pa": float(result.throat_pressure_Pa),
                    "mass_flux_kg_m2_s": float(result.mass_flux_kg_m2_s),
                },
            },
        }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    state_snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": args.component_id,
        "captured_at_s": 0.0,
        "origin": "synthetic",
        "pressure_pa_abs": args.inlet_pressure_pa,
        "temperature_k": args.inlet_temperature_k,
        "phase": "liquid",
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "source_digest": source_digest,
    })
    request = _request(
        source_digest=source_digest,
        component_id=args.component_id,
        opening_diameter_m=args.opening_diameter_m,
        state_snapshot=state_snapshot,
        height_m=args.nozzle_height_m,
        model_revision=args.model_revision,
        event_id=args.event_id,
        port_id=args.port_id,
    )
    provider = ValveAccidentProvider(
        root,
        duration_s=args.duration_s,
        time_step_s=args.time_step_s,
        inlet_pressure_pa=args.inlet_pressure_pa,
        inlet_temperature_k=args.inlet_temperature_k,
        opening_diameter_m=args.opening_diameter_m,
        discharge_coefficient=args.discharge_coefficient,
    )
    result = export_equipment_liquid_accident_history(provider, request)
    release = result.release.model_dump(mode="json")
    verification = {
        "status": "EXTERNAL_LH2DT_VALVE_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "provider_model": "lh2dt.Valve",
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
        "limitations": [
            "synthetic liquid state, full-open Valve boundary and bounded diagnostic horizon",
            "valve owns no inventory; available mass is explicit feed-through reserve",
            "no valve failure/isolation reliability, field frequency or independent physical validation",
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
    parser.add_argument("--nozzle-height-m", type=float, default=0.5)
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
