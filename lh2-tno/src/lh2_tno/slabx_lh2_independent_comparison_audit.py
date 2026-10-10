"""Audit an independent SLABx-LH2 field comparison without over-promoting it.

The FFI Test 6 record is a different experiment from the accepted Test 4
component comparison.  It is useful evidence because its source is a
published P04 condition and the output declares no sensor fitting.  The
record must remain restricted while the source/numerical acceptance gate is
open; this module makes that distinction explicit and digest-bound.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


AUDIT_SCHEMA = "prism.slabx_lh2_independent_comparison_audit.v1"
_REQUIRED_COLUMNS = {
    "sensor",
    "radius_m",
    "bearing_deg",
    "height_m",
    "observed_mean_vol_pct",
    "SLABx_mean_wind_vol_pct",
    "observed_LFL",
    "SLABx_mean_wind_LFL",
}
_NUMERIC_COLUMNS = {
    "radius_m",
    "bearing_deg",
    "height_m",
    "observed_mean_vol_pct",
    "SLABx_mean_wind_vol_pct",
    "observed_LFL",
    "SLABx_mean_wind_LFL",
}
_FLOAT_TOLERANCE = 1.0e-9
_METRIC_TOLERANCE = 1.0e-6


class SlabxIndependentComparisonAuditError(ValueError):
    """Raised when an independent comparison cannot be audited."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise SlabxIndependentComparisonAuditError(f"cannot read evidence file: {path}") from error
    return digest.hexdigest()


def _read_csv(path: str | Path) -> tuple[Path, list[dict[str, str]]]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise SlabxIndependentComparisonAuditError(f"prediction ledger is missing: {resolved}")
    try:
        with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
            missing = sorted(_REQUIRED_COLUMNS - fields)
            if missing:
                raise SlabxIndependentComparisonAuditError(
                    f"prediction ledger is missing columns: {', '.join(missing)}"
                )
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise SlabxIndependentComparisonAuditError(
            f"cannot read prediction ledger: {resolved}"
        ) from error
    if not rows:
        raise SlabxIndependentComparisonAuditError(f"prediction ledger has no rows: {resolved}")
    return resolved, rows


