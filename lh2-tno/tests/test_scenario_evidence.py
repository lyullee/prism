import csv

from lh2_tno.scenario_evidence import audit_scenario_root


def test_scenario_register_is_preserved_without_provider_promotion(tmp_path):
    path = tmp_path / "scenario.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "시나리오", "탱크", "절차번호", "동작내용", "위험성분류",
                "누출_예상고장", "누출_위험", "화재_위험", "폭발_위험",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "시나리오": "액화수소 저장(벤트)",
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
    assert report["provider_promotion"]["qualified_packet_count"] == 0


def test_missing_scenario_root_is_fail_closed(tmp_path):
    report = audit_scenario_root(tmp_path / "missing")
    assert report["status"] == "MISSING_SOURCE_ROOT"
    assert report["blocking_reasons"]

