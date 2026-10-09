"""Regression checks for the published PRISM readiness status ledgers."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "results/20261024/ijhe_completion_audit_native_generic_scope_vertical_v16.json"
ASSESSMENT_PATH = ROOT / "results/20261024/native_generic_scope_vertical_merged_facility_assessment_population_v6.json"


def _json(path: Path) -> dict:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise AssertionError(f"duplicate JSON key in {path}: {key}")
            result[key] = item
        return result

    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
    )
    assert isinstance(value, dict)
    return value


def test_status_ledgers_match_latest_audit_and_facility_gate() -> None:
    audit = _json(AUDIT_PATH)
    assessment = _json(ASSESSMENT_PATH)

    assert audit["status"] == "INCOMPLETE_EVIDENCE"
    assert len(audit["checks"]) == 34
    assert len(audit["blocking_reasons"]) == 4
    case_check = next(
        check for check in audit["checks"]
        if check["name"] == "facility_case_provider_packet_coverage"
    )
    assert case_check["status"] == "BLOCKED"
    assert case_check["evidence"]["case_request_count"] == 34
    assert case_check["evidence"]["qualified_provider_case_count"] == 0

    coverage = assessment["facility_case_packet_coverage"]
    assert coverage["coverage_status"] == "NO_CASE_MATCH"
    assert coverage["case_request_count"] == 34
    assert coverage["qualified_provider_case_count"] == 0
    assert assessment["facility_case_packet_coverage_complete"] is False
    assert assessment["qualified_facility_qra_available"] is False
    assert assessment["facility_total_risk_available"] is False

    for status_path in (ROOT / "CURRENT_STATUS.json", ROOT / "DEVELOPMENT_GOAL.json"):
        status = _json(status_path)
        assert status["ijhe_completion_audit_latest_record"].endswith(AUDIT_PATH.name)
        assert status["ijhe_completion_audit_latest_check_count"] == len(audit["checks"])
        assert status["ijhe_completion_audit_latest_blocking_reason_count"] == len(
            audit["blocking_reasons"]
        )
        assert status["ijhe_completion_audit_latest_facility_assessment_record"].endswith(
            ASSESSMENT_PATH.name
        )
        assert status["full_portable_test_count"] == 604
        assert status["full_portable_test_status"] == "604 passed"
        assert status["facility_evidence_request_latest_record"].endswith(
            "native_generic_scope_vertical_facility_evidence_request_v2.json"
        )
        if "facility_ledger_latest_record" in status:
            assert status["facility_ledger_latest_record"].endswith(
                "native_generic_scope_vertical_merged_facility_ledger_population_v3.json"
            )
        if "ijhe_audit_latest_record" in status:
            assert status["ijhe_audit_latest_record"].endswith(AUDIT_PATH.name)
