from lh2_tno.facility_aggregate_closure_audit import (
    build_facility_aggregate_closure_audit,
)


def _campaign():
    atoms = [
        {
            "initiating_frequency_per_year": 2.0e-5,
            "conditional_weight": 0.5,
            "receptor_harm_low_high": {"worker": [0.2, 0.4]},
            "expected_deaths_low_high": [1.0, 2.0],
        },
        {
            "initiating_frequency_per_year": 1.0e-5,
            "conditional_weight": 1.0,
            "receptor_harm_low_high": {"worker": [0.1, 0.1]},
            "expected_deaths_low_high": [0.5, 1.0],
        },
    ]
    return {
        "facility_id": "facility",
        "risk_atoms": atoms,
        "conditional_diagnostic_facility_annual_ir_low_high": {
            "worker": [3.0e-6, 5.0e-6],
        },
        "conditional_diagnostic_facility_expected_death_fn_low_high": [
            {
                "expected_deaths": [1.0],
                "cumulative_frequency_per_year": [1.0e-5],
            },
            {
                "expected_deaths": [1.0, 2.0],
                "cumulative_frequency_per_year": [2.0e-5, 1.0e-5],
            },
        ],
        "facility_total_risk_available": False,
        "complete_facility_qra_claim": False,
    }


def test_facility_aggregate_closure_reproduces_ir_and_fn():
    report = build_facility_aggregate_closure_audit(_campaign())
    assert report["status"] == "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC"
    assert report["risk_atom_count"] == 2
    assert report["ir_mismatch_count"] == 0
    assert report["fn_mismatch_count"] == 0
    assert report["diagnostic_only"] is True
    assert report["facility_qra_claim"] is False


def test_facility_aggregate_closure_fails_closed_on_changed_ir():
    campaign = _campaign()
    campaign["conditional_diagnostic_facility_annual_ir_low_high"]["worker"][0] = 9.0e-6
    report = build_facility_aggregate_closure_audit(campaign)
    assert report["status"] == "BLOCKED_FACILITY_IR_FN_AGGREGATE_CLOSURE"
    assert report["ir_mismatch_count"] == 1
    assert report["fn_mismatch_count"] == 0
    assert report["blocking_reasons"] == ["receptor worker IR differs"]
