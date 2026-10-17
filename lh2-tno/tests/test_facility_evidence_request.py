from __future__ import annotations

from lh2_tno.facility_evidence_request import build_facility_evidence_request


def _assessment() -> dict:
    return {
        "facility_id": "facility",
        "facility_risk_ledger": {
            "status": "PARTIAL_FACILITY_SCOPE",
            "event_count": 2,
            "case_count": 3,
            "uncomputed_case_count": 1,
            "risk_atoms": [{"x": 1}],
            "facility_total_risk_available": False,
            "physical_validation_claim": False,
            "qualified_facility_qra_blocking_reasons": [
                "operator-limited cases remain",
                "independent physical validation claim is absent",
            ],
            "blocking_reasons": ["family pipe_hole: PARTIAL", "family pipe_hole: PARTIAL"],
            "component_statuses": {"pipe-01": "PARTIAL", "vent-01": "EXECUTED", "boundary-01": "EXCLUDED"},
            "component_coverage": {
                "pipe-01": {
                    "event_count": 2,
                    "conditional_case_count": 3,
                    "conditional_executed_case_count": 2,
                    "conditional_uncomputed_case_count": 1,
                    "strict_uncomputed_case_count": 1,
                    "operator_limited_case_count": 2,
                    "risk_atom_count": 4,
                    "strict_gate_categories": [
                        "MISSING_PROVIDER_CASES", "OPERATOR_LIMITED_INPUT"
                    ],
                },
            },
        },
    }


def test_builds_family_and_component_requests_without_frequency_inference():
    report = build_facility_evidence_request(
        _assessment(),
        {
            "facility_id": "facility",
            "rows": [
                {
                    "family": "pipe_hole",
                    "status": "PARTIAL",
                    "generated_event_count": 2,
                    "executed_case_count": 3,
                    "uncomputed_case_count": 1,
                    "operator_limited_case_count": 2,
                    "gap_class": "QUALIFICATION_EVIDENCE_WITHHELD",
                    "gap_reasons": ["diagnostic evidence"],
                    "closure_requirements": ["qualified provider packet"],
                    "case_status_counts": {"EXECUTED_OPERATOR_LIMITED": 2},
                    "event_ids": ["e1", "e2"],
                }
            ],
        },
    )
    assert report["status"] == "OPEN_EVIDENCE_REQUEST"
    assert report["provider_export_schema_required"] == "prism.external_accident_history.v1"
    assert report["promotion_gate"]["provider_packet_evidence_schema"] == "prism.provider_packet_evidence.v1"
    assert report["promotion_gate"]["exact_event_component_port_and_digest_match_required"] is True
    assert report["family_requests"][0]["promotion_allowed_now"] is False
    assert report["family_requests"][0]["conditional_status"] == "PARTIAL"
    assert report["family_requests"][0]["conditional_executed_case_count"] == 3
    assert report["family_requests"][0]["conditional_uncomputed_case_count"] == 1
    assert report["family_requests"][0]["strict_blocking_reason"] == "pipe_hole: PARTIAL"
    assert report["family_requests"][0]["strict_gate_categories"] == [
        "MISSING_PROVIDER_CASES", "OPERATOR_LIMITED_INPUT"
    ]
    assert report["family_requests"][0]["gap_class"] == "QUALIFICATION_EVIDENCE_WITHHELD"
    assert report["family_requests"][0]["gap_reasons"] == ["diagnostic evidence"]
    assert report["scope_gap_summary"] == {}
    assert len(report["family_requests"][0]["strict_gate_requirements"]) == 2
    assert report["current_assessment"]["strict_gate_categories"] == [
        "MISSING_PROVIDER_CASES", "OPERATOR_LIMITED_INPUT"
    ]
    assert report["current_assessment"]["qualified_facility_qra_blocking_reasons"] == [
        "operator-limited cases remain",
        "independent physical validation claim is absent",
    ]
    assert report["family_requests"][0]["family_scope_ready"] is False
    assert report["family_requests"][0]["facility_promotion_allowed_now"] is False
    assert "facility qualified IR/F-N gate is closed" in report["family_requests"][0]["facility_promotion_blocking_reasons"]
    assert "pipe upstream/downstream state and isolation response history" in report["family_requests"][0]["required_provider_evidence"]
    assert report["blocking_reasons"] == ["family pipe_hole: PARTIAL"]
    assert report["frequency_policy"]["infer_frequency_from_provider_or_sensor"] is False
    assert {row["component_id"] for row in report["component_requests"]} == {"pipe-01", "vent-01"}
    assert report["excluded_components"] == [{"component_id": "boundary-01", "current_status": "EXCLUDED"}]
    pipe = next(row for row in report["component_requests"] if row["component_id"] == "pipe-01")
    assert pipe["conditional_executed_case_count"] == 2
    assert pipe["conditional_uncomputed_case_count"] == 1
    assert pipe["strict_gate_categories"] == [
        "MISSING_PROVIDER_CASES", "OPERATOR_LIMITED_INPUT"
    ]
    assert len(pipe["strict_gate_requirements"]) == 2
    assert "operator-limited boundary inputs" in " ".join(pipe["required_evidence"])


