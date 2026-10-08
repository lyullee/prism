from lh2_tno.completion_audit import build_ijhe_completion_audit


def _campaign_result(total=True):
    return {
        "events": [{"id": "event-1"}],
        "cases": [{
            "status": "EXECUTED",
            "termination": {"basis": "synthetic", "time_s": 0.2},
            "mass_ledger": {"end_to_end_residual_kg": 0.0},
        }],
        "timing": {"fresh_physics_cases": 1, "campaign_elapsed_ms": 12.5},
        "total_facility_annual_ir_low_high": {"r1": [1e-6, 2e-6]} if total else None,
        "total_facility_expected_death_fn_low_high": [[], []] if total else None,
    }


def _matrix(complete=True):
    return {
        "matrix_complete": complete,
        "blocking_reasons": [] if complete else ["pipe_hole: UNCOMPUTED"],
        "required_families": ["pipe_hole"],
    }


def _status(validated=True):
    return {
        "physical_validation_claim": validated,
        "physical_validation_evidence_status": "INDEPENDENT_END_TO_END" if validated else "RESTRICTED",
        "provider_release_contract_actual_facility_packet_available": validated,
        "external_provider_evidence_release_inventory_status": "QUALIFIED_ACCIDENT_RELEASE_EXPORT" if validated else "NO_ACCIDENT_RELEASE_EXPORT",
        "one_hz_fresh_physics_demonstrated": False,
    }


def test_completion_audit_blocks_incomplete_facility_claim():
    report = build_ijhe_completion_audit(
        _status(False),
        _matrix(False),
        _campaign_result(False),
        {"scenarios": [{"id": "known"}], "facility_credible_interval": False},
    )
    assert report["status"] == "INCOMPLETE_EVIDENCE"
    assert report["complete_facility_qra_claim"] is False
    assert len(report["blocking_reasons"]) == 5


def test_completion_audit_passes_only_when_every_claim_gate_is_present():
    report = build_ijhe_completion_audit(
        _status(True),
        _matrix(True),
        _campaign_result(True),
        {"scenarios": [{"id": "complete"}], "facility_credible_interval": True},
    )
    assert report["status"] == "READY_FOR_IJHE_SCOPE"
    assert report["complete_facility_qra_claim"] is True
    assert not report["blocking_reasons"]
