from __future__ import annotations

from lh2_tno.state_release_mass_consistency_audit import (
    AUDIT_SCHEMA,
    build_state_release_mass_consistency_audit,
)


def _campaign(state_mass: object = 2.0, initial_mass: object = 2.0) -> dict:
    return {
        "cases": [{
            "event_id": "tank/hole",
            "asset_id": "tank-01",
            "provider_packet_identity": {
                "state_snapshot": {"component_id": "tank-01", "mass_kg": state_mass},
                "provider_mass_balances": [{"initial_mass_kg": initial_mass}],
            },
        }],
    }


def test_matching_mass_boundary_is_reported_as_pass() -> None:
    report = build_state_release_mass_consistency_audit(_campaign())
    assert report["schema_version"] == AUDIT_SCHEMA
    assert report["status"] == "MASS_STATE_CONSISTENCY_PASS"
    assert report["matched_case_count"] == 1
    assert report["mismatch_case_count"] == 0
    assert report["not_comparable_case_count"] == 0
    assert report["promotion_allowed"] is False


def test_mismatch_is_explicit_and_never_corrected() -> None:
    report = build_state_release_mass_consistency_audit(_campaign(0.028, 71.764))
    assert report["status"] == "MASS_STATE_CONSISTENCY_REVIEW_REQUIRED"
    assert report["mismatch_case_count"] == 1
    assert report["mismatch_rows"][0]["case_id"] == "tank/hole"
    assert report["mismatch_rows"][0]["relative_difference"] > 0.99
    assert report["provider_packet_promoted"] is False
    assert report["facility_qra_claim"] is False


def test_missing_mass_is_not_counted_as_a_match() -> None:
    report = build_state_release_mass_consistency_audit(_campaign(None, 2.0))
    assert report["status"] == "MASS_STATE_CONSISTENCY_REVIEW_REQUIRED"
    assert report["matched_case_count"] == 0
    assert report["mismatch_case_count"] == 0
    assert report["not_comparable_case_count"] == 1
