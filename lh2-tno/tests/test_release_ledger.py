from lh2_tno.release_ledger import (
    build_release_termination_inventory_ledger,
    evaluate_facility_release_boundary,
)


def test_release_ledger_preserves_provider_duration_isolation_and_inventory():
    report = build_release_termination_inventory_ledger(
        [
            {
                "event_id": "tank/hole",
                "asset_id": "tank-01",
                "release_branch_id": "isolation-success",
                "annual_condition_id": "dry",
                "status": "EXECUTED",
                "initiating_frequency_per_year": 1.0e-3,
                "release_branch_probability": 0.9,
                "termination": {
                    "basis": "reviewed_isolation_success",
                    "time_s": 0.25,
                    "provenance": "provider valve closure ledger",
                },
                "provider_packet_identity": {
                    "event_id": "tank/hole",
                    "component_id": "tank-01",
                    "provider_export_schema": "prism.resolved_release.v1",
                    "provider_source_digests": ["a" * 64],
                    "provider_result_digests": ["b" * 64],
                    "provider_boundary_references": ["outlet"],
                    "termination_bases": ["reviewed_isolation_success"],
                    "duration_s": [0.25],
                    "available_mass_kg": [10.0],
                    "cumulative_mass_out_kg": [0.2],
                },
                "mass_ledger": {
                    "released_kg": 0.2,
                    "end_to_end_residual_kg": 0.0,
                },
            },
            {
                "event_id": "tank/inventory",
                "asset_id": "tank-01",
                "release_branch_id": "missing-packet",
                "annual_condition_id": "dry",
                "status": "UNCOMPUTED",
                "reason": "provider packet missing",
                "release_branch_probability": 0.1,
            },
        ]
    )
    row = report["rows"][0]
    assert report["schema_version"] == "prism.release_termination_inventory_ledger.v1"
    assert row["ledger_status"] == "COMPLETE"
    assert row["isolation_status"] == "provider_declared_isolation_success"
    assert row["inventory_status"] == "not_inventory_termination"
    assert row["provider"]["residual_mass_kg"] == [9.8]
    assert report["rows"][1]["ledger_status"] == "UNCOMPUTED"
    assert report["summary"]["uncomputed_row_count"] == 1


def test_release_ledger_does_not_infer_inventory_from_mass_without_provider_basis():
    report = build_release_termination_inventory_ledger(
        [
            {
                "event_id": "tank/hole",
                "asset_id": "tank-01",
                "release_branch_id": "diagnostic",
                "annual_condition_id": "dry",
                "status": "EXECUTED_OPERATOR_LIMITED",
                "termination": {
                    "basis": "synthetic_diagnostic_horizon",
                    "time_s": 1.0,
                    "provenance": "screening horizon",
                },
                "mass_ledger": {
                    "released_kg": 5.0,
                    "end_to_end_residual_kg": 0.0,
                },
            },
        ]
    )
    row = report["rows"][0]
    assert row["inventory_status"] == "not_inventory_termination"
    assert row["provider"]["available_mass_kg"] is None
    assert row["ledger_status"] == "OPERATOR_LIMITED_OR_DOMAIN_INCOMPLETE"


def test_release_ledger_keeps_domain_incomplete_separate_from_operator_limited():
    report = build_release_termination_inventory_ledger(
        [{
            "event_id": "tank/full-bore",
            "status": "EXECUTED_DOMAIN_INCOMPLETE",
            "termination": {"basis": "synthetic_diagnostic_horizon", "time_s": 1.0},
            "mass_ledger": {"released_kg": 1.0, "end_to_end_residual_kg": 0.0},
        }]
    )
    assert report["rows"][0]["ledger_status"] == "DOMAIN_INCOMPLETE"
    assert report["summary"]["domain_incomplete_row_count"] == 1
    assert report["summary"]["operator_limited_or_domain_incomplete_row_count"] == 0


