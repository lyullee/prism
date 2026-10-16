"""Convert process-model forecast rows into strict PRISM HAZOP frames.

The adapter is deliberately an input boundary, not a risk model.  It keeps
the source digest, uses an explicitly supplied operating mode, converts the
declared engineering units to SI, and emits ``model_prediction`` frames that
can be passed to :func:`lh2_tno.hazop_forecast.run_hazop_forecast_risk_scan`.
It never infers a mode, an accident frequency, a release packet, or facility
IR/F-N from a process workbook.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import hashlib
import json
import math
from typing import Any

from .hazop import HAZOP_STATE_SCHEMA


SCHEMA = "prism.process_forecast_frame_set.v1"
ORIGIN = "model_prediction"


class ProcessForecastError(ValueError):
    """Raised when process forecast data cannot satisfy the input contract."""


def _name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProcessForecastError(f"{field} must be a non-empty string")
    return value.strip()


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ProcessForecastError(f"{field} must be finite") from error
    if not math.isfinite(number):
        raise ProcessForecastError(f"{field} must be finite")
    return number


def _unit(value: Any, field: str) -> str:
    unit = _name(value, field).replace("°", "deg").replace("℃", "C")
    aliases = {
        "MPa": "MPa", "kPa": "kPa", "Pa": "Pa", "bar": "bar",
        "K": "K", "C": "C", "degC": "C", "deg C": "C",
        "kg": "kg", "kg/s": "kg/s", "m3/s": "m3/s", "fraction": "fraction",
        "1": "fraction",
    }
    if unit not in aliases:
        raise ProcessForecastError(
            f"{field} has unsupported unit {unit!r}; use Pa, kPa, MPa, bar, K, C, kg, kg/s, m3/s, or fraction"
        )
    return aliases[unit]


def _to_si(value: Any, unit: str, field: str) -> float:
    number = _finite(value, field)
    factors = {"Pa": 1.0, "kPa": 1_000.0, "MPa": 1_000_000.0, "bar": 100_000.0,
               "K": 1.0, "C": 1.0, "kg": 1.0, "kg/s": 1.0, "m3/s": 1.0,
               "fraction": 1.0}
    if unit == "C":
        return number + 273.15
    return number * factors[unit]


def _time_s(value: Any, *, first: Any, index: int, sample_period_s: float, field: str) -> float:
    if value is None:
        return index * sample_period_s
    if isinstance(value, datetime):
        return (value - first).total_seconds()
    if isinstance(value, date):
        return (value - first).total_seconds()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ProcessForecastError(f"{field} must be numeric or ISO datetime") from error
        if isinstance(first, str):
            first = datetime.fromisoformat(first)
        return (parsed - first).total_seconds()
    return _finite(value, field) - _finite(first, field)


def _digest_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps([dict(row) for row in rows], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_forecast_frames(
    rows: Sequence[Mapping[str, Any]],
    *,
    facility_id: str,
    component_id: str,
    operating_mode: str,
    mapping: Mapping[str, Mapping[str, Any]],
    source_id: str,
    source_provenance: str,
    time_column: str | None = None,
    sample_period_s: float = 1.0,
    source_digest: str | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """Build a forecast frame set from rows and an explicit column mapping.

    ``mapping`` is keyed by the PRISM tag and each value contains
    ``source_column``, ``quantity``, ``unit`` and optional ``sensor_location``.
    The operating mode is copied verbatim to every frame; it is never inferred
    from an action label or a sensor value.
    """
    facility_id = _name(facility_id, "facility_id")
    component_id = _name(component_id, "component_id")
    operating_mode = _name(operating_mode, "operating_mode")
    source_id = _name(source_id, "source_id")
    source_provenance = _name(source_provenance, "source_provenance")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        raise ProcessForecastError("rows must be a non-empty sequence")
    if not isinstance(mapping, Mapping) or not mapping:
        raise ProcessForecastError("mapping must be a non-empty mapping")
    sample_period_s = _finite(sample_period_s, "sample_period_s")
    if sample_period_s <= 0:
        raise ProcessForecastError("sample_period_s must be positive")
    if max_rows is not None:
        if isinstance(max_rows, bool) or not isinstance(max_rows, int) or max_rows <= 0:
            raise ProcessForecastError("max_rows must be a positive integer")
        rows = rows[:max_rows]
    rows = [dict(row) for row in rows]
    headers = set(rows[0])
    normalized_mapping: dict[str, dict[str, Any]] = {}
    for tag, raw in mapping.items():
        tag = _name(tag, "mapping tag")
        if not isinstance(raw, Mapping):
            raise ProcessForecastError(f"mapping[{tag}] must be a mapping")
        source_column = _name(raw.get("source_column"), f"mapping[{tag}].source_column")
        quantity = _name(raw.get("quantity"), f"mapping[{tag}].quantity")
        unit = _unit(raw.get("unit"), f"mapping[{tag}].unit")
        if source_column not in headers:
            raise ProcessForecastError(f"source column {source_column!r} is missing")
        normalized_mapping[tag] = {
            "source_column": source_column,
            "quantity": quantity,
            "unit": unit,
            "sensor_location": raw.get("sensor_location"),
        }
    first_time = rows[0].get(time_column) if time_column else None
    if time_column and time_column not in headers:
        raise ProcessForecastError(f"time column {time_column!r} is missing")
    resolved_source_digest = source_digest or _digest_rows(rows)
    frames: list[dict[str, Any]] = []
    previous_time = -1.0
    for index, row in enumerate(rows):
        forecast_time_s = _time_s(
            row.get(time_column) if time_column else None,
            first=first_time,
            index=index,
            sample_period_s=sample_period_s,
            field=f"rows[{index}].{time_column or 'sample_period_s'}",
        )
        if forecast_time_s < 0 or forecast_time_s <= previous_time:
            raise ProcessForecastError("forecast times must be strictly increasing")
        previous_time = forecast_time_s
        values: dict[str, dict[str, Any]] = {}
        for tag, spec in normalized_mapping.items():
            raw_value = row.get(spec["source_column"])
            value_si = _to_si(raw_value, spec["unit"], f"rows[{index}].{spec['source_column']}")
            values[tag] = {
                "component_id": component_id,
                "quantity": spec["quantity"],
                "value_si": value_si,
                "sensor_location": spec["sensor_location"],
                "quality": "valid",
            }
        frames.append({
            "schema_version": HAZOP_STATE_SCHEMA,
            "facility_id": facility_id,
            "component_id": component_id,
            "operating_mode": operating_mode,
            "captured_at_s": forecast_time_s,
            "forecast_time_s": forecast_time_s,
            "origin": ORIGIN,
            "source_digest": resolved_source_digest,
            "source_provenance": source_provenance,
            "values": values,
        })
    return {
        "schema_version": SCHEMA,
        "status": "PROCESS_FORECAST_FRAMES_READY",
        "facility_id": facility_id,
        "component_id": component_id,
        "operating_mode": operating_mode,
        "origin": ORIGIN,
        "source": {
            "source_id": source_id,
            "source_provenance": source_provenance,
            "source_digest": resolved_source_digest,
            "row_count_selected": len(rows),
            "time_column": time_column,
            "sample_period_s": sample_period_s if time_column is None else None,
        },
        "mapping": normalized_mapping,
        "frames": frames,
        "policy": {
            "operating_mode_taken_from_input": True,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_release_created": False,
            "facility_qra_promotion": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Process-model forecast frames are ready for HAZOP forecast scanning. "
            "They carry state and mode only; no accident frequency, release boundary, "
            "physical validation, or facility IR/F-N claim is created."
        ),
    }


__all__ = ["SCHEMA", "ORIGIN", "ProcessForecastError", "build_forecast_frames"]
