from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from lh2_tno.observed_state_model_binding_audit import audit_observed_state_model_binding


ROOT = Path(__file__).parents[1]


def _inputs() -> tuple[dict, dict, dict]:
    evidence = json.loads((ROOT / "examples/inspection_center_observed_state_evidence.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "examples/inspection_center_observed_component_mapping_manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "examples/generic_lh2_model_binding.json").read_text(encoding="utf-8"))
    return evidence, manifest, catalog


def test_observed_signals_bind_to_normal_models_without_release_promotion():
    report = audit_observed_state_model_binding(*_inputs())
    assert report["status"] == "STATE_MODEL_BINDINGS_DIAGNOSTIC_ONLY"
    assert report["observed_component_count"] == 3
    assert report["state_model_bound_component_count"] == 3
    assert report["diagnostic_release_adapter_component_count"] == 3
    assert report["qualified_provider_packet_count"] == 0
    assert report["policy"]["normal_state_model_is_not_accident_release"] is True
    assert all(
        row["status"] == "STATE_MODEL_BOUND_DIAGNOSTIC_ADAPTER_SEPARATE"
        and row["accident_release_export_status"] == "missing"
        for row in report["rows"]
    )


def test_missing_required_signal_blocks_model_binding():
    evidence, manifest, catalog = _inputs()
    evidence = deepcopy(evidence)
    evidence["source_rows"][0]["signal_map"].pop("temperature")
    report = audit_observed_state_model_binding(evidence, manifest, catalog)
    assert report["status"] == "PARTIAL_STATE_MODEL_BINDINGS"
    assert report["state_model_bound_component_count"] == 2
    assert any("required state quantities are missing" in reason for reason in report["blocking_reasons"])
