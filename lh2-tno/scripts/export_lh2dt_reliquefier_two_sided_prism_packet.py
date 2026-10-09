"""Export a strict two-ended ``DynamicReliquefier`` rupture packet.

Both atmospheric endpoints are computed from one shared finite-volume state.
The adapter creates a ``ResolvedGasReleaseSet`` and never duplicates one
endpoint to stand in for the other.
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
from lh2_tno.equipment_boundary import ResolvedGasReleaseSet  # noqa: E402
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


def _request(*, source_digest: str, component_id: str, port_id: str,
             event_id: str, opening_diameter_m: float, state_snapshot: EquipmentStateSnapshot,
             height_m: float, revision: str) -> AccidentReleaseExportRequest:
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id,
        "failure_mode": "explicit_two_sided_full_bore_rupture",
        "failure_opening_diameter_m": opening_diameter_m,
        "horizon_s": 600.0,
        "position_enu_m": [0.0, 0.0, height_m],
        "direction_enu": [1.0 if port_id.endswith("-1") else -1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 288.15,
        "provider_source_digest": source_digest,
        "provider_boundary_reference": "lh2dt DynamicReliquefier shared state with two explicit atmospheric outlets",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "DynamicReliquefier",
        "model_revision": revision,
        "state_snapshot_digest": state_snapshot.digest(),
        "state_snapshot": state_snapshot.to_mapping(),
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit external DynamicReliquefier two-sided rupture diagnostic; not site-calibrated",
        "provider_termination_required": True,
    })


class TwoSidedReliquefierProvider:
    def __init__(self, root: Path, *, duration_s: float, time_step_s: float,
                 fluid_volume_m3: float, wall_heat_capacity_j_k: float,
                 fluid_wall_ua_w_k: float, boundary_ua_w_k: float,
                 boundary_temperature_k: float, maximum_heat_w: float,
                 inlet_pressure_pa: float, inlet_temperature_k: float,
                 opening_diameter_m: float, discharge_coefficient: float) -> None:
        self.root = root.resolve()
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
        self._responses: dict[str, Mapping[str, Any]] | None = None

    def _build(self, request: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        if self.duration_s <= 0.0 or self.time_step_s <= 0.0 or not math.isclose(self.duration_s / self.time_step_s, round(self.duration_s / self.time_step_s), rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("two-sided rupture duration must be a positive integer number of time steps")
        sys.path.insert(0, str(self.root / "src"))
        from lh2dt.dynamic_reliquefier import DynamicReliquefier
        from lh2dt.properties import HydrogenProperties
        from lh2dt.valve import Valve
        properties = HydrogenProperties("Hydrogen")
        model = DynamicReliquefier(self.fluid_volume_m3, self.wall_heat_capacity_j_k, self.fluid_wall_ua_w_k,
                                   self.boundary_temperature_k, self.boundary_ua_w_k, self.maximum_heat_w,
                                   properties=properties)
        inlet = properties.from_pT(self.inlet_pressure_pa, self.inlet_temperature_k)
        if inlet.phase not in {"gas", "supercritical_gas"}:
            raise ValueError("reliquefier rupture initial state must be gas-like")
        state = model.initialize(inlet)
        initial_mass = float(state.mass_kg)
        ambient_pressure = float(request["ambient_pressure_pa_abs"])
        ambient_temperature = float(request["ambient_temperature_k"])
        ambient = properties.from_pT(ambient_pressure, ambient_temperature)
        area = math.pi * self.opening_diameter_m**2 / 4.0
        valves = {
            "reliquefier-accident-out-1": Valve(area, self.discharge_coefficient, properties=properties, allow_reverse=False),
            "reliquefier-accident-out-2": Valve(area, self.discharge_coefficient, properties=properties, allow_reverse=False),
        }
        endpoint_steps = {port: [] for port in valves}
        cumulative = {port: 0.0 for port in valves}
        enthalpy_totals = {port: 0.0 for port in valves}
        time_s = 0.0
        intervals = int(round(self.duration_s / self.time_step_s))
        for index in range(intervals):
            fluid = model.thermo(state)
            hydraulic = {port: valve.evaluate(fluid, ambient, opening=1.0) for port, valve in valves.items()}
            flows = {port: float(result.mass_flow_kg_s) for port, result in hydraulic.items()}
            if any(not math.isfinite(flow) or flow < 0.0 for flow in flows.values()):
                raise ValueError(f"two-sided reliquefier returned invalid flow at interval {index}")
            total_flow = sum(flows.values())
            if total_flow <= 0.0:
                raise ValueError("two-sided reliquefier produced no outward flow")
            if state.mass_kg - total_flow * self.time_step_s <= 1.0e-10:
                raise ValueError("two-sided diagnostic horizon would deplete shared inventory")
            result = model.step(state, fluid, 0.0, total_flow, self.time_step_s)
            for port, hydraulic_result in hydraulic.items():
                exit_state = properties.from_ph(ambient_pressure, float(hydraulic_result.outlet_specific_enthalpy_J_kg))
                if exit_state.phase not in {"gas", "supercritical_gas"}:
                    raise ValueError("two-sided reliquefier endpoint is outside gas contract")
                enthalpy = float(hydraulic_result.outlet_specific_enthalpy_J_kg)
                flow = flows[port]
                cumulative[port] += flow * self.time_step_s
                enthalpy_totals[port] += flow * self.time_step_s * enthalpy
                endpoint_steps[port].append({
                    "time_s": time_s,
                    "mass_flow_kg_s": flow,
                    "pressure_pa_abs": ambient_pressure,
                    "specific_enthalpy_j_kg": enthalpy,
                    "temperature_k": float(exit_state.temperature_K),
                    "density_kg_m3": float(exit_state.density_kg_m3),
                    "effective_area_m2": area,
                    "velocity_m_s": flow / (float(exit_state.density_kg_m3) * area),
                    "area_provenance": "explicit full-bore rupture endpoint area",
                    "velocity_origin": "mass_continuity_from_declared_area",
                })
            state = result.state
            time_s += self.time_step_s
        responses = {}
        for port in valves:
            responses[port] = {
                "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
                "provider_state_snapshot_digest": request["state_snapshot_digest"],
                "provider_model": "lh2dt.DynamicReliquefier",
                "provider_source_digest": request["provider_source_digest"],
                "data": {
                    "event_kind": "accidental_leak",
                    "event_id": request["event_id"],
                    "component_id": request["component_id"],
                    "port_id": port,
                    "duration_s": self.duration_s,
                    "available_mass_kg": initial_mass,
                    "cumulative_mass_out_kg": cumulative[port],
                    "cumulative_static_enthalpy_out_j": enthalpy_totals[port],
                    "termination_provenance": "external DynamicReliquefier shared inventory over declared two-sided rupture horizon",
                    "termination_basis": "two_sided_rupture",
                    "fluid": "Hydrogen",
                    "steps": endpoint_steps[port],
                    "provider_meta": {
                        "model_class": "lh2dt.DynamicReliquefier",
                        "rupture_endpoint": port,
                        "shared_initial_mass_kg": initial_mass,
                        "shared_final_mass_kg": float(state.mass_kg),
                        "shared_total_cumulative_mass_kg": sum(cumulative.values()),
                        "opening_diameter_m": self.opening_diameter_m,
                    },
                },
            }
        return responses

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._responses is None:
            self._responses = self._build(request)
        port = str(request["port_id"])
        if port not in self._responses:
            raise ValueError("two-sided provider request port is not one of the declared rupture endpoints")
        return self._responses[port]


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    event_id = args.event_id or f"{args.component_id}/two-sided/{args.opening_diameter_m:.12g}m"
    state_snapshot = EquipmentStateSnapshot.from_mapping({
        "schema_version": EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        "component_id": args.component_id,
        "captured_at_s": 0.0,
        "origin": "synthetic",
        "pressure_pa_abs": args.inlet_pressure_pa,
        "temperature_k": args.inlet_temperature_k,
        "phase": "vapour",
        "position_enu_m": [0.0, 0.0, args.nozzle_height_m],
        "source_digest": source_digest,
    })
    provider = TwoSidedReliquefierProvider(root, duration_s=args.duration_s, time_step_s=args.time_step_s,
        fluid_volume_m3=args.fluid_volume_m3, wall_heat_capacity_j_k=args.wall_heat_capacity_j_k,
        fluid_wall_ua_w_k=args.fluid_wall_ua_w_k, boundary_ua_w_k=args.boundary_ua_w_k,
        boundary_temperature_k=args.boundary_temperature_k, maximum_heat_w=args.maximum_heat_w,
        inlet_pressure_pa=args.inlet_pressure_pa, inlet_temperature_k=args.inlet_temperature_k,
        opening_diameter_m=args.opening_diameter_m, discharge_coefficient=args.discharge_coefficient)
    requests = [_request(source_digest=source_digest, component_id=args.component_id, port_id=port,
                          event_id=event_id, opening_diameter_m=args.opening_diameter_m,
                          state_snapshot=state_snapshot, height_m=args.nozzle_height_m,
                          revision=args.model_revision) for port in ("reliquefier-accident-out-1", "reliquefier-accident-out-2")]
    results = [export_equipment_gas_accident_history(provider, request) for request in requests]
    releases = tuple(result.release for result in results)
    available_mass = releases[0].available_mass_kg
    release_set = ResolvedGasReleaseSet(
        event_id=event_id,
        component_id=args.component_id,
        releases=releases,
        available_mass_kg=available_mass,
        cumulative_mass_out_kg=sum(release.cumulative_mass_out_kg for release in releases),
        inventory_provenance="external DynamicReliquefier shared finite-volume inventory and two explicit rupture endpoints",
    )
    packet = {
        "provider_export_schema": "prism.resolved_release_set.v1",
        "event_id": event_id,
        "component_id": args.component_id,
        "rupture_mode": "two_sided_rupture",
        "releases": [release.model_dump(mode="json") for release in releases],
        "available_mass_kg": release_set.available_mass_kg,
        "cumulative_mass_out_kg": release_set.cumulative_mass_out_kg,
        "inventory_provenance": release_set.inventory_provenance,
        "provider_source_digest": source_digest,
        "provider_result_digest": canonical_digest([result.provider_response for result in results]),
    }
    verification = {
        "status": "EXTERNAL_LH2DT_RELIQUEFIER_TWO_SIDED_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "provider_model": "lh2dt.DynamicReliquefier",
        "state_snapshot": state_snapshot.to_mapping(),
        "state_snapshot_handoff": {
            "present": True,
            "digest": state_snapshot.digest(),
            "provider_echo_digest": [result.provider_response.get("provider_state_snapshot_digest") for result in results],
            "digest_match": all(result.provider_response.get("provider_state_snapshot_digest") == state_snapshot.digest() for result in results),
        },
        "strict_packet_duration_s": release_set.duration_s,
        "strict_packet_endpoint_count": len(release_set.releases),
        "strict_packet_mass_residual_kg": release_set.cumulative_mass_out_kg - release_set.integrated_mass_kg,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "limitations": ["synthetic shared inventory, full-bore endpoints and bounded horizon", "two-sided endpoints are diagnostic and not field-calibrated", "no facility frequency or independent validation"],
    }
    _save(args.output_dir / "resolved_release_set.json", packet)
    _save(args.output_dir / "provider_response_endpoints.json", {key: provider._responses[key] for key in provider._responses or {}})
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a two-sided DynamicReliquefier rupture set into PRISM")
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=1.0e-5)
    parser.add_argument("--time-step-s", type=float, default=1.0e-6)
    parser.add_argument("--fluid-volume-m3", type=float, default=0.01)
    parser.add_argument("--wall-heat-capacity-j-k", type=float, default=1000.0)
    parser.add_argument("--fluid-wall-ua-w-k", type=float, default=100.0)
    parser.add_argument("--boundary-ua-w-k", type=float, default=10.0)
    parser.add_argument("--boundary-temperature-k", type=float, default=288.15)
    parser.add_argument("--maximum-heat-w", type=float, default=10000.0)
    parser.add_argument("--inlet-pressure-pa", type=float, default=102000.0)
    parser.add_argument("--inlet-temperature-k", type=float, default=300.0)
    parser.add_argument("--opening-diameter-m", type=float, default=0.025)
    parser.add_argument("--discharge-coefficient", type=float, default=0.7)
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    parser.add_argument("--component-id", default="reliquefier-01")
    parser.add_argument("--event-id", default=None)
    parser.add_argument("--model-revision", default="external-library-dynamic-reliquefier-two-sided-0.1.1")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(f"two-sided reliquefier export failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
