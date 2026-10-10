from __future__ import annotations

from lh2_tno.isolation_release_closure import audit_isolation_release_closure


def _case(branch: str, basis: str) -> dict:
    return {
        "event_id": f"event/{branch}",
        "release_branch_id": branch,
        "status": "EXECUTED",
        "termination": {"basis": basis, "time_s": 0.5},
        "mass_ledger": {"end_to_end_residual_kg": 1.0e-12},
        "provider_packet_identity": {
            "state_snapshot": {"component_id": "pipe"},
            "state_snapshot_digest": "a" * 64,
            "provider_result_digests": ["b" * 64],
        },
    }


def test_isolation_release_closure_preserves_success_and_failure_boundaries() -> None:
    report = audit_isolation_release_closure(
        {
            "facility_id": "test-facility",
            "cases": [
                _case("provider-isolation-success", "reviewed_isolation_success"),
                _case("provider-isolation-failure", "synthetic_diagnostic_horizon"),
            ],
        }
    )
    assert report["status"] == "ISOLATION_RELEASE_CLOSURE_DIAGNOSTIC"
    assert report["success_case_count"] == 1
    assert report["failure_case_count"] == 1
    assert report["mass_closed_case_count"] == 2
    assert report["qualified_provider_packet_case_count"] == 0
    assert report["barrier_probability_promoted"] is False
    assert any("synthetic diagnostic horizons" in reason for reason in report["blocking_reasons"])
