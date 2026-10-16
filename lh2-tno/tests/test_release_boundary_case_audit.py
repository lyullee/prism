from lh2_tno.release_boundary_case_audit import build_release_boundary_case_audit


def _case(event_id, *, status="EXECUTED", basis="reviewed_isolation_success", origins=None, domain_truncated=False):
    origins = ["model_prediction"] if origins is None else origins
    identity = {
        "component_id": "component-1",
        "input_origins": origins,
        "physical_validation_claim": False,
        "provider_source_digests": ["source"],
        "provider_result_digests": ["result"],
    }
    return {
        "event_id": event_id,
        "asset_id": "asset-1",
        "frequency_port_ids": ["port-1"],
        "operating_mode": "receiving",
        "hazop_scenario_id": "hazop-1",
        "scenario_families": ["vessel_hole"],
        "status": status,
        "provider_packet_identity": identity,
        "domain_assessment": {"domain_truncated": domain_truncated},
    }


def _ledger_row(event_id, *, status="EXECUTED", basis="reviewed_isolation_success", residual=0.0, provider_residual=None):
    return {
        "event_id": event_id,
        "asset_id": "asset-1",
        "status": status,
        "ledger_status": "COMPLETE" if status == "EXECUTED" else "OPERATOR_LIMITED_OR_DOMAIN_INCOMPLETE",
        "termination": {"basis": basis, "time_s": 0.5, "provenance": "test"},
        "isolation_status": "provider_declared_isolation_success" if basis == "reviewed_isolation_success" else "not_declared",
        "inventory_status": "provider_declared_inventory_depletion" if basis == "inventory_depletion" else "not_inventory_termination",
        "provider": {
            "provider_mass_balance_statuses": ["CLOSED"],
            "duration_s": [0.5],
            "available_mass_kg": [10.0],
            "cumulative_mass_out_kg": [3.0],
            "residual_mass_kg": provider_residual,
        },
        "mass_ledger": {"end_to_end_residual_kg": residual},
    }


def _assessment(cases, rows, *, events=None):
    return {"facility_risk_ledger": {
        "cases": cases,
        "release_termination_inventory_ledger": {"rows": rows},
        "events": list(events or []),
    }}


def test_case_audit_keeps_release_boundary_and_provider_qualification_separate():
    report = build_release_boundary_case_audit(_assessment(
        [_case("good")],
        [_ledger_row("good")],
    ))
    assert report["status"] == "CASE_BOUNDARY_CLOSED"
    assert report["strict_release_boundary_eligible_case_count"] == 1
    row = report["rows"][0]
    assert row["strict_release_boundary_status"] == "ELIGIBLE"
    assert row["facility_qra_promotion_eligible"] is False
    assert "provider_input_is_not_actual_field_data" in row["provider_qualification_blocking_reasons"]
    assert row["evidence_request_status"] == "OPEN"
    assert any("qualification sidecar" in item for item in row["required_evidence"])
    assert row["release_duration_s"] == [0.5]
    assert row["available_mass_kg"] == [10.0]
    assert row["residual_fraction"] == []
    assert row["numerical_closure_status"] == "NUMERICALLY_CLOSED"
    assert row["consequence_domain_status"] == "CLOSED"


def test_case_audit_rechecks_literature_frequency_event_and_port_binding():
    case = _case("event-1")
    row = _ledger_row("event-1")
    report = build_release_boundary_case_audit(
        _assessment(
            [case],
            [row],
            events=[{
                "id": "event-1",
                "port_ids": ["port-1"],
                "annual_frequency_per_year": 2.5e-4,
                "marginal_p05_per_year": 1.0e-4,
                "marginal_p95_per_year": 5.0e-4,
                "statistic": "published",
                "source": "literature:example",
                "source_sha256": "a" * 64,
            }],
        )
    )
    audited = report["rows"][0]
    assert audited["frequency_binding_status"] == "BOUND"
    assert audited["frequency_uncertainty_status"] == "BOUND"
    assert audited["initiating_frequency_per_year"] == 2.5e-4
    assert audited["frequency_marginal_p05_per_year"] == 1.0e-4
    assert audited["frequency_marginal_p95_per_year"] == 5.0e-4
    assert audited["frequency_inference_performed"] is False
    assert report["frequency_binding_status_counts"] == {"BOUND": 1}
    assert report["frequency_unbound_case_count"] == 0
    assert report["frequency_uncertainty_status_counts"] == {"BOUND": 1}
    assert report["frequency_uncertainty_unavailable_case_count"] == 0


