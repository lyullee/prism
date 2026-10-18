from __future__ import annotations

import json
from pathlib import Path

from lh2_tno.chain_closure_audit import build_chain_closure_audit


def _digest(char: str) -> str:
    return char * 64


def _campaign(released_kg: float = 1.25, harm: float = 0.1) -> dict:
    event_id = "facility/tank/G1"
    source_digest = _digest("a")
    result_digest = _digest("b")
    identity = {
        "event_id": event_id,
        "component_id": "tank-01",
        "provider_export_schema": "prism.resolved_release.v1",
        "provider_result_digests": [result_digest],
        "duration_s": [2.0],
        "available_mass_kg": [5.0],
        "cumulative_mass_out_kg": [released_kg],
        "termination_bases": ["reviewed_isolation_success"],
        "termination_provenances": ["provider closed isolation"],
    }
    case = {
        "event_id": event_id,
        "annual_condition_id": "weather-1",
        "release_branch_id": "isolation-success",
        "provider_packet_identity": identity,
        "status": "EXECUTED",
        "termination": {"time_s": 2.0},
        "mass_ledger": {"released_kg": released_kg},
    }
    atom = {
        "event_id": event_id,
        "annual_condition_id": "weather-1",
        "release_branch_id": "isolation-success",
        "ignition_branch": "direct_fire",
        "initiating_frequency_per_year": 0.5,
        "conditional_weight": 0.5,
        "provider_packet_identity": identity,
        "receptor_harm_low_high": {"worker-01": [harm, harm * 2.0]},
        "expected_deaths_low_high": [harm, harm * 2.0],
    }
    return {
        "facility_id": "facility",
        "events": [{"id": event_id, "model_component_id": "tank-01"}],
        "cases": [case],
        "risk_atoms": [atom],
        "conditional_diagnostic_facility_annual_ir_low_high": {
            "worker-01": [0.025 * harm / 0.1, 0.05 * harm / 0.1]
        },
        "conditional_diagnostic_facility_expected_death_fn_low_high": [
            {"expected_deaths": [], "cumulative_frequency_per_year": []},
            {"expected_deaths": [], "cumulative_frequency_per_year": []},
        ],
        "facility_total_risk_available": False,
        "complete_facility_qra_claim": False,
    }


def _packet_evidence(tmp_path: Path, *, cumulative_mass: float = 1.25) -> dict:
    packet = {
        "provider_export_schema": "prism.resolved_release.v1",
        "event_id": "facility/tank/G1",
        "component_id": "tank-01",
        "provider_result_digest": _digest("b"),
        "duration_s": 2.0,
        "available_mass_kg": 5.0,
        "cumulative_mass_out_kg": cumulative_mass,
        "termination_basis": "reviewed_isolation_success",
        "termination_provenance": "provider closed isolation",
    }
    packet_path = tmp_path / "resolved_release.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    return {
        "qualified_provider_packet_count": 0,
        "rows": [{
            "event_id": "facility/tank/G1",
            "evidence": {"resolved_packet_paths": [str(packet_path)]},
        }],
    }


def test_release_packet_to_facility_harm_closure_is_recomputed(tmp_path: Path):
    report = build_chain_closure_audit(
        _campaign(), packet_evidence=_packet_evidence(tmp_path), packet_root=tmp_path
    )
    assert report["status"] == "PARTIAL_DIAGNOSTIC_CHAIN_CLOSED"
    assert report["packet_chain_closed_event_count"] == 1
    assert report["facility_ir_aggregate_closed"] is True
    assert report["facility_fn_aggregate_closed"] is True
    assert report["facility_total_risk_available"] is False


def test_release_value_mismatch_blocks_event_chain(tmp_path: Path):
    report = build_chain_closure_audit(
        _campaign(),
        packet_evidence=_packet_evidence(tmp_path, cumulative_mass=1.0),
        packet_root=tmp_path,
    )
    assert report["status"] == "BLOCKED_CHAIN_CLOSURE"
    assert report["packet_chain_mismatch_event_count"] == 1
    assert report["packet_chain_mismatch_event_ids"] == ["facility/tank/G1"]


