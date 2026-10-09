"""Attach an externally resolved compressible gas plane to a PRISM packet.

The adapter is intentionally a boundary utility.  It does not solve a nozzle,
expand a jet, estimate entrainment, or change the provider's release history.
An external near-field provider must export a conservation-closed carrier
section and identify the exact gas packet it consumed.  PRISM then validates
the section against the packet's interval mass flow before downstream models
can consume it.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from .equipment_boundary import ResolvedGasRelease


COMPRESSIBLE_HANDOFF_SCHEMA = "prism.compressible_plane_handoff.v1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_EVIDENCE_STATUSES = {"qualified_actual", "synthetic_diagnostic", "screening_only"}


class CompressibleHandoffExportError(ValueError):
    """Raised when an external handoff cannot be bound to one gas packet."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompressibleHandoffExportError(f"{field} must be a non-empty string")
    return value.strip()


def _digest(value: Any, field: str) -> str:
    text = _text(value, field)
    if not _DIGEST.fullmatch(text):
        raise CompressibleHandoffExportError(f"{field} must be a lowercase SHA-256 digest")
    return text


def attach_compressible_plane_handoff(
    packet: Mapping[str, Any] | ResolvedGasRelease,
    export: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a validated packet and an audit record for one external handoff.

    ``export`` is the separate provider artifact with schema
    ``prism.compressible_plane_handoff.v1``.  The original provider result
    digest is retained in the gas packet: the handoff is a downstream provider
    stage and must refer to, rather than rewrite, that exact history.
    """
    if isinstance(packet, ResolvedGasRelease):
        release = packet
    else:
        try:
            # JSON validation intentionally mirrors the packet loader: tuple
            # vectors are accepted from their on-disk JSON array form while
            # arbitrary Python lists are not silently reinterpreted.
            release = ResolvedGasRelease.model_validate_json(
                json.dumps(dict(packet), allow_nan=False)
            )
        except Exception as error:  # pydantic error text is part of the audit
            raise CompressibleHandoffExportError(
                f"upstream gas packet is not a valid ResolvedGasRelease: {error}"
            ) from error
    if not isinstance(export, Mapping):
        raise CompressibleHandoffExportError("compressible handoff export must be an object")
    if export.get("schema_version") != COMPRESSIBLE_HANDOFF_SCHEMA:
        raise CompressibleHandoffExportError(
            f"schema_version must be {COMPRESSIBLE_HANDOFF_SCHEMA}"
        )
    for field in ("component_id", "port_id", "event_id", "handoff_model", "handoff_revision"):
        _text(export.get(field), field)
    if export["component_id"] != release.component_id:
        raise CompressibleHandoffExportError("handoff component_id does not match gas packet")
    if export["port_id"] != release.port_id:
        raise CompressibleHandoffExportError("handoff port_id does not match gas packet")
    if export["event_id"] != release.event_id:
        raise CompressibleHandoffExportError("handoff event_id does not match gas packet")
    if export["upstream_provider_result_digest"] != release.provider_result_digest:
        raise CompressibleHandoffExportError(
            "handoff must name the exact upstream provider_result_digest"
        )
    if export["upstream_provider_source_digest"] != release.provider_source_digest:
        raise CompressibleHandoffExportError(
            "handoff must name the exact upstream provider_source_digest"
        )
    upstream_result = _digest(export["upstream_provider_result_digest"], "upstream_provider_result_digest")
    upstream_source = _digest(export["upstream_provider_source_digest"], "upstream_provider_source_digest")
    handoff_source = _digest(export["handoff_provider_source_digest"], "handoff_provider_source_digest")
    handoff_result = _digest(export["handoff_provider_result_digest"], "handoff_provider_result_digest")
    evidence_status = _text(export.get("evidence_status"), "evidence_status")
    if evidence_status not in _EVIDENCE_STATUSES:
        raise CompressibleHandoffExportError(
            f"evidence_status must be one of {sorted(_EVIDENCE_STATUSES)}"
        )
    provenance = _text(export.get("scenario_provenance"), "scenario_provenance")
    handoff_payload = export.get("handoff")
    if not isinstance(handoff_payload, Mapping):
        raise CompressibleHandoffExportError("handoff must be an object")
    try:
        # Import locally to keep this boundary module's public dependency small.
        from .equipment_boundary import CompressibleGasPlaneHandoff

        handoff = CompressibleGasPlaneHandoff.model_validate_json(
            json.dumps(dict(handoff_payload), allow_nan=False)
        )
    except Exception as error:
        raise CompressibleHandoffExportError(f"provider handoff failed contract validation: {error}") from error
    if handoff.states and len(handoff.states) != len(release.steps):
        raise CompressibleHandoffExportError(
            "provider handoff state count must equal the upstream gas interval count"
        )

    payload = release.model_dump(mode="json")
    payload["compressible_plane_handoff"] = handoff.model_dump(mode="json")
    try:
        validated = ResolvedGasRelease.model_validate_json(
            json.dumps(payload, allow_nan=False)
        )
    except Exception as error:
        raise CompressibleHandoffExportError(
            f"handoff does not close against the upstream gas history: {error}"
        ) from error
    audit = {
        "status": "COMPRESSIBLE_PLANE_HANDOFF_ATTACHED_AND_VALIDATED",
        "schema_version": COMPRESSIBLE_HANDOFF_SCHEMA,
        "component_id": validated.component_id,
        "port_id": validated.port_id,
        "event_id": validated.event_id,
        "upstream_provider_source_digest": upstream_source,
        "upstream_provider_result_digest": upstream_result,
        "handoff_provider_source_digest": handoff_source,
        "handoff_provider_result_digest": handoff_result,
        "handoff_model": export["handoff_model"],
        "handoff_revision": export["handoff_revision"],
        "evidence_status": evidence_status,
        "scenario_provenance": provenance,
        "handoff_state_count": len(handoff.states) if handoff.states else 1,
        "upstream_interval_count": len(validated.steps),
        "provider_packet_qualified": False,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "interpretation": (
            "The external handoff is conservation-checked and bound to one exact provider history. "
            "This command does not qualify the provider, assign frequency, or promote facility IR/F-N."
        ),
    }
    return validated.model_dump(mode="json"), audit


__all__ = [
    "COMPRESSIBLE_HANDOFF_SCHEMA",
    "CompressibleHandoffExportError",
    "attach_compressible_plane_handoff",
]
