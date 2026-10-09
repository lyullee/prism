from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).parents[1] / "scripts" / "audit_native_source_state_completeness.py"
_SPEC = importlib.util.spec_from_file_location("native_source_state_completeness", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_native_source_state_audit_keeps_gas_and_liquid_scope_separate():
    report = _MODULE.build()
    assert report["native_model_count"] == 7
    assert report["gas_model_count"] == 4
    assert report["gas_models_complete_for_compressible_adapter"] == 3
    assert report["gas_models_blocked_for_compressible_adapter"] == 1
    assert {entry["phase_family"] for entry in report["entries"]} == {"gas", "liquid", "liquid_or_two_phase"}


def test_native_source_state_audit_reports_exact_missing_fields():
    report = _MODULE.build()
    valve = next(entry for entry in report["entries"] if entry["model_class"] == "StrokeLimitedCommandedValve")
    assert valve["compressible_adapter_status"] == "COMPLETE"
    assert valve["missing_required_by_interval"] == []
    tank = next(entry for entry in report["entries"] if entry["model_class"] == "LayeredTank")
    assert tank["compressible_adapter_status"] == "NOT_APPLICABLE_CURRENT_GAS_ADAPTER"
    vaporizer = next(entry for entry in report["entries"] if entry["model_class"] == "DynamicVaporizer")
    assert vaporizer["compressible_adapter_status"] == "COMPLETE"
    assert vaporizer["missing_required_by_interval"] == []
    vent = next(entry for entry in report["entries"] if entry["model_class"] == "VentStack")
    assert vent["compressible_adapter_status"] == "INCOMPLETE"
