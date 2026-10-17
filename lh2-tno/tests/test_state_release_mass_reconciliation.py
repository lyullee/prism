from __future__ import annotations

from lh2_tno.state_release_mass_reconciliation import (
    build_state_release_mass_reconciliation,
)


def _audit() -> dict:
    return {
        "status": "MASS_STATE_CONSISTENCY_REVIEW_REQUIRED",
        "case_count": 44,
        "mismatch_rows": [{
            "event_id": "facility/storage-shell/AREA_0.01%",
            "state_mass_kg": 0.028492061899609754,
            "provider_initial_mass_kg": 71.7644005715206,
            "relative_difference": 0.9996,
        }],
    }


def test_reconciliation_closes_legacy_mismatch_without_replacing_authority():
    report = build_state_release_mass_reconciliation(
        _audit(),
        [{
            "event_id": "facility/storage-shell/AREA_0.01%",
            "state_snapshot_previous_mass_kg": 0.028492061899609754,
            "state_snapshot_provider_mass_kg": 71.7644005715206,
            "provider_available_mass_kg": 71.7644005715206,
            "state_snapshot_release_mass_match": True,
            "provider_result_digest": "a" * 64,
        }],
    )

    assert report["status"] == "MASS_STATE_CONSISTENCY_RECONCILED_DIAGNOSTIC_ONLY"
    assert report["resolved_mismatch_count"] == 1
    assert report["authoritative_campaign_replaced"] is False
    assert report["promotion_allowed"] is False


def test_reconciliation_keeps_unmatched_mismatch_open():
    report = build_state_release_mass_reconciliation(_audit(), [])

    assert report["status"] == "MASS_STATE_CONSISTENCY_REVIEW_REQUIRED"
    assert report["unresolved_mismatch_count"] == 1
