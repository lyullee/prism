import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_header_bound_facility_bridge_summary_preserves_multi_equipment_chain():
    summary = json.loads(
        (ROOT / "results/20261115/header_bound_facility_bridge_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["schema_version"] == "prism.header_bound_facility_hazop_bridge_summary.v1"
    assert summary["status"] == "MULTI_EQUIPMENT_HEADER_BOUND_FACILITY_RUNTIME_EXECUTED_DIAGNOSTIC"
    assert summary["component_count"] == 3
    assert summary["selected_component_count"] == 3
    assert summary["executed_component_count"] == 3
    assert summary["ready_provider_scenario_count"] == 3
    assert summary["withheld_provider_scenario_count"] == 0
    assert summary["risk_atom_count"] == 3
    assert summary["policy"]["explicit_operating_mode_input"] is True
    assert summary["policy"]["frequency_assignment_performed"] is True
    assert summary["policy"]["frequency_inference_performed"] is False
    assert summary["policy"]["sensor_frequency_learning_used"] is False
    assert summary["policy"]["provider_packets_qualified"] is False
    assert summary["policy"]["facility_qra_claim"] is False
    assert {row["operating_mode"] for row in summary["components"]} == {
        "receiving",
        "standby",
        "supply",
    }
    assert all(
        row["status"] == "CONSEQUENCE_BRANCHES_EVALUATED"
        and row["branch_statuses"] == ["CONSEQUENCE_EVALUATED"]
        for row in summary["components"]
    )


def test_header_bound_facility_bridge_runtime_record_is_present():
    runtime = json.loads(
        (ROOT / "results/20261115/header_bound_facility_bridge_runtime.json").read_text(
            encoding="utf-8"
        )
    )
    assert runtime["schema_version"] == "prism.inspection_center_header_bound_facility_hazop_bridge.v1"
    assert runtime["facility_bridge_audit"]["diagnostic_only"] is True
    assert runtime["facility_bridge_audit"]["physical_validation_claim"] is False
    assert runtime["facility_annual_ir_available"] is False
    assert runtime["facility_fn_available"] is False
