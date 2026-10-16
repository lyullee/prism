import json

import pytest

from lh2_tno.provider_artifact_audit import (
    audit_provider_artifact_root,
    audit_provider_artifact_roots,
)


def test_provider_artifact_audit_keeps_diagnostic_packets_unqualified(tmp_path):
    (tmp_path / "equipment" ).mkdir()
    (tmp_path / "equipment" / "provider_response.json").write_text(
        json.dumps({"ok": True, "physical_validation_claim": False}), encoding="utf-8"
    )
    (tmp_path / "equipment" / "verification.json").write_text(
        json.dumps({"facility_total_risk_withheld": True}), encoding="utf-8"
    )

    report = audit_provider_artifact_root(tmp_path)

    assert report["status"] == "EXTERNAL_ARTIFACTS_DIAGNOSTIC_ONLY"
    assert report["provider_response_count"] == 1
    assert report["qualification_artifact_count"] == 0
    assert report["physical_validation_artifact_count"] == 0
    assert report["complete_facility_qra_artifact_count"] == 0
    assert report["promotion_policy"]["frequency_assigned"] is False


def test_provider_artifact_audit_detects_qualification_record(tmp_path):
    (tmp_path / "provider_response.json").write_text(
        json.dumps({
            "provider_qualification": {
                "schema_version": "prism.provider_qualification_evidence.v1",
                "status": "qualified_actual",
                "evidence_id": "evidence-1",
            },
            "physical_validation_claim": True,
            "complete_facility_qra_claim": True,
        }), encoding="utf-8"
    )

    report = audit_provider_artifact_root(tmp_path)

    assert report["qualification_artifact_count"] == 1
    assert report["physical_validation_artifact_count"] == 1
    assert report["complete_facility_qra_artifact_count"] == 1
    assert report["status"] == "ARTIFACTS_REQUIRE_PRISM_RECONCILIATION"


def test_provider_artifact_audit_excludes_named_virtual_environment_trees(tmp_path):
    (tmp_path / ".venv-local" / "Lib").mkdir(parents=True)
    (tmp_path / "venv" / "Lib").mkdir(parents=True)
    (tmp_path / ".venv-local" / "Lib" / "package.json").write_text(
        json.dumps({"physical_validation_claim": True}), encoding="utf-8"
    )
    (tmp_path / "venv" / "Lib" / "package.json").write_text(
        json.dumps({"complete_facility_qra_claim": True}), encoding="utf-8"
    )
    (tmp_path / "equipment.json").write_text(
        json.dumps({"physical_validation_claim": False}), encoding="utf-8"
    )

    report = audit_provider_artifact_root(tmp_path)

    assert report["artifact_count"] == 1
    assert report["physical_validation_artifact_count"] == 0
    assert report["complete_facility_qra_artifact_count"] == 0


def test_provider_artifact_audit_reads_korean_windows_encoded_json(tmp_path):
    (tmp_path / "provider_response.json").write_text(
        '{"schema_version": "screening_only", "facility": "액화수소"}',
        encoding="cp949",
    )

    report = audit_provider_artifact_root(tmp_path)

    assert report["artifact_count"] == 1
    assert report["errors"] == []
    assert report["provider_response_count"] == 1


def test_provider_artifact_audit_roots_keeps_sources_separate_and_fail_closed(
    tmp_path,
):
    current = tmp_path / "current"
    legacy = tmp_path / "legacy"
    current.mkdir()
    legacy.mkdir()
    (current / "provider_response.json").write_text("{}", encoding="utf-8")
    (legacy / "verification.json").write_text("{}", encoding="utf-8")

    report = audit_provider_artifact_roots(
        {"current": current, "legacy": legacy}
    )

    assert report["schema_version"] == "prism.provider_artifact_roots_audit.v1"
    assert report["status"] == "EXTERNAL_ARTIFACTS_DIAGNOSTIC_ONLY"
    assert report["root_count"] == 2
    assert set(report["roots"]) == {"current", "legacy"}
    assert report["summary"]["artifact_count"] == 2
    assert report["summary"]["provider_response_count"] == 1
    assert report["summary"]["qualification_artifact_count"] == 0
    assert report["summary"]["facility_ir_fn_allowed"] is False
    assert report["promotion_policy"]["roots_remain_separate"] is True


def test_provider_artifact_audit_roots_rejects_empty_mapping(tmp_path):
    with pytest.raises(ValueError, match="non-empty"):
        audit_provider_artifact_roots({})
