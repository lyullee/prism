"""Bridge a LayeredTank liquid boundary through SLABx-LH2 and PRISM.

The equipment export supplies the total rate and interval clock.  SLABx-LH2
is called for the same upstream state and declared outlet geometry to obtain
the atmospheric partition.  A relative-rate gate prevents the two models from
quietly describing different releases; the combined packet keeps the
equipment rate as the authoritative mass ledger and scales only the SLABx
partition.  The example is synthetic and remains operator-limited.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.backend import BackendConfig, IsolatedBackend, tree_digest
from lh2_tno.contracts import Facility, canonical_digest
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.equipment_boundary import ResolvedLiquidRelease
from lh2_tno.equipment_release_adapter import (
    build_resolved_liquid_release_from_provider_response,
)
from lh2_tno.pipeline import ResearchPipeline
from lh2_tno.provider_liquid_partition import combine_provider_liquid_partition
from lh2_tno.slabx_provider_boundary import evaluate_provider_state_partition


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _provider_rows(packet: dict) -> tuple[list[dict], float]:
    if packet.get("interval_semantics") != "provider_result_end_state_representative_for_preceding_fixed_step":
        raise ValueError("LayeredTank export must declare its interval-end sampling semantics")
    dt = float(packet["time_step_s"])
    if dt <= 0.0:
        raise ValueError("LayeredTank export time_step_s must be positive")
    rows = []
    for raw in packet["steps"]:
        end_time = float(raw["time_s"])
        start_time = end_time - dt
        if start_time < -1.0e-12:
            raise ValueError("LayeredTank endpoint clock precedes its declared interval")
        source = raw["source_state"]
        flow = raw["flow"]
        rows.append({
            "time_s": max(0.0, start_time),
            "total_mass_flow_kg_s": float(flow["mass_flow_kg_s"]),
            "specific_enthalpy_j_kg": float(
                flow.get("transmitted_specific_enthalpy_J_kg", source["specific_enthalpy_J_kg"])
            ),
            "source_pressure_pa": float(source["pressure_Pa"]),
            "source_temperature_k": float(source["temperature_K"]),
            "source_density_kg_m3": float(source["density_kg_m3"]),
        })
        if "specific_entropy_J_kgK" in source:
            rows[-1]["source_specific_enthalpy_j_kg"] = float(source["specific_enthalpy_J_kg"])
            rows[-1]["source_specific_entropy_j_kg_k"] = float(source["specific_entropy_J_kgK"])
        if "vapour_quality" in source:
            rows[-1]["source_vapour_quality"] = float(source["vapour_quality"])
    return rows, dt


def _slabx_partition_rows(provider_rows: list[dict], packet: dict, dt: float) -> list[dict]:
    partition_rows = []
    for provider in provider_rows:
        total = provider["total_mass_flow_kg_s"]
        if total <= 1.0e-12:
            partition_rows.append({
                "time_s": provider["time_s"], "total_mass_flow_kg_s": 0.0,
                "gas_mass_flow_kg_s": 0.0, "airborne_liquid_mass_flow_kg_s": 0.0,
                "ground_liquid_mass_flow_kg_s": 0.0, "droplet_class_outcomes": [],
                "velocity_vector_m_s": [0.0, 0.0, 0.0],
            })
            continue
        if "source_specific_entropy_j_kg_k" not in provider:
            # Historical LayeredTank exports predate the explicit provider
            # entropy field.  Preserve their P,T screening path, while new
            # lh2dt exports use the provider-state-aware boundary below.
            from dataclasses import asdict
            from slabx_lh2.integrated_lh2_source import (
                AmbientState,
                IntegratedSourceInput,
                ModelChoices,
                NozzleGeometry,
                TankState,
                evaluate_integrated_lh2_source,
            )
            geometry = packet["source_geometry"]
            diameter = (4.0 * float(geometry["full_open_area_m2"]) / 3.141592653589793) ** 0.5
            direction = tuple(float(value) for value in geometry["direction_enu"])
            inp = IntegratedSourceInput(
                tank=TankState(
                    pressure_pa=provider["source_pressure_pa"],
                    temperature_k=provider["source_temperature_k"],
                    volume_m3=float(packet.get("tank_volume_m3", 1.0)),
                    vapour_quality=0.0,
                    fluid=packet.get("fluid", "Hydrogen"),
                ),
                pipe_sections=(),
                nozzle=NozzleGeometry(
                    diameter_m=diameter,
                    length_m=float(geometry.get("length_m", 0.01)),
                    height_m=float(geometry["nozzle_height_m"]),
                    direction_enu=direction,
                    discharge_coefficient=float(geometry["discharge_coefficient"]),
                ),
                ambient=AmbientState(
                    pressure_pa=float(packet["ambient_pressure_pa"]),
                    temperature_k=float(packet.get("ambient_temperature_k", 288.15)),
                    wind_speed_m_s=float(packet.get("wind_speed_m_s", 0.0)),
                    wind_from_bearing_deg=packet.get("wind_from_bearing_deg"),
                ),
                choices=ModelChoices(
                    phase_model="HEM",
                    fictitious_nozzle="momentum_adiabatic",
                    droplet_correlation="rescigno_yellow_book",
                    distribution="single_smd",
                ),
                duration_s=dt,
                time_step_s=dt,
            )
            history = evaluate_integrated_lh2_source(inp)
            if not history.steps:
                raise ValueError("SLABx returned no partition interval")
            step = history.steps[0]
            nozzle = step.fictitious_nozzle
            if step.gas_mass_flow_kg_s > 1.0e-12 and nozzle is None:
                raise ValueError("SLABx positive gas flow has no atmospheric handoff state")
            outcomes = [
                {
                    "ground_liquid_mass_flow_kg_s": outcome.ground_liquid_mass_flow_kg_s,
                    "airborne_liquid_mass_flow_kg_s": outcome.airborne_evaporated_mass_flow_kg_s * 0.0,
                    "flight_time_s": outcome.flight_time_s,
                    "impact_position_m": None if outcome.impact_position_m is None else list(outcome.impact_position_m),
                    "droplet_diameter_m": outcome.diameter_m,
                }
                for outcome in step.droplet_class_outcomes
            ]
            partition_rows.append({
                "time_s": provider["time_s"],
                "total_mass_flow_kg_s": step.total_mass_flow_kg_s,
                "gas_mass_flow_kg_s": step.gas_mass_flow_kg_s,
                "airborne_liquid_mass_flow_kg_s": step.airborne_liquid_mass_flow_kg_s,
                "ground_liquid_mass_flow_kg_s": step.ground_liquid_mass_flow_kg_s,
                "gas_pressure_pa_abs": None if nozzle is None else nozzle.pressure_pa,
                "gas_temperature_k": None if nozzle is None else nozzle.temperature_k,
                "gas_density_kg_m3": None if nozzle is None else nozzle.density_kg_m3,
                "gas_velocity_m_s": None if nozzle is None else nozzle.velocity_m_s,
                "droplet_class_outcomes": outcomes,
                "velocity_vector_m_s": list(step.velocity_vector_m_s),
                "slabx_step": asdict(step),
            })
            continue
        partition_row, _boundary_audit = evaluate_provider_state_partition(provider, packet)
        partition_rows.append(partition_row)
    return partition_rows


def _packet_from_bridge(source: dict, provider_rows: list[dict], rows: list[dict], audit: dict, duration_s: float,
                        component_id: str | None = None, port_id: str | None = None,
                        event_id: str | None = None) -> dict:
    mass = sum(row["total_mass_flow_kg_s"] * duration_s / len(provider_rows) for row in provider_rows)
    enthalpy = sum(row["total_mass_flow_kg_s"] * row["specific_enthalpy_j_kg"] * duration_s / len(provider_rows) for row in provider_rows)
    geometry = source["source_geometry"]
    direction = tuple(float(value) for value in geometry["direction_enu"])
    norm = sum(value * value for value in direction) ** 0.5
    direction = [value / norm for value in direction]
    gas_area = next((row["gas_boundary_area_m2"] for row in rows if row["gas_mass_flow_kg_s"] > 1.0e-12), 1.0e-6)
    contract_steps = []
    for row, provider in zip(rows, provider_rows):
        nozzle = row["real_nozzle"]
        contract_steps.append({
            "time_s": row["time_s"],
            "total_mass_flow_kg_s": row["total_mass_flow_kg_s"],
            "gas_mass_flow_kg_s": row["gas_mass_flow_kg_s"],
            "ground_liquid_mass_flow_kg_s": row["ground_liquid_mass_flow_kg_s"],
            "airborne_liquid_mass_flow_kg_s": row["airborne_liquid_mass_flow_kg_s"],
            "specific_enthalpy_j_kg": provider["specific_enthalpy_j_kg"],
            "gas_pressure_pa_abs": None if nozzle is None else nozzle["pressure_pa"],
            "gas_temperature_k": None if nozzle is None else nozzle["temperature_k"],
            "gas_density_kg_m3": None if nozzle is None else nozzle["density_kg_m3"],
            "gas_effective_area_m2": None if nozzle is None else nozzle["effective_area_m2"],
            "gas_velocity_m_s": None if nozzle is None else nozzle["velocity_m_s"],
            "gas_velocity_origin": None if nozzle is None else "provider_resolved",
            "droplet_class_outcomes": row["droplet_class_outcomes"],
        })
    provider_response = {
        "data": {
            "event_kind": "accidental_leak",
            "upstream_service": "LH2",
            "fluid": source.get("fluid", "Hydrogen"),
            "phase_basis": "two_phase",
            "duration_s": duration_s,
            "available_mass_kg": mass,
            "cumulative_mass_out_kg": mass,
            "cumulative_specific_enthalpy_out_j": enthalpy,
            "reference_area_m2": gas_area,
            "reference_area_provenance": "SLABx-LH2 scaled atmospheric gas area",
            "termination_provenance": source.get(
                "termination_provenance",
                "LayeredTank declared endpoint clock",
            ),
            "droplet_partition_provenance": "SLABx-LH2 integrated flash/droplet partition",
            "steps": contract_steps,
        }
    }
    release = build_resolved_liquid_release_from_provider_response(
        provider_response,
        component_id=component_id or source["component_id"],
        port_id=port_id or f"{component_id or source['component_id']}.out",
        event_id=event_id or "layered-tank-slabsx-liquid-bridge-diagnostic",
        provider_source_digest=canonical_digest(source),
        upstream_service_provenance="LayeredTank provider state plus SLABx-LH2 partition",
        provider_boundary_reference=(
            "LayeredTank liquid endpoint with explicit end-state interval semantics"
        ),
        input_origin="model_prediction",
        position_enu_m=[0.0, 0.0, geometry["nozzle_height_m"]],
        direction_enu=direction,
        ambient_pressure_pa_abs=source["ambient_pressure_pa"],
        ambient_temperature_k=source.get("ambient_temperature_k", 288.15),
        failure_opening_diameter_m=(
            4.0 * geometry["full_open_area_m2"] / 3.141592653589793
        ) ** 0.5,
        provider_result={"provider": provider_rows, "partition_audit": audit},
    )
    return release.model_dump(mode="json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    parser.add_argument("--slabx-root", type=Path, required=True,
                        help="directory containing source/slabx-lh2")
    parser.add_argument("--facility-component-id", default="storage",
                        help="facility component receiving this diagnostic release")
    parser.add_argument("--facility-port-id", default=None,
                        help="outward liquid/two-phase facility port; defaults to '<component>.out'")
    parser.add_argument("--chain-component-id", default=None,
                        help="optional synthetic facility component id for --execute-chain; keeps packet identity separate")
    parser.add_argument("--chain-port-id", default=None,
                        help="optional synthetic facility port id for --execute-chain; keeps packet identity separate")
    parser.add_argument("--event-id", default=None,
                        help="optional exact frequency-worklist event id; omitted for the diagnostic id")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="diagnostic output directory")
    parser.add_argument("--execute-chain", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.slabx_root / "source" / "slabx-lh2"))
    source = json.loads(args.export.read_text(encoding="utf-8"))
    provider_rows, dt = _provider_rows(source)
    partition = _slabx_partition_rows(provider_rows, source, dt)
    rows, audit = combine_provider_liquid_partition(
        provider_rows, partition, ambient_pressure_pa=source["ambient_pressure_pa"],
    )
    duration = dt * len(provider_rows)
    packet = _packet_from_bridge(source, provider_rows, rows, audit, duration,
                                 component_id=args.facility_component_id,
                                 port_id=args.facility_port_id,
                                 event_id=args.event_id)
    release = ResolvedLiquidRelease.model_validate_json(json.dumps(packet, allow_nan=False))
    output = args.output_dir or (ROOT / "results" / "20261009" / "equipment_layered_tank_slabsx")
    _save(output / "provider_export.json", source)
    _save(output / "slabx_partition.json", partition)
    _save(output / "combined_liquid_rows.json", {"rows": rows, "audit": audit})
    _save(output / "resolved_liquid_release.json", packet)
    verification = {
        "status": "BRIDGE_CONTRACT_VALIDATED",
        "release_validated": True,
        "provider_rate_owner": audit["provider_rate_owner"],
        "partition_owner": audit["partition_owner"],
        "duration_s": duration,
        "provider_mass_kg": release.integrated_mass_kg,
        "provider_mass_residual_kg": release.integrated_mass_kg - release.cumulative_mass_out_kg,
        "rate_relative_tolerance": audit["rate_relative_tolerance"],
        "rate_intervals": audit["intervals"],
        "operator_limited": True,
        "physical_validation_claim": False,
        "facility_property_basis_rebound": False,
        "source_operator": (
            "equipment_liquid_release"
            if source.get("termination_basis") == "inventory_depletion"
            else "integrated_transient"
        ),
        "termination_basis": source.get("termination_basis", "synthetic_diagnostic_horizon"),
    }
    if args.execute_chain:
        base = json.loads((ROOT / "results" / "20261008" / "full_chain" / "gas_release_request.json").read_text(encoding="utf-8"))
        facility_data = json.loads((ROOT / "examples" / "consequence_facility.json").read_text(encoding="utf-8"))
        # This is a synthetic chain diagnostic, so the example facility is
        # rebased to the provider's explicit CoolProp fluid before validation.
        # A real facility must declare the same property basis in its own
        # manifest; PRISM never performs this rebase for a production catalog.
        provider_fluid = source.get("fluid", "Hydrogen")
        for component in facility_data["components"]:
            basis = component.get("property_basis")
            if isinstance(basis, dict):
                basis["fluid"] = provider_fluid
                basis["energy_reference"] = f"CoolProp-HEOS:{provider_fluid}:native"
        facility_data["configuration_origin"] = "synthetic"
        for port in facility_data["ports"]:
            if port["id"] == "storage.out": port["phase"] = "two_phase"
        facility = Facility.model_validate_json(json.dumps(facility_data, allow_nan=False))
        chain_component_id = args.chain_component_id or args.facility_component_id
        chain_release = release
        chain_port_id = args.chain_port_id or (
            f"{chain_component_id}.out"
            if chain_component_id != release.component_id
            else release.port_id
        )
        if chain_component_id != release.component_id or chain_port_id != release.port_id:
            # Keep the exact worklist packet immutable while rebinding only
            # the synthetic facility fixture used by this diagnostic chain.
            chain_payload = release.model_dump(mode="json")
            chain_payload["component_id"] = chain_component_id
            chain_payload["port_id"] = chain_port_id
            chain_release = ResolvedLiquidRelease.model_validate_json(
                json.dumps(chain_payload, allow_nan=False)
            )
        config_raw = json.loads((ROOT / "results" / "20261009" / "backend_config_current.json").read_text(encoding="utf-8"))
        for pin in config_raw["packages"]:
            pin["sha256"] = tree_digest(Path(pin["root"]))
        backend = IsolatedBackend(BackendConfig.model_validate_json(json.dumps(config_raw)))
        request = copy.deepcopy(base)
        request.update(
            source_input=None, resolved_release=None, resolved_release_set=None,
            resolved_liquid_release=chain_release.model_dump(mode="json"),
            # A positive-mass threshold is a provider-owned depletion event;
            # the fixed diagnostic horizon remains a generic transient case.
            # This prevents a short horizon from being mislabeled as depletion
            # while allowing an explicitly crossed threshold to bind to the
            # liquid inventory operator.
            component_id=chain_component_id,
            source_operator=(
                "equipment_liquid_release"
                if source.get("termination_basis") == "inventory_depletion"
                else "integrated_transient"
            ),
            source_duration_mode="declared", available_mass_kg=chain_release.available_mass_kg,
            source_position_enu_m=list(chain_release.position_enu_m),
            evaluation_times_s=sorted(set(
                base["evaluation_times_s"]
                + [duration]
                + [step["time_s"] for step in packet["steps"]]
            )),
            release_termination={
                "basis": source.get("termination_basis", "inventory_depletion"),
                "time_s": duration,
                "provenance": source.get(
                    "termination_provenance",
                    "LayeredTank declared provider endpoint",
                ),
            },
            annual_frequency_per_year=None, annual_frequency_provenance=None,
            initiation_intensity_per_s=None,
        )
        result = ResearchPipeline(facility, backend).consequences(
            ConsequenceRequest.model_validate_json(json.dumps(request, allow_nan=False))
        )
        _save(output / "facility.json", facility.model_dump(mode="json"))
        _save(output / "request.json", request)
        _save(output / "result.json", result)
        data = result["data"]
        verification.update({
            "status": data.get("status"),
            "full_chain_executed": data.get("full_chain_executed"),
            "mass_ledger": data.get("mass_ledger"),
            "elapsed_ms": result.get("elapsed_ms"),
            "stage_elapsed_ms": data.get("stage_elapsed_ms"),
            "facility_property_basis_rebound": True,
            "facility_property_basis_fluid": provider_fluid,
            "packet_component_id": release.component_id,
            "chain_component_id": chain_component_id,
            "packet_port_id": release.port_id,
            "chain_port_id": chain_port_id,
            "facility_component_rebound": (
                chain_component_id != release.component_id or chain_port_id != release.port_id
            ),
        })
    _save(output / "verification.json", verification)
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
