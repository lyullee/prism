"""Build synthetic LayeredTank liquid isolation branches for work-list events.

The external ``lh2dt`` model owns tank state, valve opening, interval mass and
energy ledgers.  A success branch commands an ideal provider valve closed at a
declared time and requires a zero-flow observation; a failure branch keeps the valve open to an
explicit diagnostic horizon.  Each history is passed through the existing
LayeredTank-to-SLABx-LH2 bridge and emitted as a strict provider branch packet.

This is a development diagnostic.  Geometry, initial state, post-close observation delay,
branch probability and horizon are synthetic and are never promoted to actual
facility evidence or field frequency.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_layered_tank_slabsx_bridge import _save


def _finite_positive(name: str, value: float) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _provider_history(
    lh2dt_root: Path,
    *,
    opening_diameter_m: float,
    outcome: str,
    time_step_s: float,
    close_command_time_s: float,
    post_close_observation_delay_s: float,
    horizon_s: float,
) -> tuple[dict, dict]:
    """Run one state-feedback liquid accident history.

    The positive-mass threshold is a numerical safety stop.  It is reported as
    ``inventory_depletion`` only when crossed before the requested branch
    termination; no zero-inventory extrapolation is attempted.
    """
    if outcome not in {"success", "failure"}:
        raise ValueError("outcome must be success or failure")
    diameter = _finite_positive("opening_diameter_m", opening_diameter_m)
    dt = _finite_positive("time_step_s", time_step_s)
    close_time = _finite_positive("close_command_time_s", close_command_time_s)
    post_close_delay = _finite_positive(
        "post_close_observation_delay_s", post_close_observation_delay_s
    )
    horizon = _finite_positive("horizon_s", horizon_s)
    if close_time >= horizon and outcome == "success":
        raise ValueError("success close_command_time_s must precede horizon_s")

    sys.path.insert(0, str(lh2dt_root / "src"))
    from lh2dt import (  # type: ignore[import-not-found]
        HydrogenProperties,
        HorizontalVesselGeometry,
        LayeredTank,
        LayeredTankNetworkSimulator,
        LayeredTankParameters,
        LayeredTankPort,
        LayeredTankState,
        SteadyNetwork,
        CommandedValve,
        Valve,
    )

    properties = HydrogenProperties("Hydrogen")
    geometry = HorizontalVesselGeometry(
        inner_diameter_m=1.0,
        straight_length_m=10.0,
        head_depth_m=0.5,
        quadrature_order=32,
    )
    parameters = LayeredTankParameters(
        liquid_cell_count=2,
        vapor_cell_count=2,
        wall_node_count=4,
        wall_heat_capacity_J_K=1.0e6,
        ambient_UA_W_K=0.0,
        distributed_boiling_model="phase_change_complementarity",
    )
    tank = LayeredTank(geometry, parameters, properties=properties)
    saturated = tank.initialize_saturated(
        pressure_Pa=205_000.0, liquid_volume_fraction=0.2
    )
    initial = tank.project_pressure(
        LayeredTankState(
            saturated.pressure_Pa,
            saturated.liquid_masses_kg,
            tuple(value - 500.0 for value in saturated.liquid_specific_enthalpies_J_kg),
            saturated.vapor_masses_kg,
            saturated.vapor_specific_enthalpies_J_kg,
            saturated.wall_temperatures_K,
        )
    )
    initial_mass = float(tank.total_mass_kg(initial))
    # Keep a deliberately conservative positive-mass stop.  The external
    # layered solver rejects non-positive cell masses during an RK stage; a
    # half-inventory diagnostic threshold lets the failure branch terminate
    # with an explicit provider ledger instead of stepping into an invalid
    # zero-mass EOS state.  This is a numerical guard, not a plant depletion
    # estimate.
    positive_threshold = max(1.0e-8, 0.50 * initial_mass)

    ambient_pressure_pa = 101_325.0
    ambient_temperature_k = 288.15
    area = math.pi * diameter**2 / 4.0
    network = SteadyNetwork(properties)
    network.add_boundary("liquid_port", tank.thermo(initial).liquid[0])
    network.add_boundary(
        "atmospheric_sink",
        properties.from_pT(ambient_pressure_pa, ambient_temperature_k),
    )
    valve = CommandedValve(
        Valve(
            area,
            0.8,
            properties,
            pressure_samples=12,
            allow_reverse=False,
            closed_leakage_CdA_m2=0.0,
        ),
        initial_opening=1.0,
    )
    network.add_link(
        "liquid_out",
        "liquid_port",
        "atmospheric_sink",
        valve,
        source_port_id="TANK:L0",
        target_port_id="ATMOSPHERE:IN",
    )

    clock = {"base_s": 0.0, "last_s": 0.0}

    def command_callback(_time_s: float, _network: object) -> None:
        # Apply the command at an interval boundary.  Holding the command
        # constant through all RK stages keeps the exported interval-average
        # rate compatible with the SLABx boundary; a command halfway through
        # an interval would mix open and closed states in one packet row.
        valve.set_opening(
            0.0 if outcome == "success" and clock["base_s"] >= close_time else 1.0
        )

    simulator = LayeredTankNetworkSimulator(
        tank,
        network,
        ports=(LayeredTankPort("liquid_port", "liquid", 0),),
        ambient_temperature_K=ambient_temperature_k,
        command_callback=command_callback,
    )

    state = initial
    elapsed_s = 0.0
    cumulative_mass_kg = 0.0
    cumulative_energy_j = 0.0
    rows: list[dict] = []
    interval_audit: list[dict] = []
    termination_basis = None
    max_pre_close_flow = 0.0
    max_post_close_flow = 0.0
    close_zero_flow_confirmed = False

    while elapsed_s + 1.0e-12 < horizon:
        interval = min(dt, horizon - elapsed_s)
        result = simulator.simulate(state, duration_s=interval, time_step_s=interval)[0]
        flow = result.network_solution.link_flows["liquid_out"]
        boundary_mass_delta = float(result.tank.cumulative_boundary_mass_kg)
        boundary_energy_delta = float(result.tank.cumulative_boundary_energy_J)
        outward_mass = max(0.0, -boundary_mass_delta)
        outward_energy = max(0.0, -boundary_energy_delta)
        average_flow = outward_mass / interval
        endpoint = result.tank.thermo.liquid[0]
        elapsed_s += interval
        clock["base_s"] = elapsed_s
        state = result.tank.state
        cumulative_mass_kg += outward_mass
        cumulative_energy_j += outward_energy
        source_state = {
            "pressure_Pa": float(endpoint.pressure_Pa),
            "phase": endpoint.phase,
            "temperature_K": float(endpoint.temperature_K),
            "density_kg_m3": float(endpoint.density_kg_m3),
            "specific_enthalpy_J_kg": float(endpoint.specific_enthalpy_J_kg),
            "specific_entropy_J_kgK": float(endpoint.specific_entropy_J_kgK),
        }
        rows.append(
            {
                "time_s": elapsed_s,
                "flow": {
                    "mass_flow_kg_s": average_flow,
                    "network_endpoint_mass_flow_kg_s": float(flow.mass_flow_kg_s),
                    "transmitted_specific_enthalpy_J_kg": (
                        outward_energy / outward_mass
                        if outward_mass > 1.0e-15
                        else float(flow.transmitted_specific_enthalpy_J_kg)
                    ),
                    "source_port_id": flow.source_port_id,
                    "target_port_id": flow.target_port_id,
                },
                "source_state": source_state,
                "target_state": {"pressure_Pa": ambient_pressure_pa, "phase": "gas"},
                "tank": {
                    "total_mass_kg": float(tank.total_mass_kg(state)),
                    "liquid_mass_kg": float(sum(state.liquid_masses_kg)),
                    "vapor_mass_kg": float(sum(state.vapor_masses_kg)),
                    "cumulative_boundary_mass_kg": -cumulative_mass_kg,
                    "cumulative_boundary_energy_J": -cumulative_energy_j,
                    "total_mass_residual_kg": float(result.tank.total_mass_residual_kg),
                    "total_energy_residual_J": float(result.tank.total_energy_residual_J),
                },
                "valve": {
                    "opening": float(valve.opening),
                    "target_opening": float(valve.opening),
                },
            }
        )
        endpoint_flow = max(0.0, float(flow.mass_flow_kg_s))
        if elapsed_s <= close_time + 1.0e-12:
            max_pre_close_flow = max(max_pre_close_flow, endpoint_flow)
        if outcome == "success" and valve.opening <= 1.0e-12:
            max_post_close_flow = max(max_post_close_flow, endpoint_flow)
        interval_audit.append(
            {
                "time_s": elapsed_s,
                "outward_mass_kg": outward_mass,
                "outward_energy_j": outward_energy,
                "provider_network_endpoint_mass_flow_kg_s": endpoint_flow,
                "provider_mass_residual_kg": float(result.tank.total_mass_residual_kg),
                "provider_energy_residual_j": float(result.tank.total_energy_residual_J),
                "remaining_inventory_kg": float(tank.total_mass_kg(state)),
                "valve_opening": float(valve.opening),
            }
        )

        remaining_mass = float(tank.total_mass_kg(state))
        if remaining_mass <= positive_threshold:
            termination_basis = "inventory_depletion"
            break
        if (
            outcome == "success"
            and elapsed_s >= close_time + post_close_delay
            and valve.opening <= 1.0e-12
            and endpoint_flow <= 1.0e-12
        ):
            close_zero_flow_confirmed = True
            termination_basis = "isolation_success"
            break

    if termination_basis is None:
        if elapsed_s + 1.0e-12 >= horizon:
            termination_basis = "isolation_failure_diagnostic_horizon" if outcome == "failure" else "isolation_success_observation_horizon"
        else:
            raise RuntimeError("LayeredTank isolation branch ended without a termination basis")

    remaining_mass = float(tank.total_mass_kg(state))
    provider_export = {
        "component_id": "storage-tank-01",
        "port_id": "tank-accident-out",
        "event_id": "layered-tank-isolation-branch-diagnostic",
        "event_kind": "accidental_leak",
        "upstream_service": "LH2",
        "upstream_service_provenance": "external lh2dt LayeredTank with commanded isolation valve",
        "fluid": "Hydrogen",
        "ambient_pressure_pa": ambient_pressure_pa,
        "ambient_temperature_k": ambient_temperature_k,
        "tank_volume_m3": geometry.volume_m3,
        "time_step_s": dt,
        "interval_semantics": "provider_result_end_state_representative_for_preceding_fixed_step",
        "source_geometry": {
            "full_open_area_m2": area,
            "discharge_coefficient": 0.8,
            "nozzle_height_m": 1.0,
            "direction_enu": [0.0, 0.0, -1.0],
            "synthetic_geometry": True,
        },
        "provider_model": {
            "name": "lh2dt.LayeredTankNetworkSimulator",
            "valve_model": "CommandedValve",
            "outcome": outcome,
            "initial_pressure_pa": initial.pressure_Pa,
            "initial_total_mass_kg": initial_mass,
            "positive_inventory_threshold_kg": positive_threshold,
            "close_command_time_s": close_time,
            "post_close_observation_delay_s": post_close_delay,
            "horizon_s": horizon,
            "remaining_mass_kg": remaining_mass,
            "termination_basis": termination_basis,
        },
        "available_mass_kg": initial_mass,
        "cumulative_mass_out_kg": cumulative_mass_kg,
        "cumulative_specific_enthalpy_out_j": cumulative_energy_j,
        "duration_s": elapsed_s,
        "termination_basis": termination_basis,
        "termination_provenance": (
            "external commanded valve reached zero flow after the declared close command"
            if termination_basis == "isolation_success"
            else "external LayeredTank branch stopped at the declared positive threshold or diagnostic horizon"
        ),
        "steps": rows,
        "interval_audit": interval_audit,
    }
    provider_meta = {
        "status": "LAYERED_TANK_ISOLATION_BRANCH_COMPLETED",
        "outcome": outcome,
        "available_mass_kg": initial_mass,
        "remaining_mass_kg": remaining_mass,
        "cumulative_mass_out_kg": cumulative_mass_kg,
        "duration_s": elapsed_s,
        "interval_count": len(rows),
        "termination_basis": termination_basis,
        "close_zero_flow_confirmed": close_zero_flow_confirmed,
        "max_pre_close_flow_kg_s": max_pre_close_flow,
        "max_post_close_flow_kg_s": max_post_close_flow,
        "max_abs_mass_residual_kg": max(
            abs(item["provider_mass_residual_kg"]) for item in interval_audit
        ),
        "max_abs_energy_residual_j": max(
            abs(item["provider_energy_residual_j"]) for item in interval_audit
        ),
        "synthetic_diagnostic": True,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "frequency_inference": False,
    }
    return provider_export, provider_meta


def _coverage(worklist: dict, branch_rows: list[dict]) -> dict:
    items = worklist.get("work_items", [])
    exact_event_ids = {
        row["event_id"] for row in branch_rows if row["status"] == "PACKET_BUILT_SYNTHETIC"
    }
    event_rows = []
    for item in items:
        event_id = item.get("event_id")
        branches = [row for row in branch_rows if row["event_id"] == event_id]
        event_rows.append(
            {
                "event_id": event_id,
                "component_id": item.get("component_id"),
                "status": "EXACT_MATCH" if event_id in exact_event_ids else "UNMATCHED_NO_PROVIDER_PACKET",
                "branch_count": len(branches),
                "built_branch_count": sum(row["status"] == "PACKET_BUILT_SYNTHETIC" for row in branches),
                "branch_probability_covered": sum(
                    float(row["probability_given_event"])
                    for row in branches
                    if row["status"] == "PACKET_BUILT_SYNTHETIC"
                ),
            }
        )
    exact_count = sum(row["status"] == "EXACT_MATCH" for row in event_rows)
    return {
        "schema": "prism.provider_release_branch_catalog_coverage.diagnostic.v1",
        "status": "FULLY_MATCHED" if exact_count == len(items) else ("PARTIAL_EXACT_MATCH" if exact_count else "NO_EXACT_MATCH"),
        "worklist_event_count": len(items),
        "exact_match_count": exact_count,
        "unmatched_event_count": len(items) - exact_count,
        "branch_row_count": len(branch_rows),
        "built_branch_count": sum(row["status"] == "PACKET_BUILT_SYNTHETIC" for row in branch_rows),
        "uncomputed_branch_count": sum(row["status"] != "PACKET_BUILT_SYNTHETIC" for row in branch_rows),
        "frequency_inference": False,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "work_items": event_rows,
    }


def build_branch_packets(
    worklist: dict,
    *,
    lh2dt_root: Path,
    slabx_root: Path,
    output_dir: Path,
    component_id: str,
    time_step_s: float,
    close_command_time_s: float,
    post_close_observation_delay_s: float,
    horizon_s: float,
    max_cases: int | None,
) -> dict:
    items = [
        item
        for item in worklist.get("work_items", [])
        if item.get("component_id") == component_id
        and item.get("release_mode") == "hole"
        and item.get("provider_event_kind") == "accidental_leak"
        and item.get("required_opening_diameter_m") is not None
        and len(item.get("accident_port_ids", [])) == 1
    ]
    if max_cases is not None:
        if max_cases < 1:
            raise ValueError("max_cases must be positive when supplied")
        items = items[:max_cases]
    if not items:
        raise ValueError("no supported storage-tank hole work-list events were selected")

    branches: list[dict] = []
    rows: list[dict] = []
    for index, item in enumerate(items, start=1):
        event_id = item["event_id"]
        port_id = item["accident_port_ids"][0]
        diameter = float(item["required_opening_diameter_m"])
        case_dir = output_dir / f"storage_case_{index:02d}"
        for outcome, probability in (("success", 0.99), ("failure", 0.01)):
            branch_dir = case_dir / outcome
            row = {
                "event_id": event_id,
                "component_id": component_id,
                "port_id": port_id,
                "outcome": outcome,
                "probability_given_event": probability,
                "opening_diameter_m": diameter,
                "status": "UNCOMPUTED",
                "synthetic_diagnostic": True,
                "provider_packet_promoted": False,
                "physical_validation_claim": False,
                "frequency_inference": False,
            }
            try:
                provider_export, provider_meta = _provider_history(
                    lh2dt_root,
                    opening_diameter_m=diameter,
                    outcome=outcome,
                    time_step_s=time_step_s,
                    close_command_time_s=close_command_time_s,
                    post_close_observation_delay_s=post_close_observation_delay_s,
                    horizon_s=horizon_s,
                )
                provider_export["event_id"] = event_id
                provider_export["component_id"] = component_id
                provider_export["port_id"] = port_id
                _save(branch_dir / "layered_tank_provider_export.json", provider_export)
                _save(branch_dir / "layered_tank_provider_verification.json", provider_meta)
                bridge = ROOT / "scripts" / "validate_layered_tank_slabsx_bridge.py"
                command = [
                    sys.executable,
                    str(bridge),
                    str(branch_dir / "layered_tank_provider_export.json"),
                    "--slabx-root",
                    str(slabx_root),
                    "--facility-component-id",
                    component_id,
                    "--facility-port-id",
                    port_id,
                    "--event-id",
                    event_id,
                    "--output-dir",
                    str(branch_dir / "slabx_bridge"),
                ]
                completed = subprocess.run(command, check=False, capture_output=True, text=True)
                if completed.returncode != 0:
                    detail = completed.stderr.strip() or completed.stdout.strip()
                    raise RuntimeError(detail or f"bridge exited {completed.returncode}")
                packet_path = branch_dir / "slabx_bridge" / "resolved_liquid_release.json"
                packet = json.loads(packet_path.read_text(encoding="utf-8"))
                if packet.get("event_id") != event_id or packet.get("component_id") != component_id or packet.get("port_id") != port_id:
                    raise ValueError("bridge packet identity does not match work-list branch")
                if not math.isclose(
                    float(packet.get("failure_opening_diameter_m")),
                    diameter,
                    rel_tol=1e-10,
                    abs_tol=1e-12,
                ):
                    raise ValueError("bridge packet opening does not match work-list branch")
                branch_id = f"{event_id}::{outcome}"
                branches.append(
                    {
                        "id": branch_id,
                        "probability_given_event": probability,
                        "provenance": (
                            f"synthetic lh2dt LayeredTank commanded isolation {outcome}; "
                            "provider state and termination are retained"
                        ),
                        "release": packet,
                    }
                )
                row.update(
                    {
                        "status": "PACKET_BUILT_SYNTHETIC",
                        "branch_id": branch_id,
                        "duration_s": packet["duration_s"],
                        "termination_basis": provider_meta["termination_basis"],
                        "close_zero_flow_confirmed": provider_meta["close_zero_flow_confirmed"],
                        "max_pre_close_flow_kg_s": provider_meta["max_pre_close_flow_kg_s"],
                        "max_post_close_flow_kg_s": provider_meta["max_post_close_flow_kg_s"],
                        "provider_mass_residual_kg": provider_meta["max_abs_mass_residual_kg"],
                        "provider_energy_residual_j": provider_meta["max_abs_energy_residual_j"],
                    }
                )
            except Exception as error:  # retain every unsupported branch explicitly
                row["blocking_reason"] = f"{type(error).__name__}: {error}"
            rows.append(row)
            _save(branch_dir / "branch_verification.json", row)

    coverage = _coverage(worklist, rows)
    _save(output_dir / "provider_release_branch_catalog.json", {"branches": branches})
    _save(output_dir / "provider_branch_catalog_coverage.json", coverage)
    report = {
        "status": "SYNTHETIC_LAYERED_TANK_ISOLATION_BRANCH_DIAGNOSTIC",
        "provider_model": "lh2dt.LayeredTankNetworkSimulator",
        "component_id": component_id,
        "case_count": len(items),
        "branch_case_count": len(rows),
        "built_branch_count": len(branches),
        "uncomputed_branch_count": len(rows) - len(branches),
        "coverage_status": coverage["status"],
        "coverage_exact_match_count": coverage["exact_match_count"],
        "coverage_unmatched_event_count": coverage["unmatched_event_count"],
        "branch_probability_given_event": {"success": 0.99, "failure": 0.01},
        "synthetic_diagnostic": True,
        "provider_packet_promoted": False,
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "branches": rows,
    }
    _save(output_dir / "campaign_verification.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-worklist", type=Path, required=True)
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--slabx-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--component-id", default="storage-tank-01")
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--close-command-time-s", type=float, default=0.10)
    parser.add_argument("--post-close-observation-delay-s", type=float, default=0.05)
    parser.add_argument("--horizon-s", type=float, default=0.50)
    parser.add_argument("--max-cases", type=int, default=None)
    args = parser.parse_args()
    try:
        worklist = json.loads(args.provider_worklist.read_text(encoding="utf-8"))
        report = build_branch_packets(
            worklist,
            lh2dt_root=args.lh2dt_root,
            slabx_root=args.slabx_root,
            output_dir=args.output_dir,
            component_id=args.component_id,
            time_step_s=args.time_step_s,
            close_command_time_s=args.close_command_time_s,
            post_close_observation_delay_s=args.post_close_observation_delay_s,
            horizon_s=args.horizon_s,
            max_cases=args.max_cases,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"LayeredTank isolation branch build failed: {error}") from error
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
