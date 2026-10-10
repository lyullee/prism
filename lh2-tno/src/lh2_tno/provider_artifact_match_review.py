"""Compare external provider artifacts with the current generic LH2 packet set.

The review is deliberately conservative.  It reports exact identity matches
only when event, component, port, source digest, and result digest all agree.
External files that merely contain a provider-like JSON shape remain diagnostic
and cannot qualify a packet, assign frequency, or open facility QRA.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


MATCH_REVIEW_SCHEMA = "prism.external_provider_artifact_match_review.v1"


def _read_json(path: Path) -> Any:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"unable to decode JSON artifact: {path}")


def _qualification_present(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("schema_version") == "prism.provider_qualification_evidence.v1":
            return True
        if value.get("status") == "qualified_actual" and value.get("evidence_id"):
            return True
        return any(_qualification_present(item) for item in value.values())
    if isinstance(value, list):
        return any(_qualification_present(item) for item in value)
    return False


def _true_field(value: Any, key: str) -> bool:
    if isinstance(value, Mapping):
        return value.get(key) is True or any(_true_field(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_true_field(item, key) for item in value)
    return False


def _candidate_from_directory(directory: Path) -> dict[str, Any]:
    response_path = directory / "provider_response.json"
    release_path = directory / "resolved_release.json"
    verification_path = directory / "verification.json"
    response = _read_json(response_path)
    release = _read_json(release_path) if release_path.is_file() else {}
    verification = _read_json(verification_path) if verification_path.is_file() else {}
    data = response.get("data", {}) if isinstance(response, Mapping) else {}
    if not isinstance(data, Mapping):
        data = {}
    if not isinstance(release, Mapping):
        release = {}
    if not isinstance(verification, Mapping):
        verification = {}
    source_digest = (
        release.get("provider_source_digest")
        or response.get("provider_source_digest")
        if isinstance(response, Mapping)
        else None
    )
    result_digest = release.get("provider_result_digest") or verification.get("provider_result_digest")
    identity = {
        "event_id": release.get("event_id") or data.get("event_id"),
        "component_id": release.get("component_id") or data.get("component_id"),
        "port_id": release.get("port_id") or data.get("port_id"),
        "provider_source_digest": source_digest,
        "provider_result_digest": result_digest,
    }
    return {
        "directory": directory.as_posix(),
        "provider_model": response.get("provider_model") if isinstance(response, Mapping) else None,
        "provider_export_schema": response.get("provider_export_schema") if isinstance(response, Mapping) else None,
        **identity,
        "input_origin": release.get("input_origin"),
        "upstream_service_provenance": release.get("upstream_service_provenance"),
        "termination_basis": release.get("termination_basis") or verification.get("termination_basis"),
        "duration_s": release.get("duration_s") or verification.get("duration_s"),
        "verification_status": verification.get("status"),
        "qualification_evidence_present": _qualification_present(response)
        or _qualification_present(release)
        or _qualification_present(verification),
        "physical_validation_claim": _true_field(response, "physical_validation_claim")
        or _true_field(release, "physical_validation_claim")
        or _true_field(verification, "physical_validation_claim"),
        "complete_facility_qra_claim": _true_field(response, "complete_facility_qra_claim")
        or _true_field(release, "complete_facility_qra_claim")
        or _true_field(verification, "complete_facility_qra_claim"),
    }


def _packet_identities(closure_audit: Mapping[str, Any]) -> set[tuple[Any, ...]]:
    identities: set[tuple[Any, ...]] = set()
    for event in closure_audit.get("event_rows", []):
        for packet in event.get("packet_rows", []):
            path_value = packet.get("path")
            if not path_value:
                continue
            path = Path(path_value)
            if not path.is_file():
                continue
            try:
                payload = _read_json(path)
            except (OSError, ValueError):
                continue
            if not isinstance(payload, Mapping):
                continue
            identities.add(
                tuple(payload.get(key) for key in (
                    "event_id", "component_id", "port_id",
                    "provider_source_digest", "provider_result_digest",
                ))
            )
    return identities


def audit_external_provider_artifact_matches(
    source_root: str | Path,
    closure_audit: str | Path | Mapping[str, Any],
) -> dict[str, Any]:
    """Return an exact-match review without promoting external artifacts."""
    root = Path(source_root).resolve()
    if isinstance(closure_audit, Mapping):
        audit = closure_audit
    else:
        audit = _read_json(Path(closure_audit))
    if not root.is_dir():
        return {
            "schema": MATCH_REVIEW_SCHEMA,
            "status": "MISSING_SOURCE_ROOT",
            "source_root": str(source_root),
            "candidate_count": 0,
            "exact_match_count": 0,
            "promotion": {"provider_packet": False, "frequency": False, "facility_qra": False},
            "blocking_reasons": ["external provider artifact root does not exist"],
        }

    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for response_path in sorted(root.rglob("provider_response.json")):
        try:
            candidates.append(_candidate_from_directory(response_path.parent))
        except (OSError, ValueError, TypeError) as error:
            errors.append({"file": response_path.as_posix(), "error": str(error)})

    packet_ids = _packet_identities(audit if isinstance(audit, Mapping) else {})
    exact_match_count = 0
    for candidate in candidates:
        key = tuple(candidate.get(name) for name in (
            "event_id", "component_id", "port_id",
            "provider_source_digest", "provider_result_digest",
        ))
        candidate["exact_match_to_generic_packet"] = key in packet_ids and all(value is not None for value in key)
        if candidate["exact_match_to_generic_packet"]:
            exact_match_count += 1

    qualified_count = sum(1 for item in candidates if item["qualification_evidence_present"])
    physical_count = sum(1 for item in candidates if item["physical_validation_claim"])
    qra_count = sum(1 for item in candidates if item["complete_facility_qra_claim"])
    reasons = [
        "external artifacts are diagnostic unless a separate exact-digest qualification sidecar is present",
    ]
    if not candidates:
        reasons.append("no provider_response.json artifact was found")
    if exact_match_count == 0:
        reasons.append("no external provider artifact exactly matches a current generic event/component/port/source/result identity")
    if qualified_count == 0:
        reasons.append("no prism.provider_qualification_evidence.v1 record was found")
    if physical_count == 0:
        reasons.append("no artifact claims independent physical validation")
    if qra_count == 0:
        reasons.append("no artifact claims a complete facility QRA")
    if errors:
        reasons.append("one or more external provider artifacts could not be read")
    return {
        "schema": MATCH_REVIEW_SCHEMA,
        "status": "NO_EXACT_QUALIFIED_MATCH" if exact_match_count == 0 else "EXACT_MATCH_REQUIRES_QUALIFICATION",
        "source_root": str(source_root),
        "closure_audit": str(closure_audit) if not isinstance(closure_audit, Mapping) else "inline",
        "candidate_count": len(candidates),
        "exact_match_count": exact_match_count,
        "qualification_artifact_count": qualified_count,
        "physical_validation_artifact_count": physical_count,
        "complete_facility_qra_artifact_count": qra_count,
        "candidates": candidates,
        "errors": errors,
        "blocking_reasons": reasons,
        "promotion": {"provider_packet": False, "frequency": False, "facility_qra": False},
    }
