"""Audit a native SLABx reconstruction against PRESLHY sensor windows.

The PRESLHY runner is an external, component-level consequence comparison.
This adapter binds its CSV/JSON outputs by digest so the result can be shown in
the PRISM readiness report without treating it as a qualified facility input.
It deliberately does not promote a window comparison to end-to-end physical
validation, an equipment release packet, a frequency, or a facility QRA.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


PRESLHY_SLABX_WINDOW_SCHEMA = "prism.preslhy_slabx_window_comparison_audit.v1"


class PreslhySlabxWindowAuditError(ValueError):
    """Raised when a PRESLHY-SLABx output bundle is malformed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise PreslhySlabxWindowAuditError(f"cannot read PRESLHY-SLABx file: {path}") from error
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreslhySlabxWindowAuditError(f"invalid PRESLHY-SLABx JSON: {path}") from error
    if not isinstance(value, dict):
        raise PreslhySlabxWindowAuditError(f"PRESLHY-SLABx JSON must be an object: {path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise PreslhySlabxWindowAuditError(f"invalid PRESLHY-SLABx CSV: {path}") from error


def _number(value: str | None, *, field: str, allow_empty: bool = False) -> float | None:
    if value is None or not str(value).strip():
        if allow_empty:
            return None
        raise PreslhySlabxWindowAuditError(f"missing numeric field: {field}")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise PreslhySlabxWindowAuditError(f"invalid numeric field {field}: {value!r}") from error
    if not math.isfinite(result):
        raise PreslhySlabxWindowAuditError(f"non-finite numeric field {field}")
    return result


def audit_preslhy_slabx_window_comparison(results_dir: str | Path) -> dict[str, Any]:
    """Return a digest-bound, restricted PRESLHY/SLABx comparison ledger."""
    root = Path(results_dir).resolve()
    if not root.is_dir():
        raise PreslhySlabxWindowAuditError(f"PRESLHY-SLABx result directory is missing: {root}")
    sensor_path = root / "sensor_predictions_final.csv"
    refinement_path = root / "refinement_summary.csv"
    gate_path = root / "numerical_gate.csv"
    provenance_path = root / "provenance.json"
    paths = (sensor_path, refinement_path, gate_path, provenance_path)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise PreslhySlabxWindowAuditError("missing PRESLHY-SLABx output: " + ", ".join(missing))

    provenance = _read_json(provenance_path)
    rows = _read_csv(sensor_path)
    refinement = _read_csv(refinement_path)
    gate = _read_csv(gate_path)
    blockers: list[str] = []

    purpose = str(provenance.get("purpose", ""))
    if "SLABx" not in purpose or "PRESLHY" not in purpose:
        blockers.append("provenance does not declare a native PRESLHY-SLABx reconstruction")
    if not rows:
        blockers.append("sensor_predictions_final.csv contains no rows")
    if not refinement:
        blockers.append("refinement_summary.csv contains no numerical refinement rows")
    if not gate:
        blockers.append("numerical_gate.csv contains no numerical gate rows")

    required = {
        "trial", "serial", "observed_window_mean_vol_pct", "slabx_window_mean_vol_pct",
        "evaluable", "observed_lfl", "slabx_lfl",
    }
    if rows:
        missing_columns = sorted(required - set(rows[0]))
        if missing_columns:
            blockers.append("sensor comparison is missing columns: " + ", ".join(missing_columns))

    evaluable_rows = 0
    predicted_rows = 0
    nonzero_prediction_rows = 0
    absolute_errors: list[float] = []
    evaluated_trials: set[int] = set()
    invalid_rows = 0
    for row in rows:
        try:
            trial = int(row.get("trial", ""))
            evaluable = int(row.get("evaluable", ""))
            observed = _number(row.get("observed_window_mean_vol_pct"), field="observed_window_mean_vol_pct")
            prediction = _number(
                row.get("slabx_window_mean_vol_pct"),
                field="slabx_window_mean_vol_pct",
                allow_empty=True,
            )
        except (PreslhySlabxWindowAuditError, TypeError, ValueError):
            invalid_rows += 1
            continue
        if evaluable:
            evaluable_rows += 1
            evaluated_trials.add(trial)
            if prediction is None:
                invalid_rows += 1
                continue
            predicted_rows += 1
            if abs(prediction) > 1.0e-12:
                nonzero_prediction_rows += 1
            absolute_errors.append(abs(prediction - float(observed)))

    if evaluable_rows == 0:
        blockers.append("no evaluable sensor rows remain after the declared source-plane filter")
    if invalid_rows:
        blockers.append(f"{invalid_rows} sensor rows have invalid or incomplete numeric values")

    accepted_gate_count = 0
    gate_trial_count = 0
    for row in gate:
        gate_trial_count += 1
        try:
            accepted_gate_count += int(row.get("accepted", "0"))
        except (TypeError, ValueError):
            blockers.append("numerical_gate.csv contains a non-integer accepted flag")
    if accepted_gate_count == 0:
        blockers.append("no trial passed the declared final-resolution numerical gate")

    files = [
        {"role": "sensor_predictions", "path": str(sensor_path), "sha256": _sha256(sensor_path)},
        {"role": "refinement_summary", "path": str(refinement_path), "sha256": _sha256(refinement_path)},
        {"role": "numerical_gate", "path": str(gate_path), "sha256": _sha256(gate_path)},
        {"role": "provenance", "path": str(provenance_path), "sha256": _sha256(provenance_path)},
    ]
    status = (
        "RESTRICTED_PRESLHY_SLABX_WINDOW_COMPARISON"
        if not blockers
        else "BLOCKED_PRESLHY_SLABX_WINDOW_COMPARISON"
    )
    return {
        "schema_version": PRESLHY_SLABX_WINDOW_SCHEMA,
        "status": status,
        "source_directory": str(root),
        "source_files": files,
        "provenance": {
            "purpose": provenance.get("purpose"),
            "trials": provenance.get("trials"),
            "final_level": provenance.get("final_level"),
            "coordinate_frame": provenance.get("meteorology", {}).get("coordinate_frame")
            if isinstance(provenance.get("meteorology"), dict) else None,
            "observation_operator": provenance.get("observation_operator"),
        },
        "metrics": {
            "sensor_row_count": len(rows),
            "evaluable_sensor_row_count": evaluable_rows,
            "predicted_sensor_row_count": predicted_rows,
            "nonzero_prediction_row_count": nonzero_prediction_rows,
            "evaluated_trial_count": len(evaluated_trials),
            "refinement_row_count": len(refinement),
            "numerical_gate_trial_count": gate_trial_count,
            "accepted_numerical_gate_count": accepted_gate_count,
            "mean_absolute_error_of_evaluable_windows_vol_pct": (
                sum(absolute_errors) / len(absolute_errors) if absolute_errors else None
            ),
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "scope": {
            "supports": [
                "reproducible native-SLABx PRESLHY sensor-window comparison",
                "trial-level numerical refinement and LFL-state traceability",
            ],
            "excludes": [
                "equipment release qualification or initiating-event frequency",
                "full time-history validation or independent end-to-end validation",
                "ignition, fire, explosion, IR/F-N, or facility-QRA promotion",
            ],
        },
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference_performed": False,
        "promotion_policy": {
            "component_evidence_only": True,
            "external_output_is_not_provider_packet": True,
            "frequency_is_not_inferred": True,
            "facility_qra_requires_independent_full_chain_validation": True,
        },
    }


__all__ = [
    "PRESLHY_SLABX_WINDOW_SCHEMA",
    "PreslhySlabxWindowAuditError",
    "audit_preslhy_slabx_window_comparison",
]
