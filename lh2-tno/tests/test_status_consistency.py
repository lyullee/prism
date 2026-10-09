"""Tests for the cross-artifact readiness ledger audit."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from lh2_tno.status_consistency import build_status_consistency_report, load_json_object


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "results/20261024/ijhe_completion_audit_native_generic_scope_vertical_v12.json"
ASSESSMENT = ROOT / "results/20261024/native_generic_scope_vertical_merged_facility_assessment_population_v6.json"
EVIDENCE_REQUEST = ROOT / "results/20261024/native_generic_scope_vertical_facility_evidence_request_v2.json"
LEDGER = ROOT / "results/20261024/native_generic_scope_vertical_merged_facility_ledger_population_v3.json"
COVERAGE = ROOT / "results/20261024/native_generic_scope_vertical_case_packet_coverage_v1.json"


def _report(**overrides):
    values = {
        "current_status": load_json_object(ROOT / "CURRENT_STATUS.json"),
        "development_goal": load_json_object(ROOT / "DEVELOPMENT_GOAL.json"),
        "audit": load_json_object(AUDIT),
        "assessment": load_json_object(ASSESSMENT),
        "evidence_request": load_json_object(EVIDENCE_REQUEST),
        "ledger": load_json_object(LEDGER),
        "coverage": load_json_object(COVERAGE),
        "audit_filename": AUDIT.name,
        "assessment_filename": ASSESSMENT.name,
        "evidence_request_filename": EVIDENCE_REQUEST.name,
        "ledger_filename": LEDGER.name,
        "coverage_filename": COVERAGE.name,
    }
    values.update(overrides)
    return build_status_consistency_report(**values)


def test_current_published_artifacts_are_consistent() -> None:
    report = _report()
    assert report["status"] == "CONSISTENT"
    assert report["blocking_reasons"] == []
    assert report["facility_ir_fn_promotion"] is False
    assert all(row["status"] == "PASS" for row in report["checks"])


def test_changed_case_coverage_cannot_pass() -> None:
    coverage = deepcopy(load_json_object(COVERAGE))
    coverage["qualified_provider_case_count"] = 1
    report = _report(coverage=coverage)
    assert report["status"] == "INCONSISTENT"
    assert "coverage_gate" in report["blocking_reasons"]
