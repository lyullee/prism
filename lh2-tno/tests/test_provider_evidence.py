import json
from pathlib import Path

from lh2_tno.provider_evidence import audit_provider_root


def _write(root: Path, name: str, value: dict) -> None:
    path = root / "configs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_provider_evidence_preserves_partial_readiness_and_counts(tmp_path):
    configs = {
        "center_assets.json": {"assets": [{"asset_id": "TK-1", "validation_status": "baseline_only"}]},
        "center_component_bindings.json": {"node_bindings": [{"binding_status": "audit"}], "edge_bindings": [{"binding_status": "tag_required"}]},
        "center_operation_command_bindings.json": {"confirmed_tag_map": {}, "procedure_to_pid_tag_map": {}},
        "center_operation_sequences.json": {"scenarios": [{"rows": [{"physical_time_s": None}]}]},
        "center_parameter_input_template.json": {"row_count": 2, "rows": [{"priority": "P0", "value_status": "unconfirmed", "review_status": "unconfirmed"}, {"priority": "P1", "value_status": "unconfirmed", "review_status": "unconfirmed"}]},
        "center_port_mappings.json": {"mappings": [{"status": "candidate_mapping"}]},
        "center_port_netlist.json": {"connections": [{"status": "unresolved"}]},
        "center_screening_closure.json": {"facility": "fixture", "status": "screening_only", "parameter_policy": {"bind_center_asset": False}, "promotion_rule": {"forward_comparison_allowed": False}},
        "center_observation_bindings.json": {"bindings": [{"status": "candidate"}]},
        "scenarios.json": {"scenarios": [{"scenario_id": "S01"}]},
    }
    for name, value in configs.items():
        _write(tmp_path, name, value)
    (tmp_path / "검증결과.md").write_text("최신 전체 회귀 **822개가 모두 통과**했다.", encoding="utf-8")

    report = audit_provider_root(tmp_path)

    assert report["status"] == "PARTIAL_PROVIDER_EVIDENCE"
    assert report["provider_validation"]["test_count"] == 822
    assert report["coverage"]["parameter_requests"]["priority"] == {"P0": 1, "P1": 1}
    assert report["coverage"]["operation_sequences"]["physical_time_missing"] == 1
    assert report["readiness"]["center_binding_ready"] is False
    assert report["promotion_policy"]["screening_values_are_not_promoted"] is True


def test_provider_evidence_can_reach_executable_provider_status(tmp_path):
    configs = {
        "center_assets.json": {"assets": []},
        "center_component_bindings.json": {"node_bindings": [], "edge_bindings": []},
        "center_operation_command_bindings.json": {"confirmed_tag_map": {"XV1": "open"}, "procedure_to_pid_tag_map": {"S01": ["XV1"]}},
        "center_operation_sequences.json": {"scenarios": [{"rows": [{"physical_time_s": 1.0}]}]},
        "center_parameter_input_template.json": {"row_count": 0, "rows": []},
        "center_port_mappings.json": {"mappings": []},
        "center_port_netlist.json": {"connections": []},
        "center_screening_closure.json": {"facility": "fixture", "status": "ready", "parameter_policy": {"bind_center_asset": True}, "promotion_rule": {"forward_comparison_allowed": True}},
        "center_observation_bindings.json": {"bindings": []},
        "scenarios.json": {"scenarios": []},
    }
    for name, value in configs.items():
        _write(tmp_path, name, value)

    report = audit_provider_root(tmp_path)

    assert report["status"] == "EXECUTABLE_PROVIDER"
    assert report["blocking_reasons"] == []