def test_case_audit_keeps_point_rate_when_literature_interval_is_missing():
    report = build_release_boundary_case_audit(
        _assessment(
            [_case("point-rate-event")],
            [_ledger_row("point-rate-event")],
            events=[{
                "id": "point-rate-event",
                "port_ids": ["port-1"],
                "annual_frequency_per_year": 2.5e-4,
                "statistic": "published_default",
                "source": "literature:point-rate-only",
                "source_sha256": "b" * 64,
            }],
        )
    )
    audited = report["rows"][0]
    assert audited["frequency_binding_status"] == "BOUND"
    assert audited["frequency_uncertainty_status"] == "NOT_AVAILABLE"
    assert audited["initiating_frequency_per_year"] == 2.5e-4
    assert audited["frequency_marginal_p05_per_year"] is None
    assert audited["frequency_marginal_p95_per_year"] is None
    assert audited["frequency_inference_performed"] is False
    assert report["frequency_uncertainty_status_counts"] == {"NOT_AVAILABLE": 1}
    assert report["frequency_uncertainty_unavailable_case_count"] == 1


def test_case_audit_blocks_horizon_and_operator_limited_rows():
    cases = [
        _case("limited", status="EXECUTED_OPERATOR_LIMITED"),
        _case("horizon"),
        _case("inventory"),
    ]
    rows = [
        _ledger_row("limited", status="EXECUTED_OPERATOR_LIMITED"),
        _ledger_row("horizon", basis="inventory_over_600s"),
        _ledger_row("inventory", basis="inventory_depletion", provider_residual=[0.2]),
    ]
    report = build_release_boundary_case_audit(_assessment(cases, rows))
    assert report["status"] == "CASE_BOUNDARY_BLOCKED"
    assert report["strict_release_boundary_eligible_case_count"] == 0
    reasons = {
        reason
        for row in report["rows"]
        for reason in row["release_boundary_blocking_reasons"]
    }
    assert "status_executed_operator_limited" in reasons
    assert "termination_basis_inventory_over_600s_is_not_allowed" in reasons
    assert "provider_inventory_residual_not_depleted" in reasons
    assert all(row["required_evidence"] for row in report["rows"])
    assert report["numerical_closure_status_counts"]["NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED"] == 1
    assert report["numerical_closure_status_counts"]["NUMERICALLY_OPEN"] == 2
    assert report["operator_review_required_case_count"] == 1


def test_case_audit_records_domain_truncation_and_does_not_promote_facility_qra():
    report = build_release_boundary_case_audit(_assessment(
        [_case("truncated", domain_truncated=True)],
        [_ledger_row("truncated")],
    ))
    row = report["rows"][0]
    assert row["strict_release_boundary_status"] == "PROMOTION_BLOCKED"
    assert "consequence_domain_truncated" in row["release_boundary_blocking_reasons"]
    assert row["numerical_closure_status"] == "NUMERICALLY_CLOSED"
    assert row["consequence_domain_status"] == "TRUNCATED"
    assert report["consequence_domain_truncated_case_count"] == 1
    assert report["provider_qualification_claim"] is False
    assert report["facility_ir_fn_promotion"] is False


def test_case_audit_fails_closed_when_case_and_release_ledgers_do_not_align():
    report = build_release_boundary_case_audit(_assessment(
        [_case("case-only")],
        [_ledger_row("ledger-only")],
    ))
    assert report["status"] == "CASE_BOUNDARY_BLOCKED"
    assert report["source_alignment_status"] == "BLOCKED"
    assert "case_rows_missing_from_release_ledger" in report["source_alignment_blocking_reasons"]
    assert "release_ledger_rows_missing_case_metadata" in report["source_alignment_blocking_reasons"]


def test_case_audit_uses_event_branch_and_annual_condition_as_case_key():
    first_case = _case("same-event")
    second_case = _case("same-event")
    first_case.update({"release_branch_id": "branch-a", "annual_condition_id": "weather-a"})
    second_case.update({"release_branch_id": "branch-b", "annual_condition_id": "weather-b"})
    first_row = _ledger_row("same-event")
    second_row = _ledger_row("same-event")
    first_row.update({"release_branch_id": "branch-a", "annual_condition_id": "weather-a"})
    second_row.update({"release_branch_id": "branch-b", "annual_condition_id": "weather-b"})
    report = build_release_boundary_case_audit(
        _assessment([first_case, second_case], [first_row, second_row])
    )
    assert report["source_alignment_status"] == "ALIGNED"
    assert len({row["case_key"] for row in report["rows"]}) == 2


