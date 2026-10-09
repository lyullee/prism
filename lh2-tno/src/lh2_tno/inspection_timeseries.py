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


def normalise_unit_map(value: Mapping[str, Any] | None) -> dict[str, str]:
    """Return an exact, case-insensitive reviewed tag-to-unit map."""

    if not value:
        return {}
    nested = value.get("signal_units") if isinstance(value, Mapping) else None
    source = nested if isinstance(nested, Mapping) else value
    result: dict[str, str] = {}
    for key, unit in source.items():
        if str(key).strip() and str(unit).strip():
            result[_normalise_header(key)] = str(unit).strip()
    return result


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