def test_request_preserves_facility_level_conditional_case_accounting():
    assessment = _assessment()
    assessment["facility_risk_ledger"]["conditional_case_count"] = 12
    assessment["facility_risk_ledger"]["conditional_executed_case_count"] = 10
    assessment["facility_risk_ledger"]["conditional_uncomputed_case_count"] = 2
    assessment["facility_risk_ledger"]["conditional_diagnostic_facility_coverage"] = {
        "strict_uncomputed_case_count": 7,
    }
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": []},
    )
    current = report["current_assessment"]
    assert current["conditional_case_count"] == 12
    assert current["conditional_executed_case_count"] == 10
    assert current["conditional_uncomputed_case_count"] == 2
    assert current["strict_uncomputed_case_count"] == 7


def test_facility_promotion_gate_requires_complete_qualified_assessment():
    assessment = _assessment()
    assessment.update({
        "facility_total_risk_available": True,
        "qualified_facility_qra_available": True,
        "complete_facility_qra_claim": True,
    })
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": [{
            "family": "vent_hole",
            "status": "EXECUTED",
            "generated_event_count": 1,
            "executed_case_count": 1,
            "uncomputed_case_count": 0,
            "event_ids": ["vent-01"],
        }]},
    )
    row = report["family_requests"][0]
    assert row["family_scope_ready"] is True
    assert row["facility_promotion_allowed_now"] is True
    assert row["facility_promotion_blocking_reasons"] == []
    assert report["current_assessment"]["facility_promotion_allowed_now"] is True


def test_not_applicable_family_does_not_create_a_provider_evidence_request():
    report = build_facility_evidence_request(
        _assessment(),
        {
            "facility_id": "facility",
            "rows": [{
                "family": "pump_hole",
                "status": "NOT_APPLICABLE",
                "generated_event_count": 0,
                "executed_case_count": 0,
                "uncomputed_case_count": 0,
                "event_ids": [],
            }],
        },
    )
    row = report["family_requests"][0]
    assert row["applicability"] == "NOT_APPLICABLE"
    assert row["evidence_required"] is False
    assert row["required_provider_evidence"] == []
    assert row["promotion_allowed_now"] is True


def test_two_sided_request_exposes_joint_interaction_evidence_gap():
    report = build_facility_evidence_request(
        _assessment(),
        {
            "facility_id": "facility",
            "rows": [{
                "family": "two_sided_rupture",
                "status": "PARTIAL",
                "generated_event_count": 1,
                "executed_case_count": 1,
                "uncomputed_case_count": 1,
                "event_ids": ["rupture-01"],
            }],
        },
    )
    required = report["family_requests"][0]["required_provider_evidence"]
    assert any("paired plume/pressure/inventory interaction" in item for item in required)


def test_gate_categories_preserve_domain_and_failure_reasons():
    report = build_facility_evidence_request(
        _assessment(),
        {"facility_id": "facility", "rows": [{
            "family": "vertical_handoff",
            "status": "PARTIAL",
            "strict_uncomputed_case_count": 0,
            "operator_limited_case_count": 0,
            "domain_incomplete_case_count": 2,
            "failed_case_count": 1,
        }]},
    )
    row = report["family_requests"][0]
    assert row["strict_gate_categories"] == ["DOMAIN_INCOMPLETE", "FAILED_PROVIDER_CASE"]
    assert "DOMAIN_INCOMPLETE" in report["current_assessment"]["strict_gate_categories"]
    assert report["strict_gate_catalog"]["FAILED_PROVIDER_CASE"].startswith("repeat the failed")


