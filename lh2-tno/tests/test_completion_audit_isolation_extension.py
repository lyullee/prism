from __future__ import annotations

import copy
import json
from pathlib import Path

from lh2_tno.completion_audit import build_ijhe_completion_audit


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "results/20261026/native_full_scope_union_assessment/isolation_extension/verification.json"


def _campaign() -> dict:
    return {
        "events": [{"id": "event-1"}],
        "cases": [
            {
                "status": "EXECUTED",
                "termination": {"basis": "synthetic", "time_s": 0.2},
                "mass_ledger": {"end_to_end_residual_kg": 0.0},
            }
        ],
        "timing": {"fresh_physics_cases": 1, "campaign_elapsed_ms": 1.0},
        "total_facility_annual_ir_low_high": None,
        "total_facility_expected_death_fn_low_high": None,
    }


def _audit(extension: dict) -> dict:
    return build_ijhe_completion_audit(
        {
            "physical_validation_claim": False,
            "realtime_monitor_implemented": True,
        },
        {"matrix_complete": False, "blocking_reasons": ["pipe_hole: PARTIAL"]},
        _campaign(),
        isolation_union_extension_verification=extension,
    )


def test_completion_audit_consumes_isolation_union_extension_as_diagnostic_pass() -> None:
    extension = json.loads(EXTENSION.read_text(encoding="utf-8"))
    report = _audit(extension)
    check = next(
        row for row in report["checks"] if row["name"] == "diagnostic_isolation_union_extension"
    )
    assert check["status"] == "PASS"
    assert check["diagnostic_only"] is True
    assert check["evidence"]["merged_counts"] == {
        "events": 39,
        "cases": 64,
        "risk_atoms": 256,
    }
    assert check["evidence"]["provider_packet_collection_manifest_status"] == (
        "OPEN_PROVIDER_PACKET_COLLECTION"
    )
    assert check["evidence"]["provider_packet_collection_request_count"] == 20
    assert check["evidence"]["provider_packet_collection_open_request_count"] == 20
    assert check["evidence"]["provider_packet_collection_qualified_packet_count"] == 0


def test_completion_audit_blocks_unsafe_isolation_union_extension() -> None:
    extension = json.loads(EXTENSION.read_text(encoding="utf-8"))
    broken = copy.deepcopy(extension)
    broken["policy"]["frequency_inference_performed"] = True
    report = _audit(broken)
    check = next(
        row for row in report["checks"] if row["name"] == "diagnostic_isolation_union_extension"
    )
    assert check["status"] == "BLOCKED"
    assert check["diagnostic_only"] is True


def test_completion_audit_blocks_missing_isolation_collection_manifest() -> None:
    extension = json.loads(EXTENSION.read_text(encoding="utf-8"))
    broken = copy.deepcopy(extension)
    broken["provider_packet_collection_manifest_status"] = "MISSING"
    report = _audit(broken)
    check = next(
        row for row in report["checks"] if row["name"] == "diagnostic_isolation_union_extension"
    )
    assert check["status"] == "BLOCKED"
