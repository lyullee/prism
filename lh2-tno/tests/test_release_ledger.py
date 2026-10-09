from lh2_tno.release_ledger import build_release_termination_inventory_ledger


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