def test_case_requests_preserve_exact_vertical_handoff_identity_and_qualification_gap():
    assessment = _assessment()
    ledger = assessment["facility_risk_ledger"]
    ledger.update({
        "case_count": 1,
        "qualified_provider_packet_case_count": 0,
        "cases": [{
            "event_id": "facility/vertical-handoff/terminal-valve/AREA_100%",
            "asset_id": "vertical-handoff-vent",
            "release_branch_id": "provider-vertical-handoff",
            "annual_condition_id": "D-3ms-west",
            "scenario_families": ["pipe_hole", "liquid_two_phase", "vertical_handoff"],
            "status": "EXECUTED_OPERATOR_LIMITED",
            "reason": "synthetic vertical handoff",
            "provider_packet_identity": {
                "event_id": "facility/vertical-handoff/terminal-valve/AREA_100%",
                "component_id": "vertical-handoff-terminal-pipe-01",
                "port_ids": ["terminal_pipe.out"],
                "provider_source_digests": ["source-digest"],
                "provider_result_digests": ["result-digest"],
            },
        }],
        "uncomputed_cases": [],
    })
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": [{
            "family": "vertical_handoff",
            "status": "PARTIAL",
            "strict_uncomputed_case_count": 1,
            "event_ids": ["facility/vertical-handoff/terminal-valve/AREA_100%"],
        }]},
    )
    assert report["case_request_count"] == 1
    request = report["case_requests"][0]
    assert request["request_kind"] == "QUALIFIED_PROVIDER_PACKET"
    assert request["gap_class"] == "QUALIFICATION_EVIDENCE_WITHHELD"
    assert request["qualification_required"] is True
    assert request["exact_match_required"]["component_id"] == "vertical-handoff-terminal-pipe-01"
    assert request["exact_match_required"]["port_ids"] == ["terminal_pipe.out"]
    assert "provider-owned vertical-to-horizontal handoff state and boundary" in request[
        "required_provider_evidence"
    ]
    assert any("EXECUTED_OPERATOR_LIMITED" in reason for reason in request["blocking_reasons"])


def test_case_request_merge_keeps_identity_present_only_on_duplicate_row():
    assessment = _assessment()
    ledger = assessment["facility_risk_ledger"]
    ledger.update({
        "case_count": 1,
        "qualified_provider_packet_case_count": 0,
        "cases": [{
            "event_id": "event-duplicate",
            "asset_id": "asset-duplicate",
            "release_branch_id": "release-01",
            "annual_condition_id": "D-3ms-west",
            "scenario_families": ["pipe_hole"],
            "status": "EXECUTED",
        }],
        "uncomputed_cases": [{
            "event_id": "event-duplicate",
            "asset_id": "asset-duplicate",
            "release_branch_id": "release-01",
            "annual_condition_id": "D-3ms-west",
            "scenario_families": ["vertical_handoff"],
            "status": "EXECUTED_OPERATOR_LIMITED",
            "provider_packet_identity": {
                "event_id": "event-duplicate",
                "component_id": "vertical-pipe-01",
                "port_ids": ["pipe.out"],
                "provider_source_digests": ["source-digest"],
                "provider_result_digests": ["result-digest"],
            },
        }],
    })
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": [{
            "family": "vertical_handoff",
            "status": "PARTIAL",
            "strict_uncomputed_case_count": 1,
        }]},
    )
    assert report["case_request_count"] == 1
    request = report["case_requests"][0]
    assert request["current_status"] == "EXECUTED_OPERATOR_LIMITED"
    assert request["component_id"] == "vertical-pipe-01"
    assert request["exact_match_required"]["port_ids"] == ["pipe.out"]
    assert request["scenario_families"] == ["pipe_hole", "vertical_handoff"]


