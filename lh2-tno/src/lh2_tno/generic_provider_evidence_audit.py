"""Audit qualification sidecars for the generic LH2 evidence catalogue.

The catalogue is intentionally fail-closed.  This module only checks whether
an adjacent provider qualification sidecar is an exact, digest-bound match for
the packet requested by the catalogue.  It never creates a sidecar, repairs a
digest, infers a release frequency, or promotes a facility QRA claim.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any


SCHEMA = "prism.generic_provider_evidence_audit.v1"
QUALIFICATION_SCHEMA = "prism.provider_qualification_evidence.v1"
_SIDECAR_NAMES = (
    "provider_qualification.json",
    "provider_qualification_evidence.json",
    "qualification_sidecar.json",
    "qualification.json",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _packet_at(packet: Mapping[str, Any], index: int) -> Mapping[str, Any] | None:
    releases = packet.get("releases")
    if isinstance(releases, list) and releases and all(isinstance(item, Mapping) for item in releases):
        if 0 <= index < len(releases):
            return releases[index]
        return None
    return packet if index == 0 else None


def _sidecar(parent: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    for name in _SIDECAR_NAMES:
        path = parent / name
        if not path.is_file():
            continue
        try:
            value = _load(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None, str(path)
        if not isinstance(value, Mapping):
            return None, str(path)
        nested = value.get("provider_qualification")
        return (nested if isinstance(nested, Mapping) else value), str(path)
    return None, None


def _sidecar_path(path: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    """Load an explicitly declared sidecar path without searching elsewhere."""

    if not path.is_file():
        return None, str(path)
    try:
        value = _load(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, str(path)
    if not isinstance(value, Mapping):
        return None, str(path)
    nested = value.get("provider_qualification")
    return (nested if isinstance(nested, Mapping) else value), str(path)


def _declared_list(record: Mapping[str, Any], plural: str, singular: str) -> list[str] | None:
    value = record.get(plural)
    if value is None and singular in record:
        value = [record.get(singular)]
    if not isinstance(value, (list, tuple)):
        return None
    return [str(item) for item in value]


def _digest_ok(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _match_sidecar(
    packets: list[Mapping[str, Any]],
    sidecar: Mapping[str, Any] | None,
) -> tuple[bool, str | None]:
    """Match one sidecar against a flat packet or every side of a release set."""

    if sidecar is None:
        return False, "qualification_sidecar_missing"
    if not packets:
        return False, "qualification_sidecar_invalid"
    if sidecar.get("schema_version") != QUALIFICATION_SCHEMA:
        return False, "qualification_sidecar_invalid"
    if sidecar.get("status") != "qualified_actual":
        return False, "qualification_sidecar_invalid"
    origins = sidecar.get("provider_origin")
    if isinstance(origins, str):
        origins = [origins]
    if not isinstance(origins, (list, tuple)) or not origins:
        return False, "qualification_sidecar_invalid"
    if not set(str(item) for item in origins).issubset({"native_provider", "reviewed_actual"}):
        return False, "qualification_sidecar_invalid"
    if not isinstance(sidecar.get("evidence_id"), str) or not sidecar["evidence_id"].strip():
        return False, "qualification_sidecar_invalid"
    if sidecar.get("exact_digest_binding") is not True:
        return False, "qualification_sidecar_digest_mismatch"
    event_ids = [str(packet.get("event_id")) for packet in packets]
    component_ids = [str(packet.get("component_id")) for packet in packets]
    if len(set(event_ids)) != 1 or len(set(component_ids)) != 1:
        return False, "qualification_sidecar_invalid"
    if sidecar.get("event_id") != packets[0].get("event_id") or sidecar.get("component_id") != packets[0].get("component_id"):
        return False, "qualification_sidecar_identity_mismatch"
    declared_ports = _declared_list(sidecar, "port_ids", "port_id")
    packet_ports = [str(packet.get("port_id")) for packet in packets]
    if declared_ports != packet_ports:
        return False, "qualification_sidecar_identity_mismatch"
    sources = [packet.get("provider_source_digest") for packet in packets]
    results = [packet.get("provider_result_digest") for packet in packets]
    if not all(_digest_ok(value) for value in (*sources, *results)):
        return False, "qualification_sidecar_digest_mismatch"
    if _declared_list(sidecar, "provider_source_digests", "provider_source_digest") != [str(value) for value in sources]:
        return False, "qualification_sidecar_digest_mismatch"
    if _declared_list(sidecar, "provider_result_digests", "provider_result_digest") != [str(value) for value in results]:
        return False, "qualification_sidecar_digest_mismatch"
    return True, None


def audit_generic_provider_evidence(
    catalogue: Mapping[str, Any] | str | Path,
    *,
    packet_root: str | Path | None = None,
) -> dict[str, Any]:
    """Audit every request in a generic provider evidence catalogue."""

    if isinstance(catalogue, (str, Path)):
        catalogue_path = Path(catalogue).resolve()
        value = _load(catalogue_path)
        base = catalogue_path.parent
    else:
        value = catalogue
        base = Path(packet_root).resolve() if packet_root is not None else Path.cwd()
    if not isinstance(value, Mapping):
        raise ValueError("generic provider evidence catalogue must be an object")
    if value.get("schema_version") != "prism.generic_provider_evidence_requests.v1":
        raise ValueError("unsupported generic provider evidence catalogue schema")
    requests = value.get("requests")
    if not isinstance(requests, list):
        raise ValueError("generic provider evidence catalogue requests must be an array")
    rows: list[dict[str, Any]] = []
    counts = {
        "qualified": 0,
        "closure_ready_qualified": 0,
        "sidecar_present": 0,
        "missing_packet": 0,
        "missing_sidecar": 0,
        "invalid": 0,
        "identity_mismatch": 0,
        "digest_mismatch": 0,
    }
    loaded: list[dict[str, Any]] = []
    for request_index, raw in enumerate(requests):
        if not isinstance(raw, Mapping):
            loaded.append({"request_index": request_index, "raw": raw, "packet_path": None, "packet": None, "sidecar": None, "sidecar_path": None, "load_error": "invalid_request"})
            continue
        packet_path_value = raw.get("packet_path")
        packet_path = Path(str(packet_path_value)) if packet_path_value else None
        if packet_path is None or not packet_path.is_absolute():
            packet_path = (base / packet_path) if packet_path is not None else None
        packet_index = int(raw.get("packet_index", 0)) if str(raw.get("packet_index", 0)).isdigit() else 0
        if packet_path is None or not packet_path.is_file():
            loaded.append({"request_index": request_index, "raw": raw, "packet_path": packet_path, "packet": None, "sidecar": None, "sidecar_path": None, "load_error": "missing_packet"})
            continue
        try:
            packet_value = _load(packet_path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            loaded.append({"request_index": request_index, "raw": raw, "packet_path": packet_path, "packet": None, "sidecar": None, "sidecar_path": None, "load_error": "packet_json_invalid"})
            continue
        if not isinstance(packet_value, Mapping):
            loaded.append({"request_index": request_index, "raw": raw, "packet_path": packet_path, "packet": None, "sidecar": None, "sidecar_path": None, "load_error": "packet_not_object"})
            continue
        packet = _packet_at(packet_value, packet_index)
        if packet is None:
            loaded.append({"request_index": request_index, "raw": raw, "packet_path": packet_path, "packet": None, "sidecar": None, "sidecar_path": None, "load_error": "packet_index_missing"})
            continue
        explicit_sidecar = raw.get("qualification_sidecar_path")
        if explicit_sidecar:
            explicit_path = Path(str(explicit_sidecar))
            if not explicit_path.is_absolute():
                explicit_path = base / explicit_path
            sidecar, sidecar_path = _sidecar_path(explicit_path)
        else:
            sidecar, sidecar_path = _sidecar(packet_path.parent)
        loaded.append({"request_index": request_index, "raw": raw, "packet_path": packet_path, "packet": packet, "sidecar": sidecar, "sidecar_path": sidecar_path, "load_error": None})

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in loaded:
        if item["packet_path"] is not None and item["packet"] is not None:
            groups.setdefault(str(item["packet_path"]), []).append(item)
    group_packets: dict[str, list[Mapping[str, Any]]] = {}
    group_sidecars: dict[str, tuple[Mapping[str, Any] | None, str | None]] = {}
    for key, items in groups.items():
        ordered = sorted(items, key=lambda item: int(item["raw"].get("packet_index", 0)))
        group_packets[key] = [item["packet"] for item in ordered]
        group_sidecars[key] = (ordered[0]["sidecar"], ordered[0]["sidecar_path"])

    for item in loaded:
        request_index = item["request_index"]
        raw = item["raw"]
        if not isinstance(raw, Mapping):
            rows.append({"request_index": request_index, "status": "INVALID_REQUEST"})
            counts["invalid"] += 1
            continue
        packet_index = int(raw.get("packet_index", 0)) if str(raw.get("packet_index", 0)).isdigit() else 0
        row: dict[str, Any] = {
            "request_index": request_index,
            "request_id": raw.get("request_id"),
            "event_id": raw.get("current_packet", {}).get("event_id") if isinstance(raw.get("current_packet"), Mapping) else None,
            "component_id": raw.get("current_packet", {}).get("component_id") if isinstance(raw.get("current_packet"), Mapping) else None,
            "port_id": raw.get("current_packet", {}).get("port_id") if isinstance(raw.get("current_packet"), Mapping) else None,
            "packet_path": str(item["packet_path"]) if item["packet_path"] is not None else None,
            "packet_index": packet_index,
            "closure_status": raw.get("closure_status"),
            "request_kind": raw.get("request_kind"),
            "status": "MISSING_PACKET",
            "qualification_sidecar_path": None,
            "reason": "packet_path_missing",
            "exact_match": False,
            "qualified_provider_packet": False,
        }
        packet_path = item["packet_path"]
        if item["load_error"] == "missing_packet":
            counts["missing_packet"] += 1
            rows.append(row)
            continue
        if item["load_error"] == "packet_json_invalid":
            counts["invalid"] += 1
            row.update({"status": "INVALID_PACKET", "reason": "packet_json_invalid"})
            rows.append(row)
            continue
        if item["load_error"] == "packet_not_object":
            counts["invalid"] += 1
            row.update({"status": "INVALID_PACKET", "reason": "packet_not_object"})
            rows.append(row)
            continue
        if item["load_error"] == "packet_index_missing":
            counts["invalid"] += 1
            row.update({"status": "INVALID_PACKET", "reason": "packet_index_missing"})
            rows.append(row)
            continue
        packet = item["packet"]
        sidecar, sidecar_path = group_sidecars[str(packet_path)]
        row["qualification_sidecar_path"] = sidecar_path
        if item["sidecar_path"] is not None:
            counts["sidecar_present"] += 1
        matched, reason = _match_sidecar(group_packets[str(packet_path)], sidecar)
        row["exact_match"] = matched
        row["qualified_provider_packet"] = bool(
            matched and raw.get("closure_status") == "CLOSURE_READY_FOR_QUALIFICATION"
        )
        if matched:
            counts["qualified"] += 1
            if row["qualified_provider_packet"]:
                counts["closure_ready_qualified"] += 1
            row.update({"status": "QUALIFIED_SIDECAR_EXACT_MATCH", "reason": None})
        else:
            row["status"] = {
                "qualification_sidecar_missing": "MISSING_QUALIFICATION_SIDECAR",
                "qualification_sidecar_identity_mismatch": "QUALIFICATION_IDENTITY_MISMATCH",
                "qualification_sidecar_digest_mismatch": "QUALIFICATION_DIGEST_MISMATCH",
                "qualification_sidecar_invalid": "INVALID_QUALIFICATION_SIDECAR",
            }.get(reason or "", "QUALIFICATION_NOT_MATCHED")
            row["reason"] = reason
            counts["missing_sidecar" if reason == "qualification_sidecar_missing" else "invalid" if reason == "qualification_sidecar_invalid" else "identity_mismatch" if reason == "qualification_sidecar_identity_mismatch" else "digest_mismatch"] += 1
        rows.append(row)
    status = "QUALIFIED_SIDECAR_EVIDENCE_FOUND" if counts["qualified"] else "NO_QUALIFIED_PROVIDER_EVIDENCE"
    return {
        "schema_version": SCHEMA,
        "status": status,
        "source_schema_version": value.get("schema_version"),
        "request_count": len(requests),
        "packet_count": value.get("packet_count"),
        "qualification_sidecar_present_count": counts["sidecar_present"],
        "exact_match_count": counts["qualified"],
        "qualified_provider_packet_count": counts["closure_ready_qualified"],
        "missing_packet_count": counts["missing_packet"],
        "missing_sidecar_count": counts["missing_sidecar"],
        "invalid_count": counts["invalid"],
        "identity_mismatch_count": counts["identity_mismatch"],
        "digest_mismatch_count": counts["digest_mismatch"],
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "diagnostic_only": True,
        "rows": rows,
        "interpretation": (
            "An exact qualification sidecar is a diagnostic evidence match only. "
            "It does not establish independent physical validation, frequency binding, "
            "or facility QRA readiness."
        ),
    }


__all__ = ["audit_generic_provider_evidence"]
