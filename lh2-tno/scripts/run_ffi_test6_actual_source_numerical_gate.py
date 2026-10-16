"""Run a reproducible numerical-refinement gate for the actual FFI Test 6 source.

The PRISM repository contains the contract and audit for this calculation, but
the SLABx source tree is intentionally kept as an external, separately
versioned dependency.  This runner makes the boundary explicit: it imports an
operator-supplied SLABx/SLABx-LH2 checkout, runs the published FFI Test 6
HorizontalJet source without fitting sensor values, and writes the same
``refinement.json``/``provenance.json`` pair consumed by
``audit_ffi_test6_actual_source_numerical_gate.py``.

The result is diagnostic until the audit accepts the final pair.  No result
from this runner promotes physical validation, release-frequency evidence, or
facility QRA claims.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np


SOURCE = {
    "rate_kg_s": 0.8317,
    "nozzle_diameter_m": 0.0254,
    "liquid_mass_fraction": 0.559,
    "height_m": 0.5,
    "duration_s": 120.0,
    "temperature_K": 20.37,
}
MONITORED = (
    "H2_vol_pct_at_30_m",
    "centre_height_m_at_30_m",
    "cloud_depth_m_at_30_m",
    "temperature_K_at_30_m",
    "MAE_vol_pct",
    "RMSE_vol_pct",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slabx-src", type=Path, required=True,
                        help="SLABx source directory containing slabx/")
    parser.add_argument("--slabx-lh2-src", type=Path, required=True,
                        help="SLABx-LH2 source directory containing slabx_lh2/")
    parser.add_argument("--observations", type=Path, required=True,
                        help="FFI sensor CSV with test, R_m, bearing_deg, z_m, observed_mean_vol_pct")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--levels", default="40,80,160,320,640,1280",
                        help="comma-separated field-grid levels")
    parser.add_argument("--puff-steps", type=int, default=120)
    parser.add_argument("--substeps", type=int, default=3)
    parser.add_argument("--disable-lh2-extensions", action="store_true",
                        help="run the native SLABx source without plume-width/ice extensions")
    return parser


def _levels(value: str) -> tuple[int, ...]:
    values = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if len(values) < 2 or any(item < 1 for item in values):
        raise ValueError("--levels must contain at least two positive integers")
    if tuple(sorted(set(values))) != values:
        raise ValueError("--levels must be strictly increasing without duplicates")
    return values


def _relative(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-12)


def _observations(path: Path) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["test"]) != 6:
                continue
            rows.append({key: float(row[key]) for key in
                         ("R_m", "bearing_deg", "z_m", "observed_mean_vol_pct")})
    if not rows:
        raise ValueError("observation CSV contains no FFI Test 6 rows")
    return rows


def _operator_metrics(trajectory: Any, atmosphere: Any, observations: Iterable[Mapping[str, float]],
                      concentration_field: Any) -> tuple[float, float, int, int, int]:
    """Apply the fixed mean-wind observation operator used by the comparison.

    The operator only maps the reported polar sensor coordinates to the
    computed field.  It never changes source rate, area, duration, or wind to
    improve agreement with observations.
    """
    wind_to_deg = (245.0 + 180.0) % 360.0
    fields = {
        z: concentration_field(trajectory, atmosphere, z=z, t_avg=120.0,
                                t_release=120.0)
        for z in (0.1, 1.0, 1.8)
    }
    predicted: list[float] = []
    observed: list[float] = []
    for row in observations:
        radius, bearing, height = row["R_m"], row["bearing_deg"], row["z_m"]
        delta = math.radians(bearing - wind_to_deg)
        x, y = radius * math.cos(delta), radius * math.sin(delta)
        field = fields[min(fields, key=lambda value: abs(value - height))]
        value = (float(np.interp(x, field.x, field.at_y(y))) * 100.0
                 if field.x[0] <= x <= field.x[-1] else 0.0)
        # A receptor outside the finite crosswind section is assigned zero by
        # the fixed operator.  This is a declared domain rule, never a fit to
        # the observed value, and keeps the refinement metrics finite.
        if not math.isfinite(value):
            value = 0.0
        predicted.append(value)
        observed.append(row["observed_mean_vol_pct"])
    residual = np.asarray(predicted) - np.asarray(observed)
    observed_lfl = np.asarray(observed) >= 4.0
    predicted_lfl = np.asarray(predicted) >= 4.0
    return (
        float(np.mean(np.abs(residual))),
        float(np.sqrt(np.mean(residual ** 2))),
        int(np.count_nonzero(observed_lfl & predicted_lfl)),
        int(np.count_nonzero(observed_lfl & ~predicted_lfl)),
        int(np.count_nonzero(~observed_lfl & predicted_lfl)),
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    levels = _levels(args.levels)
    slabx = args.slabx_src.resolve()
    slabx_lh2 = args.slabx_lh2_src.resolve()
    if not (slabx / "slabx").is_dir():
        raise FileNotFoundError(f"SLABx source not found: {slabx}")
    if not (slabx_lh2 / "slabx_lh2").is_dir():
        raise FileNotFoundError(f"SLABx-LH2 source not found: {slabx_lh2}")
    sys.path[:0] = [str(slabx), str(slabx_lh2)]

    from slabx.core.plume import run_dispersion
    from slabx.core.source import HorizontalJet
    from slabx.post.concentration import concentration_field
    from slabx.submodels.atmosphere import Atmosphere
    from slabx.thermo.base import Substance
    from slabx.thermo.coolprop import CoolPropThermo, coolprop_water
    if args.disable_lh2_extensions:
        extension_context = nullcontext
        water_factory = coolprop_water
        extension_status = "native SLABx source; SLABx-LH2 plume-width/ice extensions disabled"
    else:
        from slabx_lh2.plume_width import plume_width_coupling
        from slabx_lh2.water_ice import with_sublimation
        extension_context = plume_width_coupling
        water_factory = lambda: with_sublimation(coolprop_water())
        extension_status = "SLABx-LH2 plume-width coupling and water-ice sublimation enabled"

    h2 = Substance(name="H2", mw=0.002016, cp_vapour=14300.0,
                   cp_liquid=9800.0, dh_vap=445000.0, T_boil=20.3,
                   rho_liquid=70.8)
    atmosphere = Atmosphere(u_ref=2.7, z_ref=10.0, T=276.95, rh=75.0,
                            z0=0.01, stability="D")
    observations = _observations(args.observations.resolve())
    rows: list[dict[str, Any]] = []
    for n_field_steps in levels:
        source = HorizontalJet(
            substance=h2, rate=SOURCE["rate_kg_s"],
            area=math.pi * SOURCE["nozzle_diameter_m"] ** 2 / 4.0,
            duration=SOURCE["duration_s"],
            liquid_fraction=SOURCE["liquid_mass_fraction"],
            height=SOURCE["height_m"], T_source=SOURCE["temperature_K"],
        )
        started = time.perf_counter()
        with extension_context():
            trajectory, _ = run_dispersion(
                source, atmosphere, CoolPropThermo(h2, fluid="Hydrogen"),
                water_factory(), x_max=30.0, n_puff_steps=args.puff_steps,
                n_field_steps=n_field_steps, substeps=args.substeps,
            )
        i30 = int(np.argmin(np.abs(np.asarray(trajectory.x, dtype=float) - 30.0)))
        mae, rmse, tp, fn, fp = _operator_metrics(
            trajectory, atmosphere, observations, concentration_field)
        rows.append({
            "n_field_steps": n_field_steps,
            "H2_vol_pct_at_30_m": 100.0 * float(trajectory.vol_frac[i30]),
            "centre_height_m_at_30_m": float(trajectory.z_c[i30]),
            "cloud_depth_m_at_30_m": float(trajectory.h[i30]),
            "temperature_K_at_30_m": float(trajectory.T[i30]),
            "sensor_count": len(observations), "MAE_vol_pct": mae,
            "RMSE_vol_pct": rmse, "LFL_observed": sum(int(r["observed_mean_vol_pct"] >= 4.0) for r in observations),
            "LFL_predicted": tp + fp, "TP": tp, "FN": fn, "FP": fp,
            "elapsed_s": time.perf_counter() - started,
        })
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    refinement = {
        "schema_version": "prism.slabx_lh2_ffi_test6_actual_source_refinement.v1",
        "scope": "actual FFI Test 6 HorizontalJet source; no sensor fitting",
        "source": SOURCE,
        "levels": rows,
    }
    (out / "refinement.json").write_text(json.dumps(refinement, indent=2) + "\n", encoding="utf-8")
    changes = {key: _relative(float(rows[-2][key]), float(rows[-1][key])) for key in MONITORED}
    provenance = {
        "schema_version": "prism.slabx_lh2_ffi_test6_actual_source_numerical_gate.v1",
        "scope": "actual FFI Test 6 HorizontalJet source; no sensor fitting",
        "criterion": "last two refinements <2% for all monitored values",
        "levels": list(levels),
        "last_pair": {"from_n_field_steps": levels[-2], "to_n_field_steps": levels[-1]},
        "relative_changes": changes,
        "accepted": all(value < 0.02 for value in changes.values()),
        "status": "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_ACCEPTED" if all(value < 0.02 for value in changes.values()) else "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_OPEN",
        "source": SOURCE,
        "execution": {"slabx_src": str(slabx), "slabx_lh2_src": str(slabx_lh2),
                       "extensions": extension_status, "puff_steps": args.puff_steps,
                       "substeps": args.substeps,
                       "out_of_domain_observation_policy": "zero"},
        "physical_validation_claim": False,
        "facility_qra_claim": False,
    }
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


def main() -> int:
    args = _parser().parse_args()
    result = run(args)
    print(json.dumps({"status": result["status"], "accepted": result["accepted"],
                      "output_dir": str(args.output_dir.resolve())}, ensure_ascii=False))
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
