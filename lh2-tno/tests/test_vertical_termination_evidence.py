import json

from lh2_tno.vertical_termination_evidence import (
    build_vertical_termination_evidence_search,
)


def test_synthetic_vertical_horizon_remains_not_supplied(tmp_path):
    catalog = tmp_path / "vertical"
    catalog.mkdir()
    (catalog / "resolved_release_catalog.json").write_text(
        json.dumps(
            {
                "vertical-vent-campaign/terminal-valve/AREA_100%": {
                    "component_id": "terminal-pipe",
                    "provider_result_digest": "digest-1",
                    "termination_basis": "synthetic_diagnostic_horizon",
                    "termination_provenance": "synthetic history",
                    "duration_s": 0.37,
                    "available_mass_kg": 0.01,
                    "cumulative_mass_out_kg": 0.0018,
                    "vertical_handoff": {"provenance": "not independently validated"},
                }
            }
        ),
        encoding="utf-8",
    )
    (catalog / "verification.json").write_text(
        json.dumps({"mass_residual_max_kg": 0.0}),
        encoding="utf-8",
    )
    result = build_vertical_termination_evidence_search(
        catalog,
        vertical_chain_audit={
            "vertical_case_count": 2,
            "event_rows": [
                {
                    "event_id": "generic/vertical-handoff/terminal-valve/AREA_100%",
                    "case_count": 2,
                    "status": "CLOSED_OPERATOR_LIMITED_DIAGNOSTIC",
                }
            ],
        },
    )
    assert result["status"] == "SEARCH_COMPLETE_EVIDENCE_OPEN"
    assert result["source_catalog_event_count"] == 1
    assert result["not_supplied_event_count"] == 1
    assert result["not_supplied_case_count"] == 2
    row = result["rows"][0]
    assert row["status"] == "NOT_SUPPLIED"
    assert "termination_basis_synthetic_diagnostic_horizon" in row["blocking_reasons"]
    assert row["facility_case_count"] == 2


def test_reviewed_boundary_can_be_classified_valid(tmp_path):
    catalog = tmp_path / "events"
    event = catalog / "event-01"
    event.mkdir(parents=True)
    (event / "resolved_release.json").write_text(
        json.dumps(
            {
                "event_id": "vertical/AREA_1%",
                "component_id": "pipe-01",
                "provider_result_digest": "digest-2",
                "termination_basis": "reviewed_isolation_success",
                "termination_provenance": "provider zero-flow observation",
                "duration_s": 0.25,
                "available_mass_kg": 1.0,
                "cumulative_mass_out_kg": 0.2,
            }
        ),
        encoding="utf-8",
    )
    (event / "verification.json").write_text(
        json.dumps({"mass_residual_max_kg": 0.0}),
        encoding="utf-8",
    )
    result = build_vertical_termination_evidence_search(catalog)
    assert result["status"] == "SEARCH_COMPLETE_PARTIAL"
    assert result["valid_termination_event_count"] == 1
    assert result["not_supplied_event_count"] == 0
    assert result["rows"][0]["status"] == "VALID"


def test_provider_run_meta_supplies_inventory_termination_fields(tmp_path):
    catalog = tmp_path / "events"
    event = catalog / "event-02"
    event.mkdir(parents=True)
    (event / "resolved_release.json").write_text(
        json.dumps(
            {
                "event_id": "vertical/AREA_10%",
                "component_id": "pipe-02",
                "provider_result_digest": "digest-3",
                "termination_basis": "inventory_depletion_positive_threshold",
                "termination_provenance": "provider positive threshold",
                "duration_s": 0.5,
            }
        ),
        encoding="utf-8",
    )
    (event / "verification.json").write_text(
        json.dumps(
            {
                "provider_run_meta": {
                    "available_mass_kg": 1.0,
                    "cumulative_mass_out_kg": 0.2,
                    "max_abs_mass_residual_kg": 0.0,
                }
            }
        ),
        encoding="utf-8",
    )
    result = build_vertical_termination_evidence_search(catalog)
    row = result["rows"][0]
    assert row["status"] == "VALID"
    assert row["available_mass_kg"] == 1.0
    assert row["cumulative_mass_out_kg"] == 0.2
    assert row["mass_residual_kg"] == 0.0
