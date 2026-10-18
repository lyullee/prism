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
    assert report["facility_case_rows"][0]["status"] == "UNQUALIFIED_RESPONSE"
    assert report["facility_case_exact_response_count"] == 1


def test_missing_event_or_port_is_not_repaired_by_component_name():
    report = reconcile_provider_responses(
        _audit([_response(event_id="native-event", component_id="component-1", port_id="native-port")]),
        _request_doc([_request(event_id="facility-event", component_id="component-1", port_ids=("facility-port",))]),
    )
    assert report["component_candidate_response_count"] == 1
    assert report["exact_case_match_count"] == 0
    assert report["no_exact_case_match_count"] == 1
    assert report["rows"][0]["status"] == "NO_EXACT_CASE_MATCH"
    assert report["facility_case_rows"][0]["status"] == "COMPONENT_CANDIDATE_ONLY"
    assert report["facility_case_component_candidate_only_count"] == 1


def test_unrepresented_facility_case_is_explicitly_open():
    report = reconcile_provider_responses(
        _audit([_response(event_id="other-event", component_id="other-component", port_id="other-port")]),
        _request_doc([_request()]),
    )
    assert report["facility_case_rows"][0]["status"] == "NO_PROVIDER_RESPONSE"
    assert report["facility_case_no_provider_response_count"] == 1
    assert report["facility_case_exact_response_count"] == 0


def test_multiple_cases_are_not_covered_by_one_unscoped_response():
    report = reconcile_provider_responses(
        _audit([_response()]),
        _request_doc([
            _request(),
            {**_request(), "request_id": "request-2", "annual_condition_id": "weather-2"},
        ]),
    )
    assert report["ambiguous_case_match_count"] == 1
    assert report["response_accounting_complete"] is True
    assert report["rows"][0]["status"] == "AMBIGUOUS_CASE_MATCH"
    assert all(
        row["status"] == "AMBIGUOUS_RESPONSE_IDENTITY"
        for row in report["facility_case_rows"]
    )
    assert report["facility_case_ambiguous_response_identity_count"] == 2


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
