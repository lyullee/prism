from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import sys

from lh2_tno.completion_audit import build_ijhe_completion_audit


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
    assert len(result["checks"]) == 11
    assert not result["blocking_reasons"]
    assert result["qualification_boundary"]["facility_ir_fn_available"] is False
    assert result["qualification_boundary"]["physical_validation_claim"] is False
    assert result["major_accident_scope"]["selected_families"] == ["vaporizer_hole"]
    assert len(result["major_accident_scope"]["not_evaluated_families"]) == 11
    assert result["major_accident_scope"]["implicit_substitution_performed"] is False
    assert result["processing_time"]["fresh_physics_claim"] is False
    assert result["processing_time"]["case_stage_elapsed_ms"]["source"] >= 0.0


def test_full_ijhe_audit_consumes_facility_handoff_audit_as_diagnostic_check():
    report = build_ijhe_completion_audit(
        {"validated": False},
        {"matrix_complete": False, "blocking_reasons": ["diagnostic"]},
        {"events": [], "cases": [], "timing": {}},
        inspection_center_facility_ijhe_handoff_audit={
            "schema_version": "prism.inspection_center_facility_ijhe_audit.v1",
            "status": "PASS_WITH_SCOPE_LIMITATIONS",
            "checks": [{"status": "PASS", "blocking_reason": None}],
            "blocking_reasons": [],
            "qualification_boundary": {
                "facility_ir_fn_available": False,
                "provider_packet_qualification": "UNQUALIFIED_DIAGNOSTIC",
                "physical_validation_claim": False,
            },
        },
    )
    check = next(
        item for item in report["checks"]
        if item["name"] == "diagnostic_inspection_center_facility_ijhe_handoff"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
