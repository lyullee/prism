import json
from pathlib import Path

from lh2_tno.provider_artifact_match_review import audit_external_provider_artifact_matches


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_exact_identity_is_reported_but_not_promoted(tmp_path):
    external = tmp_path / "external" / "pipe"
    identity = {
        "event_id": "event-1",
        "component_id": "pipe-1",
        "port_id": "pipe-out",
        "provider_source_digest": "source-1",
        "provider_result_digest": "result-1",
    }
    _write(external / "provider_response.json", {
        "provider_export_schema": "prism.external_accident_history.v1",
        "provider_model": "test.pipe",
        "provider_source_digest": "source-1",
        "data": identity,
    })
    _write(external / "resolved_release.json", {
        **identity,
        "input_origin": "model_prediction",
        "termination_basis": "reviewed_isolation_success",
    })
    _write(external / "verification.json", {
        "status": "NATIVE_EXTERNAL_ACCIDENT_EXPORT_EXECUTED_DIAGNOSTIC",
        "provider_result_digest": "result-1",
        "physical_validation_claim": False,
    })
    packet = tmp_path / "packet.json"
    _write(packet, identity)
    closure = {
        "event_rows": [{"packet_rows": [{"path": str(packet)}]}]
    }

    report = audit_external_provider_artifact_matches(external, closure)

    assert report["status"] == "EXACT_MATCH_REQUIRES_QUALIFICATION"
    assert report["candidate_count"] == 1
    assert report["exact_match_count"] == 1
    assert report["qualification_artifact_count"] == 0
    assert report["promotion"] == {
        "provider_packet": False,
        "frequency": False,
        "facility_qra": False,
    }
