"""Audit filename provenance signals against an observed-state manifest.

Names such as ``예측데이터`` or ``원본 학습데이터`` are review clues, not
proof of origin. This module only flags a declared-origin conflict and never
changes the origin automatically.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SCHEMA = "prism.observed_origin_provenance_audit.v1"


def _name_signal(path: str) -> str:
    lowered = path.lower()
    if "예측데이터" in path or "prediction" in lowered or "forecast" in lowered:
        return "prediction_named"
    if "원본" in path or "학습" in path or "training" in lowered:
        return "training_or_source_named"
    return "no_filename_origin_signal"


def audit_manifest_origin(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        raise TypeError("manifest must be an object")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("manifest.sources must be a non-empty array")
    rows: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise ValueError(f"manifest.sources[{index}] must be an object")
        source_id = str(source.get("source_id") or "").strip()
        path = str(source.get("path") or source.get("source_path") or "").strip()
        origin = str(source.get("origin") or "").strip()
        if not source_id or not path or not origin:
            raise ValueError(f"manifest.sources[{index}] requires source_id, path, and origin")
        signal = _name_signal(path)
        conflict = (
            signal == "prediction_named" and origin == "historian_measured"
        ) or (
            signal == "training_or_source_named" and origin == "model_prediction"
        )
        rows.append({
            "source_id": source_id,
            "path": path,
            "declared_origin": origin,
            "filename_origin_signal": signal,
            "status": "ORIGIN_REVIEW_REQUIRED" if conflict else "NO_FILENAME_CONFLICT",
        })
    conflicts = [row for row in rows if row["status"] == "ORIGIN_REVIEW_REQUIRED"]
    return {
        "schema_version": SCHEMA,
        "status": "ORIGIN_REVIEW_REQUIRED" if conflicts else "NO_FILENAME_CONFLICTS",
        "source_count": len(rows),
        "conflict_count": len(conflicts),
        "sources": rows,
        "policy": {
            "origin_changed_automatically": False,
            "state_snapshot_binding_allowed": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_packet_created": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Filename semantics are review clues only. A declared origin is not changed without "
            "source-owner evidence."
        ),
    }


__all__ = ["SCHEMA", "audit_manifest_origin"]
