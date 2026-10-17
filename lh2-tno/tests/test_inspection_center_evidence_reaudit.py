import csv
import importlib.util
from datetime import datetime
from pathlib import Path

import pytest


def _load_builder():
    script = Path(__file__).parents[1] / "scripts" / "build_inspection_center_evidence_reaudit.py"
    spec = importlib.util.spec_from_file_location("prism_inspection_center_reaudit", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reaudit_preserves_scope_split_and_nonpromotion_policy(tmp_path):
    csv_path = tmp_path / "scenario.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["시나리오", "탱크", "절차번호", "동작내용", "위험성분류"],
        )
        writer.writeheader()
        writer.writerow({
            "시나리오": "저장(벤트)",
            "탱크": "TANK1",
            "절차번호": "1",
            "동작내용": "XV OPEN",
            "위험성분류": "relief_vent",
        })
        writer.writerow({
            "시나리오": "시험동 공급",
            "탱크": "TANK1",
            "절차번호": "2",
            "동작내용": "SUPPLY",
            "위험성분류": "test_building_supply_gas",
        })

    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "trace"
    sheet.append(["timestamp", "PT1 (bar)"])
    sheet.append([datetime(2026, 1, 1), 3.0])
    workbook.save(tmp_path / "trace.xlsx")

    report = _load_builder().build_reaudit(tmp_path)

    assert report["status"] == "SCREENING_EVIDENCE_ONLY"
    assert report["scenario_evidence"]["source_file_count"] == 1
    assert report["scenario_evidence"]["record_count"] == 2
    assert report["scenario_evidence"]["outdoor_candidate_count"] == 1
    assert report["scenario_evidence"]["out_of_scope_count"] == 1
    assert report["scenario_evidence"]["qualified_packet_count"] == 0
    assert report["scenario_evidence"]["frequency_applied"] is False
    assert report["timeseries_audit"]["workbook_count"] == 1
    assert report["timeseries_audit"]["state_snapshot_binding_allowed"] is False
    assert report["timeseries_audit"]["sensor_frequency_learning_used"] is False
    assert "do not create provider release packets" in report["promotion_policy"]
