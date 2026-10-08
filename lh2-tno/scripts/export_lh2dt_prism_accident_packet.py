"""Run one explicit external ``lh2dt`` accident scenario into PRISM's packet contract.

This is the first executable provider bridge for the new
``export_accident_history(request)`` interface.  It uses the external
``HomogeneousTank`` and ``Valve`` classes with an explicit failed opening and
keeps the provider's real step clock and inventory ledger.  The default inputs
are synthetic diagnostics; the output is therefore a strict packet with
``provider_packet_promoted=false`` until qualified equipment evidence is
supplied.

The script deliberately does not turn a normal ``lh2dt`` state export into an
accident.  The provider method receives the explicit PRISM accident request,
checks its opening identity, executes a separate transient, and returns the
``prism.external_accident_history.v1`` response consumed by
``equipment_accident_export``.
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
    export_equipment_liquid_accident_history,
)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    for path in files:
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


class HomogeneousTankAccidentProvider:
    """Explicit provider adapter around external ``HomogeneousTank``/``Valve``."""

    def __init__(
        self,
        lh2dt_root: Path,
        *,
        duration_s: float,
        time_step_s: float,
        tank_pressure_pa: float,
        liquid_volume_fraction: float,
        hole_diameter_m: float,
        discharge_coefficient: float,
        termination_threshold_mass_kg: float | None,
        release_kind: str = "liquid",
    ) -> None:
        self.lh2dt_root = Path(lh2dt_root).resolve()
        self.duration_s = float(duration_s)
        self.time_step_s = float(time_step_s)
        self.tank_pressure_pa = float(tank_pressure_pa)
        self.liquid_volume_fraction = float(liquid_volume_fraction)
        self.hole_diameter_m = float(hole_diameter_m)
        self.discharge_coefficient = float(discharge_coefficient)
        self.termination_threshold_mass_kg = termination_threshold_mass_kg
        self.release_kind = release_kind

    def export_accident_history(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Execute the explicitly requested opening and return a provider history."""

        from export_lh2dt_accident_history import export_history
        from lh2dt.properties import HydrogenProperties

        opening = float(request["failure_opening_diameter_m"])
        if not math.isclose(opening, self.hole_diameter_m, rel_tol=0.0, abs_tol=1.0e-12):
            raise ValueError("provider configuration opening disagrees with accident request")
        export, audit = export_history(
            self.lh2dt_root,
            duration_s=self.duration_s,
            time_step_s=self.time_step_s,
            tank_pressure_pa=self.tank_pressure_pa,
            liquid_volume_fraction=self.liquid_volume_fraction,
            hole_diameter_m=self.hole_diameter_m,
            discharge_coefficient=self.discharge_coefficient,
            ambient_pressure_pa=float(request["ambient_pressure_pa_abs"]),
            ambient_temperature_k=float(request["ambient_temperature_k"]),
            termination_threshold_mass_kg=self.termination_threshold_mass_kg,
        )
        source_geometry = export["source_geometry"]
        properties = HydrogenProperties(export["fluid"])
        raw_steps = export["steps"]
        if not raw_steps:
            raise ValueError("external provider returned no accident steps")
        steps: list[dict[str, Any]] = []
        previous_time = 0.0
        cumulative_enthalpy = 0.0
        for index, raw in enumerate(raw_steps):
            end_time = float(raw["time_s"])
            interval_s = end_time - previous_time
            if interval_s <= 0.0 or not math.isfinite(interval_s):
                raise ValueError(f"external provider step {index} has a non-positive interval")
            source = raw["source_state"]
            flow = raw["flow"]
            mass_flow = float(flow["mass_flow_kg_s"])
            area = float(source_geometry["full_open_area_m2"])
            enthalpy = float(flow["transmitted_specific_enthalpy_J_kg"])
            # The provider must export a resolved atmospheric plane.  Reusing
            # the tank pressure here would create an underexpanded packet and
            # the PRISM low-Mach worker correctly rejects that boundary.
            exit_state = properties.from_ph(
                float(request["ambient_pressure_pa_abs"]), enthalpy
            )
            cumulative_enthalpy += mass_flow * interval_s * enthalpy
            if self.release_kind == "gas":
                quality = exit_state.quality
                if quality is None or quality < 1.0 - 1.0e-9:
                    raise ValueError(
                        "external provider atmospheric state is not a vapour exit; "
                        "use --release-kind liquid for a two-phase flash"
                    )
                density = float(exit_state.density_kg_m3)
                velocity = mass_flow / (density * area)
                steps.append({
                    "time_s": previous_time,
                    "mass_flow_kg_s": mass_flow,
                    "pressure_pa_abs": float(exit_state.pressure_Pa),
                    "specific_enthalpy_j_kg": enthalpy,
                    "temperature_k": float(exit_state.temperature_K),
                    "density_kg_m3": density,
                    "effective_area_m2": area,
                    "velocity_m_s": velocity,
                    "area_provenance": "external lh2dt explicit failed-opening area",
                    "velocity_origin": "mass_continuity_from_declared_area",
                })
            elif self.release_kind == "liquid":
                quality = exit_state.quality
                if quality is None or not 0.0 <= quality <= 1.0:
                    raise ValueError("external provider atmospheric state is not a resolved liquid/two-phase state")
                gas_flow = mass_flow * float(quality)
                ground_flow = mass_flow - gas_flow
                vapor = properties.saturated_vapor(float(request["ambient_pressure_pa_abs"]))
                gas_velocity = gas_flow / (vapor.density_kg_m3 * area) if gas_flow > 0.0 else 0.0
                steps.append({
                    "time_s": previous_time,
                    "total_mass_flow_kg_s": mass_flow,
                    "gas_mass_flow_kg_s": gas_flow,
                    "ground_liquid_mass_flow_kg_s": ground_flow,
                    "airborne_liquid_mass_flow_kg_s": 0.0,
                    "specific_enthalpy_j_kg": enthalpy,
                    "gas_pressure_pa_abs": float(vapor.pressure_Pa),
                    "gas_temperature_k": float(vapor.temperature_K),
                    "gas_density_kg_m3": float(vapor.density_kg_m3),
                    "gas_effective_area_m2": area,
                    "gas_velocity_m_s": gas_velocity,
                    "gas_velocity_origin": "mass_continuity_from_declared_area",
                    "droplet_class_outcomes": [{
                        "ground_liquid_mass_flow_kg_s": ground_flow,
                        "airborne_liquid_mass_flow_kg_s": 0.0,
                        "flight_time_s": 0.0,
                        "impact_position_m": list(request["position_enu_m"]),
                        "droplet_diameter_m": 0.001,
                    }],
                })
            else:
                raise ValueError("release_kind must be gas or liquid")
            previous_time = end_time
        duration = float(audit["actual_duration_s"])
        if not math.isclose(previous_time, duration, rel_tol=0.0, abs_tol=1.0e-10):
            raise ValueError("provider step clock disagrees with actual duration")
        data = {
            "event_kind": "accidental_leak",
            "event_id": request["event_id"],
            "component_id": request["component_id"],
            "port_id": request["port_id"],
            "duration_s": duration,
            "available_mass_kg": float(export["provider_initial_mass_kg"]),
            "cumulative_mass_out_kg": float(audit["provider_mass_kg"]),
            "termination_provenance": export["termination_provenance"],
            "termination_basis": export["termination_basis"],
            "steps": steps,
        }
        if self.release_kind == "liquid":
            data.update({
                "upstream_service": "LH2",
                "fluid": export["fluid"],
                "phase_basis": "two_phase",
                "reference_area_m2": float(source_geometry["full_open_area_m2"]),
                "reference_area_provenance": "external lh2dt explicit failed-opening area",
                "cumulative_specific_enthalpy_out_j": cumulative_enthalpy,
                "droplet_partition_provenance": "provider diagnostic ground interception; airborne liquid set to zero",
            })
        else:
            data["cumulative_static_enthalpy_out_j"] = cumulative_enthalpy
        return {
            "provider_export_schema": EXTERNAL_ACCIDENT_EXPORT_SCHEMA,
            "provider_model": "lh2dt.HomogeneousTank+Valve",
            "provider_source_digest": request["provider_source_digest"],
            "data": data,
        }

