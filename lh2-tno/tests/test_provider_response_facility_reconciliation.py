from lh2_tno.provider_response_facility_reconciliation import reconcile_provider_responses


def _request(event_id="event-1", component_id="component-1", port_ids=("port-1",)):
    return {
        "request_id": "request-1",
        "event_id": event_id,
        "component_id": component_id,
        "exact_match_required": {
            "event_id": event_id,
            "component_id": component_id,
            "port_ids": list(port_ids),
        },
    }


def _response(**overrides):
    row = {
        "file": "provider_response.json",
        "sha256": "a" * 64,
        "event_id": "event-1",
        "component_id": "component-1",
        "port_id": "port-1",
        "input_origin": None,
        "evidence_status": None,
        "qualification_sidecar_present": False,
        "blocking_reasons": ["no qualification sidecar"],
    }
    row.update(overrides)
    return row


def _audit(rows):
    return {
        "schema_version": "prism.external_provider_response_gap_audit.v1",
        "rows": rows,
    }


def _request_doc(requests):
    return {
        "schema_version": "prism.facility_evidence_request.v1",
        "case_requests": requests,
    }


def test_exact_identity_match_stays_unqualified_without_sidecar():
    report = reconcile_provider_responses(_audit([_response()]), _request_doc([_request()]))
    assert report["exact_case_match_count"] == 1
    assert report["qualified_exact_case_match_count"] == 0
    assert report["rows"][0]["status"] == "EXACT_CASE_MATCH_UNQUALIFIED"
    assert report["promotion"]["provider_packet_promoted"] is False


def test_missing_event_or_port_is_not_repaired_by_component_name():
    report = reconcile_provider_responses(
        _audit([_response(event_id="native-event", component_id="component-1", port_id="native-port")]),
        _request_doc([_request(event_id="facility-event", component_id="component-1", port_ids=("facility-port",))]),
    )
    assert report["component_candidate_response_count"] == 1
    assert report["exact_case_match_count"] == 0
    assert report["no_exact_case_match_count"] == 1
    assert report["rows"][0]["status"] == "NO_EXACT_CASE_MATCH"


def test_qualified_exact_match_requires_all_explicit_fields():
    response = _response(
        input_origin="reviewed_measurement",
        evidence_status="qualified_actual",
        qualification_sidecar_present=True,
        blocking_reasons=[],
    )
    report = reconcile_provider_responses(_audit([response]), _request_doc([_request()]))
    assert report["qualified_exact_case_match_count"] == 1
    assert report["rows"][0]["status"] == "QUALIFIED_EXACT_CASE_MATCH"
    assert report["rows"][0]["promotion_allowed"] is True
