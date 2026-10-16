from __future__ import annotations

import json
from pathlib import Path

from scripts.build_inspection_center_source_inventory import build_record


def test_source_inventory_keeps_normal_operation_data_diagnostic_only(tmp_path: Path) -> None:
    audit_path = tmp_path / "timeseries.json"
    audit_path.write_text(
        json.dumps(
            {
                "schema_version": "prism.inspection_center_timeseries_audit.v1",
                "status": "SCREENING_ONLY_UNIT_BASIS_UNCONFIRMED",
                "source_file_count": 2,
                "aggregate": {
                    "workbook_count": 2,
                    "sheet_count": 4,
                    "signal_category_count": {"time": 2, "pressure": 3},
                    "numeric_signal_unit_status_count": {"MISSING_OR_UNCONFIRMED": 3},
                },
                "promotion_gates": {
                    "state_snapshot_binding_allowed": False,
                },
            }
        ),
        encoding="utf-8",
    )
    record = build_record(
        timeseries_audit=json.loads(audit_path.read_text(encoding="utf-8")),
        timeseries_path=audit_path,
        reviewed_unit_evidence=None,
        reviewed_unit_path=None,
        reconstructed_state_evidence=None,
        reconstructed_state_path=None,
    )

    assert record["status"] == "NORMAL_OPERATION_SOURCE_SCREENED_DIAGNOSTIC_ONLY"
    assert record["inventory"]["workbook_count"] == 2
    assert record["evidence_suitability"]["accident_release_boundary"]["available"] is False
    assert record["promotion_gates"]["frequency_applied"] is False
    assert record["promotion_gates"]["provider_packet_qualified"] is False
    assert record["promotion_gates"]["facility_qra_claim"] is False
