"""Pure helpers for auditing LH2 inspection-centre time-series evidence.

The audit deliberately separates signal-name discovery from engineering-unit
approval.  A tag such as ``PT1105A`` can be classified as pressure, but its
numeric values must not enter a state snapshot until a reviewed unit map is
provided.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .state_snapshot import EquipmentStateSnapshot, build_state_snapshot_from_normalized
from .telemetry import Frame, Value


def _normalise_header(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").strip().upper())


def classify_signal(header: Any) -> dict[str, str]:
    """Classify a header without guessing its physical unit."""

    raw = str(header or "").strip()
    token = _normalise_header(raw)
    if not token:
        return {"category": "unknown", "basis": "empty_header"}
    if token.startswith("DPT") or token.startswith("DP"):
        return {"category": "differential_pressure", "basis": "tag_prefix"}
    if token.startswith("PT") or token.startswith("P_"):
        return {"category": "pressure", "basis": "tag_prefix"}
    if token.startswith("TT") or token.startswith("T_"):
        return {"category": "temperature", "basis": "tag_prefix"}
    if token.startswith("LT") or token.startswith("L_"):
        return {"category": "level", "basis": "tag_prefix"}
    if token.startswith("FT") or token.startswith("F_"):
        return {"category": "flow", "basis": "tag_prefix"}
    if token.startswith(("TCV", "PCV", "FCV", "LCV", "XV", "HV")):
        return {"category": "control_or_valve_state", "basis": "tag_prefix"}
    if any(word in token for word in ("TIMESTAMP", "DATETIME", "DATE", "TIME")):
        return {"category": "time", "basis": "header_keyword"}
    if token in {"ACTION", "ATSTEP", "FROMSTEP", "TOSTEP", "PROGRESSPCT"}:
        return {"category": "sequence_metadata", "basis": "header_keyword"}
    return {"category": "unknown", "basis": "unresolved_header"}


def normalise_unit_claims(value: Mapping[str, Any] | None) -> dict[str, dict[str, str | None]]:
    """Return exact reviewed source and comparison unit roles.

    ``source_unit`` is the unit carried by the incoming time-series column.
    ``comparison_unit`` is optional procedure or setpoint context and is never
    silently used as a runtime conversion unit.  Legacy strings and
    ``{"unit": ...}`` mappings remain source-unit declarations.
    """

    if not value:
        return {}
    nested = value.get("signal_units") if isinstance(value, Mapping) else None
    source = nested if isinstance(nested, Mapping) else value
    result: dict[str, dict[str, str | None]] = {}
    for key, raw in source.items():
        if isinstance(raw, Mapping):
            source_unit = raw.get("source_unit", raw.get("unit"))
            comparison_unit = raw.get("comparison_unit")
        else:
            source_unit = raw
            comparison_unit = None
        if isinstance(source_unit, str) and str(key).strip() and source_unit.strip():
            result[_normalise_header(key)] = {
                "source_unit": source_unit.strip(),
                "comparison_unit": (
                    comparison_unit.strip()
                    if isinstance(comparison_unit, str) and comparison_unit.strip()
                    else None
                ),
            }
    return result


def normalise_unit_map(value: Mapping[str, Any] | None) -> dict[str, str]:
    """Return the legacy exact tag-to-source-unit map.

    Use :func:`normalise_unit_claims` when procedure or setpoint context is
    also needed by an audit or user interface.
    """

    return {
        tag: str(claim["source_unit"])
        for tag, claim in normalise_unit_claims(value).items()
        if claim.get("source_unit") is not None
    }


def resolve_unit(header: Any, unit_map: Mapping[str, str]) -> tuple[str | None, str]:
    """Resolve only an exact reviewed mapping; never infer from value ranges."""

    unit = unit_map.get(_normalise_header(header))
    if unit:
        return unit, "CONFIRMED_BY_REVIEWED_MAP"
    return None, "MISSING_OR_UNCONFIRMED"


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def summarise_numeric(values: Iterable[Any]) -> dict[str, Any]:
    """Summarise numeric values while retaining no raw samples."""

    count = 0
    minimum: float | None = None
    maximum: float | None = None
    for value in values:
        if not is_number(value):
            continue
        number = float(value)
        count += 1
        minimum = number if minimum is None else min(minimum, number)
        maximum = number if maximum is None else max(maximum, number)
    return {"numeric_count": count, "min": minimum, "max": maximum}


def frame_from_row(
    row: Mapping[str, Any],
    *,
    stream_id: str,
    sequence: int,
    source_time_s: float,
    arrival_time_s: float,
    origin: str,
    bindings: Mapping[str, Mapping[str, Any]],
) -> Frame:
    """Convert one tabular process-state row into a strict telemetry frame.

    The caller must provide the engineering unit, PRISM tag, and quality for
    every selected source column.  Header prefixes, numeric ranges, and row
    order are never used to infer units, timestamps, quality, or component
    identity.  This keeps XLSX/CSV evidence separate from accident release
    ownership: the returned frame contains process-state values only.
    """
    if not isinstance(row, Mapping):
        raise TypeError("timeseries row must be a mapping")
    if not isinstance(bindings, Mapping) or not bindings:
        raise ValueError("explicit row bindings are required")
    values: dict[str, Value] = {}
    seen_tags: set[str] = set()
    allowed_quality = {"valid", "invalid", "suspect", "missing"}
    for source_header, binding in bindings.items():
        if not isinstance(source_header, str) or not source_header.strip():
            raise ValueError("source headers must be nonempty strings")
        if not isinstance(binding, Mapping):
            raise ValueError(f"binding for {source_header} must be a mapping")
        tag = binding.get("tag")
        unit = binding.get("unit")
        quality = binding.get("quality")
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError(f"binding for {source_header} requires an explicit tag")
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError(f"binding for {source_header} requires an explicit unit")
        if quality not in allowed_quality:
            raise ValueError(
                f"binding for {source_header} requires quality in {sorted(allowed_quality)}"
            )
        if tag in seen_tags:
            raise ValueError(f"duplicate PRISM tag in row bindings: {tag}")
        if source_header not in row:
            raise ValueError(f"row is missing explicitly bound source column: {source_header}")
        raw_value = row[source_header]
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"row value is not numeric: {source_header}")
        if not math.isfinite(float(raw_value)):
            raise ValueError(f"row value is not finite: {source_header}")
        seen_tags.add(tag)
        values[tag] = Value(value=float(raw_value), unit=unit, quality=quality)
    try:
        return Frame(
            stream_id=stream_id,
            sequence=sequence,
            source_time_s=source_time_s,
            arrival_time_s=arrival_time_s,
            origin=origin,
            values=values,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid telemetry frame metadata: {error}") from error


def state_snapshot_from_row(
    row: Mapping[str, Any],
    *,
    stream_id: str,
    sequence: int,
    source_time_s: float,
    arrival_time_s: float,
    origin: str,
    bindings: Mapping[str, Mapping[str, Any]],
    normalizer: Any,
    now_s: float,
    component_id: str,
    pressure_tag: str | None = None,
    temperature_tag: str | None = None,
    position_enu_m: tuple[float, float, float] | None = None,
    ambient_pressure_pa: float | None = None,
) -> EquipmentStateSnapshot:
    """Build a state-only equipment snapshot from one explicitly bound row.

    The normalizer remains the authority for sensor location, source-unit
    conversion, pressure basis, freshness, ordering, and quality.  This
    helper only composes ``frame_from_row`` with the existing state-snapshot
    contract; it does not create an accident request, opening, duration,
    frequency, or provider release.
    """
    if not callable(getattr(normalizer, "normalize", None)):
        raise TypeError("normalizer must provide normalize()")
    if not isinstance(component_id, str) or not component_id.strip():
        raise ValueError("component_id must be a nonempty string")
    frame = frame_from_row(
        row,
        stream_id=stream_id,
        sequence=sequence,
        source_time_s=source_time_s,
        arrival_time_s=arrival_time_s,
        origin=origin,
        bindings=bindings,
    )
    normalized = normalizer.normalize(
        frame,
        now_s=now_s,
        ambient_pressure_pa=ambient_pressure_pa,
    )
    return build_state_snapshot_from_normalized(
        normalized,
        component_id=component_id,
        captured_at_s=source_time_s,
        pressure_tag=pressure_tag,
        temperature_tag=temperature_tag,
        position_enu_m=position_enu_m,
    )
