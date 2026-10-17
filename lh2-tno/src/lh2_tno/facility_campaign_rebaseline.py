"""Explicitly rebaseline a diagnostic facility campaign to new packet digests.

The facility campaign is a join of provider packets and a reviewed frequency
catalogue.  Re-exporting the provider model can change result digests without
changing event identity.  This module verifies the identity join, records the
old and new digest maps, and keeps all promotion gates closed.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "prism.native_external_facility_campaign_rebaseline.v1"
_DIGEST = re.compile(r"^[0-9a-fA-F]{64}$")


class FacilityCampaignRebaselineError(ValueError):
    """Raised when the two campaign records cannot be safely joined."""


def _read_json(path: str | Path) -> dict[str, Any]:
    import json

    source = Path(path).resolve()
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise FacilityCampaignRebaselineError(f"invalid campaign verification JSON: {source}") from error
    if not isinstance(value, Mapping):
        raise FacilityCampaignRebaselineError("campaign verification must be an object")
    return dict(value)


def _digest(value: Any, field: str) -> str:
    text = str(value or "")
    if not _DIGEST.fullmatch(text):
        raise FacilityCampaignRebaselineError(f"{field} must be a 64-character SHA-256 digest")
    return text.lower()


def _rows(
    value: Mapping[str, Any],
    label: str,
    *,
    source_digest: str | None = None,
) -> dict[str, dict[str, Any]]:
    rows = value.get("packet_digests")
    if not isinstance(rows, list) or not rows:
        raise FacilityCampaignRebaselineError(f"{label}.packet_digests must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise FacilityCampaignRebaselineError(f"{label}.packet_digests[{index}] must be an object")
        event_id = raw.get("event_id")
        if not isinstance(event_id, str) or not event_id or event_id in result:
            raise FacilityCampaignRebaselineError(f"{label} has invalid or duplicate event_id at {index}")
        result_row = dict(raw)
        if result_row.get("provider_source_digest") is None:
            if source_digest is None:
                raise FacilityCampaignRebaselineError(
                    f"{label}.{event_id}.provider_source_digest is missing; provide the campaign source digest"
                )
            result_row["provider_source_digest"] = source_digest
        for field in ("provider_source_digest", "provider_result_digest"):
            _digest(result_row.get(field), f"{label}.{event_id}.{field}")
        result[event_id] = result_row
    return result


def _identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    port_ids = row.get("port_ids")
    if isinstance(port_ids, list):
        ports: tuple[Any, ...] = tuple(port_ids)
    else:
        ports = (row.get("port_id"),)
    return (
        row.get("event_id"),
        row.get("component_id"),
        ports,
        row.get("event_kind"),
        row.get("release_kind"),
    )


def _summary(value: Mapping[str, Any], source: str | None) -> dict[str, Any]:
    fields = (
        "status",
        "event_count",
        "case_count",
        "executed_case_count",
        "uncomputed_case_count",
        "failed_case_count",
        "operator_limited_case_count",
        "withheld_case_count",
        "risk_atom_count",
        "facility_total_risk_available",
        "facility_qra_claim",
        "provider_packet_promoted",
        "physical_validation_claim",
        "conditional_diagnostic_facility_risk_available",
        "frequency_scenario_count",
        "campaign_elapsed_ms",
    )
    return {"record": source, **{field: copy.deepcopy(value.get(field)) for field in fields}}


def rebaseline_facility_campaign(
    previous: Mapping[str, Any] | str | Path,
    current: Mapping[str, Any] | str | Path,
    *,
    acknowledged: bool = False,
    previous_source_digest: str | None = None,
    current_source_digest: str | None = None,
) -> dict[str, Any]:
    """Return a digest-bound diagnostic rebaseline report.

    The explicit acknowledgement is required whenever a current campaign is
    substituted for a stored campaign.  The function never changes frequency,
    provider qualification, physical validation, or facility-QRA flags.
    """
    if not acknowledged:
        raise FacilityCampaignRebaselineError(
            "explicit acknowledgement is required to rebaseline a facility campaign"
        )
    if isinstance(previous, (str, Path)):
        old = _read_json(previous)
        old_source = str(Path(previous).resolve())
    else:
        old = dict(previous)
        old_source = None
    if isinstance(current, (str, Path)):
        new = _read_json(current)
        new_source = str(Path(current).resolve())
    else:
        new = dict(current)
        new_source = None
    old_rows = _rows(old, "previous", source_digest=previous_source_digest)
    new_rows = _rows(new, "current", source_digest=current_source_digest)
    if set(old_rows) != set(new_rows):
        raise FacilityCampaignRebaselineError(
            "previous/current event sets differ; no campaign rebinding is allowed"
        )
    changed_rows: list[dict[str, Any]] = []
    for event_id in sorted(old_rows):
        previous_row = old_rows[event_id]
        current_row = new_rows[event_id]
        if _identity(previous_row) != _identity(current_row):
            raise FacilityCampaignRebaselineError(
                f"event identity changed for {event_id}; no campaign rebinding is allowed"
            )
        previous_source = _digest(previous_row["provider_source_digest"], "previous source digest")
        previous_result = _digest(previous_row["provider_result_digest"], "previous result digest")
        current_source = _digest(current_row["provider_source_digest"], "current source digest")
        current_result = _digest(current_row["provider_result_digest"], "current result digest")
        changed_rows.append({
            "event_id": event_id,
            "identity": {
                "component_id": current_row.get("component_id"),
                "port_id": current_row.get("port_id"),
                "port_ids": current_row.get("port_ids"),
                "event_kind": current_row.get("event_kind"),
                "release_kind": current_row.get("release_kind"),
            },
            "previous_provider_source_digest": previous_source,
            "current_provider_source_digest": current_source,
            "previous_provider_result_digest": previous_result,
            "current_provider_result_digest": current_result,
            "source_digest_changed": previous_source != current_source,
            "result_digest_changed": previous_result != current_result,
            "current_termination_basis": current_row.get("termination_basis"),
            "current_duration_s": current_row.get("duration_s"),
        })
    return {
        "schema_version": SCHEMA,
        "status": "CAMPAIGN_REBASELINE_APPLIED_DIAGNOSTIC",
        "acknowledged": True,
        "previous": _summary(old, old_source),
        "current": _summary(new, new_source),
        "event_count": len(changed_rows),
        "identity_match_count": len(changed_rows),
        "digest_comparison": {
            "source_digest_changed_count": sum(row["source_digest_changed"] for row in changed_rows),
            "result_digest_changed_count": sum(row["result_digest_changed"] for row in changed_rows),
            "rows": changed_rows,
        },
        "promotion": {
            "campaign_rebaseline_applied": True,
            "authoritative_union_rebound": False,
            "provider_packet_promoted": False,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
            "facility_qra_allowed": False,
            "slabx_lh2_modified": False,
        },
        "interpretation": (
            "The current campaign matches the previous event/component/port identity set and may be used as a "
            "digest-rebased diagnostic record. Previous digests remain preserved; no provider qualification or "
            "facility-QRA promotion is inferred."
        ),
    }


__all__ = ["SCHEMA", "FacilityCampaignRebaselineError", "rebaseline_facility_campaign"]