def test_case_audit_cross_checks_facility_evidence_request_catalog():
    report = build_release_boundary_case_audit(
        _assessment([_case("good")], [_ledger_row("good")]),
        facility_evidence_request={
            "case_requests": [{
                "event_id": "good",
                "annual_condition_id": None,
                "release_branch_id": None,
                "request_id": "request-good",
                "required_provider_evidence": ["provider history"],
            }]
        },
    )
    assert report["facility_evidence_request_alignment_status"] == "ALIGNED"
    row = report["rows"][0]
    assert row["facility_evidence_request_match"] is True
    assert row["facility_evidence_request_id"] == "request-good"
    assert row["facility_evidence_required_provider_evidence_count"] == 1


def test_case_audit_blocks_missing_facility_evidence_request_case():
    report = build_release_boundary_case_audit(
        _assessment([_case("good")], [_ledger_row("good")]),
        facility_evidence_request={"case_requests": []},
    )
    assert report["status"] == "CASE_BOUNDARY_BLOCKED"
    assert report["facility_evidence_request_alignment_status"] == "BLOCKED"
    assert report["rows"][0]["facility_evidence_request_match"] is False


def test_case_audit_reports_request_contract_status_and_root_status():
    report = build_release_boundary_case_audit(
        _assessment([_case("good")], [_ledger_row("good")]),
        facility_evidence_request={
            "status": "OPEN_EVIDENCE_REQUEST",
            "frequency_inference_allowed": False,
            "facility_qra_allowed": False,
            "case_requests": [{
                "event_id": "good",
                "annual_condition_id": None,
                "release_branch_id": None,
                "request_id": "request-good",
                "qualification_required": True,
                "required_provider_evidence": ["provider history"],
            }],
        },
    )
    assert report["facility_evidence_request_status"] == "OPEN_EVIDENCE_REQUEST"
    assert report["facility_evidence_request_contract_status_counts"] == {"ALIGNED": 1}
    assert report["rows"][0]["facility_evidence_request_status"] == "OPEN_EVIDENCE_REQUEST"
    assert report["rows"][0]["facility_evidence_request_contract_status"] == "ALIGNED"


def test_case_audit_blocks_contradictory_request_contract():
    report = build_release_boundary_case_audit(
        _assessment([_case("good")], [_ledger_row("good")]),
        facility_evidence_request={
            "status": "OPEN_EVIDENCE_REQUEST",
            "frequency_inference_allowed": True,
            "facility_qra_allowed": False,
            "case_requests": [{
                "event_id": "good",
                "annual_condition_id": None,
                "release_branch_id": None,
                "request_id": "request-good",
                "qualification_required": True,
                "required_provider_evidence": [],
            }],
        },
    )
    row = report["rows"][0]
    assert row["facility_evidence_request_contract_status"] == "BLOCKED"
    assert "facility_evidence_request_required_evidence_missing" in row[
        "facility_evidence_request_contract_blocking_reasons"
    ]
    assert "facility_evidence_request_allows_frequency_inference" in row[
        "facility_evidence_request_contract_blocking_reasons"
    ]


def test_case_audit_aggregates_release_boundary_by_asset():
    first = _case("same-event")
    second = _case("same-event")
    first.update({"asset_id": "tank", "release_branch_id": "branch-a"})
    second.update({"asset_id": "pipe", "release_branch_id": "branch-b"})
    first_row = _ledger_row("same-event")
    second_row = _ledger_row("same-event")
    first_row.update({"asset_id": "tank", "release_branch_id": "branch-a"})
    second_row.update({"asset_id": "pipe", "release_branch_id": "branch-b", "status": "EXECUTED_OPERATOR_LIMITED"})
    report = build_release_boundary_case_audit(
        _assessment([first, second], [first_row, second_row])
    )
    assert set(report["asset_summary"]) == {"pipe", "tank"}
    assert report["asset_summary"]["tank"]["case_count"] == 1
    assert report["asset_summary"]["tank"]["strict_release_boundary_eligible_case_count"] == 1
    assert report["asset_summary"]["pipe"]["strict_release_boundary_blocked_case_count"] == 1
    assert report["asset_summary"]["pipe"]["blocking_reason_counts"][
        "status_executed_operator_limited"
    ] == 1