def test_case_request_preserves_operating_mode_and_flags_duplicate_mode_conflict():
    assessment = _assessment()
    ledger = assessment["facility_risk_ledger"]
    ledger.update({
        "case_count": 1,
        "qualified_provider_packet_case_count": 0,
        "cases": [{
            "event_id": "event-mode-duplicate",
            "asset_id": "asset-mode-duplicate",
            "release_branch_id": "release-01",
            "annual_condition_id": "D-3ms-west",
            "hazop_scenario_id": "TK01-receiving-hole",
            "operating_mode": "receiving",
            "scenario_families": ["pipe_hole"],
            "status": "EXECUTED",
        }],
        "uncomputed_cases": [{
            "event_id": "event-mode-duplicate",
            "asset_id": "asset-mode-duplicate",
            "release_branch_id": "release-01",
            "annual_condition_id": "D-3ms-west",
            "hazop_scenario_id": "TK01-supply-hole",
            "operating_mode": "supply",
            "scenario_families": ["pipe_hole"],
            "status": "EXECUTED_OPERATOR_LIMITED",
        }],
    })
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": [{
            "family": "pipe_hole",
            "status": "PARTIAL",
            "strict_uncomputed_case_count": 1,
        }]},
    )
    request = report["case_requests"][0]
    assert request["hazop_scenario_id"] == "TK01-receiving-hole"
    assert request["exact_match_required"]["hazop_scenario_id"] == "TK01-receiving-hole"
    assert request["operating_mode"] == "receiving"
    assert request["exact_match_required"]["operating_mode"] == "receiving"
    assert any("conflicting operating modes" in reason for reason in request["blocking_reasons"])
    assert any("conflicting HAZOP scenario IDs" in reason for reason in request["blocking_reasons"])


def test_case_request_marks_missing_numerical_case_separately():
    assessment = _assessment()
    ledger = assessment["facility_risk_ledger"]
    ledger.update({
        "case_count": 1,
        "qualified_provider_packet_case_count": 0,
        "cases": [{
            "event_id": "event-missing",
            "asset_id": "asset-missing",
            "release_branch_id": "release-01",
            "annual_condition_id": "D-3ms-west",
            "scenario_families": ["pipe_hole"],
            "status": "UNCOMPUTED",
            "uncomputed_reason": "provider did not return a consequence result",
        }],
        "uncomputed_cases": [],
    })
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": [{
            "family": "pipe_hole",
            "status": "PARTIAL",
            "strict_uncomputed_case_count": 1,
        }]},
    )
    assert report["case_requests"][0]["gap_class"] == "NUMERICAL_CASE_MISSING"


def test_case_request_preserves_reviewed_frequency_port_without_provider_packet():
    assessment = _assessment()
    ledger = assessment["facility_risk_ledger"]
    ledger.update({
        "case_count": 1,
        "qualified_provider_packet_case_count": 0,
        "cases": [{
            "event_id": "event-port-bound",
            "asset_id": "asset-port-bound",
            "component_id": "pipe-01",
            "frequency_port_ids": ["pipe.out"],
            "release_branch_id": "release-01",
            "annual_condition_id": "D-3ms-west",
            "scenario_families": ["pipe_hole"],
            "status": "UNCOMPUTED",
        }],
        "uncomputed_cases": [],
    })
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": [{
            "family": "pipe_hole",
            "status": "PARTIAL",
            "strict_uncomputed_case_count": 1,
        }]},
    )
    request = report["case_requests"][0]
    assert request["frequency_port_ids"] == ["pipe.out"]
    assert request["provider_packet_port_ids"] is None
    assert request["port_binding"]["status"] == "REVIEWED_FREQUENCY_PORTS"
    assert request["exact_match_required"]["port_ids"] == ["pipe.out"]
    assert request["exact_match_required"]["reviewed_frequency_port_ids"] == ["pipe.out"]
    assert request["port_binding"]["frequency_inference_allowed"] is False
    assert report["frequency_port_binding"]["status"] == "PORT_BINDING_COMPLETE"
    assert report["frequency_port_binding"]["reviewed_frequency_port_case_count"] == 1


