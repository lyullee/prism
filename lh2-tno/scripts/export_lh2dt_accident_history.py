"""Export an explicit diagnostic accident history from the external lh2dt model.

The external model does not currently emit a PRISM accident packet.  This
adapter runs a declared tank/valve diagnostic with an explicit failed opening
and either a fixed termination clock or an explicit positive-mass inventory
threshold, then writes the provider history format consumed by
``validate_layered_tank_slabsx_bridge.py``.  It never treats an existing
normal-flow JSON file as an accident and it labels the output synthetic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


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


def export_history(
    lh2dt_root: Path,
    *,
    duration_s: float,
    time_step_s: float,
    tank_pressure_pa: float,
    liquid_volume_fraction: float,
    hole_diameter_m: float,
    discharge_coefficient: float,
    ambient_pressure_pa: float,
    ambient_temperature_k: float,
    termination_threshold_mass_kg: float | None = None,
) -> tuple[dict, dict]:
    """Run one explicit external-model diagnostic and return export + audit."""
    if duration_s <= 0.0 or time_step_s <= 0.0:
        raise ValueError("duration_s and time_step_s must be positive")
    if duration_s < time_step_s:
        raise ValueError("duration_s must be at least one time step")
    if not math.isclose(duration_s / time_step_s, round(duration_s / time_step_s), rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError("duration_s must be an integer multiple of time_step_s")
    if tank_pressure_pa <= ambient_pressure_pa:
        raise ValueError("tank pressure must exceed the atmospheric boundary")
    if not 0.0 < liquid_volume_fraction < 1.0:
        raise ValueError("liquid_volume_fraction must lie in (0, 1)")
    if hole_diameter_m <= 0.0 or discharge_coefficient <= 0.0:
        raise ValueError("failed opening and discharge coefficient must be positive")

    sys.path.insert(0, str(lh2dt_root / "src"))
    try:
        from lh2dt import (
            HydrogenProperties,
            HomogeneousTank,
            MassEnergyFlow,
            TankGeometry,
            Valve,
        )
    except ImportError as error:
        raise RuntimeError(
            f"cannot import external lh2dt package from {lh2dt_root / 'src'}: {error}"
        ) from error

    properties = HydrogenProperties()
    tank = HomogeneousTank(
        TankGeometry(
            volume_m3=1.0,
            wall_heat_capacity_J_K=2.0e5,
            ambient_UA_W_K=10.0,
            fluid_wall_UA_W_K=20.0,
        ),
        properties,
    )
    initial = tank.initialize_saturated(tank_pressure_pa, liquid_volume_fraction)
    if termination_threshold_mass_kg is not None:
        if not math.isfinite(termination_threshold_mass_kg) or termination_threshold_mass_kg <= 0.0:
            raise ValueError("termination_threshold_mass_kg must be finite and positive")
        if termination_threshold_mass_kg >= initial.hydrogen_mass_kg:
            raise ValueError("termination threshold must be below the initial provider inventory")
    failed_valve = Valve(
        full_open_area_m2=math.pi * hole_diameter_m**2 / 4.0,
        discharge_coefficient=discharge_coefficient,
        properties=properties,
        allow_reverse=False,
    )
    ambient = properties.from_pT(ambient_pressure_pa, ambient_temperature_k)
    started = time.perf_counter()
    step_records: list[tuple[float, float, object, list[tuple[float, object, object]]]] = []
    state = initial
    elapsed = 0.0
    while elapsed < duration_s - 1.0e-12:
        interval_s = min(time_step_s, duration_s - elapsed)
        callback_records: list[tuple[float, object, object]] = []

        def flow_callback(time_s: float, thermo):
            valve_result = failed_valve.evaluate(thermo, ambient, opening=1.0)
            callback_records.append((time_s, thermo, valve_result))
            return [
                MassEnergyFlow(
                    -valve_result.mass_flow_kg_s,
                    thermo.specific_enthalpy_J_kg,
                    "declared-accidental-opening",
                )
            ]

        results = tank.simulate(
            state,
            interval_s,
            interval_s,
            ambient_temperature_k,
            flow_callback,
        )
        expected_callback_count = len(results) * 4
        if len(callback_records) != expected_callback_count:
            raise RuntimeError(
                f"unexpected external RK4 callback count: {len(callback_records)} != {expected_callback_count}"
            )
        for index, result in enumerate(results):
            group = callback_records[index * 4 : (index + 1) * 4]
            step_records.append((elapsed + result.time_s, interval_s, result, group))
        if not results:
            break
        state = results[-1].state
        elapsed += interval_s
        if termination_threshold_mass_kg is not None and state.hydrogen_mass_kg <= termination_threshold_mass_kg:
            break
    elapsed_s = time.perf_counter() - started
    if not step_records:
        raise RuntimeError("external model returned no diagnostic release intervals")

    steps: list[dict] = []
    for end_time, interval_s, result, group in step_records:
        representative = group[0][1]
        average_mass_flow = sum(
            weight * record[2].mass_flow_kg_s
            for weight, record in zip((1.0, 2.0, 2.0, 1.0), group)
        ) / 6.0
        steps.append(
            {
                "time_s": end_time,
                "source_state": {
                    "pressure_Pa": representative.pressure_Pa,
                "temperature_K": representative.temperature_K,
                    "density_kg_m3": representative.density_kg_m3,
                    "specific_enthalpy_J_kg": representative.specific_enthalpy_J_kg,
                    "specific_entropy_J_kgK": representative.specific_entropy_J_kgK,
                    "vapour_quality": representative.quality,
                },
                "flow": {
                    "mass_flow_kg_s": average_mass_flow,
                    "transmitted_specific_enthalpy_J_kg": representative.specific_enthalpy_J_kg,
                },
            }
        )

    provider_mass = sum(row["flow"]["mass_flow_kg_s"] * interval_s for row, (_, interval_s, _, _) in zip(steps, step_records))
    final_state = step_records[-1][2].state
    actual_mass_decrease = initial.hydrogen_mass_kg - final_state.hydrogen_mass_kg
    inventory_depletion_detected = (
        termination_threshold_mass_kg is not None
        and final_state.hydrogen_mass_kg <= termination_threshold_mass_kg
    )
    if termination_threshold_mass_kg is not None and not inventory_depletion_detected:
        raise RuntimeError("declared inventory threshold was not reached within the diagnostic horizon")
    # A positive threshold closes the diagnostic integration clock, but it is
    # not zero inventory. Keep this basis distinct so downstream audits never
    # mistake a short diagnostic for full inventory depletion.
    termination_basis = (
        "inventory_depletion_positive_threshold"
        if inventory_depletion_detected
        else "synthetic_diagnostic_horizon"
    )
    export = {
        "schema_version": "lh2dt.external_accident_export.diagnostic.v1",
        "event_kind": "accidental_leak",
        "interval_semantics": "provider_result_end_state_representative_for_preceding_fixed_step",
        "time_step_s": time_step_s,
        "component_id": "lh2dt-homogeneous-tank-diagnostic",
        "port_id": "lh2dt-homogeneous-tank-diagnostic.accident-out",
        "steps": steps,
        "source_geometry": {
            "full_open_area_m2": math.pi * hole_diameter_m**2 / 4.0,
            "length_m": 0.01,
            "nozzle_height_m": 1.0,
            "direction_enu": [1.0, 0.0, 0.0],
            "discharge_coefficient": discharge_coefficient,
        },
        "ambient_pressure_pa": ambient_pressure_pa,
        "ambient_temperature_k": ambient_temperature_k,
        "wind_speed_m_s": 3.0,
        "wind_from_bearing_deg": 270.0,
        "tank_volume_m3": 1.0,
        "fluid": properties.fluid,
        "termination_basis": termination_basis,
        "termination_provenance": (
            (
                "external lh2dt HomogeneousTank positive-mass inventory threshold; explicit failed opening; "
                f"threshold_mass_kg={termination_threshold_mass_kg:.12g}; provider state is not site-calibrated"
            )
            if inventory_depletion_detected
            else (
                "external lh2dt HomogeneousTank fixed diagnostic horizon; explicit failed opening; "
                "provider state is not a site-calibrated accident history"
            )
        ),
        "provider_initial_mass_kg": initial.hydrogen_mass_kg,
        "provider_final_mass_kg": final_state.hydrogen_mass_kg,
        "provider_mass_decrease_kg": actual_mass_decrease,
        "provider_mass_ledger_residual_kg": actual_mass_decrease - provider_mass,
        "inventory_depletion_detected": inventory_depletion_detected,
        "depletion_threshold_mass_kg": termination_threshold_mass_kg,
    }
    audit = {
        "status": "EXTERNAL_MODEL_HISTORY_EXPORTED",
        "external_model_root": str(lh2dt_root),
        "external_model_source_digest": _tree_digest(lh2dt_root),
        "event_kind": "accidental_leak",
        "synthetic_diagnostic": True,
        "provider_packet_promoted": False,
        "normal_flow_promotion": False,
        "step_count": len(steps),
        "duration_s": duration_s,
        "time_step_s": time_step_s,
        "actual_duration_s": step_records[-1][0],
        "termination_basis": termination_basis,
        "inventory_depletion_detected": inventory_depletion_detected,
        "depletion_threshold_mass_kg": termination_threshold_mass_kg,
        "remaining_inventory_kg": final_state.hydrogen_mass_kg,
        "elapsed_s": elapsed_s,
        "provider_mass_kg": provider_mass,
        "model_mass_decrease_kg": actual_mass_decrease,
        "mass_ledger_residual_kg": actual_mass_decrease - provider_mass,
        "physical_validation_claim": False,
        "limitations": [
            "synthetic tank, failed opening, weather, and geometry inputs",
            "external lh2dt output requires a separate SLABx-LH2 boundary comparison",
            "no site asset, failure frequency, or sensor-based frequency was inferred",
        ],
    }
    return export, audit


def main() -> int:
    parser = argparse.ArgumentParser()
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
    parser.add_argument(
        "--termination-threshold-mass-kg",
        type=float,
        default=None,
        help="optional positive provider inventory threshold; its crossing declares inventory_depletion_positive_threshold",
    )
    args = parser.parse_args()
    try:
        export, audit = export_history(
            args.lh2dt_root,
            duration_s=args.duration_s,
            time_step_s=args.time_step_s,
            tank_pressure_pa=args.tank_pressure_pa,
            liquid_volume_fraction=args.liquid_volume_fraction,
            hole_diameter_m=args.hole_diameter_m,
            discharge_coefficient=args.discharge_coefficient,
            ambient_pressure_pa=args.ambient_pressure_pa,
            ambient_temperature_k=args.ambient_temperature_k,
            termination_threshold_mass_kg=args.termination_threshold_mass_kg,
        )
    except (OSError, ImportError, RuntimeError, ValueError) as error:
        raise SystemExit(f"external lh2dt export failed: {error}") from error
    _save(args.output_dir / "provider_export.json", export)
    _save(args.output_dir / "verification.json", audit)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
