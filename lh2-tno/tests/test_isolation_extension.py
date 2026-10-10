from __future__ import annotations

import json
from pathlib import Path

from lh2_tno.isolation_extension import build_isolation_union_extension


ROOT = Path(__file__).resolve().parents[1]
BASE_ROOT = ROOT / "results/20261026/native_full_scope_union_assessment"
ISOLATION_ROOT = ROOT / "results/20261009/equipment_isolation_campaign"


def _inputs() -> tuple[dict, dict, dict]:
    return (
        json.loads((BASE_ROOT / "campaign_result.json").read_text(encoding="utf-8")),
        json.loads((BASE_ROOT / "scope_matrix.json").read_text(encoding="utf-8")),
        json.loads((ISOLATION_ROOT / "campaign_result.json").read_text(encoding="utf-8")),
    )


def test_isolation_extension_merges_namespaced_branches_into_facility_chain() -> None:
    base, scope, isolation = _inputs()

    report = build_isolation_union_extension(base, scope, isolation)
    merged = report["merged_campaign_result"]

    assert report["schema"] == "prism.isolation_union_extension.v1"
    assert report["status"] == "ISOLATION_UNION_EXTENSION_DIAGNOSTIC"
    assert (report["base_event_count"], report["base_case_count"], report["base_risk_atom_count"]) == (34, 44, 176)
    assert (report["isolation_event_count"], report["isolation_case_count"], report["isolation_risk_atom_count"]) == (5, 20, 80)
    assert report["isolation_branch_case_counts"] == {"success": 10, "failure": 10}
    assert (report["merged_event_count"], report["merged_case_count"], report["merged_risk_atom_count"]) == (39, 64, 256)
    assert len({row["id"] for row in merged["events"]}) == 39
    assert report["risk_atom_chain_audit"]["status"] == "FULL_RISK_ATOM_CHAIN_CLOSED_DIAGNOSTIC"
    assert report["risk_atom_chain_audit"]["complete_case_count"] == 64
    assert report["equipment_state_release_audit"]["status"] == "PARTIAL_EQUIPMENT_STATE_RELEASE_CHAIN"
    assert report["equipment_state_release_audit"]["complete_case_count"] == 44
    assert report["equipment_state_release_audit"]["incomplete_case_count"] == 20
    assert report["facility_aggregate_closure_audit"]["status"] == "FACILITY_IR_FN_AGGREGATE_CLOSED_DIAGNOSTIC"
    assert report["facility_component_contribution_audit"]["status"] == "FACILITY_COMPONENT_CONTRIBUTIONS_CLOSED_DIAGNOSTIC"
    assert report["merged_provider_packet_case_count"] == 44
    assert report["merged_qualified_provider_packet_case_count"] == 0
    assert report["merged_facility_total_risk_available"] is False
    assert report["merged_complete_facility_qra_claim"] is False


def test_isolation_extension_keeps_legacy_cases_and_marks_isolation_identity_diagnostic() -> None:
    base, scope, isolation = _inputs()

    report = build_isolation_union_extension(base, scope, isolation)
    rebound = report["isolation_rebound_result"]

    assert all(
        row["annual_condition_id"].startswith(
            f"{base['facility_id']}/isolation-response/"
        )
        for row in rebound["cases"]
    )
    assert all(row["provider_packet_identity"]["diagnostic_identity_only"] for row in rebound["cases"])
    assert all(row["domain_assessment"]["diagnostic_only"] for row in rebound["cases"])
    assert rebound["provider_packet_case_count"] == 0
    assert rebound["qualified_provider_packet_case_count"] == 0
    assert rebound["provider_packet_promoted"] is False
