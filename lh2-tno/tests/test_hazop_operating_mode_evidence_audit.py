import csv
import json
from pathlib import Path

from lh2_tno.hazop_operating_mode_evidence_audit import audit_hazop_operating_mode_evidence


HEADERS = [
    "시나리오", "탱크", "절차번호", "동작내용", "위험성분류",
    "누출_예상고장", "누출_위험", "누출_조치방법", "누출_근거기준",
    "화재_예상고장", "화재_위험", "화재_조치방법", "화재_근거기준",
    "폭발_예상고장", "폭발_위험", "폭발_조치방법", "폭발_근거기준",
]


def _write_sources(root: Path, *, include_supply_mode: bool = True) -> None:
    rows = [
        ["액화수소 인수", "TANK1", "1", "플랜지 결합", "flange_connect", "failure", "risk", "action", "ref", "fire", "risk", "action", "ref", "explosion", "risk", "action", "ref"],
        ["액화수소 저장(벤트)", "TANK1·TANK2 공통", "1", "압력상승", "pressure_rise_monitor", "failure", "risk", "action", "ref", "fire", "risk", "action", "ref", "explosion", "risk", "action", "ref"],
    ]
    if include_supply_mode:
        supply_dir = root / "3. 액화수소 공급 시나리오 데이터"
        supply_dir.mkdir(parents=True)
        with (supply_dir / "수소공급_운전시퀀스.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["시나리오", "공급모드", "탱크"] + HEADERS[2:])
            writer.writerow(["수소 공급", "기체수소", "TANK1"] + rows[0][2:])
            writer.writerow(["수소 공급", "액화수소", "TANK2"] + rows[0][2:])
    for relative, row in [
        ("1. 액화수소 인수 시나리오 데이터/액화수소인수_운전시퀀스.csv", rows[0]),
        ("2. 액화수소 저장(벤트) 시나리오 데이터/액화수소저장벤트_운전시퀀스.csv", rows[1]),
    ]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADERS)
            writer.writerow(row)
    (root / "액화수소 인수·저장(벤트)·공급 시나리오 설명자료.pdf").write_bytes(b"placeholder")
    (root / "액화수소 인수·저장(벤트)·공급 시나리오 설명자료.pptx").write_bytes(b"placeholder")


def test_explicit_scenarios_and_supply_modes_are_preserved(tmp_path):
    _write_sources(tmp_path)
    report = audit_hazop_operating_mode_evidence(tmp_path)
    assert report["sequence_row_count"] == 4
    assert report["operating_mode_counts"] == {
        "receiving": 1,
        "storage_vent": 1,
        "supply_gas": 1,
        "supply_liquid": 1,
    }
    assert report["policy"]["mode_inference_from_numeric_values_performed"] is False
    assert report["coverage"]["frequency_event_binding_closed"] is False


def test_missing_supply_mode_is_withheld_from_exact_mode_binding(tmp_path):
    _write_sources(tmp_path, include_supply_mode=False)
    supply_dir = tmp_path / "3. 액화수소 공급 시나리오 데이터"
    supply_dir.mkdir(parents=True)
    with (supply_dir / "수소공급_운전시퀀스.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["시나리오", "공급모드", "탱크"] + HEADERS[2:])
        writer.writerow(["수소 공급", "", "TANK1"] + ["1"] + HEADERS[4:])
    report = audit_hazop_operating_mode_evidence(tmp_path)
    assert report["operating_mode_counts"]["supply_unspecified"] == 1
    assert report["coverage"]["explicit_operating_mode_rows_closed"] is False


def test_unreviewed_timeseries_units_keep_numeric_binding_locked(tmp_path):
    _write_sources(tmp_path)
    timeseries = tmp_path / "timeseries.json"
    timeseries.write_text(json.dumps({
        "schema_version": "prism.inspection_center_timeseries_audit.v1",
        "aggregate": {
            "reviewed_unit_map_supplied": False,
            "numeric_signal_unit_status_count": {"MISSING_OR_UNCONFIRMED": 10},
        },
    }), encoding="utf-8")
    report = audit_hazop_operating_mode_evidence(tmp_path, timeseries_audit_path=timeseries)
    assert report["status"] == "HAZOP_OPERATING_MODE_EVIDENCE_AUDIT_WITH_STATE_BINDING_WITHHELD"
    assert report["timeseries_audit"]["numeric_state_binding_allowed"] is False
    assert report["policy"]["normal_timeseries_promoted_to_accident_evidence"] is False
