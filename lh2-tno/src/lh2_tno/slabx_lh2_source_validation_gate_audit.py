"""Audit the SLABx-LH2 source-term validation gate ledger.

The external SLABx-LH2 validation folder contains useful HEM/HNEM, mass-flow,
numerical-closure, and rainout-classification records.  This module preserves
their exact status and hashes, while refusing to turn a restricted source-term
check into independent full-chain physical validation.
"""
from __future__ import annotations

import csv
import hashlib
import math
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any


AUDIT_SCHEMA = "prism.slabx_lh2_source_validation_gate_audit.v1"
_REQUIRED_GATE_COLUMNS = {"gate", "operator", "status", "result", "source"}
_INDEPENDENT_STATUSES = {
    "independent_quantitative_validation",
    "independent_holdout_validation",
}
_MASS_TOLERANCE = 1.0e-8
_ENERGY_TOLERANCE = 1.0e-6


class SlabxSourceValidationGateAuditError(ValueError):
    """Raised when a source validation gate ledger is malformed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_csv(path: str | Path, label: str) -> tuple[Path, list[dict[str, str]]]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise SlabxSourceValidationGateAuditError(f"{label} is missing: {resolved}")
    try:
        with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
            if not _REQUIRED_GATE_COLUMNS.issubset(fields) and label == "gate ledger":
                missing = sorted(_REQUIRED_GATE_COLUMNS - fields)
                raise SlabxSourceValidationGateAuditError(
                    "gate ledger is missing columns: " + ", ".join(missing)
                )
            return resolved, [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise SlabxSourceValidationGateAuditError(f"cannot read {label}: {resolved}") from error


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SlabxSourceValidationGateAuditError(f"{field} must be non-empty")
    return value.strip()


def _number(value: str | None, field: str) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise SlabxSourceValidationGateAuditError(f"{field} must be numeric") from error
    if not math.isfinite(parsed):
        raise SlabxSourceValidationGateAuditError(f"{field} must be finite")
    return parsed


def audit_slabx_lh2_source_validation_gates(
    gate_ledger_path: str | Path,
    *,
    casewise_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return a digest-bound, fail-closed source-term validation audit."""
    gate_path, raw_rows = _read_csv(gate_ledger_path, "gate ledger")
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for index, raw in enumerate(raw_rows):
        gate = _text(raw.get("gate"), f"gate ledger row {index}.gate")
        operator = _text(raw.get("operator"), f"gate ledger row {index}.operator")
        status = _text(raw.get("status"), f"gate ledger row {index}.status")
        result = _text(raw.get("result"), f"gate ledger row {index}.result")
        source = _text(raw.get("source"), f"gate ledger row {index}.source")
        if status in _INDEPENDENT_STATUSES:
            blockers.append(
                f"gate {gate} declares independent physical validation; manual review is required"
            )
        rows.append({
            "gate": gate,
            "operator": operator,
            "status": status,
            "result": result,
            "source": source,
            "independent_quantitative_validation": status in _INDEPENDENT_STATUSES,
        })

    casewise_summary: dict[str, Any] = {
        "row_count": 0,
        "mass_closed_row_count": 0,
        "energy_closed_row_count": 0,
        "invalid_residual_row_count": 0,
        "mass_residual_tolerance_kg_s": _MASS_TOLERANCE,
        "energy_residual_tolerance_w": _ENERGY_TOLERANCE,
    }
    casewise_source: dict[str, Any] | None = None
    if casewise_path is not None:
        resolved, case_rows = _read_csv(casewise_path, "casewise ledger")
        casewise_source = {"path": str(resolved), "sha256": _sha256(resolved)}
        casewise_summary["row_count"] = len(case_rows)
        for index, raw in enumerate(case_rows):
            mass = _number(raw.get("mass_residual_kg_s"), f"casewise row {index}.mass_residual_kg_s")
            energy = _number(raw.get("energy_residual_w"), f"casewise row {index}.energy_residual_w")
            if mass is None or energy is None:
                casewise_summary["invalid_residual_row_count"] += 1
                continue
            if abs(mass) <= _MASS_TOLERANCE:
                casewise_summary["mass_closed_row_count"] += 1
            if abs(energy) <= _ENERGY_TOLERANCE:
                casewise_summary["energy_closed_row_count"] += 1
            if abs(mass) > _MASS_TOLERANCE or abs(energy) > _ENERGY_TOLERANCE:
                casewise_summary["invalid_residual_row_count"] += 1

    summary_source: dict[str, Any] | None = None
    if summary_path is not None:
        resolved = Path(summary_path).resolve()
        if not resolved.is_file():
            raise SlabxSourceValidationGateAuditError(f"summary is missing: {resolved}")
        summary_source = {"path": str(resolved), "sha256": _sha256(resolved)}

    status_counts = Counter(row["status"] for row in rows)
    independent_count = sum(row["independent_quantitative_validation"] for row in rows)
    if independent_count:
        blockers.append("source validation ledger contains a status that requires independent review")
    if casewise_summary["invalid_residual_row_count"]:
        blockers.append("casewise source ledger contains residual rows outside the declared tolerance")
    blockers = list(dict.fromkeys(blockers))

    return {
        "schema_version": AUDIT_SCHEMA,
        "status": "RESTRICTED_SOURCE_VALIDATION_GATES" if not independent_count else "REVIEW_REQUIRED_SOURCE_VALIDATION_GATES",
        "scope": "SLABx-LH2 source-term gate ledger; component evidence only",
        "gate_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "independent_quantitative_gate_count": independent_count,
        "restricted_gate_count": len(rows) - independent_count,
        "gates": rows,
        "casewise_numerical_closure": casewise_summary,
        "sources": {
            "gate_ledger": {"path": str(gate_path), "sha256": _sha256(gate_path)},
            "casewise_ledger": casewise_source,
            "summary": summary_source,
        },
        "blocking_reasons": blockers,
        "promotion_gates": {
            "source_term_component_evidence_allowed": not bool(blockers),
            "independent_physical_validation_allowed": False,
            "full_chain_physical_validation_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "physical_validation_claim": False,
        "independent_physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "diagnostic_only": True,
        "policy": {
            "source_gate_status_is_not_independent_validation": True,
            "published_envelope_is_not_point_prediction": True,
            "separate_operators_are_not_fit_into_each_other": True,
            "numerical_mass_closure_is_not_physical_validation": True,
            "rainout_classification_is_not_concentration_validation": True,
            "no_facility_qra_promotion": True,
        },
        "required_next_evidence": [
            "independent holdout source-term measurements with reviewed geometry and time base",
            "quantitative concentration or LFL comparison for the declared outdoor domain",
            "reviewed release boundary, isolation and inventory evidence before facility QRA",
        ],
    }


__all__ = [
    "AUDIT_SCHEMA",
    "SlabxSourceValidationGateAuditError",
    "audit_slabx_lh2_source_validation_gates",
]
