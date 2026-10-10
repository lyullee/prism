"""Audit a direct, same-operator SLABx-LH2 comparison record.

The accepted FFI Test 4 record is useful quantitative evidence for the
SLABx-LH2 consequence component: 30 published sensor means are compared with
the native two-phase SLABx route using the same 275 s observation window, and
the 320/640 numerical refinement is repeated.  It is deliberately kept below
the facility-QRA gate.  The record does not prove that an LH2 equipment
release packet, an accident frequency, or the complete outdoor risk chain is
validated.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


AUDIT_SCHEMA = "prism.slabx_lh2_direct_comparison_audit.v1"
_PREDICTION_COLUMNS = {
    "test",
    "sensor",
    "radius_m",
    "height_m",
    "averaging_time_s",
    "observed_time_mean_vol_pct",
    "SLABx_time_mean_vol_pct",
    "residual_vol_pct",
    "observed_LFL",
    "SLABx_LFL",
}
_REFINEMENT_COLUMNS = {
    "n_field_steps",
    "substeps",
    "n_sensor_height_pairs",
    "bias_vol_pct",
    "MAE_vol_pct",
    "RMSE_vol_pct",
    "observed_LFL_pairs",
    "predicted_LFL_pairs",
    "TP",
    "FN",
    "FP",
}
_NUMERIC_PREDICTION_COLUMNS = {
    "radius_m",
    "height_m",
    "averaging_time_s",
    "observed_time_mean_vol_pct",
    "SLABx_time_mean_vol_pct",
    "residual_vol_pct",
    "observed_LFL",
    "SLABx_LFL",
}
_NUMERIC_REFINEMENT_COLUMNS = _REFINEMENT_COLUMNS - {"n_field_steps", "substeps"}
_FLOAT_TOLERANCE = 1.0e-9
_METRIC_TOLERANCE = 1.0e-6
_REFINEMENT_CHANGE_LIMIT = 0.02


class SlabxDirectComparisonAuditError(ValueError):
    """Raised when a direct comparison record cannot be audited."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise SlabxDirectComparisonAuditError(f"cannot read evidence file: {path}") from error
    return digest.hexdigest()


def _read_csv(path: str | Path, required: set[str], label: str) -> tuple[Path, list[dict[str, str]]]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise SlabxDirectComparisonAuditError(f"{label} is missing: {resolved}")
    try:
        with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
            missing = sorted(required - fields)
            if missing:
                raise SlabxDirectComparisonAuditError(
                    f"{label} is missing columns: {', '.join(missing)}"
                )
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise SlabxDirectComparisonAuditError(f"cannot read {label}: {resolved}") from error
    if not rows:
        raise SlabxDirectComparisonAuditError(f"{label} has no data rows: {resolved}")
    return resolved, rows


def _number(value: Any, field: str, row_index: int) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise SlabxDirectComparisonAuditError(
            f"{field} must be numeric at row {row_index}"
        ) from error
    if not math.isfinite(parsed):
        raise SlabxDirectComparisonAuditError(f"{field} must be finite at row {row_index}")
    return parsed


def _integer(value: Any, field: str, row_index: int) -> int:
    parsed = _number(value, field, row_index)
    if abs(parsed - round(parsed)) > _FLOAT_TOLERANCE:
        raise SlabxDirectComparisonAuditError(f"{field} must be an integer at row {row_index}")
    return int(round(parsed))


def _source(path: Path, role: str) -> dict[str, str]:
    return {"role": role, "path": str(path), "sha256": _sha256(path)}


def _relative_change(first: float, second: float) -> float:
    scale = max(abs(first), _FLOAT_TOLERANCE)
    return abs(second - first) / scale


