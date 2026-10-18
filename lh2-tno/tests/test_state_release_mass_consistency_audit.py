from __future__ import annotations

from lh2_tno.state_release_mass_consistency_audit import (
    AUDIT_SCHEMA,
    build_state_release_mass_consistency_audit,
)
from lh2_tno.state_snapshot import EQUIPMENT_STATE_SNAPSHOT_SCHEMA, EquipmentStateSnapshot


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
    assert report["mismatch_rows"][0]["classification"] == "MASS_BASIS_UNDECLARED_REVIEW_REQUIRED"
    assert report["mass_basis_review_required_case_count"] == 1
    assert report["provider_packet_promoted"] is False
    assert report["facility_qra_claim"] is False


def test_missing_mass_is_not_counted_as_a_match() -> None:
    report = build_state_release_mass_consistency_audit(_campaign(None, 2.0))
    assert report["status"] == "MASS_STATE_CONSISTENCY_REVIEW_REQUIRED"
    assert report["matched_case_count"] == 0
    assert report["mismatch_case_count"] == 0
    assert report["not_comparable_case_count"] == 1


def test_explicitly_different_mass_basis_tokens_are_not_inferred_as_equal() -> None:
    campaign = _campaign(2.0, 3.0)
    identity = campaign["cases"][0]["provider_packet_identity"]
    identity["state_snapshot"]["mass_basis_id"] = "local-vessel-inventory"
    identity["provider_mass_balances"][0]["mass_basis_id"] = "upstream-reserve"
    report = build_state_release_mass_consistency_audit(campaign)
    row = report["mismatch_rows"][0]
    assert row["classification"] == "MASS_BASIS_ID_MISMATCH_REVIEW_REQUIRED"
    assert row["state_mass_basis"] == "local-vessel-inventory"
    assert row["provider_mass_basis"] == "upstream-reserve"


def test_absent_mass_basis_is_omitted_from_legacy_snapshot_wire_shape() -> None:
    snapshot = EquipmentStateSnapshot(
        schema_version=EQUIPMENT_STATE_SNAPSHOT_SCHEMA,
        component_id="tank-01",
        captured_at_s=0.0,
        origin="model_prediction",
        pressure_pa_abs=200000.0,
        mass_kg=2.0,
    )
    assert "mass_basis_id" not in snapshot.to_mapping()
    with_basis = snapshot.model_copy(update={"mass_basis_id": "local-vessel-inventory"})
    assert with_basis.to_mapping()["mass_basis_id"] == "local-vessel-inventory"
