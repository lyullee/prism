"""Compare an observed-state manifest with independently reviewed units.

The runtime manifest and the reviewed operating-procedure evidence are two
different claims.  This module makes disagreement explicit before a signal
can be used to construct a state snapshot.  It never chooses a unit from a
numeric range and it never opens a release or frequency gate.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


SCHEMA = "prism.observed_unit_consistency_audit.v1"


def _tag(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").strip().upper())


def _unit(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    token = value.strip().lower().replace(" ", "")
    aliases = {
        "c": "degc",
        "°c": "degc",
        "degc": "degc",
        "mpa": "mpa",
        "kpa": "kpa",
        "pa": "pa",
        "bar": "bar",
        "kg": "kg",
        "kg/s": "kg/s",
        "k": "k",
    }
    return aliases.get(token, token)


def _reviewed_unit_claims(reviewed_map: Mapping[str, Any]) -> dict[str, dict[str, str | None]]:
    """Return reviewed unit roles without collapsing source and comparison units.

    ``unit`` is the legacy field and means the unit carried by the observed
    source column.  New maps may state that role explicitly as ``source_unit``
    and may additionally record a procedure/setpoint ``comparison_unit``.
    The latter is contextual evidence only and is never compared with the
    runtime source unit.
    """
    if not isinstance(reviewed_map, Mapping):
        raise TypeError("reviewed_map must be an object")
    source = reviewed_map.get("signal_units", reviewed_map)
    if not isinstance(source, Mapping):
        raise ValueError("reviewed_map.signal_units must be an object")
    result: dict[str, dict[str, str | None]] = {}
    for raw_tag, raw_value in source.items():
        tag = _tag(raw_tag)
        if not tag:
            continue
        if isinstance(raw_value, Mapping):
            legacy = _unit(raw_value.get("unit"))
            source_unit = _unit(raw_value.get("source_unit")) or legacy
            comparison_unit = _unit(raw_value.get("comparison_unit"))
        else:
            source_unit = _unit(raw_value)
            comparison_unit = None
        if source_unit is None:
            continue
        previous = result.get(tag)
        claim = {
            "source_unit": source_unit,
            "comparison_unit": comparison_unit,
        }
        if previous is not None and (
            previous.get("source_unit") != source_unit
            or previous.get("comparison_unit") != comparison_unit
        ):
            raise ValueError(f"reviewed map contains conflicting units for {tag}")
        result[tag] = claim
    return result


def _reviewed_units(reviewed_map: Mapping[str, Any]) -> dict[str, str]:
    """Backward-compatible source-unit-only view for existing callers."""

    return {
        tag: str(claim["source_unit"])
        for tag, claim in _reviewed_unit_claims(reviewed_map).items()
        if claim.get("source_unit") is not None
    }


def audit_observed_unit_consistency(
    manifest: Mapping[str, Any], reviewed_map: Mapping[str, Any]
) -> dict[str, Any]:
    """Audit exact manifest-column and reviewed-tag unit agreement."""

    if not isinstance(manifest, Mapping):
        raise TypeError("manifest must be an object")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("manifest.sources must be a non-empty array")
    reviewed_claims = _reviewed_unit_claims(reviewed_map)
    rows: list[dict[str, Any]] = []
    manifest_tags: set[str] = set()
    for source_index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise ValueError(f"manifest.sources[{source_index}] must be an object")
        source_id = str(source.get("source_id") or "").strip()
        if not source_id:
            raise ValueError(f"manifest.sources[{source_index}] requires source_id")
        signals = source.get("signals")
        if not isinstance(signals, Mapping) or not signals:
            raise ValueError(f"source {source_id} requires signals")
        for quantity, raw_rule in signals.items():
            rule = raw_rule if isinstance(raw_rule, Mapping) else {"column": raw_rule}
            column = str(rule.get("column") or "").strip()
            manifest_unit = _unit(rule.get("unit"))
            if not column or manifest_unit is None:
                raise ValueError(
                    f"source {source_id} signal {quantity} requires column and unit"
                )
            tag = _tag(column)
            manifest_tags.add(tag)
            claim = reviewed_claims.get(tag)
            reviewed_unit = claim.get("source_unit") if claim else None
            comparison_unit = claim.get("comparison_unit") if claim else None
            if reviewed_unit is None:
                status = "MANIFEST_ONLY_UNREVIEWED"
            elif reviewed_unit != manifest_unit:
                status = "CONFLICTING_UNITS"
            else:
                status = "MATCHED"
            rows.append(
                {
                    "source_id": source_id,
                    "quantity": str(quantity),
                    "column": column,
                    "normalized_tag": tag,
                    "manifest_unit": manifest_unit,
                    "reviewed_unit": reviewed_unit,
                    "reviewed_source_unit": reviewed_unit,
                    "reviewed_comparison_unit": comparison_unit,
                    "unit_roles": {
                        "manifest": "source",
                        "reviewed_unit": "source",
                        "reviewed_comparison_unit": "procedure_or_setpoint_context",
                    },
                    "status": status,
                }
            )
    reviewed_only = sorted(set(reviewed_claims) - manifest_tags)
    conflict_count = sum(row["status"] == "CONFLICTING_UNITS" for row in rows)
    unreviewed_count = sum(row["status"] == "MANIFEST_ONLY_UNREVIEWED" for row in rows)
    matched_count = sum(row["status"] == "MATCHED" for row in rows)
    if conflict_count:
        status = "BLOCKED_UNIT_CONFLICT"
    elif unreviewed_count:
        status = "REVIEWED_UNIT_COVERAGE_INCOMPLETE"
    else:
        status = "REVIEWED_UNITS_MATCH_MANIFEST"
    return {
        "schema_version": SCHEMA,
        "status": status,
        "source_manifest_schema": manifest.get("schema_version"),
        "reviewed_map_schema": reviewed_map.get("schema_version") if isinstance(reviewed_map, Mapping) else None,
        "source_count": len(sources),
        "binding_count": len(rows),
        "matched_count": matched_count,
        "conflict_count": conflict_count,
        "unreviewed_count": unreviewed_count,
        "reviewed_only_tag_count": len(reviewed_only),
        "reviewed_only_tags": reviewed_only,
        "bindings": rows,
        "policy": {
            "numeric_range_unit_inference": False,
            "source_unit_vs_comparison_unit_distinguished": True,
            "comparison_unit_used_for_runtime_conversion": False,
            "unit_precedence_selected": False,
            "state_snapshot_binding_allowed": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "provider_packet_created": False,
            "facility_qra_claim": False,
            "diagnostic_only": True,
        },
        "interpretation": (
            "Manifest units are source-column units. A reviewed comparison_unit is procedure or "
            "setpoint context only; it is not compared with or substituted for the source unit. "
            "A source-unit conflict or missing review keeps state binding closed; no unit is selected "
            "by inference."
        ),
    }


__all__ = ["SCHEMA", "audit_observed_unit_consistency"]