def test_known_contribution_fn_fallback_is_recomputed(tmp_path: Path):
    campaign = _campaign()
    campaign["known_contribution_expected_death_fn_low_high"] = campaign.pop(
        "conditional_diagnostic_facility_expected_death_fn_low_high"
    )
    report = build_chain_closure_audit(
        campaign, packet_evidence=_packet_evidence(tmp_path), packet_root=tmp_path
    )
    assert report["diagnostic_only"] is True
    assert report["facility_fn_aggregate_closed"] is True


def test_inventory_provider_basis_alias_is_explicitly_recorded(tmp_path: Path):
    campaign = _campaign()
    campaign["cases"][0]["provider_packet_identity"]["termination_bases"] = [
        "inventory_depletion"
    ]
    campaign["cases"][0]["provider_packet_identity"]["termination_provenances"] = [
        "provider closed inventory"
    ]
    campaign["cases"][0]["termination"] = {
        "time_s": 2.0,
        "basis": "inventory_depletion",
        "provenance": "provider closed inventory",
    }
    campaign["risk_atoms"][0]["provider_packet_identity"] = dict(
        campaign["cases"][0]["provider_packet_identity"]
    )
    packet = _packet_evidence(tmp_path)
    packet_path = Path(packet["rows"][0]["evidence"]["resolved_packet_paths"][0])
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    payload["termination_basis"] = "inventory_depletion_positive_threshold"
    payload["termination_provenance"] = "provider closed inventory"
    packet_path.write_text(json.dumps(payload), encoding="utf-8")
    report = build_chain_closure_audit(
        campaign, packet_evidence=packet, packet_root=tmp_path
    )
    assert report["status"] == "PARTIAL_DIAGNOSTIC_CHAIN_CLOSED"
    assert report["termination_basis_alias_count"] == 1
    assert report["event_rows"][0]["termination_basis_aliases_applied"] == [{
        "case_index": 0,
        "packet_basis": "inventory_depletion_positive_threshold",
        "campaign_basis": "inventory_depletion",
    }]


def test_unpacketised_handoff_is_reported_without_being_substituted(tmp_path: Path):
    campaign = _campaign()
    campaign["events"].append({"id": "facility/vertical/G1", "model_component_id": "vent-01"})
    report = build_chain_closure_audit(
        campaign, packet_evidence=_packet_evidence(tmp_path), packet_root=tmp_path
    )
    assert report["status"] == "PARTIAL_DIAGNOSTIC_CHAIN_CLOSED"
    assert report["campaign_events_without_packet_count"] == 1
    vertical = next(row for row in report["event_rows"] if row["event_id"] == "facility/vertical/G1")
    assert vertical["status"] == "HANDOFF_OR_PACKET_MISSING"

def test_uncomputed_packet_evidence_row_documents_gap_without_blocking_closed_subset(tmp_path: Path):
    packet = _packet_evidence(tmp_path)
    packet["rows"].append({
        "event_id": "facility/vaporizer/G1",
        "status": "UNCOMPUTED_PROVIDER_PACKET",
        "evidence": {},
    })
    campaign = _campaign()
    campaign["events"].append({"id": "facility/vaporizer/G1", "model_component_id": "vaporizer-01"})
    report = build_chain_closure_audit(campaign, packet_evidence=packet, packet_root=tmp_path)
    assert report["status"] == "PARTIAL_DIAGNOSTIC_CHAIN_CLOSED"
    assert report["packet_chain_closed_event_count"] == 1
    assert report["campaign_events_without_packet_count"] == 1
    row = next(item for item in report["event_rows"] if item["event_id"] == "facility/vaporizer/G1")
    assert row["status"] == "HANDOFF_OR_PACKET_MISSING"
