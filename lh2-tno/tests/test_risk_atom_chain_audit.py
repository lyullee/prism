from lh2_tno.risk_atom_chain_audit import build_risk_atom_chain_audit


def _result():
    case = {
        "event_id": "event-1",
        "annual_condition_id": "condition-1",
        "release_branch_id": "branch-1",
        "status": "EXECUTED_OPERATOR_LIMITED",
        "termination": {"basis": "inventory_depletion", "time_s": 0.5},
        "mass_ledger": {"released_kg": 1.0, "end_to_end_residual_kg": 0.0},
        "stage_elapsed_ms": {
            "source": 1.0,
            "pool": 2.0,
            "near_field_and_dispersion": 3.0,
            "cloud_observation": 4.0,
            "fire_explosion_damage_risk": 5.0,
        },
        "domain_assessment": {"domain_truncated": False},
        "provider_packet_identity": {"event_id": "event-1"},
    }
    atoms = [
        {
            "event_id": "event-1",
            "annual_condition_id": "condition-1",
            "release_branch_id": "branch-1",
            "ignition_branch": branch,
            "receptor_harm_low_high": {"worker-1": [0.1, 0.2]},
            "expected_deaths_low_high": [0.1, 0.2],
        }
        for branch in (
            "direct_fire",
            "delayed_flash_fire",
            "delayed_explosion",
            "no_ignition",
        )
    ]
    return {"facility_id": "facility-1", "cases": [case], "risk_atoms": atoms}


def test_risk_atom_chain_audit_closes_case_to_final_damage_atoms():
    report = build_risk_atom_chain_audit(_result())
    assert report["status"] == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
    assert report["case_count"] == 1
    assert report["risk_atom_count"] == 4
    assert report["complete_case_count"] == 1
    assert report["operator_limited_case_count"] == 1
    assert report["blocking_reasons"] == []


def test_risk_atom_chain_audit_blocks_missing_stage_or_ignition_atom():
    result = _result()
    result["cases"][0]["stage_elapsed_ms"].pop("pool")
    result["risk_atoms"] = result["risk_atoms"][:-1]
    report = build_risk_atom_chain_audit(result)
    assert report["status"] == "PARTIAL_RISK_ATOM_CHAIN"
    assert report["complete_case_count"] == 0
    assert any("stage pool" in reason for reason in report["blocking_reasons"])
    assert any("four ignition branches" in reason for reason in report["blocking_reasons"])


def test_risk_atom_chain_audit_accepts_signed_roundoff_residual_and_paired_endpoints():
    result = _result()
    case = result["cases"][0]
    case["mass_ledger"]["end_to_end_residual_kg"] = -5.0e-11
    case["stage_elapsed_ms"] = {
        "endpoint_a": 3.0,
        "endpoint_b": 4.0,
        "endpoint_aggregation": 5.0,
    }
    report = build_risk_atom_chain_audit(result)
    assert report["status"] == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
    assert report["complete_case_count"] == 1
    assert report["blocking_reasons"] == []
    assert all(
        report["stage_complete_case_counts"][stage] == 1
        for stage in report["required_stage_names"]
    )


def test_risk_atom_chain_audit_distinguishes_computed_zero_harm_from_empty_harm():
    result = _result()
    for atom in result["risk_atoms"]:
        atom["receptor_harm_low_high"] = {"worker-1": [0.0, 0.0]}
        atom["expected_deaths_low_high"] = [0.0, 0.0]
    report = build_risk_atom_chain_audit(result)
    assert report["status"] == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
    assert report["zero_harm_atom_count"] == 4
    assert report["positive_harm_atom_count"] == 0
    assert report["empty_harm_atom_count"] == 0
    assert report["zero_expected_death_atom_count"] == 4
