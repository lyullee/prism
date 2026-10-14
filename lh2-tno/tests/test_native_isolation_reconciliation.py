from __future__ import annotations

import json

from lh2_tno.native_isolation_reconciliation import (
    build_native_isolation_event_reconciliation,
)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _catalog(tmp_path):
    root = tmp_path / "catalog"
    event_dir = root / "events" / "e1"
    _write(
        root / "verification.json",
        {
            "frequency_event_count": 1,
            "exact_native_packet_count": 1,
            "uncomputed_event_count": 0,
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "frequency_inference_performed": False,
            "state_snapshot_binding": {"status": "STATE_SNAPSHOT_BOUND_AND_ECHOED"},
            "event_rows": [
                {
                    "event_id": "event-1",
                    "component_id": "line-1",
                    "event_dir": "events/e1",
                    "status": "EXACT_NATIVE_PACKET",
                    "packet_kind": "native",
                    "diagnostic_termination_basis": "reviewed_isolation_success",
                    "diagnostic_duration_s": 0.3,
                    "isolation_requested": True,
                    "isolation_success": True,
                }
            ],
        },
    )
    _write(
        root / "isolation_branch_audit.json",
        {"isolation_success_count": 1},
    )
    _write(
        event_dir / "verification.json",
        {
            "status": "EXECUTED",
            "provider_packet_promoted": False,
            "physical_validation_claim": False,
            "facility_qra_claim": False,
            "frequency_inference_performed": False,
        },
    )
    _write(
        event_dir / "resolved_release.json",
        {
            "event_id": "event-1",
            "component_id": "line-1",
            "port_id": "outlet-1",
            "termination_basis": "reviewed_isolation_success",
            "duration_s": 0.3,
            "available_mass_kg": 1.0,
            "cumulative_mass_out_kg": 0.1,
        },
    )
    return root


def test_native_isolation_reconciliation_passes_for_matching_artifacts(tmp_path):
    result = build_native_isolation_event_reconciliation(_catalog(tmp_path))

    assert result["status"] == "NATIVE_ISOLATION_EVENT_ROWS_RECONCILED_DIAGNOSTIC"
    assert result["event_count"] == 1
    assert result["mismatch_count"] == 0
    assert all(result["checks"].values())


def test_native_isolation_reconciliation_blocks_identity_mismatch(tmp_path):
    root = _catalog(tmp_path)
    release_path = root / "events" / "e1" / "resolved_release.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    release["component_id"] = "different-line"
    release_path.write_text(json.dumps(release), encoding="utf-8")

    result = build_native_isolation_event_reconciliation(root)

    assert result["status"] == "NATIVE_ISOLATION_EVENT_ROWS_RECONCILIATION_BLOCKED"
    assert result["mismatch_count"] == 1
    assert "component_id_mismatch" in result["mismatches"][0]["reasons"]
