from __future__ import annotations

import json
from pathlib import Path

from scripts.reconcile_native_provider_qualification_assessment import reconcile_assessment


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "results/20261115/native_external_facility_full_scope_campaign_current"


def test_native_provider_audit_is_consumed_as_a_fail_closed_assessment_gate():
    assessment = json.loads(
        (CURRENT / "facility_assessment.json").read_text(encoding="utf-8")
    )
    audit = json.loads(
        (CURRENT / "provider_qualification_audit.json").read_text(encoding="utf-8")
    )
    result = reconcile_assessment(
        assessment,
        audit,
        assessment_record="facility_assessment.json",
        audit_record="provider_qualification_audit.json",
    )
    gate = result["provider_qualification_coverage"]
    assert result["status"] == "PARTIAL_FACILITY_SCOPE"
    assert gate["complete"] is False
    assert gate["qualified_provider_packet_count"] == 0
    assert result["provider_qualification_audit_facility_qra_allowed"] is False
    assert result["qualified_facility_qra_available"] is False
