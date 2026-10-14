import csv
from datetime import datetime, timedelta

import pytest

from lh2_tno.scenario_evidence import audit_scenario_root, build_provider_packet_request_catalog


def test_scenario_register_is_preserved_without_provider_promotion(tmp_path):
    path = tmp_path / "scenario.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "시나리오", "운전모드", "탱크", "절차번호", "동작내용", "위험성분류",
                "누출_예상고장", "누출_위험", "화재_위험", "폭발_위험",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "시나리오": "액화수소 저장(벤트)",
            "운전모드": "공급",
            "탱크": "TANK1",
            "절차번호": "2",
            "동작내용": "XV10 OPEN",
            "위험성분류": "relief_vent",
            "누출_예상고장": "valve delay",
            "누출_위험": "residual release",
            "화재_위험": "vent fire",
            "폭발_위험": "delayed ignition",
        })

    report = audit_scenario_root(tmp_path)

    assert report["status"] == "SCENARIO_EVIDENCE_ONLY"
    assert report["files"]["scenario_rows"] == 1
    assert report["candidate_accident_family_counts"] == {"vent_hole": 1}
    record = report["scenario_records"][0]
    assert record["promotion_status"] == "SCENARIO_ONLY_PROVIDER_PACKET_MISSING"
    assert record["frequency_assigned"] is False
    assert record["operating_mode_candidate"] == "supply"
    assert record["operating_mode_source"] == "procedure_field:공급"
    assert record["operating_mode_is_runtime_input"] is False
    assert report["provider_promotion"]["qualified_packet_count"] == 0


def test_missing_scenario_root_is_fail_closed(tmp_path):
    report = audit_scenario_root(tmp_path / "missing")
    assert report["status"] == "MISSING_SOURCE_ROOT"
    assert report["blocking_reasons"]


def test_provider_packet_request_catalog_keeps_scenario_rows_unpromoted(tmp_path):
    path = tmp_path / "scenario.csv"
    path.write_text(
        "scenario,asset,step,operation,hazard_class\n"
        "storage,TANK1,1,XV OPEN,pressure_rise_monitor\n",
        encoding="utf-8",
    )
    audit = audit_scenario_root(tmp_path)
    catalog = build_provider_packet_request_catalog(audit)
    assert catalog["status"] == "PROVIDER_PACKET_REQUESTS_ONLY"
    assert catalog["request_count"] == 1
    assert catalog["candidate_family_request_counts"] == {
        "inventory_over_600s": 1,
        "vent_hole": 1,
    }
    request = catalog["requests"][0]
    assert request["promotion_status"] == "REQUESTED_PROVIDER_PACKET"
    assert request["frequency_assigned"] is False
    assert request["release_values_present"] is False
    assert request["provider_export_schema"] == "prism.resolved_release.v1"
    assert request["runtime_operating_mode_required"] is True
    assert request["source"]["operating_mode_candidate"] is None
    assert "boundary_kind" in request["required_provider_fields"]
    assert "failure_opening_diameter_m" in request["required_provider_fields"]
    assert catalog["provider_promotion"]["qualified_packet_count"] == 0


def test_time_series_metadata_is_observed_but_not_promoted(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "sensor_trace"
    worksheet.append(["timestamp", "PT1206 (bar)", "TT1206 (K)"])
    start = datetime(2026, 1, 1, 0, 0, 0)
    worksheet.append([start, 3.2, 21.0])
    worksheet.append([start + timedelta(seconds=2), 3.1, 21.1])
    workbook.save(tmp_path / "trace.xlsx")

    report = audit_scenario_root(tmp_path)

    assert report["files"]["telemetry_candidate_sheet_count"] == 1
    assert report["files"]["telemetry_metadata_incomplete_sheet_count"] == 1
    telemetry = report["workbook_reports"][0]["sheets"][0]["telemetry"]
    assert telemetry["sample_count"] == 2
    assert telemetry["sample_interval_s"]["median"] == 2.0
    assert telemetry["sensor_columns"][0]["explicit_unit"] == "bar"
    assert telemetry["promotion_status"] == "TELEMETRY_CANDIDATE_METADATA_INCOMPLETE"
    assert report["provider_promotion"]["qualified_packet_count"] == 0
    assert any("sensor traces" in reason for reason in report["blocking_reasons"])


def test_external_csv_import_maps_candidates_without_frequency(tmp_path):
    path = tmp_path / "sequence.csv"
    path.write_text(
        "시나리오,탱크,절차번호,동작내용,위험성분류,누출_예상고장,누출_위험,누출_조치방법\n"
        "저장,TANK1,1,XV10 OPEN,relief_vent,valve stuck,vent leak,ESD and gas detector\n"
        "공급,TANK1,2,시험동 공급,test_building_supply_gas,line leak,indoor accumulation,ventilation\n",
        encoding="utf-8-sig",
    )
    from lh2_tno.scenario_evidence import import_scenario_evidence

    report = import_scenario_evidence(tmp_path)
    assert report["status"] == "SCREENING_EVIDENCE_IMPORTED"
    assert report["summary"]["record_count"] == 2
    assert report["summary"]["family_candidate_counts"]["vent_hole"] == 1
    assert report["policy"]["frequency_applied"] is False
    assert report["policy"]["facility_qra_claim"] is False
    assert report["records"][1]["scope_status"] == "OUTSIDE_DECLARED_OUTDOOR_SCOPE"
    assert "hydrogen_detection" in report["records"][0]["candidate_monitoring_signals"]
    assert report["records"][0]["operating_mode_candidate"] == "storage_vent"
    assert report["records"][1]["operating_mode_candidate"] == "supply"
    assert report["records"][0]["candidate_component_kinds"] == ["vent_stack"]
    assert report["records"][0]["candidate_release_modes"] == [
        "maximum_relief_discharge", "hole"
    ]
    assert report["records"][0]["hazop_row_status"] == (
        "CANDIDATE_REQUIRES_NUMERIC_TRIGGER_AND_REVIEWED_TAG"
    )
    assert report["records"][0]["numeric_trigger_status"] == "MISSING_FROM_PROCEDURE_REGISTER"
    assert report["policy"]["candidate_component_and_release_maps_are_not_provider_bindings"] is True
    assert report["policy"]["numeric_trigger_and_unit_review_required_before_hazop_table_promotion"] is True
    assert report["records"][0]["operating_mode_is_runtime_input"] is False
    assert report["policy"]["procedure_label_is_not_a_runtime_operating_mode"] is True
