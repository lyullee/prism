import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_generic_facility_hazop_handoff import build_handoff


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    frames = json.loads((ROOT / "examples/generic_facility_forecast_frames.json").read_text(encoding="utf-8"))
    tables = json.loads((ROOT / "examples/generic_facility_hazop_tables.json").read_text(encoding="utf-8"))
    current_frames = json.loads((ROOT / "examples/generic_facility_current_frames.json").read_text(encoding="utf-8"))
    return frames, tables, current_frames


def test_generic_facility_hazop_handoff_covers_all_components_and_modes():
    result = build_handoff(*_inputs())

    assert result["schema_version"] == "prism.generic_outdoor_facility_hazop_handoff.v1"
    assert result["component_ids"] == [
        "liquid-transfer-line-01",
        "pressure-relief-vent-01",
        "storage-tank-01",
    ]
    assert result["operating_modes"] == ["receiving", "standby", "supply"]
    assert result["scan"]["trigger_count"] == 3
    assert result["scan"]["evaluated_count"] == 0
    assert result["scan"]["withheld_count"] == 3
    assert result["quantitative_handoff"]["summary"]["request_count"] == 3
    assert result["current_state_handoff"]["summary"]["request_count"] == 3
    assert result["current_state_handoff"]["status"] == "CURRENT_HAZOP_SELECTION_COMPLETE"
    assert result["current_evidence_coverage"]["status"] == "WITHHELD_QUANTITATIVE_EVIDENCE_MISSING"
    assert result["forecast_evidence_coverage"]["summary"]["evidence_missing_count"] == 3
    assert result["policy"]["operating_mode_taken_from_forecast_input"] is True
    assert result["policy"]["operating_mode_inferred"] is False


def test_generic_facility_hazop_handoff_keeps_quantitative_evidence_withheld():
    result = build_handoff(*_inputs())

    requests = result["quantitative_handoff"]["requests"]
    assert {row["status"] for row in requests} == {"READY_FOR_QUANTITATIVE_EVALUATION"}
    assert {row["operating_mode"] for row in requests} == {"receiving", "supply", "standby"}
    assert all(
        "qualified_provider_release_packet" in row["required_inputs"]
        and "SLABx-LH2_consequence_result" in row["required_inputs"]
        for row in requests
    )
    policy = result["quantitative_handoff"]["policy"]
    assert policy["provider_release_created"] is False
    assert policy["slabx_lh2_calculated"] is False
    assert policy["facility_ir_fn_calculated"] is False
    current_requests = result["current_state_handoff"]["requests"]
    assert {row["source_trigger_type"] for row in current_requests} == {"CURRENT_HAZOP_DEVIATION"}
    assert {row["operating_mode"] for row in current_requests} == {"receiving", "supply", "standby"}


def test_generic_handoff_rejects_missing_component_table():
    frames, tables, current_frames = _inputs()
    tables.pop("storage-tank-01")
    try:
        build_handoff(frames, tables, current_frames)
    except ValueError as error:
        assert "cover exactly" in str(error)
    else:
        raise AssertionError("missing component table must be rejected")


def test_current_and_forecast_worklists_preserve_the_same_scenario_families():
    result = build_handoff(*_inputs())
    current = {
        (row["component_id"], row["scenario_family"], row["operating_mode"])
        for row in result["current_state_handoff"]["requests"]
    }
    forecast = {
        (row["component_id"], row["scenario_family"], row["operating_mode"])
        for row in result["quantitative_handoff"]["requests"]
    }
    assert current == forecast


def test_evidence_coverage_rejects_extra_attachment_keys():
    frames, tables, current_frames = _inputs()
    attachments = {"unexpected": {"evidence": {}}}
    result = build_handoff(frames, tables, current_frames, attachments, {})
    coverage = result["current_evidence_coverage"]
    assert coverage["status"] == "WITHHELD_QUANTITATIVE_EVIDENCE_MISSING"
    assert coverage["summary"]["extra_attachment_key_count"] == 1


def test_attached_provider_chain_is_exposed_without_frequency_inference():
    frames, _, current_frames = _inputs()
    tables = json.loads(
        (ROOT / "examples/generic_provider_bound_hazop_tables.json").read_text(
            encoding="utf-8"
        )
    )
    current = json.loads(
        (ROOT / "results/20261115/generic_current_quantitative_attachments.json").read_text(
            encoding="utf-8"
        )
    )
    forecast = json.loads(
        (ROOT / "results/20261115/generic_forecast_quantitative_attachments.json").read_text(
            encoding="utf-8"
        )
    )
    result = build_handoff(frames, tables, current_frames, current, forecast)
    current_eval = result["current_diagnostic_evaluation"]
    forecast_eval = result["forecast_diagnostic_evaluation"]
    assert current_eval["status"] == "CONDITIONAL_DIAGNOSTIC_EVALUATION_AVAILABLE"
    assert forecast_eval["status"] == "CONDITIONAL_DIAGNOSTIC_EVALUATION_AVAILABLE"
    assert current_eval["summary"]["request_count"] == 3
    assert forecast_eval["summary"]["request_count"] == 3
    assert current_eval["summary"]["diagnostic_chain_attached_count"] == 3
    assert forecast_eval["summary"]["diagnostic_chain_attached_count"] == 3
    assert current_eval["summary"]["frequency_value_withheld_count"] == 1
    assert forecast_eval["summary"]["frequency_value_withheld_count"] == 1
    assert current_eval["summary"]["release_boundary_valid_count"] == 2
    assert current_eval["summary"]["release_boundary_withheld_count"] == 1
    assert forecast_eval["summary"]["release_boundary_valid_count"] == 2
    assert forecast_eval["summary"]["release_boundary_withheld_count"] == 1
    storage_row = next(
        row for row in current_eval["rows"] if row["component_id"] == "storage-tank-01"
    )
    assert storage_row["status"] == "WITHHELD_RELEASE_BOUNDARY_EVIDENCE"
    assert storage_row["frequency_inference_performed"] is False
    assert storage_row["provider_release_boundary_valid"] is False
    assert any(
        "inventory_depletion" in reason
        for reason in storage_row["provider_release_boundary_blocking_reasons"]
    )
    line_row = next(
        row for row in current_eval["rows"] if row["component_id"] == "liquid-transfer-line-01"
    )
    assert line_row["provider_release_boundary_valid"] is True
    assert storage_row["facility_qra_promotion"] is False
