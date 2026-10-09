"""Audit external digital-twin artifacts without promoting them to QRA inputs.

External equipment projects often export a mixture of provider responses,
verification ledgers and campaign summaries.  This module inventories those
files and checks whether the artifacts contain the separate qualification
evidence required by PRISM.  It deliberately does not load a release packet,
assign a frequency, or claim physical validation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


PROVIDER_ARTIFACT_AUDIT_SCHEMA = "prism.provider_artifact_audit.v1"
QUALIFICATION_SCHEMA = "prism.provider_qualification_evidence.v1"


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


def audit_provider_artifact_root(root: str | Path) -> dict[str, Any]:
    """Inventory JSON artifacts below ``root`` using relative paths only."""
    source_root = Path(root).resolve()
    if not source_root.is_dir():
        return {
            "schema_version": PROVIDER_ARTIFACT_AUDIT_SCHEMA,
            "status": "MISSING_SOURCE_ROOT",
            "source_root_provided": str(root),
            "artifact_count": 0,
            "blocking_reasons": ["external provider artifact root does not exist"],
        }

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in sorted(source_root.rglob("*.json")):
        if any(part in {".git", "__pycache__", ".venv"} for part in path.parts):
            continue
        relative = path.relative_to(source_root).as_posix()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
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
            "qualification_requires_separate_exact_digest_bound_evidence": True,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
    }