def _read_json(path: str | Path, label: str) -> tuple[Path, Mapping[str, Any]]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise SlabxIndependentComparisonAuditError(f"{label} is missing: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SlabxIndependentComparisonAuditError(f"{label} is not valid JSON: {resolved}") from error
    if not isinstance(payload, Mapping):
        raise SlabxIndependentComparisonAuditError(f"{label} must contain a JSON object: {resolved}")
    return resolved, payload


def _number(value: Any, field: str, row_index: int) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise SlabxIndependentComparisonAuditError(
            f"{field} must be numeric at row {row_index}"
        ) from error
    if not math.isfinite(parsed):
        raise SlabxIndependentComparisonAuditError(f"{field} must be finite at row {row_index}")
    return parsed


def _source(path: Path, role: str) -> dict[str, str]:
    return {"role": role, "path": str(path), "sha256": _sha256(path)}


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= _METRIC_TOLERANCE


def audit_slabx_lh2_independent_comparison(
    predictions_path: str | Path,
    summary_path: str | Path,
    *,
    numerical_gate_path: str | Path | None = None,
    source_ledger_path: str | Path | None = None,
    lfl_vol_pct: float = 4.0,
    expected_sensor_count: int = 30,
) -> dict[str, Any]:
    """Audit an independent test comparison and retain open promotion gates."""
    prediction_file, raw_rows = _read_csv(predictions_path)
    summary_file, summary = _read_json(summary_path, "comparison summary")
    gate_file: Path | None = None
    gate: Mapping[str, Any] = {}
    if numerical_gate_path is not None:
        gate_file, gate = _read_json(numerical_gate_path, "numerical/source gate")
    source_ledger_file: Path | None = None
    source_ledger: Mapping[str, Any] = {}
    if source_ledger_path is not None:
        source_ledger_file, source_ledger = _read_json(source_ledger_path, "source ledger")

    blockers: list[str] = []
    structural_blockers: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Mapping[str, Any], reason: str, *, structural: bool = False) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "BLOCKED", "evidence": dict(evidence)})
        if not passed:
            blockers.append(reason)
            if structural:
                structural_blockers.append(reason)

    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        sensor = str(raw.get("sensor", "")).strip()
        if not sensor:
            raise SlabxIndependentComparisonAuditError(f"sensor identity is empty at row {index}")
        row: dict[str, Any] = {"sensor": sensor}
        for field in _NUMERIC_COLUMNS:
            row[field] = _number(raw.get(field), field, index)
        rows.append(row)

    observed = [row["observed_mean_vol_pct"] for row in rows]
    predicted = [row["SLABx_mean_wind_vol_pct"] for row in rows]
    residuals = [pred - obs for pred, obs in zip(predicted, observed)]
    metrics = {
        "row_count": len(rows),
        "sensor_count": len({row["sensor"] for row in rows}),
        "mean_bias_vol_pct": sum(residuals) / len(residuals),
        "MAE_vol_pct": sum(abs(value) for value in residuals) / len(residuals),
        "RMSE_vol_pct": math.sqrt(sum(value * value for value in residuals) / len(residuals)),
        "observed_LFL_pairs": sum(value >= lfl_vol_pct for value in observed),
        "predicted_LFL_pairs": sum(value >= lfl_vol_pct for value in predicted),
        "TP": sum(obs >= lfl_vol_pct and pred >= lfl_vol_pct for obs, pred in zip(observed, predicted)),
        "FN": sum(obs >= lfl_vol_pct and pred < lfl_vol_pct for obs, pred in zip(observed, predicted)),
        "FP": sum(obs < lfl_vol_pct and pred >= lfl_vol_pct for obs, pred in zip(observed, predicted)),
    }
    check(
        "independent_sensor_set_is_complete",
        metrics["row_count"] == expected_sensor_count
        and metrics["sensor_count"] == expected_sensor_count,
        {"expected_sensor_count": expected_sensor_count, "row_count": metrics["row_count"], "sensor_count": metrics["sensor_count"]},
        "independent comparison must contain the declared unique sensor set",
        structural=True,
    )

    summary_stats = summary.get("mean_wind_statistics")
    if not isinstance(summary_stats, Mapping):
        summary_stats = {}
    summary_metric_map = {
        "MAE_vol_pct": "MAE_vol_pct",
        "RMSE_vol_pct": "RMSE_vol_pct",
        "mean_bias_vol_pct": "mean_bias_vol_pct",
        "observed_LFL_pairs": "observed_LFL_pairs",
        "predicted_LFL_pairs": "SLABx_LFL_pairs",
        "TP": "TP",
        "FN": "FN",
        "FP": "FP",
    }
    summary_matches = all(
        value in summary_stats and _close(float(metrics[key]), float(summary_stats[value]))
        for key, value in summary_metric_map.items()
    )
    check(
        "summary_reproduces_prediction_metrics",
        summary_matches,
        {"recomputed": metrics, "summary_mean_wind_statistics": dict(summary_stats)},
        "comparison summary does not reproduce the prediction ledger metrics",
        structural=True,
    )
    check(
        "lfl_flags_match_concentrations",
        all(
            int(round(row["observed_LFL"])) == int(row["observed_mean_vol_pct"] >= lfl_vol_pct)
            and int(round(row["SLABx_mean_wind_LFL"])) == int(row["SLABx_mean_wind_vol_pct"] >= lfl_vol_pct)
            for row in rows
        ),
        {"lfl_vol_pct": lfl_vol_pct, "TP": metrics["TP"], "FN": metrics["FN"], "FP": metrics["FP"]},
        "declared LFL flags do not match the concentration values",
        structural=True,
    )

    source_metadata = source_ledger.get("metadata") if isinstance(source_ledger.get("metadata"), Mapping) else {}
    source_text = " ".join(
        str(value).lower()
        for value in (
            summary.get("source", ""),
            source_metadata.get("source_reference", ""),
            gate.get("purpose", ""),
        )
    )
    fitting_value = summary.get("fitting")
    if fitting_value is None:
        fitting_value = source_metadata.get("sensor_fitting_used")
    if fitting_value is None:
        fitting_value = gate.get("source_fitting_used")
    fitting_text = str(fitting_value).lower()
    check(
        "published_source_and_no_sensor_fit_declared",
        "published" in source_text and ("p04" in source_text or "pseudo-source" in source_text)
        and fitting_text in {"none", "false"},
        {"source": source_text, "fitting": fitting_value},
        "independent comparison does not declare a published source with no sensor fitting",
        structural=True,
    )
    source_blockers_before_gate = list(structural_blockers)

    source_gate = gate.get("numerical_gate") if isinstance(gate.get("numerical_gate"), Mapping) else {}
    gate_accepted = source_gate.get("accepted") is True
    check(
        "source_numerical_gate_accepted",
        gate_accepted,
        {"numerical_gate": dict(source_gate), "gate_record_present": gate_file is not None},
        "independent comparison source/numerical acceptance gate remains open",
    )

    status = "BLOCKED_INDEPENDENT_COMPARISON" if structural_blockers else (
        "INDEPENDENT_COMPARISON_REVIEW_READY" if gate_accepted else "RESTRICTED_INDEPENDENT_COMPARISON_SOURCE_GATE_OPEN"
    )
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": status,
        "scope": "FFI Test 6 pre-ignition SLABx crosswind comparison; independent trial and sensor set",
        "sources": [
            _source(prediction_file, "independent sensor prediction ledger"),
            _source(summary_file, "comparison summary and source declaration"),
            *([] if gate_file is None else [_source(gate_file, "source/numerical acceptance gate")]),
            *([] if source_ledger_file is None else [_source(source_ledger_file, "published source ledger")]),
        ],
        "checks": checks,
        "metrics": {**metrics, "lfl_vol_pct": lfl_vol_pct},
        "source_gate": {
            "accepted": gate_accepted,
            "status": source_gate.get("accepted"),
            "record": None if gate_file is None else str(gate_file),
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "structural_blocking_reasons": list(dict.fromkeys(source_blockers_before_gate)),
        "claims": {
            "independent_comparison_evidence": not bool(structural_blockers),
            "independent_physical_validation_claim": False,
            "full_chain_validation_claim": False,
            "accident_release_validation_claim": False,
            "frequency_inference_performed": False,
            "facility_qra_claim": False,
        },
        "promotion_policy": {
            "independent_comparison_requires_accepted_source_gate": True,
            "open_source_gate_does_not_become_physical_validation": True,
            "comparison_does_not_validate_equipment_release": True,
            "comparison_does_not_validate_facility_qra": True,
            "frequency_is_not_inferred_from_observations": True,
        },
        "required_next_evidence": [
            "accepted source/numerical refinement gate for the independent trial",
            "external reviewer confirmation of source and observation operator",
            "equipment release packet, frequency binding and facility-chain validation",
        ],
    }


__all__ = [
    "AUDIT_SCHEMA",
    "SlabxIndependentComparisonAuditError",
    "audit_slabx_lh2_independent_comparison",
]
