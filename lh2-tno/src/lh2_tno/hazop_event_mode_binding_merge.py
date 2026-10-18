"""Merge explicit HAZOP mode records before running the canonical event audit.

The base facility campaign and optional LH2 extension campaigns are often
exported by different tools.  This adapter joins their *explicit* rows by
``event_id`` and then delegates accounting to
``audit_hazop_event_mode_binding``.  It never infers an operating mode,
scenario, release mode, or frequency from an event name.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from .hazop_event_mode_binding import audit_hazop_event_mode_binding


SCHEMA = "prism.hazop_event_mode_binding_merge.v1"


def _rows(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(dict(row))
    return rows


def _binding_rows(value: Mapping[str, Any], label: str) -> list[dict[str, Any]]:
    raw = value.get("event_rows")
    if raw is None:
        raw = value.get("bindings")
    return _rows(raw, f"{label}.event_rows/bindings")


def _event_id(row: Mapping[str, Any], label: str) -> str:
    event_id = str(row.get("event_id") or "").strip()
    if not event_id:
        raise ValueError(f"{label}.event_id must be a non-empty string")
    return event_id


def _rewrite_event_id(event_id: str, replacements: Sequence[tuple[str, str]]) -> str:
    result = event_id
    for old, new in replacements:
        if old:
            result = result.replace(old, new)
    return result


def merge_hazop_event_mode_bindings(
    campaign_result: Mapping[str, Any],
    base_binding: Mapping[str, Any],
    extension_binding: Mapping[str, Any] | None = None,
    *,
    provider_worklist: Mapping[str, Any] | None = None,
    event_id_replacements: Sequence[tuple[str, str]] = (),
    overlap_policy: str = "error",
) -> dict[str, Any]:
    """Return a canonical audit for explicitly merged base/extension rows.

    Extension rows are allowed only for event IDs not already supplied by the
    base record.  By default, if two records describe the same event the
    operation fails.  ``overlap_policy='base_wins'`` is an explicit escape for
    an extension export that is known to contain a copy of the base rows; the
    skipped count is retained in the audit metadata.  Replacement pairs are
    literal and are recorded in the output so a path normalization is
    auditable.
    """
    if not isinstance(campaign_result, Mapping):
        raise TypeError("campaign_result must be a mapping")
    if not isinstance(base_binding, Mapping):
        raise TypeError("base_binding must be a mapping")
    if extension_binding is not None and not isinstance(extension_binding, Mapping):
        raise TypeError("extension_binding must be a mapping or None")
    if overlap_policy not in {"error", "base_wins"}:
        raise ValueError("overlap_policy must be 'error' or 'base_wins'")

    merged_by_id: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    skipped_extension_overlap_count = 0
    source_rows = (("base", base_binding),)
    if extension_binding is not None:
        source_rows += (("extension", extension_binding),)
    for source_name, record in source_rows:
        for index, raw in enumerate(_binding_rows(record, source_name)):
            original_id = _event_id(raw, f"{source_name}[{index}]")
            row = deepcopy(raw)
            row["event_id"] = _rewrite_event_id(original_id, event_id_replacements)
            event_id = row["event_id"]
            if event_id in merged_by_id:
                if source_name == "extension" and overlap_policy == "base_wins":
                    skipped_extension_overlap_count += 1
                    continue
                previous = sources[event_id]
                raise ValueError(
                    f"duplicate explicit HAZOP event binding after normalization: "
                    f"{event_id} ({previous} and {source_name})"
                )
            merged_by_id[event_id] = row
            sources[event_id] = source_name

    audit = audit_hazop_event_mode_binding(
        campaign_result,
        provider_worklist=provider_worklist,
        mode_bindings={"bindings": list(merged_by_id.values())},
    )
    audit = deepcopy(audit)
    audit["merge"] = {
        "schema_version": SCHEMA,
        "base_event_count": sum(1 for source in sources.values() if source == "base"),
        "extension_event_count": sum(1 for source in sources.values() if source == "extension"),
        "merged_event_count": len(merged_by_id),
        "overlap_policy": overlap_policy,
        "skipped_extension_overlap_count": skipped_extension_overlap_count,
        "event_id_replacements": [
            {"from": old, "to": new} for old, new in event_id_replacements
        ],
        "source_by_event_id": dict(sorted(sources.items())),
        "duplicate_policy": "reject_duplicate_event_ids_after_normalization",
        "mode_inference_performed": False,
        "scenario_inference_performed": False,
        "frequency_inference_performed": False,
        "facility_qra_promotion": False,
    }
    return audit


__all__ = ["SCHEMA", "merge_hazop_event_mode_bindings"]
