from lh2_tno.facility_evidence_worklist import build_facility_evidence_worklist


def test_worklist_preserves_exact_identity_and_fail_closed_policy():
    report = build_facility_evidence_worklist({
        "schema_version": "prism.facility_evidence_request.v1",
        "facility_id": "facility-1",
        "scope": "outdoor",
        "current_assessment": {
            "case_count": 1,
            "strict_uncomputed_case_count": 1,
            "facility_promotion_allowed_now": False,
        },
        "case_requests": [{
            "request_id": "r1",
            "event_id": "e1",
            "component_id": "pipe-1",
            "scenario_families": ["pipe_hole"],
            "release_branch_id": "branch-1",
            "annual_condition_id": "weather-1",
            "current_status": "EXECUTED_OPERATOR_LIMITED",
            "gap_class": "QUALIFICATION_EVIDENCE_WITHHELD",
            "required_input_origin": "reviewed_measurement",
            "exact_match_required": {
                "event_id": "e1",
                "component_id": "pipe-1",
                "port_ids": ["out"],
                "provider_source_digests": ["a" * 64],
                "provider_result_digests": ["b" * 64],
            },
            "current_release_boundary": {
                "termination_basis": "isolation",
                "termination_time_s": 2.0,
                "domain_truncated": False,
            },
            "required_provider_evidence": ["time history"],
            "blocking_reasons": ["qualified provider packet missing"],
        }],
    })
    assert report["status"] == "OPEN_PROVIDER_EVIDENCE_WORKLIST"
    assert report["promotion_policy"]["frequency_is_not_assigned"] is True
    assert report["promotion_policy"]["facility_qra_promotion"] is False
    row = report["case_rows"][0]
    assert row["exact_identity"]["port_ids"] == ["out"]
    assert row["release_boundary"]["termination_basis"] == "isolation"
    assert report["component_summary"][0]["key"] == "pipe-1"
    assert report["family_summary"][0]["key"] == "pipe_hole"
    assert report["blocking_reason_counts"] == {"qualified provider packet missing": 1}


def test_empty_worklist_is_explicit():
    report = build_facility_evidence_worklist({"case_requests": []})
    assert report["status"] == "EMPTY_PROVIDER_EVIDENCE_WORKLIST"
    assert report["case_count"] == 0
    assert report["component_summary"] == []