def test_release_ledger_summarizes_withheld_domain_case_without_duplicate_row():
    report = build_release_termination_inventory_ledger(
        [{
            "event_id": "tank/full-bore",
            "status": "EXECUTED_OPERATOR_LIMITED",
            "termination": {"basis": "synthetic_diagnostic_horizon", "time_s": 1.0},
            "mass_ledger": {"released_kg": 1.0, "end_to_end_residual_kg": 0.0},
        }],
        withheld_cases=[{
            "event_id": "tank/full-bore",
            "status": "EXECUTED_DOMAIN_INCOMPLETE",
            "reason": "outside-domain flammable mass unresolved",
        }],
    )
    assert len(report["rows"]) == 1
    assert report["summary"]["withheld_case_count"] == 1
    assert report["summary"]["withheld_domain_incomplete_case_count"] == 1


def test_facility_release_boundary_gate_accepts_reviewed_isolation_with_closed_mass():
    ledger = build_release_termination_inventory_ledger(
        [{
            "event_id": "tank/hole",
            "status": "EXECUTED",
            "termination": {
                "basis": "reviewed_isolation_success",
                "time_s": 0.25,
                "provenance": "reviewed actuator closure record",
            },
            "mass_ledger": {
                "released_kg": 0.2,
                "end_to_end_residual_kg": 2.0e-10,
            },
        }]
    )
    gate = evaluate_facility_release_boundary(ledger)
    assert gate["schema_version"] == "prism.facility_release_boundary_gate.v1"
    assert gate["strict_release_boundary_ready"] is True
    assert gate["blocking_reasons"] == []
    assert gate["facility_ir_fn_promotion"] is False
    assert gate["provider_qualification_evaluated"] is False


def test_release_ledger_treats_emergency_relief_as_a_distinct_non_isolation_boundary():
    ledger = build_release_termination_inventory_ledger(
        [{
            "event_id": "vent/emergency-relief",
            "status": "EXECUTED",
            "termination": {
                "basis": "emergency_relief_discharge",
                "time_s": 0.5,
                "provenance": "provider relief discharge history",
            },
            "mass_ledger": {
                "released_kg": 0.25,
                "end_to_end_residual_kg": 0.0,
            },
        }]
    )
    row = ledger["rows"][0]
    assert row["isolation_status"] == "not_applicable"
    assert row["inventory_status"] == "not_applicable"
    gate = evaluate_facility_release_boundary(ledger)
    assert gate["strict_release_boundary_ready"] is True
    assert gate["blocking_reasons"] == []


def test_facility_release_boundary_accepts_explicit_pressure_equalization():
    ledger = build_release_termination_inventory_ledger(
        [{
            "event_id": "vaporizer/pressure-equalization",
            "status": "EXECUTED",
            "termination": {
                "basis": "model_pressure_equalization",
                "time_s": 1.0,
                "provenance": "provider pressure and zero-flow ledger",
            },
            "provider_packet_identity": {
                "provider_result_digests": ["b" * 64],
                "provider_mass_balances": [{
                    "initial_mass_kg": 1.0,
                    "cumulative_mass_out_kg": 0.015,
                    "final_mass_kg": 0.985,
                    "derived_accounting_residual_kg": 0.0,
                    "pressure_equalization_time_s": 1.0,
                    "post_pressure_equalization_observation_s": 1.0,
                    "pressure_equalization_success": True,
                    "terminal_source_pressure_pa_abs": 99999.0,
                    "ambient_pressure_pa_abs": 100000.0,
                    "max_post_pressure_equalization_flow_kg_s": 0.0,
                }],
            },
            "mass_ledger": {
                "released_kg": 0.015,
                "end_to_end_residual_kg": 0.0,
            },
        }]
    )
    row = ledger["rows"][0]
    assert row["pressure_equalization_status"] == (
        "provider_declared_pressure_equalization"
    )
    gate = evaluate_facility_release_boundary(ledger)
    assert gate["strict_release_boundary_ready"] is True
    assert gate["blocking_reasons"] == []


