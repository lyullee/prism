"""Run a LayeredTank liquid inventory history into the SLABx bridge.

The external ``lh2dt`` LayeredTank is advanced one bounded interval at a
time.  Its endpoint state and integrated boundary ledger are exported; the
positive inventory threshold stops the provider without inventing a zero-mass
EOS state.  The resulting export is then passed through the existing
LayeredTank -> SLABx-LH2 -> PRISM bridge and the outdoor consequence chain.

The geometry and threshold in this diagnostic are synthetic.  The script is
an end-to-end interface and feedback test, not a plant calibration or a
facility annual-risk result.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_layered_tank_slabsx_bridge import _save


def _run_provider(
    lh2dt_root: Path,
    *,
    time_step_s: float,
    target_release_kg: float,
    max_intervals: int,
    full_open_area_m2: float,
) -> tuple[dict, dict]:
    sys.path.insert(0, str(lh2dt_root / "src"))
    from lh2dt import (
        CommandedValve,
        HydrogenProperties,
        HorizontalVesselGeometry,
        LayeredTank,
        LayeredTankNetworkSimulator,
        LayeredTankParameters,
        LayeredTankPort,
        LayeredTankState,
        SteadyNetwork,
        Valve,
    )

    if time_step_s <= 0.0 or not math.isfinite(time_step_s):
        raise ValueError("time_step_s must be finite and positive")
    if target_release_kg <= 0.0 or not math.isfinite(target_release_kg):
        raise ValueError("target_release_kg must be finite and positive")
    if max_intervals < 1:
        raise ValueError("max_intervals must be positive")
    if full_open_area_m2 <= 0.0 or not math.isfinite(full_open_area_m2):
        raise ValueError("full_open_area_m2 must be finite and positive")

    fluid = "Hydrogen"
    properties = HydrogenProperties(fluid)
    geometry = HorizontalVesselGeometry(
        inner_diameter_m=0.10,
        straight_length_m=0.20,
        head_depth_m=0.025,
        quadrature_order=32,
    )
    parameters = LayeredTankParameters(
        liquid_cell_count=2,
        vapor_cell_count=2,
        wall_node_count=4,
        wall_heat_capacity_J_K=1.0e4,
        ambient_UA_W_K=0.0,
        distributed_boiling_model="phase_change_complementarity",
    )
    tank = LayeredTank(geometry, parameters, properties)
    saturated = tank.initialize_saturated(
        pressure_Pa=205_000.0, liquid_volume_fraction=0.2
    )
    # A small declared subcooling keeps the liquid-cell boundary on the
    # single-phase liquid branch.  It avoids asking SLABx/CoolProp to evaluate
    # an exactly saturated (P,T) pair, which is an explicit provider-state
    # condition rather than an implicit temperature correction.
    initial = tank.project_pressure(LayeredTankState(
        saturated.pressure_Pa,
        saturated.liquid_masses_kg,
        tuple(value - 500.0 for value in saturated.liquid_specific_enthalpies_J_kg),
        saturated.vapor_masses_kg,
        saturated.vapor_specific_enthalpies_J_kg,
        saturated.wall_temperatures_K,
    ))
    initial_mass = tank.total_mass_kg(initial)
    threshold_mass = initial_mass - target_release_kg
    if threshold_mass <= 0.0:
        raise ValueError("target_release_kg must be smaller than the initial inventory")

    time_step = float(time_step_s)
    discharge_coefficient = 0.8
    ambient_pressure_pa = 101_325.0
    ambient_temperature_k = 288.15
    tank_state = initial
    elapsed_s = 0.0
    cumulative_mass_out_kg = 0.0
    cumulative_energy_out_j = 0.0
    rows: list[dict] = []
    interval_audit: list[dict] = []

    # The same topology is reused for every bounded interval.  The tank state
    # is the feedback state; the network is solved again at each RK stage.
    network = SteadyNetwork(properties)
    network.add_boundary("liquid_port", tank.thermo(tank_state).liquid[0])
    network.add_boundary(
        "atmospheric_sink",
        properties.from_pT(ambient_pressure_pa, ambient_temperature_k),
    )
    valve = CommandedValve(
        Valve(
            full_open_area_m2,
            discharge_coefficient,
            properties,
            pressure_samples=12,
            allow_reverse=False,
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
    simulator = LayeredTankNetworkSimulator(
        tank,
        network,
        ports=(LayeredTankPort("liquid_port", "liquid", 0),),
        ambient_temperature_K=ambient_temperature_k,
    )

    for interval_index in range(max_intervals):
        result = simulator.simulate(
            tank_state,
            duration_s=time_step,
            time_step_s=time_step,
        )[0]
        flow = result.network_solution.link_flows["liquid_out"]
        if flow.mass_flow_kg_s < -1.0e-12:
            raise RuntimeError("LayeredTank provider returned inward liquid flow")
        boundary_mass_delta_kg = float(result.tank.cumulative_boundary_mass_kg)
        boundary_energy_delta_j = float(result.tank.cumulative_boundary_energy_J)
        outward_mass_kg = max(0.0, -boundary_mass_delta_kg)
        outward_energy_j = max(0.0, -boundary_energy_delta_j)
        average_mass_flow = outward_mass_kg / time_step
        interval_enthalpy = (
            outward_energy_j / outward_mass_kg
            if outward_mass_kg > 1.0e-15
            else float(flow.transmitted_specific_enthalpy_J_kg)
        )
        endpoint = result.tank.thermo.liquid[0]
        elapsed_s += time_step
        tank_state = result.tank.state
        cumulative_mass_out_kg += outward_mass_kg
        cumulative_energy_out_j += outward_energy_j
        rows.append(
            {
                "time_s": elapsed_s,
                "flow": {
                    # This is the interval-average rate obtained from the
                    # provider's integrated boundary mass ledger.
                    "mass_flow_kg_s": average_mass_flow,
                    "network_endpoint_mass_flow_kg_s": float(flow.mass_flow_kg_s),
                    "transmitted_specific_enthalpy_J_kg": interval_enthalpy,
                    "source_port_id": flow.source_port_id,
                    "target_port_id": flow.target_port_id,
                },
                "source_state": {
                    "pressure_Pa": float(endpoint.pressure_Pa),
                    "phase": endpoint.phase,
                    "temperature_K": float(endpoint.temperature_K),
                    "density_kg_m3": float(endpoint.density_kg_m3),
                    "specific_enthalpy_J_kg": float(endpoint.specific_enthalpy_J_kg),
                },
                "target_state": {
                    "pressure_Pa": ambient_pressure_pa,
                    "phase": "gas",
                },
                "tank": {
                    "total_mass_kg": float(tank.total_mass_kg(tank_state)),
                    "liquid_mass_kg": float(sum(tank_state.liquid_masses_kg)),
                    "vapor_mass_kg": float(sum(tank_state.vapor_masses_kg)),
                    "cumulative_boundary_mass_kg": -cumulative_mass_out_kg,
                    "cumulative_boundary_energy_J": -cumulative_energy_out_j,
                    "total_mass_residual_kg": float(result.tank.total_mass_residual_kg),
                    "total_energy_residual_J": float(result.tank.total_energy_residual_J),
                },
            }
        )
        interval_audit.append(
            {
                "interval_index": interval_index,
                "time_s": elapsed_s,
                "outward_mass_kg": outward_mass_kg,
                "outward_energy_j": outward_energy_j,
                "provider_network_endpoint_mass_flow_kg_s": float(flow.mass_flow_kg_s),
                "provider_mass_residual_kg": float(result.tank.total_mass_residual_kg),
                "provider_energy_residual_j": float(result.tank.total_energy_residual_J),
                "remaining_inventory_kg": float(tank.total_mass_kg(tank_state)),
            }
        )
        if tank.total_mass_kg(tank_state) <= threshold_mass:
            termination_basis = "inventory_depletion_positive_threshold"
            break
    else:
        raise RuntimeError("LayeredTank provider did not reach its positive inventory threshold")

    remaining_mass = tank.total_mass_kg(tank_state)
    provider_export = {
        "component_id": "storage",
        "port_id": "storage.out",
        "event_id": "layered-tank-inventory-slabsx-diagnostic",
        "event_kind": "accidental_leak",
        "upstream_service": "LH2",
        "upstream_service_provenance": "external lh2dt LayeredTank with liquid cell and commanded valve",
        "fluid": fluid,
        "ambient_pressure_pa": ambient_pressure_pa,
        "ambient_temperature_k": ambient_temperature_k,
        "tank_volume_m3": geometry.volume_m3,
        "time_step_s": time_step,
        "interval_semantics": "provider_result_end_state_representative_for_preceding_fixed_step",
        "source_geometry": {
            "full_open_area_m2": full_open_area_m2,
            "discharge_coefficient": discharge_coefficient,
            "nozzle_height_m": 1.0,
            "direction_enu": [1.0, 0.0, -1.0],
            "synthetic_geometry": True,
        },
        "provider_model": {
            "name": "lh2dt.LayeredTankNetworkSimulator",
            "properties": "HydrogenProperties(Hydrogen)",
            "layered_tank_parameters": {
                "liquid_cell_count": parameters.liquid_cell_count,
                "vapor_cell_count": parameters.vapor_cell_count,
                "wall_node_count": parameters.wall_node_count,
                "distributed_boiling_model": parameters.distributed_boiling_model,
            },
            "initial_pressure_pa": initial.pressure_Pa,
            "liquid_subcooling_offset_j_kg": -500.0,
            "initial_total_mass_kg": initial_mass,
            "threshold_mass_kg": threshold_mass,
            "target_release_kg": target_release_kg,
            "remaining_mass_kg": remaining_mass,
            "termination_basis": termination_basis,
            "termination_provenance": "provider stopped after a bounded interval crossed a declared positive mass threshold",
        },
        "available_mass_kg": initial_mass,
        "cumulative_mass_out_kg": cumulative_mass_out_kg,
        "cumulative_specific_enthalpy_out_j": cumulative_energy_out_j,
        "duration_s": elapsed_s,
        "termination_basis": "inventory_depletion",
        "termination_provenance": "external LayeredTank positive inventory threshold; no zero-mass extrapolation",
        "steps": rows,
        "interval_audit": interval_audit,
    }
    provider_meta = {
        "status": "LAYERED_TANK_INVENTORY_THRESHOLD_REACHED",
        "available_mass_kg": initial_mass,
        "threshold_mass_kg": threshold_mass,
        "remaining_mass_kg": remaining_mass,
        "cumulative_mass_out_kg": cumulative_mass_out_kg,
        "duration_s": elapsed_s,
        "interval_count": len(rows),
        "max_abs_mass_residual_kg": max(abs(item["provider_mass_residual_kg"]) for item in interval_audit),
        "max_abs_energy_residual_j": max(abs(item["provider_energy_residual_j"]) for item in interval_audit),
        "termination_basis": termination_basis,
        "operator_limited": True,
        "physical_validation_claim": False,
    }
    return provider_export, provider_meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lh2dt-root", type=Path, required=True,
                        help="external lh2dt project root containing src/lh2dt")
    parser.add_argument("--slabx-root", type=Path, required=True,
                        help="SLABx project root containing source/slabx-lh2")
    parser.add_argument("--time-step-s", type=float, default=0.5)
    parser.add_argument("--target-release-kg", type=float, default=1.0e-4)
    parser.add_argument("--max-intervals", type=int, default=64)
    parser.add_argument("--full-open-area-m2", type=float, default=1.0e-8,
                        help="declared provider outlet area; keep explicit when matching a reviewed frequency bin")
    parser.add_argument("--facility-component-id", default="storage",
                        help="facility component receiving the bridged diagnostic release")
    parser.add_argument("--facility-port-id", default=None,
                        help="outward liquid/two-phase facility port; defaults to '<component>.out'")
    parser.add_argument("--chain-component-id", default=None,
                        help="optional synthetic facility component id for the end-to-end fixture")
    parser.add_argument("--chain-port-id", default=None,
                        help="optional synthetic facility port id for the end-to-end fixture")
    parser.add_argument("--event-id", default=None,
                        help="optional exact frequency-worklist event id for the bridged packet")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="diagnostic output directory")
    args = parser.parse_args()
    output = args.output_dir or (ROOT / "results" / "20261009" / "layered_tank_inventory_slabsx")
    provider_export, provider_meta = _run_provider(
        args.lh2dt_root,
        time_step_s=args.time_step_s,
        target_release_kg=args.target_release_kg,
        max_intervals=args.max_intervals,
        full_open_area_m2=args.full_open_area_m2,
    )
    _save(output / "layered_tank_provider_export.json", provider_export)
    _save(output / "layered_tank_provider_verification.json", provider_meta)
    bridge = ROOT / "scripts" / "validate_layered_tank_slabsx_bridge.py"
    command = [
        sys.executable,
        str(bridge),
        str(output / "layered_tank_provider_export.json"),
        "--slabx-root",
        str(args.slabx_root),
        "--execute-chain",
        "--output-dir",
        str(output),
        "--facility-component-id",
        args.facility_component_id,
    ]
    if args.facility_port_id is not None:
        command.extend(["--facility-port-id", args.facility_port_id])
    if args.chain_component_id is not None:
        command.extend(["--chain-component-id", args.chain_component_id])
    if args.chain_port_id is not None:
        command.extend(["--chain-port-id", args.chain_port_id])
    if args.event_id is not None:
        command.extend(["--event-id", args.event_id])
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise subprocess.CalledProcessError(
            completed.returncode, command, output=completed.stdout, stderr=completed.stderr
        )
    bridge_verification = json.loads(completed.stdout)
    bridge_verification["provider_inventory_threshold"] = provider_meta
    bridge_verification["provider_export_record"] = "layered_tank_provider_export.json"
    bridge_verification["physical_validation_claim"] = False
    bridge_verification["operator_limited"] = True
    _save(output / "verification.json", bridge_verification)
    print(json.dumps(bridge_verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
