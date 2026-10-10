from __future__ import annotations

import json

from lh2_tno.generic_provider_evidence_audit import audit_generic_provider_evidence


SOURCE = "1" * 64
RESULT = "2" * 64


def _write_catalogue(tmp_path, *, sidecar: dict | None = None, closure_status: str = "CLOSURE_READY_FOR_QUALIFICATION"):
    event_dir = tmp_path / "event"
    event_dir.mkdir(parents=True)
    packet = {
        "event_id": "event-1",
        "component_id": "tank-1",
        "port_id": "tank-out",
        "provider_source_digest": SOURCE,
        "provider_result_digest": RESULT,
    }
    packet_path = event_dir / "resolved_release.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    if sidecar is not None:
        (event_dir / "provider_qualification.json").write_text(
            json.dumps(sidecar), encoding="utf-8"
        )
    catalogue = {
        "schema_version": "prism.generic_provider_evidence_requests.v1",
        "packet_count": 1,
        "requests": [{
            "request_id": "event-1",
            "packet_path": str(packet_path),
            "packet_index": 0,
            "closure_status": closure_status,
            "request_kind": "qualification_only",
            "current_packet": packet,
        }],
    }
    return catalogue


def _sidecar(**overrides):
    value = {
        "schema_version": "prism.provider_qualification_evidence.v1",
        "status": "qualified_actual",
        "provider_origin": ["native_provider", "reviewed_actual"],
        "evidence_id": "review-1",
        "event_id": "event-1",
        "component_id": "tank-1",
        "port_id": "tank-out",
        "provider_source_digests": [SOURCE],
        "provider_result_digests": [RESULT],
        "exact_digest_binding": True,
    }
    value.update(overrides)
    return value


def test_exact_sidecar_is_counted_but_does_not_open_qra_gate(tmp_path):
    report = audit_generic_provider_evidence(_write_catalogue(tmp_path, sidecar=_sidecar()))
    assert report["status"] == "QUALIFIED_SIDECAR_EVIDENCE_FOUND"
    assert report["exact_match_count"] == 1
    assert report["qualified_provider_packet_count"] == 1
    assert report["frequency_inference_allowed"] is False
    assert report["facility_qra_allowed"] is False
    assert report["rows"][0]["status"] == "QUALIFIED_SIDECAR_EXACT_MATCH"


def test_missing_sidecar_is_fail_closed(tmp_path):
    report = audit_generic_provider_evidence(_write_catalogue(tmp_path))
    assert report["status"] == "NO_QUALIFIED_PROVIDER_EVIDENCE"
    assert report["missing_sidecar_count"] == 1
    assert report["exact_match_count"] == 0


def test_identity_and_digest_mismatch_are_separate(tmp_path):
    identity = audit_generic_provider_evidence(
        _write_catalogue(tmp_path / "identity", sidecar=_sidecar(port_id="other"))
    )
    digest = audit_generic_provider_evidence(
        _write_catalogue(tmp_path / "digest", sidecar=_sidecar(provider_result_digests=["3" * 64]))
    )
    assert identity["identity_mismatch_count"] == 1
    assert digest["digest_mismatch_count"] == 1


def test_closure_open_sidecar_is_not_a_qualified_provider_packet(tmp_path):
    report = audit_generic_provider_evidence(
        _write_catalogue(
            tmp_path,
            sidecar=_sidecar(),
            closure_status="CLOSURE_EVIDENCE_OPEN",
        )
    )
    assert report["exact_match_count"] == 1
    assert report["qualified_provider_packet_count"] == 0
