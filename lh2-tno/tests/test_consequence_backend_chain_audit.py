from __future__ import annotations

from copy import deepcopy

from lh2_tno.consequence_backend_chain_audit import audit_consequence_backend_chain


CONTRACT = {
    "schema_version": "prism.consequence_backend_chain_contract.v1",
    "contract_id": "test-chain",
    "stages": [
        {"stage_id": "source", "owner": "LH2 equipment process", "required_case_fields": ["termination"]},
        {"stage_id": "pool", "owner": "DynamicLH2PoolX", "required_case_fields": ["mass_ledger.released_kg"]},
        {"stage_id": "near_field_and_dispersion", "owner": "SLABx-LH2", "required_case_fields": ["domain_assessment"]},
        {"stage_id": "cloud_observation", "owner": "SLABx-LH2", "required_case_fields": ["receptor_harm_low_high"]},
        {"stage_id": "fire_explosion_damage_risk", "owner": "PRISM", "required_case_fields": ["expected_deaths_low_high"]},
    ],
}


def _case() -> dict:
    return {
        "event_id": "e-1",
        "backend_config_digest": "backend",
        "adapter_source_digest": "adapter",
        "provider_packet_identity": {"event_id": "e-1"},
        "termination": {"basis": "inventory_depletion"},
        "mass_ledger": {"released_kg": 1.0},
        "domain_assessment": {"domain_truncated": False},
        "receptor_harm_low_high": {"worker": [0.0, 1.0]},
        "expected_deaths_low_high": [0.0, 1.0],
        "stage_elapsed_ms": {
            "source": 1.0,
            "pool": 2.0,
            "near_field_and_dispersion": 3.0,
            "cloud_observation": 4.0,
            "fire_explosion_damage_risk": 5.0,
        },
    }


def test_backend_chain_closes_case_and_declares_models() -> None:
    report = audit_consequence_backend_chain({"status": "PARTIAL_FACILITY_SCOPE", "cases": [_case()]}, CONTRACT)
    assert report["status"] == "FULL_CONSEQUENCE_BACKEND_CHAIN_DIAGNOSTIC"
    assert report["closed_case_count"] == 1
    assert report["stage_coverage"]["near_field_and_dispersion"] == 1
    assert report["policy"]["facility_ir_fn_promotion"] is False


def test_backend_chain_blocks_missing_stage_and_case_field() -> None:
    campaign = {"status": "PARTIAL_FACILITY_SCOPE", "cases": [deepcopy(_case())]}
    del campaign["cases"][0]["domain_assessment"]
    contract = deepcopy(CONTRACT)
    contract["stages"] = [row for row in contract["stages"] if row["stage_id"] != "pool"]
    report = audit_consequence_backend_chain(campaign, contract)
    assert report["status"] == "INCOMPLETE_CONSEQUENCE_BACKEND_CHAIN"
    assert any("pool" in reason for reason in report["blocking_reasons"])
    assert report["closed_case_count"] == 0


def test_backend_chain_does_not_substitute_default_path_for_unknown_family() -> None:
    campaign = {"status": "PARTIAL_FACILITY_SCOPE", "cases": [deepcopy(_case())]}
    campaign["cases"][0]["scenario_families"] = ["unsupported_accident_family"]
    contract = deepcopy(CONTRACT)
    contract["paths"] = [{
        "path_id": "default",
        "stage_ids": [row["stage_id"] for row in contract["stages"]],
        "scenario_families": [],
        "required_case_fields": [],
        "required_atom_fields": [],
    }]

    report = audit_consequence_backend_chain(campaign, contract)

    assert report["status"] == "INCOMPLETE_CONSEQUENCE_BACKEND_CHAIN"
    assert report["closed_case_count"] == 0
    assert any(
        "no backend path matches" in reason
        for reason in report["case_rows"][0]["blocking_reasons"]
    )

