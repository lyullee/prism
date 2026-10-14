"""Audit explicit operating-mode HAZOP selection on observed runtime frames.

The audit closes the qualitative bridge from a state-only runtime frame to a
mode-specific HAZOP scenario.  It intentionally stops before an accident
packet, literature frequency, SLABx-LH2 consequence, or facility QRA claim.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from .hazop import evaluate_hazop_runtime_frame


SCHEMA = "prism.observed_hazop_runtime_audit.v1"
RUNTIME_SCHEMA = "prism.observed_state_runtime_frames.v1"
TABLE_SET_SCHEMA = "prism.hazop_runtime_table_set.v1"


def _rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(row)
    return rows


def audit_observed_hazop_runtime(
    runtime_frames: Mapping[str, Any],
    hazop_table_set: Mapping[str, Any],
    *,
    now_s: float,
) -> dict[str, Any]:
    """Evaluate one HAZOP table per explicit observed runtime frame."""
    if runtime_frames.get("schema_version") != RUNTIME_SCHEMA:
        raise ValueError(f"runtime_frames schema_version must be {RUNTIME_SCHEMA}")
    if hazop_table_set.get("schema_version") != TABLE_SET_SCHEMA:
        raise ValueError(f"hazop_table_set schema_version must be {TABLE_SET_SCHEMA}")
    if isinstance(now_s, bool) or not isinstance(now_s, (int, float)):
        raise ValueError("now_s must be numeric")
    tables = hazop_table_set.get("tables")
    if not isinstance(tables, Mapping) or not tables:
        raise ValueError("hazop_table_set.tables must be a non-empty object")
    frames = _rows(runtime_frames.get("frames"), "runtime_frames.frames")
    if not frames:
        raise ValueError("runtime_frames.frames must not be empty")

    rows: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    status_counts: Counter[str] = Counter()
    selected_scenario_count = 0
    for index, frame in enumerate(frames):
        component_id = str(frame.get("component_id") or "").strip()
        if not component_id:
            blocking_reasons.append(f"frame[{index}] has no component_id")
            continue
        table = tables.get(component_id)
        if not isinstance(table, Mapping):
            blocking_reasons.append(f"{component_id}: no HAZOP table is bound")
            rows.append({
                "component_id": component_id,
                "operating_mode": frame.get("operating_mode"),
                "status": "HAZOP_TABLE_MISSING",
                "selected_scenario_count": 0,
                "blocking_reasons": ["no HAZOP table is bound"],
            })
            status_counts["HAZOP_TABLE_MISSING"] += 1
            continue
        try:
            result = evaluate_hazop_runtime_frame(table, frame, now_s=float(now_s))
        except (TypeError, ValueError) as error:
            reason = str(error)
            blocking_reasons.append(f"{component_id}: {reason}")
            rows.append({
                "component_id": component_id,
                "operating_mode": frame.get("operating_mode"),
                "status": "HAZOP_EVALUATION_BLOCKED",
                "selected_scenario_count": 0,
                "blocking_reasons": [reason],
            })
            status_counts["HAZOP_EVALUATION_BLOCKED"] += 1
            continue
        selected = int(result.get("selected_scenario_count", 0))
        selected_scenario_count += selected
        status = str(result.get("status") or "UNKNOWN")
        status_counts[status] += 1
        row = {
            "component_id": component_id,
            "source_id": frame.get("source_id"),
            "captured_at_s": frame.get("captured_at_s"),
            "operating_mode": result.get("operating_mode"),
            "state_snapshot_digest": frame.get("state_snapshot_digest"),
            "table_id": result.get("table_id"),
            "table_digest": result.get("table_digest"),
            "state_digest": result.get("state_digest"),
            "status": status,
            "active_deviation_count": result.get("active_deviation_count"),
            "selected_scenario_count": selected,
            "selected_scenarios": result.get("selected_scenarios", []),
            "checks": result.get("checks", []),
            "blocking_reasons": result.get("blocking_reasons", []),
        }
        rows.append(row)
        if status != "SCENARIOS_SELECTED":
            blocking_reasons.extend(
                f"{component_id}: {reason}"
                for reason in result.get("blocking_reasons", [])
            )

    valid = (
        len(rows) == len(frames)
        and not blocking_reasons
        and all(row.get("operating_mode") for row in rows)
        and all(row.get("status") in {"SCENARIOS_SELECTED", "NO_DEVIATION", "NO_APPLICABLE_MODE_ROW"} for row in rows)
    )
    return {
        "schema_version": SCHEMA,
        "status": "OBSERVED_HAZOP_MODE_SCENARIOS_SELECTED" if valid else "OBSERVED_HAZOP_MODE_AUDIT_BLOCKED",
        "runtime_frame_count": len(frames),
        "evaluated_frame_count": len(rows),
        "selected_scenario_count": selected_scenario_count,
        "operating_mode_counts": dict(Counter(
            str(row["operating_mode"])
            for row in rows
            if isinstance(row.get("operating_mode"), str) and row.get("operating_mode")
        )),
        "status_counts": dict(status_counts),
        "rows": rows,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "policy": {
            "operating_mode_taken_from_explicit_runtime_input": True,
            "operating_mode_inferred": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created": False,
            "consequence_calculated": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Observed state and explicit operating mode selected HAZOP scenarios. "
            "Each selected scenario still requires a qualified provider release, "
            "literature frequency binding, and the downstream SLABx-LH2/TNO chain."
        ),
    }


__all__ = ["SCHEMA", "audit_observed_hazop_runtime"]
