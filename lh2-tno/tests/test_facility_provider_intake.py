from __future__ import annotations

from lh2_tno.facility_provider_intake import audit_facility_provider_intake_template


def _request():
    return {
        "schema_version": "prism.facility_evidence_request.v1",
        "facility_id": "facility-1",
        "case_requests": [{
            "request_id": "case-1",
            "event_id": "event-1",
            "component_id": "tank-1",
            "required_input_origin": "reviewed_measurement",
            "provider_packet_port_ids": ["tank.out"],
            "exact_match_required": {
                "event_id": "event-1",
                "component_id": "tank-1",
                "port_ids": ["tank.out"],
                "provider_source_digests": ["a" * 64],
                "provider_result_digests": ["b" * 64],
            },
        }],
    }


def _template():
    return {
        "schema_version": "prism.provider_qualification_sidecar_manifest.v1",
        "status": "TEMPLATE_ONLY",
        "promotion_allowed": False,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "entries": [{
            "request_id": "case-1",
            "facility_case_request_id": "case-1",
            "required_input_origin": "reviewed_measurement",
            "provider_packet_port_ids": ["tank.out"],
            "requested_exact_identity": {
                "event_id": "event-1",
                "component_id": "tank-1",
                "port_ids": ["tank.out"],
                "provider_source_digests": ["a" * 64],
                "provider_result_digests": ["b" * 64],
            },
        }],
    }


def test_facility_provider_template_is_exactly_aligned():
    report = audit_facility_provider_intake_template(_request(), _template())
    assert report["status"] == "ALIGNED_TEMPLATE_ONLY"
    assert report["request_case_count"] == 1
    assert report["template_entry_count"] == 1
    assert report["aligned_entry_count"] == 1
    assert report["blocking_reasons"] == []
    assert report["promotion_policy"]["facility_qra_allowed"] is False


def test_facility_provider_template_mismatch_is_fail_closed():
    template = _template()
    template["entries"][0]["requested_exact_identity"]["component_id"] = "wrong"
    report = audit_facility_provider_intake_template(_request(), template)
    assert report["status"] == "BLOCKED_TEMPLATE_ALIGNMENT"
    assert "template_identity_mismatch" in report["blocking_reasons"]
    assert report["promotion_policy"]["provider_qualification"] is False


def test_facility_provider_template_missing_case_is_fail_closed():
    template = _template()
    template["entries"] = []
    report = audit_facility_provider_intake_template(_request(), template)
    assert report["status"] == "BLOCKED_TEMPLATE_ALIGNMENT"
    assert report["missing_request_ids"] == ["case-1"]
