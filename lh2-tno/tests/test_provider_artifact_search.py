import json

from lh2_tno.provider_artifact_search import audit_provider_artifact_roots


def test_combined_artifact_search_keeps_current_and_legacy_results_separate(tmp_path):
    current = tmp_path / "current"
    legacy = tmp_path / "legacy"
    current.mkdir()
    legacy.mkdir()
    (current / "normal_flow.json").write_text(
        json.dumps({"mass_flow_kg_s": 0.1}), encoding="utf-8"
    )
    (legacy / "old.json").write_text(
        json.dumps({
            "event_kind": "accidental_leak",
            "event_id": "old-1",
            "component_id": "tank-1",
            "failure_opening_diameter_m": 0.01,
            "duration_s": 1.0,
            "steps": [{"time_s": 0.0}],
        }),
        encoding="utf-8",
    )
    report = audit_provider_artifact_roots(current, (legacy,))
    assert report["status"] == "NO_QUALIFIED_PROVIDER_PACKET_FOUND"
    assert report["summary"]["current_qualified_packet_count"] == 0
    assert report["summary"]["legacy_missing_schema_count"] == 1
    assert report["summary"]["facility_ir_fn_allowed"] is False
    assert report["promotion_policy"]["current_and_legacy_results_remain_separate"] is True
