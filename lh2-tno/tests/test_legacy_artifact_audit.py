import json
from pathlib import Path

from lh2_tno.legacy_artifact_audit import audit_legacy_provider_artifacts


def test_legacy_audit_reports_missing_schema_without_mutating_packet(tmp_path):
    packet = {
        "event_kind": "accidental_leak",
        "event_id": "legacy-1",
        "component_id": "tank-1",
        "steps": [{"time_s": 0.0}],
        "duration_s": 1.0,
        "failure_opening_diameter_m": 0.01,
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    report = audit_legacy_provider_artifacts(tmp_path)
    assert report["status"] == "LEGACY_OUTPUT_REQUIRES_EXPLICIT_SCHEMA_MIGRATION"
    assert report["release_shaped_candidate_count"] == 1
    assert report["legacy_missing_schema_count"] == 1
    assert report["qualified_current_schema_count"] == 0
    assert "provider_export_schema" not in json.loads(path.read_text(encoding="utf-8"))


def test_legacy_audit_strict_validates_current_schema_candidate(tmp_path):
    root = Path(__file__).parents[1]
    source = json.loads(
        (root / "examples" / "provider_release_catalog_synthetic.json").read_text(
            encoding="utf-8"
        )
    )
    (tmp_path / "current.json").write_text(
        json.dumps(source["releases"][0]), encoding="utf-8"
    )
    report = audit_legacy_provider_artifacts(tmp_path)
    assert report["status"] == "CURRENT_SCHEMA_ARTIFACTS_AUDITED"
    assert report["release_shaped_candidate_count"] == 1
    assert report["legacy_missing_schema_count"] == 0
    assert report["qualified_current_schema_count"] == 1
    assert report["strict_validation_failure_count"] == 0
