from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
import sys

import pytest


def test_reconstructed_three_component_facility_bridge_executes_selected_supply_branch(tmp_path):
    root = Path(__file__).resolve().parents[1]
    required_inputs = (
        root / "examples/inspection_center_reconstructed_runtime_frames.json",
        root / "examples/inspection_center_hazop_runtime_tables.json",
        root / "examples/inspection_center_reconstructed_hazop_runtime_audit.json",
        root / "examples/inspection_center_reconstructed_hazop_provider_event_binding.json",
        root / "results/20261110/native_full_scope_frequency_assessment_latest2/provider_worklist.json",
        root / "results/20261110/observed_hazop_storage_vaporizer_isolation_overlay/packet_evidence.json",
        root / "results/20261110/native_generic_scope_packets_latest2",
        root / "examples/generic_lh2_full_scope_manifest.json",
        root / "results/20261110/native_full_scope_frequency_assessment_latest2/frequency_plan.json",
        root / "examples/provider_request_defaults_liquid.json",
        root / "examples/provider_emergency_relief_defaults.json",
        root / "examples/equipment_consequence_template.json",
        root / "results/20261008/full_chain/backend_config.json",
    )
    missing = [str(path) for path in required_inputs if not path.exists()]
    if missing:
        pytest.skip(
            "requires locally generated inspection-center evidence artifacts: "
            + ", ".join(missing)
        )

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_inspection_center_facility_hazop_bridge import ROOT, run

    output = tmp_path / "facility_bridge.json"
    args = Namespace(
        runtime_frames=ROOT / "examples/inspection_center_reconstructed_runtime_frames.json",
        hazop_table_set=ROOT / "examples/inspection_center_hazop_runtime_tables.json",
        observed_hazop_runtime_audit=ROOT / "examples/inspection_center_reconstructed_hazop_runtime_audit.json",
        observed_hazop_provider_binding=ROOT / "examples/inspection_center_reconstructed_hazop_provider_event_binding.json",
        provider_worklist=ROOT / "results/20261110/native_full_scope_frequency_assessment_latest2/provider_worklist.json",
        packet_evidence=ROOT / "results/20261110/observed_hazop_storage_vaporizer_isolation_overlay/packet_evidence.json",
        packet_root=ROOT / "results/20261110/native_generic_scope_packets_latest2",
        manifest=ROOT / "examples/generic_lh2_full_scope_manifest.json",
        frequency_plan=ROOT / "results/20261110/native_full_scope_frequency_assessment_latest2/frequency_plan.json",
        provider_defaults_liquid=ROOT / "examples/provider_request_defaults_liquid.json",
        provider_defaults_relief=ROOT / "examples/provider_emergency_relief_defaults.json",
        template=ROOT / "examples/equipment_consequence_template.json",
        backend_config=ROOT / "results/20261008/full_chain/backend_config.json",
        now_s=43200.0,
        deadline_s=180.0,
        output=output,
    )

    result = run(args)
    assert result["status"] == "FACILITY_HAZOP_RUNTIME_EVALUATED"
    assert result["component_count"] == 3
    assert len(result["risk_atoms"]) == 1
    assert result["facility_annual_ir_available"] is False
    assert result["facility_fn_available"] is False
    assert result["facility_bridge_audit"]["selected_component_count"] == 1
    assert result["facility_bridge_audit"]["executed_component_count"] == 1
    assert set(result["facility_bridge_audit"]["withheld_normal_component_ids"]) == {
        "lh2-intake-tank",
        "lh2-storage-vent",
    }
    # The operating mode is part of each field state frame.  HAZOP must use
    # that supplied mode to select the branch; it must not infer a mode from
    # the measured value or create a provider release for normal branches.
    components = result["components"]
    assert components["lh2-intake-tank"]["selection"]["operating_mode"] == "receiving"
    assert components["lh2-intake-tank"]["selection"]["status"] == "NO_DEVIATION"
    assert components["lh2-intake-tank"]["selection"]["selected_scenario_count"] == 0
    assert components["lh2-storage-vent"]["selection"]["operating_mode"] == "standby"
    assert components["lh2-storage-vent"]["selection"]["status"] == "NO_DEVIATION"
    assert components["lh2-storage-vent"]["selection"]["selected_scenario_count"] == 0
    supply = components["lh2-supply-vaporizer-boundary"]["selection"]
    assert supply["operating_mode"] == "supply"
    assert supply["status"] == "SCENARIOS_SELECTED"
    assert supply["active_deviation_count"] == 1
    assert supply["selected_scenario_count"] == 1
    assert result["policy"]["operating_mode_taken_from_input"] is True
    assert result["facility_bridge_audit"]["operating_mode_inferred"] is False
    mapping = result["facility_bridge_audit"]["explicit_provider_component_mapping"]
    assert mapping["observed_component_id"] == "lh2-supply-vaporizer-boundary"
    assert mapping["provider_component_id"] == "ambient-vaporizer-01"
    assert mapping["provider_port_id"] == "vaporizer-accident-out"
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == (
        "prism.inspection_center_facility_hazop_bridge.v1"
    )
