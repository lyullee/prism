"""Promote a strict resolved release plus qualification sidecar to campaign evidence.

The provider export adapter validates a live provider response.  This module
covers the reproducible file boundary used when a provider sends PRISM a
saved ``prism.resolved_release.v1`` (or two-sided release-set) packet and a
separate ``prism.provider_qualification_evidence.v1`` record.  It never
assigns a frequency and it rejects packets marked as synthetic input.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .campaign import ProviderPacketEvidence
from .provider_release import (
    ProviderReleaseContractError,
    load_provider_release,
    load_provider_release_set,
)


PROVIDER_QUALIFICATION_SCHEMA = "prism.provider_qualification_evidence.v1"
PROMOTION_SCHEMA = "prism.provider_packet_evidence.v1"


class ProviderPacketPromotionError(ValueError):
    """Raised when saved provider evidence cannot be promoted."""


def _object(value: Mapping[str, Any] | str | Path, label: str) -> Mapping[str, Any]:
    if isinstance(value, (str, Path)):
        import json

        try:
            value = json.loads(Path(value).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderPacketPromotionError(f"cannot read {label}: {error}") from error
    if not isinstance(value, Mapping):
        raise ProviderPacketPromotionError(f"{label} must be a JSON object")
    return value


def build_provider_packet_evidence_from_records(
    release_record: Mapping[str, Any] | str | Path,
    qualification_record: Mapping[str, Any] | str | Path,
) -> ProviderPacketEvidence:
    """Validate saved records and return exact campaign qualification evidence."""

    release_payload = _object(release_record, "release_record")
    qualification_payload = _object(qualification_record, "qualification_record")
    if isinstance(qualification_payload.get("provider_qualification"), Mapping):
        qualification_payload = qualification_payload["provider_qualification"]
    try:
        if release_payload.get("provider_export_schema") == "prism.resolved_release_set.v1":
            release = load_provider_release_set(release_payload)
            packets = tuple(release.releases)
        else:
            release = load_provider_release(release_payload)
            packets = (release,)
    except ProviderReleaseContractError as error:
        raise ProviderPacketPromotionError(str(error)) from error

    if qualification_payload.get("schema_version") != PROVIDER_QUALIFICATION_SCHEMA:
        raise ProviderPacketPromotionError(
            f"qualification schema must be {PROVIDER_QUALIFICATION_SCHEMA}"
        )
    if qualification_payload.get("status") != "qualified_actual":
        raise ProviderPacketPromotionError(
            "only qualification status qualified_actual can be promoted"
        )
    if qualification_payload.get("provider_origin") not in {
        "native_provider",
        "reviewed_actual",
    }:
        raise ProviderPacketPromotionError(
            "qualification provider_origin must identify a native or reviewed actual provider"
        )
    evidence_id = qualification_payload.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        raise ProviderPacketPromotionError("qualification evidence_id is required")
    if any(packet.input_origin == "synthetic" for packet in packets):
        raise ProviderPacketPromotionError(
            "synthetic input-origin packets cannot be promoted to qualified evidence"
        )

    source_digests = tuple(packet.provider_source_digest for packet in packets)
    result_digests = tuple(packet.provider_result_digest for packet in packets)
    declared_sources = qualification_payload.get("provider_source_digests")
    if declared_sources is None:
        declared_source = qualification_payload.get("provider_source_digest")
        if len(packets) != 1 or declared_source != source_digests[0]:
            raise ProviderPacketPromotionError(
                "qualification provider_source_digest disagrees with the release packet"
            )
    elif tuple(declared_sources) != source_digests:
        raise ProviderPacketPromotionError(
            "qualification provider_source_digests disagree with the release packet"
        )
    declared_results = qualification_payload.get("provider_result_digests")
    if declared_results is not None and tuple(declared_results) != result_digests:
        raise ProviderPacketPromotionError(
            "qualification provider_result_digests disagree with the release packet"
        )

    try:
        return ProviderPacketEvidence(
            event_id=release.event_id,
            component_id=release.component_id,
            port_ids=tuple(packet.port_id for packet in packets),
            provider_source_digests=source_digests,
            provider_result_digests=result_digests,
            evidence_id=evidence_id,
        )
    except ValueError as error:
        raise ProviderPacketPromotionError(str(error)) from error


__all__ = [
    "PROMOTION_SCHEMA",
    "PROVIDER_QUALIFICATION_SCHEMA",
    "ProviderPacketPromotionError",
    "build_provider_packet_evidence_from_records",
]
