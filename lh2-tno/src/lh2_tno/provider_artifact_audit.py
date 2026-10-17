"""Audit external digital-twin artifacts without promoting them to QRA inputs.

External equipment projects often export a mixture of provider responses,
verification ledgers, campaign summaries, and supporting source documents.
This module inventories those files and checks whether the artifacts contain the separate qualification
evidence required by PRISM.  It deliberately does not load a release packet,
assign a frequency, or claim physical validation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping


PROVIDER_ARTIFACT_AUDIT_SCHEMA = "prism.provider_artifact_audit.v1"
QUALIFICATION_SCHEMA = "prism.provider_qualification_evidence.v1"

# These files can contain source observations, operating sequences, or model
# validation material.  They are inventoried separately because merely finding
# one must never make it a provider release or a qualification sidecar.
SUPPORTING_EVIDENCE_SUFFIXES = frozenset({
    ".csv",
    ".xlsx",
    ".xls",
    ".pdf",
    ".pptx",
    ".parquet",
    ".h5",
    ".hdf5",
    ".mat",
})


def _contains_qualification(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("schema_version") == QUALIFICATION_SCHEMA:
            return True
        if value.get("status") == "qualified_actual" and value.get("evidence_id"):
            return True
        return any(_contains_qualification(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_qualification(item) for item in value)
    return False


def _bool_field(value: Any, key: str) -> bool:
    if isinstance(value, Mapping):
        if value.get(key) is True:
            return True
        return any(_bool_field(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_bool_field(item, key) for item in value)
    return False


def _artifact_kind(path: Path) -> str:
    name = path.name.casefold()
    if name == "provider_response.json":
        return "provider_response"
    if name == "verification.json" or "verification" in name:
        return "verification"
    if "campaign_result" in name or name == "campaign.json":
        return "campaign_result"
    return "other_json"


def _is_runtime_path(path: Path) -> bool:
    """Return whether a path belongs to a local runtime/cache tree.

    External digital-twin workspaces commonly use names such as
    ``.venv-local`` instead of the conventional ``.venv``.  Package metadata
    inside those trees is not provider evidence and must not change the audit
    counts or qualification status.
    """

    return any(
        part in {".git", "__pycache__"}
        or part.casefold().startswith(".venv")
        or part.casefold() in {"venv", "virtualenv"}
        for part in path.parts
    )


def _read_json(path: Path) -> Any:
    """Read a JSON artifact from common UTF-8 or Korean Windows encodings."""

    raw = path.read_bytes()
    decode_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return json.loads(raw.decode(encoding))
        except UnicodeDecodeError as error:
            decode_error = error
    if decode_error is not None:
        raise decode_error
    raise ValueError(f"unable to decode JSON artifact: {path}")


def _iter_source_files(source_root: Path):
    """Yield files while pruning local runtimes before descending into them."""

    runtime_names = {".git", "__pycache__", "venv", "virtualenv"}
    for directory, dirnames, filenames in os.walk(source_root, topdown=True):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in runtime_names
            and not name.casefold().startswith(".venv")
        ]
        base = Path(directory)
        for filename in filenames:
            yield base / filename


def audit_provider_artifact_root(root: str | Path) -> dict[str, Any]:
    """Inventory JSON artifacts below ``root`` using relative paths only."""
    source_root = Path(root).resolve()
    if not source_root.is_dir():
        return {
            "schema_version": PROVIDER_ARTIFACT_AUDIT_SCHEMA,
            "status": "MISSING_SOURCE_ROOT",
            "source_root_provided": str(root),
            "artifact_count": 0,
            "supporting_file_count": 0,
            "supporting_files": [],
            "blocking_reasons": ["external provider artifact root does not exist"],
        }

    rows: list[dict[str, Any]] = []
    supporting_files: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in sorted(_iter_source_files(source_root)):
        if _is_runtime_path(path):
            continue
        relative = path.relative_to(source_root).as_posix()
        if path.suffix.casefold() != ".json":
            if path.suffix.casefold() in SUPPORTING_EVIDENCE_SUFFIXES:
                try:
                    size_bytes = path.stat().st_size
                except OSError as error:
                    errors.append({"file": relative, "error": str(error)})
                    continue
                supporting_files.append({
                    "file": relative,
                    "suffix": path.suffix.casefold(),
                    "size_bytes": size_bytes,
                    "qualification_evidence_present": False,
                    "provider_release_promoted": False,
                })
            continue
        try:
            payload = _read_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append({"file": relative, "error": str(error)})
            continue
        kind = _artifact_kind(path)
        qualification_present = _contains_qualification(payload)
        physical_validation_claim = _bool_field(payload, "physical_validation_claim")
        qra_claim = _bool_field(payload, "complete_facility_qra_claim")
        rows.append({
            "file": relative,
            "kind": kind,
            "qualification_evidence_present": qualification_present,
            "physical_validation_claim": physical_validation_claim,
            "complete_facility_qra_claim": qra_claim,
            "diagnostic_only": not qualification_present and not physical_validation_claim,
        })

    provider_rows = [row for row in rows if row["kind"] == "provider_response"]
    verification_rows = [row for row in rows if row["kind"] == "verification"]
    qualification_rows = [row for row in rows if row["qualification_evidence_present"]]
    physical_rows = [row for row in rows if row["physical_validation_claim"]]
    qra_rows = [row for row in rows if row["complete_facility_qra_claim"]]
    blockers: list[str] = []
    if not provider_rows:
        blockers.append("no provider_response.json artifact was found")
    if not qualification_rows:
        blockers.append(
            "no prism.provider_qualification_evidence.v1 record was found"
        )
    if not physical_rows:
        blockers.append("no artifact claims independent physical validation")
    if not qra_rows:
        blockers.append("no artifact claims a complete facility QRA")
    if errors:
        blockers.append("one or more JSON artifacts could not be read")
    status = "EXTERNAL_ARTIFACTS_DIAGNOSTIC_ONLY"
    if not rows:
        status = "NO_EXTERNAL_JSON_ARTIFACTS"
    elif qualification_rows and physical_rows and qra_rows and not errors:
        status = "ARTIFACTS_REQUIRE_PRISM_RECONCILIATION"
    return {
        "schema_version": PROVIDER_ARTIFACT_AUDIT_SCHEMA,
        "status": status,
        "source_root_provided": str(root),
        "artifact_count": len(rows),
        "supporting_file_count": len(supporting_files),
        "supporting_files": supporting_files,
        "provider_response_count": len(provider_rows),
        "verification_artifact_count": len(verification_rows),
        "qualification_artifact_count": len(qualification_rows),
        "physical_validation_artifact_count": len(physical_rows),
        "complete_facility_qra_artifact_count": len(qra_rows),
        "diagnostic_artifact_count": sum(1 for row in rows if row["diagnostic_only"]),
        "artifacts": rows,
        "errors": errors,
        "promotion_policy": {
            "frequency_assigned": False,
            "provider_release_packet_promoted": False,
            "physical_validation_promoted": False,
            "facility_qra_promoted": False,
            "supporting_documents_are_not_qualification_evidence": True,
            "qualification_requires_separate_exact_digest_bound_evidence": True,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
    }


def audit_provider_artifact_roots(
    roots: Mapping[str, str | Path],
) -> dict[str, Any]:
    """Audit several external workspaces as one non-promoting inventory.

    A project often keeps the process-model outputs and the PRISM development
    replay in different folders.  Auditing only one folder can therefore make
    the evidence search look complete while silently omitting another source.
    This helper keeps each root's result separate, adds a deterministic
    aggregate, and never merges artifacts or opens a qualification gate.
    Labels are caller-owned identifiers; the report intentionally preserves
    the per-root ``source_root_provided`` value only inside each child result.
    """
    if not isinstance(roots, Mapping) or not roots:
        raise ValueError("roots must be a non-empty label-to-path mapping")
    labels = [str(label) for label in roots]
    if any(not label.strip() for label in labels) or len(set(labels)) != len(labels):
        raise ValueError("root labels must be unique non-empty strings")

    inventories: dict[str, dict[str, Any]] = {}
    for label, root in roots.items():
        if not isinstance(label, str) or not label.strip():
            raise ValueError("root labels must be non-empty strings")
        inventories[label] = audit_provider_artifact_root(root)

    numeric_keys = (
        "artifact_count",
        "provider_response_count",
        "verification_artifact_count",
        "qualification_artifact_count",
        "physical_validation_artifact_count",
        "complete_facility_qra_artifact_count",
        "diagnostic_artifact_count",
        "supporting_file_count",
    )
    totals = {
        key: sum(int(item.get(key, 0)) for item in inventories.values())
        for key in numeric_keys
    }
    blockers = sorted({
        str(reason)
        for item in inventories.values()
        for reason in item.get("blocking_reasons", ())
    })
    qualified = totals["qualification_artifact_count"]
    physical = totals["physical_validation_artifact_count"]
    qra = totals["complete_facility_qra_artifact_count"]
    if not totals["artifact_count"]:
        status = "NO_EXTERNAL_JSON_ARTIFACTS"
    elif not qualified or not physical or not qra:
        status = "EXTERNAL_ARTIFACTS_DIAGNOSTIC_ONLY"
    else:
        status = "ARTIFACTS_REQUIRE_PRISM_RECONCILIATION"
    return {
        "schema_version": "prism.provider_artifact_roots_audit.v1",
        "status": status,
        "root_count": len(inventories),
        "roots": inventories,
        "summary": {
            **totals,
            "qualification_evidence_present": qualified > 0,
            "independent_physical_validation_present": physical > 0,
            "complete_facility_qra_claim_present": qra > 0,
            "facility_ir_fn_allowed": False,
        },
        "blocking_reasons": blockers,
        "promotion_policy": {
            "roots_remain_separate": True,
            "frequency_assigned": False,
            "provider_release_packet_promoted": False,
            "physical_validation_promoted": False,
            "facility_qra_promoted": False,
            "supporting_documents_are_not_qualification_evidence": True,
            "qualification_requires_separate_exact_digest_bound_evidence": True,
        },
    }
