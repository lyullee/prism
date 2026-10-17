import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from attach_generic_provider_chain import attach, attach_many
from build_generic_campaign_provider_evidence import build
from build_generic_quantitative_attachments import build as build_quantitative_attachments


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    handoff = json.loads(
        (ROOT / "results/20261115/generic_provider_bound_hazop_quantitative_handoff.json")
        .read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (ROOT / "results/20261115/generic_storage_provider_bound_hazop_evidence_summary.json")
        .read_text(encoding="utf-8")
    )
    return handoff, evidence


def test_provider_chain_attaches_to_one_current_and_one_forecast_request():
    handoff, evidence = _inputs()
    result = attach(handoff, evidence)

    assert result["status"] == "PROVIDER_CHAIN_ATTACHED_OPERATOR_LIMITED"
    assert result["summary"]["matched_request_count"] == 2
    assert result["summary"]["uncomputed_request_count"] == 4
    assert "SLABx_dispersion" in result["provider_evidence"]["consequence_chain"]["stages"]
    assert result["policy"]["facility_qra_promotion"] is False


def test_provider_chain_requires_exact_family_match():
    handoff, evidence = _inputs()
    evidence["exact_identity"]["hazop_scenario_family"] = "vessel_hole"
    try:
        attach(handoff, evidence)
    except ValueError as error:
        assert "exactly one" in str(error)
    else:
        raise AssertionError("mismatched provider family must be rejected")


def test_all_generic_components_attach_without_assigning_missing_cases_zero():
    handoff = json.loads(
        (ROOT / "results/20261115/generic_provider_bound_hazop_quantitative_handoff.json")
        .read_text(encoding="utf-8")
    )
    evidences = [
        json.loads((ROOT / "results/20261115/generic_storage_provider_bound_hazop_evidence_summary.json").read_text(encoding="utf-8")),
        json.loads((ROOT / "results/20261115/generic_line_provider_bound_hazop_evidence_summary.json").read_text(encoding="utf-8")),
        json.loads((ROOT / "results/20261115/generic_vent_provider_bound_hazop_evidence_summary.json").read_text(encoding="utf-8")),
    ]
    result = attach_many(handoff, evidences)
    assert result["summary"]["provider_chain_count"] == 3
    assert result["summary"]["matched_request_count"] == 6
    assert result["summary"]["uncomputed_request_count"] == 0
    assert result["policy"]["uncomputed_cases_assigned_zero"] is False
    assert result["policy"]["facility_qra_promotion"] is False


def test_campaign_case_evidence_preserves_inventory_and_slabx_stage():
    campaign = json.loads(
        (ROOT / "results/20261115/native_external_facility_full_scope_campaign_current/campaign_result.json")
        .read_text(encoding="utf-8")
    )
    packet_path = ROOT / "results/20261115/native_external_facility_full_scope_packets_current/events/005_liquid-transfer-line-01_AREA_0.01pct/resolved_release.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    evidence = build(
        campaign,
        packet,
        campaign_path=ROOT / "results/20261115/native_external_facility_full_scope_campaign_current/campaign_result.json",
        packet_path=packet_path,
        component_id="liquid-transfer-line-01",
        event_id="generic-lh2-full-scope-frequency-example/transfer-line/AREA_0.01%",
        scenario_family="pipe_hole",
    )
    assert evidence["provider_release_boundary"]["inventory_status"] == "INVENTORY_CLOSED"
    assert "SLABx_dispersion" in evidence["consequence_chain"]["stages"]
    assert evidence["policy"]["provider_qualification_claim"] is False


def test_provider_chain_converts_to_complete_current_and_forecast_contract_coverage():
    attachment = json.loads(
        (ROOT / "results/20261115/generic_provider_chain_attachment_all_components.json")
        .read_text(encoding="utf-8")
    )
    result = build_quantitative_attachments(attachment)
    assert result["summary"] == {
        "current_attachment_count": 3,
        "forecast_attachment_count": 3,
        "total_attachment_count": 6,
    }
    for mapping in (result["current_attachments"], result["forecast_attachments"]):
        assert len(mapping) == 3
        for row in mapping.values():
            assert set(row["evidence"]) == {
                "provider_release_packet",
                "frequency_binding",
                "slabx_lh2_consequence",
                "facility_condition_binding",
            }
            assert row["evidence"]["provider_release_packet"]["status"]
            assert row["evidence"]["slabx_lh2_consequence"]["status"]
    assert result["policy"]["facility_qra_promotion"] is False


def test_published_generic_handoff_consumes_quantitative_evidence_coverage():
    published = json.loads(
        (ROOT / "results/20261115/generic_outdoor_facility_hazop_quantitative_handoff.json")
        .read_text(encoding="utf-8")
    )

    assert published["current_evidence_coverage"]["status"] == "QUANTITATIVE_EVIDENCE_COVERAGE_COMPLETE"
    assert published["forecast_evidence_coverage"]["status"] == "QUANTITATIVE_EVIDENCE_COVERAGE_COMPLETE"
    assert published["current_evidence_coverage"]["summary"]["evidence_complete_count"] == 3
    assert published["forecast_evidence_coverage"]["summary"]["evidence_complete_count"] == 3
    # Evidence coverage does not promote the absent evaluator, facility IR/F-N, or QRA.
    assert published["policy"]["facility_ir_fn_calculated"] is False
    assert published["policy"]["facility_qra_promotion"] is False
