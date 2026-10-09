from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).parents[1] / "scripts" / "build_native_direct_adapter_coverage.py"
_SPEC = importlib.util.spec_from_file_location("native_direct_adapter_coverage", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_native_direct_coverage_declares_all_seven_models():
    assert len(_MODULE._CASES) == 7
    assert {row[0] for row in _MODULE._CASES} == {
        "LayeredTank", "DynamicHEMPipe", "StrokeLimitedCommandedValve",
        "MappedPump", "DynamicVaporizer", "DynamicReliquefier", "VentStack",
    }


def test_native_direct_coverage_can_record_source_state_completion():
    report = _MODULE.build()
    assert report["source_state_completion_count"] == 3
    assert report["source_state_completion_blocked_count"] == 4
    thermal = next(item for item in report["entries"] if item["model_class"] == "DynamicVaporizer")
    assert thermal["source_state_completion_status"] == "COMPLETED_ISENTROPIC_THROAT_FIELDS"
    valve = next(item for item in report["entries"] if item["model_class"] == "StrokeLimitedCommandedValve")
    assert valve["source_state_completion_status"] == "PROVIDER_NATIVE_SOURCE_THROAT_FIELDS"
