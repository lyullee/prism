from lh2_tno.strict_eligible_facility_risk import build_strict_eligible_facility_risk_view


def _atom(status="EXECUTED", withheld=False, eligibility="ELIGIBLE_FOR_NUMERICAL_SCOPE"):
    return {
        "case_status": status,
        "case_withheld_from_strict_facility_qra": withheld,
        "risk_atom_eligibility": eligibility,
        "initiating_frequency_per_year": 1.0e-3,
        "conditional_weight": 0.5,
        "receptor_harm_low_high": {"worker-01": [1.0, 2.0]},
        "expected_deaths_low_high": [1.0, 2.0],
    }


def test_view_keeps_only_executed_non_withheld_atoms():
    result = build_strict_eligible_facility_risk_view({"facility_id": "F", "risk_atoms": [_atom(), _atom("EXECUTED_OPERATOR_LIMITED", True, "WITHHELD_FROM_STRICT_FACILITY_QRA")]})
    assert result["selected_risk_atom_count"] == 1
    assert result["excluded_risk_atom_count"] == 1
    assert result["annual_ir_low_high"]["worker-01"] == [0.0005, 0.001]
    assert result["expected_death_fn_low_high"][0]["cumulative_frequency_per_year"] == [0.0005]
    assert result["facility_qra_promotion"] is False


def test_view_is_empty_safe_for_no_selected_atoms():
    result = build_strict_eligible_facility_risk_view({"risk_atoms": [_atom("EXECUTED_OPERATOR_LIMITED", True, "WITHHELD_FROM_STRICT_FACILITY_QRA")]})
    assert result["selected_risk_atom_count"] == 0
    assert result["annual_ir_low_high"] == {}
    assert result["expected_death_fn_low_high"] == [{"expected_deaths": [], "cumulative_frequency_per_year": []}] * 2