def test_case_request_rejects_provider_port_that_differs_from_frequency_port():
    assessment = _assessment()
    ledger = assessment["facility_risk_ledger"]
    ledger.update({
        "case_count": 1,
        "qualified_provider_packet_case_count": 0,
        "cases": [{
            "event_id": "event-port-mismatch",
            "asset_id": "asset-port-mismatch",
            "frequency_port_ids": ["pipe.out"],
            "release_branch_id": "release-01",
            "annual_condition_id": "D-3ms-west",
            "scenario_families": ["pipe_hole"],
            "status": "EXECUTED_OPERATOR_LIMITED",
            "provider_packet_identity": {
                "event_id": "event-port-mismatch",
                "component_id": "pipe-01",
                "port_ids": ["wrong.out"],
                "provider_source_digests": ["source-digest"],
                "provider_result_digests": ["result-digest"],
            },
        }],
        "uncomputed_cases": [],
    })
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": [{
            "family": "pipe_hole",
            "status": "PARTIAL",
            "strict_uncomputed_case_count": 1,
        }]},
    )
    request = report["case_requests"][0]
    assert request["port_binding"]["status"] == "PORT_BINDING_MISMATCH"
    assert request["exact_match_required"]["port_ids"] == ["pipe.out"]
    assert any("port IDs differ" in reason for reason in request["blocking_reasons"])
    assert report["frequency_port_binding"]["status"] == "PORT_BINDING_MISMATCH"
    assert report["frequency_port_binding"]["port_binding_mismatch_case_count"] == 1


def test_evidence_request_distinguishes_provider_only_ports_from_reviewed_ports():
    assessment = _assessment()
    ledger = assessment["facility_risk_ledger"]
    ledger.update({
        "case_count": 1,
        "qualified_provider_packet_case_count": 0,
        "cases": [{
            "event_id": "event-provider-only-port",
            "asset_id": "asset-provider-only-port",
            "release_branch_id": "release-01",
            "annual_condition_id": "D-3ms-west",
            "scenario_families": ["pipe_hole"],
            "status": "EXECUTED_OPERATOR_LIMITED",
            "provider_packet_identity": {
                "event_id": "event-provider-only-port",
                "component_id": "pipe-01",
                "port_ids": ["provider.out"],
                "provider_source_digests": ["source-digest"],
                "provider_result_digests": ["result-digest"],
            },
        }],
        "uncomputed_cases": [],
    })
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": [{
            "family": "pipe_hole",
            "status": "PARTIAL",
            "strict_uncomputed_case_count": 1,
        }]},
    )
    binding = report["frequency_port_binding"]
    assert binding["status"] == "PORT_BINDING_WITHHELD"
    assert binding["reviewed_frequency_port_case_count"] == 0
    assert binding["provider_packet_only_case_count"] == 1
    assert binding["reviewed_frequency_ports_complete"] is False
    assert binding["frequency_inference_allowed"] is False


def test_case_request_exposes_release_boundary_gaps_without_recalculation():
    assessment = _assessment()
    ledger = assessment["facility_risk_ledger"]
    ledger.update({
        "case_count": 1,
        "qualified_provider_packet_case_count": 0,
        "cases": [{
            "event_id": "event-boundary",
            "asset_id": "asset-boundary",
            "release_branch_id": "release-01",
            "annual_condition_id": "D-3ms-west",
            "scenario_families": ["pipe_hole"],
            "status": "EXECUTED_OPERATOR_LIMITED",
            "reason": "constant-state source boundary",
            "termination": {
                "basis": "synthetic_diagnostic_horizon",
                "time_s": 600.0,
                "provenance": "screening horizon",
            },
            "domain_assessment": {
                "domain_truncated": True,
                "inventory_outside_domain": True,
                "outside_domain_h2_kg_at_ignition": 0.25,
            },
            "mass_ledger": {"end_to_end_residual_kg": 1.0e-9},
        }],
        "uncomputed_cases": [],
    })
    report = build_facility_evidence_request(
        assessment,
        {"facility_id": "facility", "rows": [{
            "family": "pipe_hole",
            "status": "PARTIAL",
            "strict_uncomputed_case_count": 1,
        }]},
    )
    request = report["case_requests"][0]
    assert request["current_release_boundary"]["termination_basis"] == "synthetic_diagnostic_horizon"
    assert request["current_release_boundary"]["termination_time_s"] == 600.0
    assert "current release ends at a synthetic diagnostic horizon" in request[
        "current_boundary_gaps"
    ]
    assert "current consequence domain is truncated" in request["current_boundary_gaps"]
    assert "current inventory remains outside the consequence domain" in request[
        "current_boundary_gaps"
    ]
    assert any("provider qualification withheld" in item for item in request["current_boundary_gaps"])
