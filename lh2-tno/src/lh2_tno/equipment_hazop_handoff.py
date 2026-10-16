"""Bind a generic equipment-twin state frame to the HAZOP selector.

This module closes the explicit qualitative handoff from an equipment manifest
and measured/predicted process state to the mode-specific HAZOP table.  It does
not create a release, a frequency, a SLABx-LH2 result, or a facility-QRA value;
those remain downstream contracts owned by the equipment provider and the
facility campaign bridge.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

from .contracts import canonical_digest
from .equipment_manifest import EquipmentManifest, audit_manifest
from .observed_hazop_runtime import audit_observed_hazop_runtime


SCHEMA = "prism.equipment_hazop_mode_handoff.v1"


class EquipmentHazopHandoffError(ValueError):
    """Raised when the equipment-to-HAZOP handoff cannot be audited."""


def build_equipment_hazop_mode_handoff(
    manifest: EquipmentManifest | Mapping[str, Any],
    runtime_frames: Mapping[str, Any],
    hazop_table_set: Mapping[str, Any],
    *,
    now_s: float,
) -> dict[str, Any]:
    """Audit one facility-neutral equipment state-to-HAZOP handoff.

    Every runtime component must be declared by the manifest.  A complete
    facility handoff additionally requires one frame for every declared
    component and an executable outdoor manifest.  Partial or unresolved
    provider exports remain visible as partial/blocked results; no component
    or operating mode is inferred from a sensor tag.
    """
    try:
        manifest_obj = (
            manifest
            if isinstance(manifest, EquipmentManifest)
            # The public boundary is JSON-compatible, so parse through the
            # same path as ``EquipmentManifest.from_json``.  This preserves
            # tuple contracts while accepting JSON arrays from connectors.
            else EquipmentManifest.model_validate_json(
                json.dumps(dict(manifest), allow_nan=False)
            )
        )
    except (TypeError, ValueError) as error:
        raise EquipmentHazopHandoffError(f"invalid equipment manifest: {error}") from error
    if not isinstance(runtime_frames, Mapping):
        raise EquipmentHazopHandoffError("runtime_frames must be an object")
    if not isinstance(hazop_table_set, Mapping):
        raise EquipmentHazopHandoffError("hazop_table_set must be an object")
    frames = runtime_frames.get("frames")
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes)) or not frames:
        raise EquipmentHazopHandoffError("runtime_frames.frames must be a non-empty array")
    frame_ids: list[str] = []
    for index, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            raise EquipmentHazopHandoffError(f"runtime_frames.frames[{index}] must be an object")
        component_id = frame.get("component_id")
        if not isinstance(component_id, str) or not component_id.strip():
            raise EquipmentHazopHandoffError(
                f"runtime_frames.frames[{index}].component_id must be non-empty"
            )
        frame_ids.append(component_id.strip())
    if len(set(frame_ids)) != len(frame_ids):
        raise EquipmentHazopHandoffError("runtime_frames must contain one frame per component_id")

    manifest_ids = {component.id for component in manifest_obj.components}
    frame_id_set = set(frame_ids)
    unknown = sorted(frame_id_set - manifest_ids)
    missing = sorted(manifest_ids - frame_id_set)
    declared_facility_id = runtime_frames.get("facility_id")
    facility_id_mismatch = (
        declared_facility_id is not None
        and declared_facility_id != manifest_obj.facility_id
    )
    manifest_audit = audit_manifest(manifest_obj)
    try:
        hazop_audit = audit_observed_hazop_runtime(
            runtime_frames,
            hazop_table_set,
            now_s=now_s,
        )
    except (TypeError, ValueError) as error:
        raise EquipmentHazopHandoffError(f"HAZOP runtime audit failed: {error}") from error

    reasons: list[str] = []
    if manifest_obj.environment != "outdoor":
        reasons.append("declared equipment environment is outside the outdoor LH2 scope")
    if unknown:
        reasons.append("runtime contains components absent from equipment manifest: " + ", ".join(unknown))
    if facility_id_mismatch:
        reasons.append("runtime facility_id does not match equipment manifest")
    if missing:
        reasons.append("manifest components have no runtime frame: " + ", ".join(missing))
    if manifest_audit.get("status") != "EXECUTABLE":
        reasons.extend(
            f"equipment manifest: {reason}"
            for reason in manifest_audit.get("blocking_reasons", [])
        )
    if hazop_audit.get("status") != "OBSERVED_HAZOP_MODE_SCENARIOS_SELECTED":
        reasons.extend(
            f"HAZOP runtime: {reason}"
            for reason in hazop_audit.get("blocking_reasons", [])
        )

    if unknown or facility_id_mismatch or hazop_audit.get("status") == "OBSERVED_HAZOP_MODE_AUDIT_BLOCKED":
        status = "EQUIPMENT_HAZOP_MODE_HANDOFF_BLOCKED"
    elif missing or manifest_audit.get("status") != "EXECUTABLE":
        status = "EQUIPMENT_HAZOP_MODE_HANDOFF_PARTIAL"
    else:
        status = "EQUIPMENT_HAZOP_MODE_HANDOFF_READY"

    return {
        "schema_version": SCHEMA,
        "status": status,
        "facility_id": manifest_obj.facility_id,
        "manifest_digest": manifest_obj.digest(),
        "runtime_frames_digest": canonical_digest(dict(runtime_frames)),
        "hazop_table_set_digest": canonical_digest(dict(hazop_table_set)),
        "component_coverage": {
            "manifest_component_count": len(manifest_ids),
            "runtime_frame_count": len(frame_ids),
            "runtime_component_ids": sorted(frame_id_set),
            "missing_manifest_component_ids": missing,
            "unknown_runtime_component_ids": unknown,
            "exact_component_set": not missing and not unknown,
        },
        "equipment_manifest_audit": manifest_audit,
        "hazop_runtime_audit": hazop_audit,
        "blocking_reasons": list(dict.fromkeys(reasons)),
        "policy": {
            "operating_mode_taken_from_explicit_runtime_input": True,
            "operating_mode_inferred": False,
            "component_identity_inferred": False,
            "release_created": False,
            "frequency_inference_performed": False,
            "sensor_frequency_learning_used": False,
            "slabx_lh2_executed": False,
            "facility_qra_claim": False,
            "physical_validation_claim": False,
            "downstream_requirement": (
                "selected HAZOP scenarios require an explicit provider release boundary, "
                "literature frequency, and the PRISM/SLABx-LH2 consequence campaign"
            ),
        },
        "interpretation": (
            "The equipment model supplied explicit component identity, state frames, "
            "and operating mode to the HAZOP selector. This handoff is qualitative "
            "and does not substitute for a provider release or frequency packet."
        ),
    }


__all__ = ["SCHEMA", "EquipmentHazopHandoffError", "build_equipment_hazop_mode_handoff"]
