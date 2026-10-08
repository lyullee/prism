import json
from pathlib import Path


def test_external_lh2dt_evidence_is_screening_only_and_cannot_be_a_release_packet():
    root = Path(__file__).parents[1]
    evidence = json.loads(
        (root / "examples" / "external_lh2dt_screening_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    screening = evidence["screening_model_evidence"]
    policy = evidence["promotion_policy"]
    assert screening["projected_asset_constructable_count"] == 12
    assert screening["confirmed_center_asset_count"] == 0
    assert screening["forward_comparison_ready_count"] == 0
    assert screening["resolved_accident_release_packet_count"] == 0
    assert policy["status"] == "SCREENING_ONLY_NO_RELEASE_PACKET"
    assert policy["promotion_allowed"] is False


def test_reference_pid_evidence_does_not_promote_center_netlist():
    root = Path(__file__).parents[1]
    evidence = json.loads(
        (root / "examples" / "external_lh2dt_screening_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    pid = evidence["reference_tank_pid_evidence"]
    assert pid["source_hash_matches"] is True
    assert pid["internal_consistency_passed"] is True
    assert pid["center_port_netlist_promotion_allowed"] is False
