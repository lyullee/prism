from __future__ import annotations

import json

from lh2_tno.native_provider_qualification_audit import (
    audit_native_full_scope_provider_qualification,
)


SOURCE = "a" * 64
RESULT = "b" * 64


def _native_catalogue(tmp_path, *, with_sidecar: bool):
    event_dir = tmp_path / "event"
    event_dir.mkdir()
    packet = {
        "event_id": "native-event",
        "component_id": "tank-1",
        "port_id": "out",
        "provider_source_digest": SOURCE,
        "provider_result_digest": RESULT,
    }
    packet_path = event_dir / "resolved_release.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    sidecar_dir = tmp_path / "review"
    sidecar_dir.mkdir()
    sidecar_path = sidecar_dir / "qualification.json"
    if with_sidecar:
        sidecar_path.write_text(json.dumps({
            "schema_version": "prism.provider_qualification_evidence.v1",
            "status": "qualified_actual",
            "provider_origin": ["native_provider", "reviewed_actual"],
            "evidence_id": "review-1",
            "event_id": "native-event",
            "component_id": "tank-1",
            "port_id": "out",
            "provider_source_digests": [SOURCE],
            "provider_result_digests": [RESULT],
            "exact_digest_binding": True,
        }), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "prism.provider_qualification_sidecar_manifest.v1",
        "entries": [{
            "request_id": "native-event",
            "qualification_sidecar_path": "review/qualification.json",
        }],
    }), encoding="utf-8")
    catalogue = tmp_path / "native.json"
    catalogue.write_text(json.dumps({
        "schema_version": "prism.native_full_scope_provider_qualification_requests.v1",
        "requests": [{
            "event_id": "native-event",
            "component_id": "tank-1",
            "packet_path": str(packet_path),
            "requests": [{
                "request_id": "native-event",
                "request_kind": "qualification_only",
                "current_packet": packet,
                "packet_path": str(packet_path),
                "packet_index": 0,
            }],
        }],
    }), encoding="utf-8")
    return catalogue, manifest


def test_native_catalogue_is_flattened_and_missing_sidecar_is_blocked(tmp_path):
    catalogue, manifest = _native_catalogue(tmp_path, with_sidecar=False)
    report = audit_native_full_scope_provider_qualification(
        catalogue, sidecar_manifest=manifest
    )
    assert report["status"] == "NO_QUALIFIED_PROVIDER_EVIDENCE"
    assert report["event_row_count"] == 1
    assert report["release_identity_request_count"] == 1
    assert report["missing_sidecar_count"] == 1
    assert report["qualified_provider_packet_count"] == 0
    assert report["facility_qra_allowed"] is False


def test_native_exact_sidecar_remains_unqualified_until_closure_is_explicit(tmp_path):
    catalogue, manifest = _native_catalogue(tmp_path, with_sidecar=True)
    report = audit_native_full_scope_provider_qualification(
        catalogue, sidecar_manifest=manifest
    )
    assert report["exact_match_count"] == 1
    assert report["qualified_provider_packet_count"] == 0
    assert report["rows"][0]["status"] == "QUALIFIED_SIDECAR_EXACT_MATCH"