def test_case_audit_accepts_explicit_positive_threshold_without_zeroing_residual():
    case = _case("inventory-threshold")
    row = _ledger_row(
        "inventory-threshold",
        basis="inventory_depletion",
        provider_residual=[7.0],
    )
    evidence = {
        "schema_version": "prism.provider_termination_evidence_catalog.v1",
        "rows": [{
            "event_id": "inventory-threshold",
            "provider_result_digest": "result",
            "termination_basis": "inventory_depletion_positive_threshold",
            "available_mass_kg": 10.0,
            "cumulative_mass_out_kg": 3.0,
            "threshold_mass_kg": 7.1,
            "remaining_mass_kg": 7.0,
            "max_abs_mass_residual_kg": 0.0,
        }],
    }
    report = build_release_boundary_case_audit(
        _assessment([case], [row]),
        provider_termination_evidence=evidence,
    )
    result = report["rows"][0]
    assert result["provider_termination_evidence_status"] == "VALID"
    assert result["provider_termination_evidence_used"] is True
    assert result["residual_closure_basis"] == "inventory_depletion_positive_threshold"
    assert "provider_inventory_residual_not_depleted" not in result[
        "release_boundary_blocking_reasons"
    ]
    assert result["residual_mass_kg"] == [7.0]
    assert report["strict_release_boundary_eligible_case_count"] == 1
    assert report["numerically_closed_case_count"] == 1


def test_case_audit_rejects_termination_evidence_digest_mismatch():
    case = _case("inventory-bad-evidence")
    row = _ledger_row(
        "inventory-bad-evidence",
        basis="inventory_depletion",
        provider_residual=[7.0],
    )
    evidence = {
        "rows": [{
            "event_id": "inventory-bad-evidence",
            "provider_result_digest": "wrong-result",
            "termination_basis": "inventory_depletion_positive_threshold",
            "available_mass_kg": 10.0,
            "cumulative_mass_out_kg": 3.0,
            "threshold_mass_kg": 7.1,
            "remaining_mass_kg": 7.0,
            "max_abs_mass_residual_kg": 0.0,
        }],
    }
    report = build_release_boundary_case_audit(
        _assessment([case], [row]),
        provider_termination_evidence=evidence,
    )
    result = report["rows"][0]
    assert result["provider_termination_evidence_status"] == "INVALID"
    assert result["provider_termination_evidence_used"] is False
    assert "provider_termination_evidence_invalid" in result[
        "release_boundary_blocking_reasons"
    ]
    assert "provider_inventory_residual_not_depleted" in result[
        "release_boundary_blocking_reasons"
    ]
    assert report["provider_termination_evidence_invalid_case_count"] == 1


def test_case_audit_accepts_provider_owned_reviewed_isolation_evidence():
    case = _case("reviewed-isolation")
    row = _ledger_row("reviewed-isolation")
    evidence = {
        "rows": [{
            "event_id": "reviewed-isolation",
            "provider_result_digest": "result",
            "termination_basis": "reviewed_isolation_success",
            "available_mass_kg": 10.0,
            "cumulative_mass_out_kg": 3.0,
            "isolation_success": True,
            "isolation_time_s": 0.1,
            "post_isolation_observation_s": 0.2,
            "termination_provenance": "provider outlet remained closed through observation",
            "post_isolation_zero_flow": True,
        }],
    }
    report = build_release_boundary_case_audit(
        _assessment([case], [row]),
        provider_termination_evidence=evidence,
    )
    result = report["rows"][0]
    assert result["provider_termination_evidence_status"] == "VALID"
    assert result["provider_termination_evidence_used"] is True
    assert result["residual_closure_basis"] == "reviewed_isolation_success"


def test_case_audit_accepts_emergency_relief_only_with_relief_specific_evidence():
    case = _case("emergency-relief")
    row = _ledger_row("emergency-relief", basis="emergency_relief_discharge")
    evidence = {
        "rows": [{
            "event_id": "emergency-relief",
            "provider_result_digest": "result",
            "termination_basis": "emergency_relief_discharge",
            "event_kind": "emergency_relief",
            "source_operator": "equipment_emergency_relief",
            "failure_opening_diameter_m": None,
            "available_mass_kg": 10.0,
            "cumulative_mass_out_kg": 3.0,
            "duration_s": 0.5,
            "termination_history_sample_count": 10,
            "relief_setpoint_pa": 102000.0,
            "relief_capacity_kg_s": 0.5,
            "discharge_complete": True,
            "termination_provenance": "provider relief setpoint reached and discharge ended",
            "max_abs_mass_residual_kg": 0.0,
        }],
    }
    report = build_release_boundary_case_audit(
        _assessment([case], [row]),
        provider_termination_evidence=evidence,
    )
    result = report["rows"][0]
    assert result["provider_termination_evidence_status"] == "VALID"
    assert result["provider_termination_evidence_used"] is True
    assert result["residual_closure_basis"] == "emergency_relief_discharge"
    assert result["release_boundary_blocking_reasons"] == []
    assert result["strict_release_boundary_eligible"] is True


