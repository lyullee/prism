"""Extract explicit engineering-unit claims from workbook header cells.

Only text written in a header such as ``PT1105A (MPa)`` is accepted. Numeric
ranges, chart axes, setpoints in a separate procedure, and signal prefixes do
not create a unit claim.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


HEADER_UNIT_PATTERN = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_-]*)\s*\(\s*([^()]+?)\s*\)\s*$"
)


def normalize_tag(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").strip().upper())


def normalize_unit(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    token = value.strip().lower().replace(" ", "")
    return {
        "mpa": "mpa",
        "kpa": "kpa",
        "pa": "pa",
        "bar": "bar",
        "c": "degc",
        "°c": "degc",
        "℃": "degc",
        "degc": "degc",
        "k": "k",
    }.get(token, token)


def extract_header_unit_claims(headers: Iterable[Any]) -> list[dict[str, str]]:
    """Return explicit tag/unit claims in a sequence of header values."""

    claims: list[dict[str, str]] = []
    for raw in headers:
        match = HEADER_UNIT_PATTERN.match(str(raw or ""))
        if match is None:
            continue
        tag = normalize_tag(match.group(1))
        unit = normalize_unit(match.group(2))
        if not tag or unit is None:
            continue
        claims.append({"tag": tag, "unit": unit, "header": str(raw).strip()})
    return claims


def summarize_header_claims(claims: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate explicit claims and expose conflicting declarations."""

    by_tag: dict[str, dict[str, Any]] = {}
    for claim in claims:
        tag = normalize_tag(claim.get("tag"))
        unit = normalize_unit(claim.get("unit"))
        if not tag or unit is None:
            continue
        row = by_tag.setdefault(tag, {"units": set(), "evidence": []})
        row["units"].add(unit)
        row["evidence"].append({k: v for k, v in claim.items() if k != "tag"})
    result: dict[str, Any] = {}
    conflict_tags: list[str] = []
    for tag in sorted(by_tag):
        row = by_tag[tag]
        units = sorted(row["units"])
        if len(units) > 1:
            conflict_tags.append(tag)
        result[tag] = {"units": units, "evidence": row["evidence"]}
    return {"by_tag": result, "conflict_tags": conflict_tags}


__all__ = [
    "HEADER_UNIT_PATTERN",
    "extract_header_unit_claims",
    "normalize_tag",
    "normalize_unit",
    "summarize_header_claims",
]
