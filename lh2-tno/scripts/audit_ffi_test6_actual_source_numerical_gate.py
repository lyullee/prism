"""Audit the actual-source FFI Test 6 numerical-refinement record.

This checker validates the source identity and recomputes the final refinement
changes. It never promotes the comparison to physical validation or facility
QRA. The physics run itself is performed in the external SLABx comparison
workspace; this script makes the recorded gate reproducible inside PRISM.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "prism.slabx_lh2_ffi_test6_actual_source_numerical_gate.v1"
MONITORED = (
    "H2_vol_pct_at_30_m",
    "centre_height_m_at_30_m",
    "cloud_depth_m_at_30_m",
    "temperature_K_at_30_m",
    "MAE_vol_pct",
    "RMSE_vol_pct",
)
EXPECTED_SOURCE = {
    "rate_kg_s": 0.8317,
    "nozzle_diameter_m": 0.0254,
    "liquid_mass_fraction": 0.559,
    "height_m": 0.5,
    "duration_s": 120.0,
    "temperature_K": 20.37,
}


def _read(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _relative(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-12)


def audit(path: str | Path, *, tolerance: float = 0.02) -> dict[str, Any]:
    source_path = Path(path).resolve()
    record = _read(source_path)
    reasons: list[str] = []
    if record.get("schema_version") != SCHEMA:
        reasons.append("schema_version is not the actual-source gate schema")
    if record.get("scope") != "actual FFI Test 6 HorizontalJet source; no sensor fitting":
        reasons.append("scope does not identify the actual FFI source")
    source = record.get("source")
    if not isinstance(source, Mapping):
        reasons.append("source metadata is missing")
        source = {}
    for key, expected in EXPECTED_SOURCE.items():
        try:
            observed = float(source[key])
        except (KeyError, TypeError, ValueError):
            reasons.append(f"source field is missing or non-numeric: {key}")
            continue
        if not math.isclose(observed, expected, rel_tol=0.0, abs_tol=1.0e-9):
            reasons.append(f"source field differs from the reviewed FFI value: {key}")

    refinement_path = source_path.with_name("refinement.json")
    refinement = _read(refinement_path) if refinement_path.exists() else {}
    levels = refinement.get("levels")
    if not isinstance(levels, list) or len(levels) < 2:
        reasons.append("refinement record must contain at least two levels")
        levels = []
    last_pair: dict[str, float] = {}
    if len(levels) >= 2:
        before, after = levels[-2], levels[-1]
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            reasons.append("last refinement rows must be objects")
        else:
            for key in MONITORED:
                try:
                    last_pair[key] = _relative(float(before[key]), float(after[key]))
                except (KeyError, TypeError, ValueError):
                    reasons.append(f"last refinement value is missing or non-numeric: {key}")
    worst_quantity = max(last_pair, key=last_pair.get) if last_pair else None
    worst_relative_change = last_pair.get(worst_quantity) if worst_quantity else None
    if last_pair and any(value >= tolerance for value in last_pair.values()):
        reasons.append(
            "last refinement pair exceeds the declared tolerance"
            + (
                f"; worst quantity={worst_quantity} ({worst_relative_change:.3%})"
                if worst_quantity is not None and worst_relative_change is not None
                else ""
            )
        )
    accepted = bool(last_pair) and all(value < tolerance for value in last_pair.values()) and not reasons
    return {
        "schema_version": SCHEMA,
        "status": "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_ACCEPTED" if accepted else "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_OPEN",
        "record": str(source_path),
        "refinement": str(refinement_path),
        "levels": [row.get("n_field_steps") for row in levels if isinstance(row, Mapping)],
        "criterion": f"last two refinements < {tolerance:.0%} for all monitored values",
        "last_pair_relative_changes": last_pair,
        "worst_quantity": worst_quantity,
        "worst_relative_change": worst_relative_change,
        "accepted": accepted,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "blocking_reasons": reasons,
        "interpretation": (
            "Numerical gate accepted for the reviewed actual FFI source; this does not open physical validation or facility QRA."
            if accepted
            else "Actual FFI source numerical gate remains open; no pseudo-source or extrapolated result may substitute for it."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True, help="provenance.json for the actual-source gate")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "accepted": result["accepted"], "blocking_reason_count": len(result["blocking_reasons"])}, ensure_ascii=False))
    return 0 if result["status"] == "ACTUAL_FFI_SOURCE_NUMERICAL_GATE_ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
