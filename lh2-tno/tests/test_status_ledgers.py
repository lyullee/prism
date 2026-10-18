"""Regression checks for the published PRISM readiness status ledgers."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "results/20261115/ijhe_completion_audit_union_vertical_inventory_handoff_isolation_current.json"
ASSESSMENT_PATH = ROOT / "results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json"
STATUS_PATH = ROOT / "CURRENT_STATUS.json"


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
    status = _json(STATUS_PATH)
    assert len(audit["checks"]) == status["latest_ijhe_audit_metadata_verifier_check_count"]
    assert len(audit["blocking_reasons"]) == 5
    case_check = next(
        check for check in audit["checks"]
        if check["name"] == "facility_case_provider_packet_coverage"
    )
    assert case_check["status"] == "BLOCKED"
    assert case_check["evidence"]["case_request_count"] == 44
    assert case_check["evidence"]["qualified_provider_case_count"] == 0

    coverage = assessment["facility_case_packet_coverage"]
    assert coverage["coverage_status"] == "NO_CASE_MATCH"
    assert coverage["case_request_count"] == 44
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
        # The ledger records the count from its latest published snapshot.
        # Keep the contract self-consistent without hard-coding a historical
        # number: adding a test should not create a CI failure merely because
        # this regression test was not edited at the same time.
        test_count = status["full_portable_test_count"]
        assert isinstance(test_count, int) and test_count > 0
        assert status["full_portable_test_status"].startswith(
            f"{test_count} passed"
        )
        # The v0.6.0 alias is a current pointer, not a historical snapshot.
        # Keep it synchronized with the authoritative audit so dashboards and
        # release notes cannot silently report the retired 42-check snapshot.
        v060_counts = {
            state: sum(check["status"] == state for check in audit["checks"])
            for state in {check["status"] for check in audit["checks"]}
        }
        assert status["v060_ijhe_completion_audit_latest_check_count"] == len(
            audit["checks"]
        )
        assert status["v060_ijhe_completion_audit_latest_check_status_counts"] == v060_counts
        assert status["v060_ijhe_completion_audit_latest_blocked_checks"] == [
            check["name"] for check in audit["checks"] if check["status"] != "PASS"
        ]
        assert status["facility_evidence_request_latest_record"].endswith(
            "facility_evidence_request.json"
        )
        if "facility_ledger_latest_record" in status:
            assert status["facility_ledger_latest_record"].endswith(
                "campaign_result.json"
            )
        if "ijhe_audit_latest_record" in status:
            assert status["ijhe_audit_latest_record"].endswith(AUDIT_PATH.name)
        high_resolution_record = status.get(
            "actual_ffi_high_resolution_recheck_record",
            status.get("slabx_lh2_test6_actual_source_high_resolution_recheck_record"),
        )
        assert high_resolution_record is not None
        # The high-resolution replay directory is a rolling evidence pointer.
        # Keep the contract focused on the artifact type instead of freezing a
        # historical resolution in the test; a refreshed qualified replay must
        # update the ledger pointer without creating a CI failure.
        assert high_resolution_record.endswith("/provenance.json")
        assert (ROOT / high_resolution_record).is_file()
        high_resolution_status = status.get(
            "actual_ffi_high_resolution_recheck_status",
            status.get("slabx_lh2_test6_actual_source_high_resolution_recheck_status", ""),
        )
        assert "9.070% H2 concentration" in high_resolution_status
        assert status.get(
            "actual_ffi_high_resolution_recheck_accepted",
            status.get("slabx_lh2_test6_actual_source_high_resolution_recheck_accepted"),
        ) is False