def test_facility_release_boundary_rejects_pressure_equalization_without_explicit_evidence():
    ledger = build_release_termination_inventory_ledger(
        [{
            "event_id": "vaporizer/pressure-equalization-open",
            "status": "EXECUTED",
            "termination": {
                "basis": "model_pressure_equalization",
                "time_s": 1.0,
            },
            "provider_packet_identity": {
                "provider_result_digests": ["b" * 64],
                "provider_mass_balances": [{
                    "initial_mass_kg": 1.0,
                    "cumulative_mass_out_kg": 0.015,
                    "final_mass_kg": 0.985,
                    "derived_accounting_residual_kg": 0.0,
                }],
            },
            "mass_ledger": {
                "released_kg": 0.015,
                "end_to_end_residual_kg": 0.0,
            },
        }]
    )
    row = ledger["rows"][0]
    assert row["pressure_equalization_status"] == "not_declared"
    gate = evaluate_facility_release_boundary(ledger)
    assert gate["strict_release_boundary_ready"] is False
    assert any("pressure-equalization" in reason for reason in gate["blocking_reasons"])


def test_provider_mass_balance_is_carried_and_blocks_unbalanced_promotion():
    ledger = build_release_termination_inventory_ledger(
        [{
            "event_id": "pipe/isolation",
            "status": "EXECUTED",
            "termination": {
                "basis": "reviewed_isolation_success",
                "time_s": 0.25,
                "provenance": "provider isolation record",
            },
            "provider_packet_identity": {
                "provider_result_digests": ["b" * 64],
                "available_mass_kg": [2.0],
                "cumulative_mass_out_kg": [1.0],
                "provider_mass_balances": [{
                    "schema_version": "prism.provider_mass_balance.v1",
                    "initial_mass_kg": 2.0,
                    "cumulative_mass_out_kg": 1.0,
                    "final_mass_kg": 1.2,
                    "reported_residual_mass_kg": 1.2,
                    "derived_accounting_residual_kg": 0.2,
                }],
            },
            "mass_ledger": {
                "released_kg": 1.0,
                "end_to_end_residual_kg": 0.0,
            },
        }]
    )
    row = ledger["rows"][0]
    assert row["provider"]["provider_mass_balance_statuses"] == ["UNBALANCED"]
    gate = evaluate_facility_release_boundary(ledger)
    assert gate["strict_release_boundary_ready"] is False
    assert gate["checks"]["all_provider_mass_balances_closed"] is False


def test_facility_release_boundary_gate_rejects_synthetic_and_withheld_rows():
    ledger = build_release_termination_inventory_ledger(
        [{
            "event_id": "tank/diagnostic",
            "status": "EXECUTED_OPERATOR_LIMITED",
            "termination": {
                "basis": "synthetic_diagnostic_horizon",
                "time_s": 600.0,
                "provenance": "diagnostic horizon",
            },
            "mass_ledger": {
                "released_kg": 1.0,
                "end_to_end_residual_kg": 0.0,
            },
        }],
        withheld_cases=[{
            "event_id": "tank/missing",
            "status": "UNCOMPUTED",
        }],
    )
    gate = evaluate_facility_release_boundary(ledger)
    assert gate["strict_release_boundary_ready"] is False
    assert gate["checks"]["no_withheld_cases"] is False
    assert any("synthetic_diagnostic_horizon" in reason for reason in gate["blocking_reasons"])
    assert any("withheld" in reason for reason in gate["blocking_reasons"])


def test_facility_release_boundary_gate_requires_inventory_residual_to_close():
    ledger = build_release_termination_inventory_ledger(
        [{
            "event_id": "tank/inventory",
            "status": "EXECUTED",
            "termination": {
                "basis": "inventory_depletion",
                "time_s": 0.5,
                "provenance": "provider depletion callback",
            },
            "provider_packet_identity": {
                "event_id": "tank/inventory",
                "component_id": "tank-01",
                "provider_result_digests": ["b" * 64],
                "available_mass_kg": [10.0],
                "cumulative_mass_out_kg": [9.9],
            },
            "mass_ledger": {
                "released_kg": 9.9,
                "end_to_end_residual_kg": 0.1,
            },
        }]
    )
    gate = evaluate_facility_release_boundary(ledger)
    assert gate["strict_release_boundary_ready"] is False
    assert gate["checks"]["all_mass_residuals_closed"] is False
