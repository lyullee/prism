"""Audit an external LH2 equipment model without promoting its plant data.

The external digital-twin project has useful tank geometry and state-model
inputs, while its procedure register and reconstructed observations do not yet
constitute an accident release packet.  This module preserves that boundary
in a portable PRISM record: state-model readiness may be reported, but release
time, isolation, inventory depletion, frequency, and facility QRA stay closed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


AUDIT_SCHEMA = "prism.external_equipment_model_audit.v1"


class ExternalEquipmentModelAuditError(ValueError):
    """Raised when an external equipment audit input is malformed."""


def _load(path: str | Path, label: str) -> tuple[Path, dict[str, Any]]:
    resolved = Path(path).resolve()
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExternalEquipmentModelAuditError(f"invalid {label}: {resolved}") from error
    if not isinstance(value, Mapping):
        raise ExternalEquipmentModelAuditError(f"{label} must be an object")
    return resolved, dict(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source(path: Path, label: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
    }


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExternalEquipmentModelAuditError(f"{label} must be an object")
    return value


def audit_external_equipment_model(
    assets_path: str | Path,
    private_inputs_audit_path: str | Path,
    connection_event_register_path: str | Path,
    observation_judgements_path: str | Path,
) -> dict[str, Any]:
    """Build a fail-closed readiness record from four external JSON ledgers."""
    assets_file, assets = _load(assets_path, "center assets")
    private_file, private = _load(private_inputs_audit_path, "private inputs audit")
    events_file, events = _load(connection_event_register_path, "connection event register")
    observations_file, observations = _load(observation_judgements_path, "observation judgements")

    asset_rows = assets.get("assets")
    audit_rows = private.get("audits")
    if not isinstance(asset_rows, list) or not isinstance(audit_rows, list):
        raise ExternalEquipmentModelAuditError("assets and private audit must contain lists")
    audit_by_asset = {
        str(row.get("asset_id")): row
        for row in audit_rows
        if isinstance(row, Mapping) and row.get("asset_id")
    }
    asset_summaries: list[dict[str, Any]] = []
    for index, raw in enumerate(asset_rows):
        asset = _mapping(raw, f"assets[{index}]")
        asset_id = str(asset.get("asset_id") or f"asset-{index}")
        private_row = audit_by_asset.get(asset_id, {})
        ready = private_row.get("ready") is True
        asset_summaries.append({
            "asset_id": asset_id,
            "component_model": asset.get("component_model"),
            "target_component_model": asset.get("target_component_model"),
            "ready_for_state_model_input": ready,
            "private_audit_status": private_row.get("issues") or [],
            "asset_status": asset.get("status"),
        })

    valve_events = events.get("valve_events")
    valve_events = valve_events if isinstance(valve_events, list) else []
    physical_time_count = sum(
        1 for row in valve_events
        if isinstance(row, Mapping) and isinstance(row.get("physical_time_s"), (int, float))
    )
    feedback_count = sum(
        1 for row in valve_events
        if isinstance(row, Mapping) and isinstance(row.get("event_feedback_channel"), str)
        and bool(row.get("event_feedback_channel"))
    )
    dead_volume = events.get("dead_volume")
    dead_volume = dead_volume if isinstance(dead_volume, Mapping) else {}
    actual_route_length = dead_volume.get("actual_installed_route_length_m")
    source_policy = str(events.get("source_policy") or "")
    physical_time_status = events.get("physical_time_status")

    time_alignment = observations.get("time_alignment")
    time_alignment = time_alignment if isinstance(time_alignment, Mapping) else {}
    provenance = observations.get("source_provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    release_policy = observations.get("release_policy")
    release_policy = release_policy if isinstance(release_policy, Mapping) else {}
    raw_historian_count = provenance.get("verified_raw_historian_session_count")
    command_timestamp = time_alignment.get("command_timestamp_available") is True
    ready_count = sum(1 for row in asset_summaries if row["ready_for_state_model_input"])
    asset_count = len(asset_summaries)
    release_boundary_ready = bool(
        physical_time_count > 0
        and feedback_count > 0
        and command_timestamp
        and isinstance(raw_historian_count, int)
        and raw_historian_count > 0
        and actual_route_length is not None
    )
    blockers = [
        "external_state_model_is_center_referenced_not_general_facility_identity",
        "procedure_events_are_not_accident_release_packets",
        "physical_event_time_unassigned" if physical_time_status != "assigned" else None,
        "verified_raw_historian_sessions_absent" if raw_historian_count != 0 else None,
        "command_timestamps_absent" if not command_timestamp else None,
        "event_feedback_channels_absent" if feedback_count == 0 else None,
        "installed_route_length_unresolved" if actual_route_length is None else None,
        "accident_release_boundary_not_released" if not release_boundary_ready else None,
        "frequency_inference_is_prohibited",
    ]
    blockers = [item for item in blockers if item is not None]
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": (
            "STATE_MODEL_INPUTS_READY_RELEASE_BOUNDARY_UNVERIFIED"
            if ready_count > 0 and not release_boundary_ready
            else "EXTERNAL_EQUIPMENT_MODEL_REVIEW_REQUIRED"
        ),
        "scope": "external_center_model_input_audit_for_general_lh2_adapter",
        "state_model_ready_asset_count": ready_count,
        "asset_count": asset_count,
        "assets": asset_summaries,
        "event_register": {
            "physical_time_status": physical_time_status,
            "valve_event_count": len(valve_events),
            "physical_time_assigned_event_count": physical_time_count,
            "event_feedback_channel_count": feedback_count,
            "installed_route_length_m": actual_route_length,
            "official_promotion_allowed": events.get("official_promotion_allowed"),
            "fitting": events.get("fitting"),
            "source_policy": source_policy,
        },
        "observation_provenance": {
            "verified_raw_historian_session_count": raw_historian_count,
            "explicit_reconstructed_session_count": provenance.get("explicit_reconstructed_session_count"),
            "command_timestamp_available": command_timestamp,
            "final_accuracy_use_allowed": observations.get("calibration", {}).get("final_accuracy_use_allowed")
            if isinstance(observations.get("calibration"), Mapping)
            else None,
            "official_94_percent_accuracy_decision_allowed": release_policy.get(
                "official_94_percent_accuracy_decision_allowed"
            ),
        },
        "promotion_gates": {
            "state_model_input_allowed": ready_count > 0,
            "accident_release_packet_allowed": False,
            "provider_qualification_allowed": False,
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "promotion_allowed": False,
        },
        "physical_validation_claim": False,
        "full_chain_validation_claim": False,
        "accident_release_validation_claim": False,
        "frequency_inference_performed": False,
        "facility_qra_claim": False,
        "blocking_reasons": blockers,
        "required_next_evidence": [
            "general-facility asset and P&ID port identity crosswalk",
            "raw historian/DCS/PLC export with calibration and timestamp provenance",
            "provider accident release packet with start, termination, isolation, inventory, and mass balance",
            "independent holdout comparison of the equipment release boundary",
        ],
        "policy": {
            "center_model_state_inputs_are_not_general_facility_identity": True,
            "procedure_intent_is_not_accidental_release": True,
            "reconstructed_time_series_is_not_raw_historian": True,
            "no_sensor_inverse_leak_or_frequency_inference": True,
            "no_automatic_provider_or_facility_qra_promotion": True,
        },
        "sources": [
            _source(assets_file, "external center assets", assets),
            _source(private_file, "external private inputs audit", private),
            _source(events_file, "external connection event register", events),
            _source(observations_file, "external observation judgements", observations),
        ],
    }


__all__ = [
    "AUDIT_SCHEMA",
    "ExternalEquipmentModelAuditError",
    "audit_external_equipment_model",
]
