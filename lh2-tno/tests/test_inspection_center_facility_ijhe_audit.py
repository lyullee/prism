from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import sys


def test_facility_ijhe_handoff_audit_is_fail_closed_and_traceable():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from audit_inspection_center_facility_ijhe_handoff import run

    output = root / ".tmp_test_inspection_center_facility_ijhe_handoff_audit.json"
    try:
        result = run(Namespace(
            bridge=root / "examples/inspection_center_facility_hazop_bridge.json",
            handoff=root / "examples/inspection_center_facility_campaign_handoff.json",
            output=output,
        ))
    finally:
        output.unlink(missing_ok=True)

    assert result["status"] == "PASS_WITH_SCOPE_LIMITATIONS"
    assert len(result["checks"]) == 8
    assert not result["blocking_reasons"]
    assert result["qualification_boundary"]["facility_ir_fn_available"] is False
    assert result["qualification_boundary"]["physical_validation_claim"] is False
