from __future__ import annotations

import json
from pathlib import Path

from scripts.build_inspection_center_sequence_evidence import build_record


def test_operation_sequence_is_hazop_provenance_without_release_promotion(tmp_path: Path) -> None:
    source = tmp_path / "sequence.csv"
    source.write_text(
        "시나리오,탱크,절차번호,동작내용,비고,위험성분류,누출_예상고장,누출_근거기준\n"
        "액화수소 저장(벤트),TANK1,1,LH2 저장 중 압력상승,6.0→6.5bar,pressure_rise_monitor,PT drift,KGS\n"
        "액화수소 저장(벤트),TANK1,2,XV10 OPEN,6.5bar 도달,relief_vent,밸브 고착,CGA\n"
        "액화수소 저장(벤트),TANK1,3,XV10 CLOSE,6.0bar까지 감압,valve_close,시트 누설,KGS\n",
        encoding="utf-8-sig",
    )

    record = build_record(source_path=source, scenario="액화수소 저장(벤트)")

    assert record["status"] == "OPERATION_SEQUENCE_SCREENED_DIAGNOSTIC_ONLY"
    assert record["source"]["row_count_selected"] == 3
    assert record["operating_sequence"]["observed_relief_setpoint_candidate_pa"] == 650000.0
    assert record["operating_sequence"]["observed_operational_close_threshold_candidate_pa"] == 600000.0
    assert record["evidence_suitability"]["release_boundary"]["available"] is False
    assert record["promotion_gates"]["provider_packet_created"] is False
    assert record["promotion_gates"]["frequency_applied"] is False
    assert record["promotion_gates"]["facility_qra_claim"] is False


def test_sequence_adapter_rejects_missing_contract_columns(tmp_path: Path) -> None:
    source = tmp_path / "invalid.csv"
    source.write_text("시나리오,탱크\n벤트,TANK1\n", encoding="utf-8-sig")

    try:
        build_record(source_path=source)
    except ValueError as error:
        assert "required columns" in str(error)
    else:  # pragma: no cover - assertion keeps the contract explicit
        raise AssertionError("missing sequence columns must be rejected")
