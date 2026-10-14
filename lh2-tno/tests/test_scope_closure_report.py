from lh2_tno.scope_closure_report import build_scope_closure_report


def _inputs():
    scope = {
        "schema_version": "prism.major_accident_scope.v1",
        "environment": "outdoor",
        "scope": "outdoor_major_accidents",
        "required_families": ["vessel_hole", "pipe_hole"],
        "rows": [
            {
                "family": "vessel_hole",
                "status": "PARTIAL",
                "conditional_status": "EXECUTED",
                "applicability": "APPLICABLE",
                "generated_event_count": 2,
                "case_count": 2,
                "executed_case_count": 2,
                "fully_validated_case_count": 0,
                "uncomputed_case_count": 2,
                "operator_limited_case_count": 2,
                "qualified_evidence_withheld_case_count": 2,
                "event_ids": ["v-1", "v-2"],
                "uncomputed_reasons": ["provider packet required"],
                "strict_gate_categories": ["MISSING_PROVIDER_CASES"],
            },
            {
                "family": "pipe_hole",
                "status": "EXCLUDED",
                "conditional_status": "NOT_APPLICABLE",
                "applicability": "EXCLUDED",
                "generated_event_count": 0,
                "case_count": 0,
                "executed_case_count": 0,
                "fully_validated_case_count": 0,
                "uncomputed_case_count": 0,
                "operator_limited_case_count": 0,
                "qualified_evidence_withheld_case_count": 0,
                "event_ids": [],
            },
        ],
    }
    assessment = {
        "facility_id": "facility-01",
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
        "provider_packet_promoted": False,
        "qualified_provider_packet_case_count": 0,
        "provider_qualification_blocking_reasons": ["provider missing"],
        "timing": {
            "fresh_physics_cases": 2,
            "case_median_ms": 100.0,
            "case_p95_ms": 150.0,
            "campaign_elapsed_ms": 250.0,
        },
        "frequency_uncertainty": {
            "scenarios": [{"id": "published"}, {"id": "p95"}],
            "frequency_inference_performed": False,
            "facility_credible_interval": False,
        },
        "strict_release_boundary": {
            "strict_release_boundary_ready": False,
            "case_count": 2,
            "withheld_case_count": 2,
            "blocking_reasons": ["withheld"],
        },
        "conditional_diagnostic_facility_coverage": {
            "event_count": 2,
            "conditional_executed_case_count": 2,
            "strict_uncomputed_case_count": 2,
            "qualified_evidence_withheld_case_count": 2,
            "component_case_accounting": {
                "tank-01": {
                    "status": "PARTIAL",
                    "event_count": 2,
                    "conditional_case_count": 2,
                    "numerically_executed_case_count": 2,
                    "strict_uncomputed_case_count": 2,
                    "operator_limited_case_count": 2,
                    "qualified_evidence_withheld_case_count": 2,
                    "event_ids": ["v-1", "v-2"],
                    "strict_gate_categories": ["MISSING_PROVIDER_CASES"],
                }
            },
        },
        "facility_risk_ledger": {"uncomputed_cases": [{"event_id": "v-1"}]},
    }
    return scope, assessment


def test_scope_closure_report_preserves_partial_and_excluded_rows():
    report = build_scope_closure_report(*_inputs())
    assert report["schema_version"] == "prism.outdoor_scope_closure_report.v1"
    assert report["status"] == "SCOPE_CLOSURE_DIAGNOSTIC_PARTIAL"
    assert report["declared_event_count"] == 2
    assert report["uncomputed_event_ids"] == ["v-1"]
    assert report["family_status_counts"]["PARTIAL_STRICT_CASES_WITHHELD"] == 1
    assert report["family_status_counts"]["EXCLUDED_OR_NOT_APPLICABLE"] == 1
    assert report["component_rows"][0]["closure_status"] == "PARTIAL_STRICT_CASES_WITHHELD"


def test_scope_closure_report_never_promotes_qra():
    report = build_scope_closure_report(*_inputs())
    assert report["policy"]["missing_accidents_are_not_inferred"] is True
    assert report["policy"]["provider_packet_promoted"] is False
    assert report["policy"]["facility_qra_claim"] is False


def test_scope_closure_report_records_uncertainty_timing_and_validation_gates():
    report = build_scope_closure_report(*_inputs())
    assert report["evidence_gates"]["frequency_uncertainty"]["status"] == "REPORTED"
    assert report["evidence_gates"]["processing_time"]["status"] == "REPORTED"
    assert report["evidence_gates"]["physical_validation"]["status"] == "WITHHELD"
    assert report["evidence_gates"]["provider_qualification"]["status"] == "WITHHELD"
    assert report["timing"]["case_p95_ms"] == 150.0


def test_scope_closure_report_prefers_explicit_frequency_scenario_record():
    scope, assessment = _inputs()
    assessment["frequency_uncertainty"] = {}
    report = build_scope_closure_report(
        scope,
        assessment,
        {
            "scenarios": [{"id": "published"}, {"id": "p05"}, {"id": "p95"}],
            "frequency_inference_performed": False,
            "facility_credible_interval": False,
        },
    )
    assert report["frequency_uncertainty"]["scenario_count"] == 3
    assert report["evidence_gates"]["frequency_uncertainty"][
        "frequency_inference_performed"
    ] is False


def test_scope_closure_report_records_complete_hazop_mode_binding():
    scope, assessment = _inputs()
    report = build_scope_closure_report(
        scope,
        assessment,
        None,
        {
            "status": "HAZOP_EVENT_MODE_BINDING_COMPLETE",
            "event_count": 2,
            "mode_bound_event_count": 2,
            "mode_required_event_count": 0,
            "scenario_id_required_event_count": 0,
            "mode_conflict_event_count": 0,
            "errors": [],
        },
    )
    assert report["evidence_gates"]["hazop_mode_binding"]["status"] == "REPORTED"
    assert report["policy"]["hazop_mode_inference_performed"] is False


def test_scope_closure_report_records_hazop_selection_event_expansion():
    scope, assessment = _inputs()
    report = build_scope_closure_report(
        scope,
        assessment,
        None,
        None,
        {
            "status": "HAZOP_SELECTION_EVENT_BINDING_COMPLETE",
            "selected_scenario_count": 2,
            "frequency_event_count": 4,
            "bound_event_count": 4,
            "unbound_event_count": 0,
            "errors": [],
        },
    )
    assert report["evidence_gates"]["hazop_selection_event_binding"]["status"] == "REPORTED"
    assert report["policy"]["hazop_selection_event_frequency_assignment_performed"] is False