def audit_slabx_lh2_direct_comparison(
    predictions_path: str | Path,
    refinement_path: str | Path,
    *,
    readme_path: str | Path | None = None,
    provenance_path: str | Path | None = None,
    expected_test: str = "4",
    expected_averaging_time_s: float = 275.0,
    lfl_vol_pct: float = 4.0,
) -> dict[str, Any]:
    """Return a digest-bound direct component comparison audit.

    The audit accepts only a same-operator sensor comparison with a numerical
    refinement record.  It reports direct quantitative evidence but leaves
    ``independent_physical_validation_claim`` and all facility claims false;
    an external reviewer and an independent holdout are still required.
    """
    prediction_file, raw_predictions = _read_csv(
        predictions_path, _PREDICTION_COLUMNS, "sensor prediction ledger"
    )
    refinement_file, raw_refinement = _read_csv(
        refinement_path, _REFINEMENT_COLUMNS, "refinement ledger"
    )
    readme_file: Path | None = None
    provenance_file: Path | None = None
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: dict[str, Any], reason: str) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "BLOCKED", "evidence": evidence})
        if not passed:
            blockers.append(reason)

    prediction_rows: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_predictions):
        row: dict[str, Any] = {"test": str(raw.get("test", "")).strip(), "sensor": str(raw.get("sensor", "")).strip()}
        if not row["test"] or not row["sensor"]:
            raise SlabxDirectComparisonAuditError(f"prediction identity is empty at row {index}")
        for field in _NUMERIC_PREDICTION_COLUMNS:
            row[field] = (
                _integer(raw.get(field), field, index)
                if field in {"observed_LFL", "SLABx_LFL"}
                else _number(raw.get(field), field, index)
            )
        prediction_rows.append(row)

    sensor_ids = [row["sensor"] for row in prediction_rows]
    common_test = {row["test"] for row in prediction_rows}
    common_windows = {row["averaging_time_s"] for row in prediction_rows}
    observed_values = [row["observed_time_mean_vol_pct"] for row in prediction_rows]
    predicted_values = [row["SLABx_time_mean_vol_pct"] for row in prediction_rows]
    residuals = [row["residual_vol_pct"] for row in prediction_rows]
    recomputed = {
        "row_count": len(prediction_rows),
        "sensor_count": len(set(sensor_ids)),
        "mean_bias_vol_pct": sum(residuals) / len(residuals),
        "MAE_vol_pct": sum(abs(value) for value in residuals) / len(residuals),
        "RMSE_vol_pct": math.sqrt(sum(value * value for value in residuals) / len(residuals)),
        "observed_LFL_pairs": sum(value >= lfl_vol_pct for value in observed_values),
        "predicted_LFL_pairs": sum(value >= lfl_vol_pct for value in predicted_values),
        "TP": sum(obs >= lfl_vol_pct and pred >= lfl_vol_pct for obs, pred in zip(observed_values, predicted_values)),
        "FN": sum(obs >= lfl_vol_pct and pred < lfl_vol_pct for obs, pred in zip(observed_values, predicted_values)),
        "FP": sum(obs < lfl_vol_pct and pred >= lfl_vol_pct for obs, pred in zip(observed_values, predicted_values)),
    }
    check(
        "same_operator_sensor_window",
        len(prediction_rows) == 30
        and len(set(sensor_ids)) == 30
        and common_test == {expected_test}
        and len(common_windows) == 1
        and abs(next(iter(common_windows)) - expected_averaging_time_s) <= _FLOAT_TOLERANCE,
        {
            "row_count": len(prediction_rows),
            "sensor_count": len(set(sensor_ids)),
            "tests": sorted(common_test),
            "averaging_windows_s": sorted(common_windows),
        },
        "direct comparison must contain 30 unique sensors from one test and one declared observation window",
    )
    check(
        "recomputed_metrics_are_finite",
        all(math.isfinite(float(value)) for value in recomputed.values()),
        recomputed,
        "direct comparison metrics are not finite",
    )
    check(
        "same_operator_lfl_classification",
        recomputed["observed_LFL_pairs"] == recomputed["predicted_LFL_pairs"]
        and recomputed["FN"] == 0
        and recomputed["FP"] == 0,
        {
            key: recomputed[key]
            for key in ("observed_LFL_pairs", "predicted_LFL_pairs", "TP", "FN", "FP")
        },
        "the direct comparison changes at least one declared LFL classification",
    )

    refinement_rows: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_refinement):
        row: dict[str, Any] = {
            "n_field_steps": _integer(raw.get("n_field_steps"), "n_field_steps", index),
            "substeps": _integer(raw.get("substeps"), "substeps", index),
        }
        for field in _NUMERIC_REFINEMENT_COLUMNS:
            row[field] = (
                _integer(raw.get(field), field, index)
                if field in {"n_sensor_height_pairs", "observed_LFL_pairs", "predicted_LFL_pairs", "TP", "FN", "FP"}
                else _number(raw.get(field), field, index)
            )
        refinement_rows.append(row)
    accepted_refinement = next(
        (row for row in refinement_rows if row["n_field_steps"] == 640 and row["substeps"] == 64),
        None,
    )
    baseline_refinement = next(
        (row for row in refinement_rows if row["n_field_steps"] == 320 and row["substeps"] == 32),
        None,
    )
    refinement_metric_map = {
        "bias_vol_pct": "mean_bias_vol_pct",
        "MAE_vol_pct": "MAE_vol_pct",
        "RMSE_vol_pct": "RMSE_vol_pct",
        "observed_LFL_pairs": "observed_LFL_pairs",
        "predicted_LFL_pairs": "predicted_LFL_pairs",
        "TP": "TP",
        "FN": "FN",
        "FP": "FP",
    }
    refinement_metrics_match = accepted_refinement is not None and all(
        abs(float(accepted_refinement[field]) - float(recomputed[recomputed_field])) <= _METRIC_TOLERANCE
        for field, recomputed_field in refinement_metric_map.items()
    )
    check(
        "accepted_refinement_matches_sensor_rows",
        refinement_metrics_match,
        {
            "accepted_refinement": accepted_refinement,
            "recomputed": recomputed,
        },
        "640/64 refinement metrics do not reproduce the sensor ledger",
    )
    refinement_converged = False
    refinement_changes: dict[str, float] = {}
    if baseline_refinement is not None and accepted_refinement is not None:
        for field in ("bias_vol_pct", "MAE_vol_pct", "RMSE_vol_pct"):
            refinement_changes[field] = _relative_change(
                float(baseline_refinement[field]), float(accepted_refinement[field])
            )
        refinement_converged = (
            all(value < _REFINEMENT_CHANGE_LIMIT for value in refinement_changes.values())
            and baseline_refinement["observed_LFL_pairs"] == accepted_refinement["observed_LFL_pairs"]
            and baseline_refinement["predicted_LFL_pairs"] == accepted_refinement["predicted_LFL_pairs"]
            and baseline_refinement["TP"] == accepted_refinement["TP"]
            and baseline_refinement["FN"] == accepted_refinement["FN"]
            and baseline_refinement["FP"] == accepted_refinement["FP"]
        )
    check(
        "numerical_refinement_converged",
        refinement_converged,
        {
            "refinement_row_count": len(refinement_rows),
            "relative_changes": refinement_changes,
            "change_limit": _REFINEMENT_CHANGE_LIMIT,
        },
        "320/32 and 640/64 refinement records are missing or diverge beyond the declared gate",
    )

    if readme_path is not None:
        readme_file = Path(readme_path).resolve()
        if not readme_file.is_file():
            blockers.append(f"comparison README is missing: {readme_file}")
        else:
            text = readme_file.read_text(encoding="utf-8", errors="replace").lower()
            no_fit_markers = ("no sensor value", "source rate", "concentration coefficient")
            check(
                "no_fit_provenance_declared",
                all(marker in text for marker in no_fit_markers),
                {"required_markers": list(no_fit_markers)},
                "comparison README does not declare the no-fit source/operator boundary",
            )
    if provenance_path is not None:
        provenance_file = Path(provenance_path).resolve()
        if not provenance_file.is_file():
            blockers.append(f"comparison provenance is missing: {provenance_file}")
        else:
            try:
                provenance = json.loads(provenance_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise SlabxDirectComparisonAuditError(
                    f"comparison provenance is not valid JSON: {provenance_file}"
                ) from error
            declared_files = provenance.get("files") if isinstance(provenance, dict) else None
            if not isinstance(declared_files, dict):
                declared_files = {}
            declared_by_name = {
                Path(str(key)).name: str(value)
                for key, value in declared_files.items()
            }
            expected_hashes = {
                prediction_file.name: _sha256(prediction_file),
                refinement_file.name: _sha256(refinement_file),
            }
            hash_matches = {
                name: declared_by_name.get(name) == digest
                for name, digest in expected_hashes.items()
            }
            check(
                "provenance_json_readable",
                provenance_file.stat().st_size > 0,
                {"size_bytes": provenance_file.stat().st_size},
                "comparison provenance file is empty",
            )
            check(
                "provenance_hashes_bind_current_ledgers",
                all(hash_matches.values()),
                {"hash_matches": hash_matches},
                "comparison provenance does not bind both current prediction and refinement ledgers",
            )

    blockers = list(dict.fromkeys(blockers))
    status = "DIRECT_COMPONENT_COMPARISON_REVIEW_READY" if not blockers else "BLOCKED_DIRECT_COMPONENT_COMPARISON"
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": status,
        "scope": "FFI Test 4 native-SLABx two-phase consequence component; same 275 s sensor operator",
        "sources": [
            _source(prediction_file, "sensor prediction ledger"),
            _source(refinement_file, "numerical refinement ledger"),
            *([] if readme_file is None else [_source(readme_file, "reproduction README")]),
            *([] if provenance_file is None else [_source(provenance_file, "route provenance")]),
        ],
        "checks": checks,
        "metrics": {
            **recomputed,
            "lfl_vol_pct": lfl_vol_pct,
            "refinement_relative_changes": refinement_changes,
            "refinement_change_limit": _REFINEMENT_CHANGE_LIMIT,
        },
        "refinement_rows": refinement_rows,
        "blocking_reasons": blockers,
        "claims": {
            "direct_component_comparison_evidence": not bool(blockers),
            "independent_holdout_validation_claim": False,
            "independent_physical_validation_claim": False,
            "full_chain_validation_claim": False,
            "accident_release_validation_claim": False,
            "frequency_inference_performed": False,
            "facility_qra_claim": False,
        },
        "promotion_policy": {
            "same_operator_component_comparison_is_not_holdout_validation": True,
            "numerical_refinement_is_not_physical_validation": True,
            "external_review_required_before_independent_gate": True,
            "component_evidence_does_not_validate_equipment_release": True,
            "component_evidence_does_not_validate_facility_qra": True,
        },
        "required_next_evidence": [
            "independent holdout or new experiment not used to select the source mapping",
            "reviewed source geometry and time-base provenance",
            "equipment release packet, frequency binding and facility-chain validation",
        ],
    }


__all__ = [
    "AUDIT_SCHEMA",
    "SlabxDirectComparisonAuditError",
    "audit_slabx_lh2_direct_comparison",
]
