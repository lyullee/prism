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