def build_request(
    provider_source_digest: str,
    *,
    component_id: str,
    port_id: str,
    event_id: str,
    hole_diameter_m: float,
    ambient_pressure_pa: float,
    ambient_temperature_k: float,
    position_enu_m: list[float],
    direction_enu: list[float],
    model_revision: str,
    state_snapshot_digest: str,
) -> AccidentReleaseExportRequest:
    return AccidentReleaseExportRequest.from_mapping({
        "schema_version": "prism.equipment_accident_export_request.v1",
        "event_kind": "accidental_leak",
        "component_id": component_id,
        "port_id": port_id,
        "event_id": event_id,
        "failure_mode": "explicit_failed_opening",
        "failure_opening_diameter_m": hole_diameter_m,
        "horizon_s": 600.0,
        "position_enu_m": position_enu_m,
        "direction_enu": direction_enu,
        "ambient_pressure_pa_abs": ambient_pressure_pa,
        "ambient_temperature_k": ambient_temperature_k,
        "provider_source_digest": provider_source_digest,
        "provider_boundary_reference": "lh2dt HomogeneousTank explicit accidental outlet",
        "input_origin": "model_prediction",
        "model_package": "lh2dt_models",
        "model_class": "HomogeneousTank+Valve",
        "model_revision": model_revision,
        "state_snapshot_digest": state_snapshot_digest,
        "evidence_status": "synthetic_diagnostic",
        "scenario_provenance": "explicit external-model diagnostic; not site-calibrated",
        "provider_termination_required": True,
    })


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.lh2dt_root.resolve()
    source_digest = _tree_digest(root)
    state_payload = {
        "tank_pressure_pa": args.tank_pressure_pa,
        "liquid_volume_fraction": args.liquid_volume_fraction,
        "hole_diameter_m": args.hole_diameter_m,
        "discharge_coefficient": args.discharge_coefficient,
        "ambient_pressure_pa": args.ambient_pressure_pa,
        "ambient_temperature_k": args.ambient_temperature_k,
        "duration_s": args.duration_s,
        "time_step_s": args.time_step_s,
        "termination_threshold_mass_kg": args.termination_threshold_mass_kg,
    }
    state_digest = canonical_digest(state_payload)
    component_id = "lh2dt-homogeneous-tank-diagnostic"
    port_id = f"{component_id}.accident-out"
    event_id = f"{component_id}/{port_id}/{args.hole_diameter_m:.12g}m"
    request = build_request(
        source_digest,
        component_id=component_id,
        port_id=port_id,
        event_id=event_id,
        hole_diameter_m=args.hole_diameter_m,
        ambient_pressure_pa=args.ambient_pressure_pa,
        ambient_temperature_k=args.ambient_temperature_k,
        position_enu_m=[0.0, 0.0, args.nozzle_height_m],
        direction_enu=[1.0, 0.0, 0.0],
        model_revision=args.model_revision,
        state_snapshot_digest=state_digest,
    )
    provider = HomogeneousTankAccidentProvider(
        root,
        duration_s=args.duration_s,
        time_step_s=args.time_step_s,
        tank_pressure_pa=args.tank_pressure_pa,
        liquid_volume_fraction=args.liquid_volume_fraction,
        hole_diameter_m=args.hole_diameter_m,
        discharge_coefficient=args.discharge_coefficient,
        termination_threshold_mass_kg=args.termination_threshold_mass_kg,
        release_kind=args.release_kind,
    )
    exporter = (
        export_equipment_liquid_accident_history
        if args.release_kind == "liquid"
        else export_equipment_gas_accident_history
    )
    result = exporter(provider, request)
    release = result.release.model_dump(mode="json")
    response = result.provider_response
    verification = {
        "status": "EXTERNAL_LH2DT_PRISM_PACKET_EXECUTED_OPERATOR_LIMITED",
        "request": request.to_mapping(),
        "provider_class": result.provider_class,
        "provider_method": result.provider_method,
        "provider_export_schema": result.provider_export_schema,
        "release_kind": args.release_kind,
        "provider_result_digest": result.provider_result_digest,
        "provider_packet_promoted": result.provider_packet_promoted,
        "promotion_status": result.promotion_status,
        "strict_packet_duration_s": result.release.duration_s,
        "strict_packet_cumulative_mass_out_kg": result.release.cumulative_mass_out_kg,
        "strict_packet_integrated_mass_kg": result.release.integrated_mass_kg,
        "strict_packet_mass_residual_kg": (
            result.release.cumulative_mass_out_kg - result.release.integrated_mass_kg
        ),
        "physical_validation_claim": False,
        "frequency_inference": False,
        "facility_qra_claim": False,
        "limitations": [
            "synthetic tank, opening, state, geometry and atmospheric inputs",
            "provider adapter currently targets HomogeneousTank+Valve diagnostic only",
            "this packet does not qualify the actual facility or any field failure frequency",
        ],
    }
    _save(args.output_dir / "provider_response.json", response)
    _save(args.output_dir / "resolved_release.json", release)
    _save(args.output_dir / "verification.json", verification)
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an explicit lh2dt scenario through PRISM's accident packet contract")
    parser.add_argument("--lh2dt-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=0.2)
    parser.add_argument("--time-step-s", type=float, default=0.05)
    parser.add_argument("--tank-pressure-pa", type=float, default=500000.0)
    parser.add_argument("--liquid-volume-fraction", type=float, default=0.7)
    parser.add_argument("--hole-diameter-m", type=float, default=0.01)
    parser.add_argument("--discharge-coefficient", type=float, default=0.8)
    parser.add_argument("--ambient-pressure-pa", type=float, default=101325.0)
    parser.add_argument("--ambient-temperature-k", type=float, default=288.15)
    parser.add_argument("--nozzle-height-m", type=float, default=1.0)
    parser.add_argument("--model-revision", default="external-library-0.1.1")
    parser.add_argument("--termination-threshold-mass-kg", type=float, default=None)
    parser.add_argument("--release-kind", choices=("liquid", "gas"), default="liquid")
    args = parser.parse_args()
    try:
        verification = run(args)
    except (OSError, ImportError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit(f"lh2dt PRISM accident export failed: {error}") from error
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
