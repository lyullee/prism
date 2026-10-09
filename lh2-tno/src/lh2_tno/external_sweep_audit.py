"""Audit external LH2 tank/PSV/TNO sweep outputs without QRA promotion.

The sweep is useful for numerical closure and processing-time evidence.  It is
not, by itself, an accident provider packet, an independent physical
validation experiment, or a qualified facility IR/F-N result.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Iterable


SCHEMA = "prism.external_lh2_sweep_audit.v1"
JSON_DATASETS = (
    "sweep_results.json",
    "secondary_results.json",
    "cd_results.json",
    "tno_policy_results.json",
    "risk_model_matrix.json",
    "vent_fire_risk_results.json",
)
CSV_DATASETS = ("all_case_summary.csv",)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _percentile(values: Iterable[float], probability: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _numeric_summary(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [
        float(row[key])
        for row in rows
        if isinstance(row.get(key), (int, float))
        and not isinstance(row.get(key), bool)
        and math.isfinite(float(row[key]))
    ]
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "median": median(values) if values else None,
        "p95": _percentile(values, 0.95),
        "max": max(values) if values else None,
    }


def _read_json_dataset(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else []
    rows = [row for row in rows if isinstance(row, dict)]
    status_counts = Counter(str(row.get("status")) for row in rows if row.get("status") is not None)
    qra_grade_counts = Counter(str(row.get("qra_grade")) for row in rows if row.get("qra_grade") is not None)
    return {
        "record_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "qra_grade_counts": dict(sorted(qra_grade_counts.items())),
        "runtime_s": _numeric_summary(rows, "runtime_s"),
        "max_mass_residual_kg": _numeric_summary(rows, "max_mass_residual_kg"),
        "max_energy_residual_J": _numeric_summary(rows, "max_energy_residual_J"),
        "overall_max_ir_proxy_per_y": _numeric_summary(rows, "overall_max_ir_proxy_per_y"),
        "hyram_field_count": sum(
            any(key.startswith("hyram_") for key in row) for row in rows
        ),
        "risk_proxy_field_count": sum(
            any("ir_proxy" in key or "risk_area" in key for key in row)
            for row in rows
        ),
    }


def _read_csv_dataset(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    status_counts = Counter(str(row.get("status")) for row in rows if row.get("status"))
    return {
        "record_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "header_count": len(rows[0]) if rows else 0,
        "raw_rows_copied": False,
    }


def audit_root(source_root: str | Path) -> dict[str, Any]:
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise ValueError(f"source_root is not a directory: {root}")
    datasets: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for name in (*JSON_DATASETS, *CSV_DATASETS):
        path = root / name
        if not path.is_file():
            missing.append(name)
            continue
        if path.suffix.casefold() == ".json":
            summary = _read_json_dataset(path)
        else:
            summary = _read_csv_dataset(path)
        datasets[name] = {
            "relative_path": name,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            **summary,
        }

    tank_record_count = sum(
        datasets.get(name, {}).get("record_count", 0)
        for name in ("sweep_results.json", "secondary_results.json", "cd_results.json")
    )
    policy = datasets.get("tno_policy_results.json", {})
    policy_runtime = policy.get("runtime_s", {})
    residual_datasets = [
        datasets[name]
        for name in ("sweep_results.json", "secondary_results.json", "cd_results.json")
        if name in datasets
    ]
    mass_max = max(
        (item["max_mass_residual_kg"]["max"] for item in residual_datasets if item["max_mass_residual_kg"]["max"] is not None),
        default=None,
    )
    energy_max = max(
        (item["max_energy_residual_J"]["max"] for item in residual_datasets if item["max_energy_residual_J"]["max"] is not None),
        default=None,
    )
    return {
        "schema_version": SCHEMA,
        "status": "SCREENING_ONLY_EXTERNAL_SWEEP",
        "source_root": str(root),
        "missing_datasets": missing,
        "datasets": datasets,
        "aggregate": {
            "tank_sweep_record_count": tank_record_count,
            "csv_case_record_count": datasets.get("all_case_summary.csv", {}).get("record_count", 0),
            "tno_policy_record_count": policy.get("record_count", 0),
            "tno_policy_runtime_s": policy_runtime,
            "maximum_tank_mass_residual_kg": mass_max,
            "maximum_tank_energy_residual_J": energy_max,
            "all_declared_tank_cases_present": tank_record_count == datasets.get("all_case_summary.csv", {}).get("record_count", -1),
            "engineering_judgement_qra_grade_count": policy.get("qra_grade_counts", {}).get("ENGINEERING_JUDGEMENT", 0),
        },
        "promotion_gates": {
            "numerical_closure_evidence_allowed": bool(residual_datasets),
            "processing_time_evidence_allowed": bool(datasets),
            "independent_physical_validation_claim": False,
            "qualified_provider_packet": False,
            "facility_ir_fn_claim": False,
            "frequency_inference": False,
            "reason": (
                "The external sweep contains model outputs and engineering-judgement risk proxies. "
                "Residuals are internal numerical closure checks; no measured release, independent "
                "experiment, qualified accident packet, or facility population evidence is supplied."
            ),
        },
    }


def public_summary(report: dict[str, Any], source_root_label: str = "<external-lh2-sweep-root>") -> dict[str, Any]:
    """Strip the local path while retaining hashes and aggregate evidence."""

    return {
        "schema_version": report["schema_version"],
        "status": report["status"],
        "source_root": source_root_label,
        "missing_datasets": report["missing_datasets"],
        "aggregate": report["aggregate"],
        "promotion_gates": report["promotion_gates"],
        "datasets": report["datasets"],
    }
