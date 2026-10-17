from __future__ import annotations

from lh2_tno.facility_case_packet_coverage import audit_facility_case_packet_coverage


def _request(event_id: str = "event-01", condition: str = "D-3ms-west") -> dict:
    return {
        "request_id": f"{event_id}/{condition}/release-01",
        "event_id": event_id,
        "annual_condition_id": condition,
        "release_branch_id": "release-01",
        "component_id": "pipe-01",
        "scenario_families": ["pipe_hole"],
        "exact_match_required": {
            "event_id": event_id,
            "component_id": "pipe-01",
            "port_ids": ["pipe.out"],
            "provider_source_digests": ["a" * 64],
            "provider_result_digests": ["b" * 64],
        },
    }


def _evidence(event_id: str = "event-01") -> dict:
    return {
        "schema_version": "prism.provider_packet_evidence.v1",
        "event_id": event_id,
        "component_id": "pipe-01",
        "port_ids": ["pipe.out"],
        "provider_source_digests": ["a" * 64],
        "provider_result_digests": ["b" * 64],
        "evidence_id": f"evidence-{event_id}",
        "provider_qualification_schema": "prism.provider_qualification_evidence.v1",
        "provider_export_schema": "prism.external_accident_history.v1",
        "status": "qualified_actual",
    }


def test_empty_catalog_reports_every_case_missing_without_inference():
    report = audit_facility_case_packet_coverage(
        {"facility_id": "facility", "case_requests": [_request()]},
    )
    assert report["status"] == "NO_CASE_MATCH"
    assert report["qualified_provider_case_count"] == 0
    assert report["status_counts"] == {"MISSING_QUALIFIED_PROVIDER_EVIDENCE": 1}
    assert report["promotion_policy"]["frequency_is_not_assigned"] is True
    assert report["status_counts_by_component"] == {"pipe-01": {"MISSING_QUALIFIED_PROVIDER_EVIDENCE": 1}}
    assert report["status_counts_by_family"] == {"pipe_hole": {"MISSING_QUALIFIED_PROVIDER_EVIDENCE": 1}}
    assert report["unclassified_family_case_count"] == 0


def test_one_provider_event_can_cover_multiple_weather_cases_exactly():
    report = audit_facility_case_packet_coverage(
        {
            "facility_id": "facility",
            "case_requests": [_request(condition="D-3ms-west"), _request(condition="D-4ms-west")],
        },
        [_evidence()],
    )
    assert report["status"] == "QUALIFIED_FULL_CASE_COVERAGE"
    assert report["qualified_provider_event_count"] == 1
    assert report["qualified_provider_case_count"] == 2
    assert report["status_counts"] == {"QUALIFIED_EXACT_MATCH": 2}


def test_digest_mismatch_is_blocking_and_does_not_promote_case():
    evidence = _evidence()
    evidence["provider_result_digests"] = ["c" * 64]
    report = audit_facility_case_packet_coverage(
        {"facility_id": "facility", "case_requests": [_request()]},
        [evidence],
    )
    assert report["status"] == "NO_CASE_MATCH"
    assert report["qualified_provider_case_count"] == 0
    assert report["status_counts"] == {"UNQUALIFIED_EVIDENCE_MISMATCH": 1}
    assert "provider_result_digests mismatch" in report["case_rows"][0]["blocking_reasons"]


def test_same_event_can_select_distinct_exact_provider_packets():
    second_request = _request(condition="D-4ms-west")
    second_request["request_id"] = "event-01/D-4ms-west/release-02"
    second_request["release_branch_id"] = "release-02"
    second_request["exact_match_required"]["provider_result_digests"] = ["c" * 64]
    second_evidence = _evidence()
    second_evidence["evidence_id"] = "evidence-event-01-release-02"
    second_evidence["provider_result_digests"] = ["c" * 64]

    report = audit_facility_case_packet_coverage(
        {
            "facility_id": "facility",
            "case_requests": [_request(), second_request],
        },
        [_evidence(), second_evidence],
    )

    assert report["status"] == "QUALIFIED_FULL_CASE_COVERAGE"
    assert report["qualified_provider_event_count"] == 1
    assert report["qualified_provider_case_count"] == 2
    assert report["status_counts"] == {"QUALIFIED_EXACT_MATCH": 2}