def test_case_audit_keeps_emergency_relief_open_without_relief_specific_evidence():
    case = _case("emergency-relief-open")
    row = _ledger_row("emergency-relief-open", basis="emergency_relief_discharge")
    evidence = {
        "rows": [{
            "event_id": "emergency-relief-open",
            "provider_result_digest": "result",
            "termination_basis": "emergency_relief_discharge",
            "event_kind": "emergency_relief",
            "available_mass_kg": 10.0,
            "cumulative_mass_out_kg": 3.0,
            "duration_s": 0.5,
            "max_abs_mass_residual_kg": 0.0,
        }],
    }
    report = build_release_boundary_case_audit(
        _assessment([case], [row]),
        provider_termination_evidence=evidence,
    )
    result = report["rows"][0]
    assert result["provider_termination_evidence_status"] == "INVALID"
    assert result["strict_release_boundary_eligible"] is False
    assert "provider_termination_evidence_invalid" in result[
        "release_boundary_blocking_reasons"
    ]
    assert "provider_termination_evidence_source_operator_is_emergency_relief" in result[
        "provider_termination_evidence_blocking_reasons"
    ]


def test_case_audit_accepts_paired_two_sided_provider_evidence():
    case = _case("two-sided")
    case["provider_packet_identity"]["provider_result_digests"] = ["left", "right"]
    row = _ledger_row("two-sided", basis="two_sided_rupture")
    row["provider"].update({
        "duration_s": [0.5, 0.5],
        "available_mass_kg": [10.0, 10.0],
        "cumulative_mass_out_kg": [3.0, 3.0],
        "residual_mass_kg": [7.0, 7.0],
    })
    evidence = {
        "rows": [{
            "event_id": "two-sided",
            "provider_result_digest": "set-digest",
            "provider_result_digests": ["left", "right"],
            "termination_basis": "two_sided_rupture",
            "available_mass_kg": [10.0, 10.0],
            "cumulative_mass_out_kg": [3.0, 3.0],
            "max_abs_mass_residual_kg": 0.0,
            "endpoint_count": 2,
            "termination_provenance": "paired endpoint histories share one provider inventory",
        }],
    }
    report = build_release_boundary_case_audit(
        _assessment([case], [row]),
        provider_termination_evidence=evidence,
    )
    result = report["rows"][0]
    assert result["provider_termination_evidence_status"] == "VALID"
    assert result["provider_termination_evidence_used"] is True
    assert result["numerical_closure_status"] == "NUMERICALLY_CLOSED"


def test_case_audit_selects_provider_replay_by_exact_digest():
    case = _case("replayed-event")
    row = _ledger_row("replayed-event")
    evidence = {
        "rows": [
            {
                "event_id": "replayed-event",
                "provider_result_digest": "old-result",
                "termination_basis": "reviewed_isolation_success",
                "available_mass_kg": 10.0,
                "cumulative_mass_out_kg": 3.0,
                "isolation_success": True,
                "isolation_time_s": 0.1,
                "post_isolation_observation_s": 0.2,
                "termination_provenance": "old replay",
            },
            {
                "event_id": "replayed-event",
                "provider_result_digest": "result",
                "termination_basis": "reviewed_isolation_success",
                "available_mass_kg": 10.0,
                "cumulative_mass_out_kg": 3.0,
                "isolation_success": True,
                "isolation_time_s": 0.1,
                "post_isolation_observation_s": 0.2,
                "termination_provenance": "new replay",
            },
        ]
    }
    report = build_release_boundary_case_audit(
        _assessment([case], [row]),
        provider_termination_evidence=evidence,
    )
    result = report["rows"][0]
    assert result["provider_termination_evidence_status"] == "VALID"
    assert result["provider_termination_evidence_used"] is True
    assert result["provider_termination_evidence_digest"] == "result"
