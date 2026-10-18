"""Audit external accident responses without qualifying or promoting them.

The workspace scanner can find provider-response files, but a response file is
not automatically a qualified release packet.  This module makes the missing
qualification, origin, termination, and mass-ledger fields explicit for each
response.  It never infers a missing field from a model name, a normal-state
calculation, or a termination horizon.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
from pathlib import Path
from typing import Any


AUDIT_SCHEMA = "prism.external_provider_response_gap_audit.v1"
SCAN_SCHEMAS = {
    "prism.provider_artifact_audit.v1",
    "prism.provider_artifact_roots_audit.v1",
}
_STRICT_TERMINATION_BASES = {
    "reviewed_isolation_success",
    "inventory_depletion",
    "emergency_relief_discharge",
    "two_sided_rupture",
    "pressure_equalization",
}


class ExternalProviderResponseGapAuditError(ValueError):
    """Raised when an external provider-response scan is malformed."""


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExternalProviderResponseGapAuditError(f"invalid {label}: {path}") from error
    if not isinstance(value, Mapping):
        raise ExternalProviderResponseGapAuditError(f"{label} must be an object")
    return dict(value)


def _finite(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_external_provider_response_gaps(
    scan_record: Mapping[str, Any] | str | Path,
    *,
    root_label: str,
) -> dict[str, Any]:
    """Return a per-response gap ledger for one scanned external workspace.

    ``scan_record`` must be the output of
    :func:`audit_provider_artifact_roots`.  The selected root must contain
    provider-response artifact rows.  A missing or incomplete field is
    reported as a blocker; no value is filled in from another artifact.
    """
    if isinstance(scan_record, (str, Path)):
        scan = _load_json(Path(scan_record), "provider artifact scan")
    elif isinstance(scan_record, Mapping):
        scan = dict(scan_record)
    else:
        raise ExternalProviderResponseGapAuditError("scan_record must be an object or JSON path")
    if scan.get("schema_version") not in SCAN_SCHEMAS:
        raise ExternalProviderResponseGapAuditError(
            "scan_record schema_version must be one of "
            + ", ".join(sorted(SCAN_SCHEMAS))
        )
    roots = scan.get("roots")
    if not isinstance(roots, Mapping) or root_label not in roots:
        raise ExternalProviderResponseGapAuditError(
            f"scan_record has no root labelled {root_label!r}"
        )
    root = roots[root_label]
    if not isinstance(root, Mapping):
        raise ExternalProviderResponseGapAuditError("selected scan root must be an object")
    source_root = root.get("source_root_provided")
    if not isinstance(source_root, str) or not source_root.strip():
        raise ExternalProviderResponseGapAuditError("selected root has no source_root_provided")
    artifacts = root.get("artifacts")
    if not isinstance(artifacts, list):
        raise ExternalProviderResponseGapAuditError("selected root artifacts must be a list")

    rows: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, Mapping):
            raise ExternalProviderResponseGapAuditError(f"artifacts[{index}] must be an object")
        if artifact.get("kind") != "provider_response":
            continue
        relative = artifact.get("file")
        if not isinstance(relative, str) or not relative.strip():
            raise ExternalProviderResponseGapAuditError(
                f"artifacts[{index}].file must be a non-empty string"
            )
        path = (Path(source_root) / relative).resolve()
        try:
            path.relative_to(Path(source_root).resolve())
        except ValueError as error:
            raise ExternalProviderResponseGapAuditError(
                f"provider-response path escapes selected root: {relative}"
            ) from error
        payload = _load_json(path, "provider response")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ExternalProviderResponseGapAuditError(
                f"provider response data must be an object: {relative}"
            )
        meta = data.get("provider_meta")
        meta = meta if isinstance(meta, Mapping) else {}
        qualification = payload.get("provider_qualification")
        qualification_present = isinstance(qualification, Mapping)
        origin = payload.get("input_origin", data.get("input_origin"))
        evidence_status = payload.get("evidence_status", data.get("evidence_status"))
        termination_basis = data.get("termination_basis")
        initial_mass = meta.get("initial_mass_kg", data.get("initial_available_mass_kg"))
        final_mass = meta.get("final_mass_kg", data.get("final_available_mass_kg"))
        residual_mass = meta.get("residual_mass_kg", data.get("mass_residual_kg"))
        cumulative_mass = data.get("cumulative_mass_out_kg")
        mass_ledger_present = all(
            _finite(value)
            for value in (initial_mass, final_mass, residual_mass, cumulative_mass)
        )
        blockers: list[str] = []
        if not qualification_present:
            blockers.append("no prism.provider_qualification_evidence.v1 sidecar")
        if not isinstance(origin, str) or not origin.strip():
            blockers.append("input_origin is missing from the provider response")
        if not isinstance(evidence_status, str) or not evidence_status.strip():
            blockers.append("evidence_status is missing from the provider response")
        if termination_basis not in _STRICT_TERMINATION_BASES:
            blockers.append(
                "termination basis is not a strict provider closure: "
                + str(termination_basis)
            )
        if not mass_ledger_present:
            blockers.append("complete initial/final/cumulative/residual mass ledger is missing")
        rows.append({
            "file": relative,
            "sha256": _sha256(path),
            "provider_export_schema": payload.get("provider_export_schema"),
            "provider_model": payload.get("provider_model"),
            "provider_source_digest": payload.get("provider_source_digest"),
            "event_id": data.get("event_id"),
            "component_id": data.get("component_id"),
            "port_id": data.get("port_id"),
            "termination_basis": termination_basis,
            "duration_s": data.get("duration_s"),
            "input_origin": origin,
            "evidence_status": evidence_status,
            "qualification_sidecar_present": qualification_present,
            "mass_ledger_present": mass_ledger_present,
            "mass_ledger": {
                "initial_mass_kg": initial_mass,
                "final_mass_kg": final_mass,
                "cumulative_mass_out_kg": cumulative_mass,
                "residual_mass_kg": residual_mass,
            },
            "strict_termination_candidate": termination_basis in _STRICT_TERMINATION_BASES,
            "promotion_allowed": False,
            "blocking_reasons": blockers,
        })

    termination_counts: dict[str, int] = {}
    for row in rows:
        basis = str(row["termination_basis"])
        termination_counts[basis] = termination_counts.get(basis, 0) + 1
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": "PROVIDER_RESPONSE_GAP_AUDIT_DIAGNOSTIC_ONLY",
        "root_label": root_label,
        "source_root": source_root,
        "provider_response_count": len(rows),
        "strict_termination_candidate_count": sum(
            row["strict_termination_candidate"] for row in rows
        ),
        "mass_ledger_present_count": sum(row["mass_ledger_present"] for row in rows),
        "qualification_sidecar_count": sum(
            row["qualification_sidecar_present"] for row in rows
        ),
        "origin_metadata_missing_count": sum(
            not isinstance(row["input_origin"], str) or not row["input_origin"].strip()
            for row in rows
        ),
        "termination_basis_counts": termination_counts,
        "rows": rows,
        "promotion": {
            "provider_packet_promoted": False,
            "frequency_inference_performed": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
        },
        "policy": {
            "missing_fields_are_not_inferred": True,
            "normal_state_or_model_prediction_is_not_qualification": True,
            "frequency_is_not_learned_from_provider_response": True,
            "facility_ir_fn_remains_withheld": True,
        },
    }


__all__ = [
    "AUDIT_SCHEMA",
    "ExternalProviderResponseGapAuditError",
    "audit_external_provider_response_gaps",
]
