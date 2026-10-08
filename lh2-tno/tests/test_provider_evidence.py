import json
from pathlib import Path

from lh2_tno.provider_evidence import audit_provider_root


def _write(root: Path, name: str, value: dict) -> None:
    path = root / "configs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _qualified_gas_release() -> dict:
    return {
        "provider_export_schema": "prism.resolved_release.v1",
        "component_id": "TK-1",
        "port_id": "leak-1",
        "event_id": "E-1",
        "event_kind": "accidental_leak",
        "upstream_service": "GH2",
        "upstream_service_provenance": "fixture",
        "input_origin": "model_prediction",
        "boundary_kind": "resolved_atmospheric_gas_exit",
        "enthalpy_convention": "static_exit_enthalpy",
        "property_basis": {"fluid": "Hydrogen", "energy_reference": "CoolProp-HEOS:Hydrogen:native"},
        "provider_source_digest": "0" * 64,
        "provider_result_digest": "1" * 64,
        "provider_boundary_reference": "fixture-boundary",
        "position_enu_m": [0.0, 0.0, 1.0],
        "direction_enu": [1.0, 0.0, 0.0],
        "ambient_pressure_pa_abs": 101325.0,
        "ambient_temperature_k": 293.15,
        "duration_s": 1.0,
        "available_mass_kg": 1.0,
        "cumulative_mass_out_kg": 0.1,
        "cumulative_static_enthalpy_out_j": 1.0,
        "termination_provenance": "fixture",
        "failure_opening_diameter_m": 0.01,
        "steps": [{"time_s": 0.0, "mass_flow_kg_s": 0.1}],
    }


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
    (tmp_path / "results" / "accident_release.json").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "results" / "accident_release.json").write_text(
        json.dumps(_qualified_gas_release()), encoding="utf-8"
    )

    report = audit_provider_root(tmp_path)

    assert report["status"] == "EXECUTABLE_PROVIDER"
    assert report["blocking_reasons"] == []
    assert report["release_evidence"]["accident_release_qualified_file_count"] == 1


def test_release_inventory_rejects_screening_flow_without_accident_contract(tmp_path):
    path = tmp_path / "screening.json"
    path.write_text(json.dumps({"mass_flow_kg_s": 0.2, "status": "screening_only"}), encoding="utf-8")

    from lh2_tno.provider_evidence import _release_packet_inventory

    report = _release_packet_inventory(tmp_path)

    assert report["accident_release_candidate_file_count"] == 0
    assert report["accident_release_qualified_file_count"] == 0
    assert report["normal_or_screening_flow_file_count"] == 1
    assert report["promotion_status"] == "NO_ACCIDENT_RELEASE_EXPORT"


def test_release_inventory_requires_schema_and_complete_ledger(tmp_path):
    candidate = _qualified_gas_release()
    candidate.pop("provider_export_schema")
    candidate.pop("cumulative_static_enthalpy_out_j")
    (tmp_path / "candidate.json").write_text(json.dumps(candidate), encoding="utf-8")

    from lh2_tno.provider_evidence import _release_packet_inventory

    report = _release_packet_inventory(tmp_path)

    assert report["accident_release_candidate_file_count"] == 1
    assert report["accident_release_qualified_file_count"] == 0
    assert report["missing_field_counts"]["missing:provider_export_schema"] == 1
    assert report["missing_field_counts"]["missing:cumulative_static_enthalpy_out_j"] == 1


def test_release_inventory_accepts_explicit_complete_contract(tmp_path):
    (tmp_path / "release.json").write_text(json.dumps(_qualified_gas_release()), encoding="utf-8")

    from lh2_tno.provider_evidence import _release_packet_inventory

    report = _release_packet_inventory(tmp_path)

    assert report["accident_release_candidate_file_count"] == 1
    assert report["accident_release_qualified_file_count"] == 1
    assert report["promotion_status"] == "QUALIFIED_ACCIDENT_RELEASE_EXPORT"
