from __future__ import annotations

import json
from pathlib import Path

from lh2_tno.external_release_artifact_intake import audit_external_release_artifacts


def _release(origin: str = "synthetic") -> dict:
    return {
        "provider_export_schema": "prism.resolved_release.v1",
        "event_id": "tank/leak-1",
        "event_kind": "accidental_leak",
        "boundary_kind": "resolved_atmospheric_gas_exit",
        "component_id": "tank-1",
        "port_id": "tank-1.out",
        "input_origin": origin,
        "termination_basis": "inventory_depletion",
        "duration_s": 2.0,
        "available_mass_kg": 10.0,
        "provider_source_digest": "a" * 64,
        "provider_result_digest": "b" * 64,
        "steps": [{"time_s": 0.0, "mass_flow_kg_s": 1.0}],
    }


def test_external_release_intake_is_diagnostic_and_preserves_synthetic_boundary(tmp_path: Path) -> None:
    path = tmp_path / "resolved_release.json"
    path.write_text(json.dumps(_release()), encoding="utf-8")

    report = audit_external_release_artifacts(paths=[path])

    assert report["schema_version"] == "prism.external_release_artifact_intake.v1"
    assert report["status"] == "EXTERNAL_RELEASE_ARTIFACTS_REQUIRE_QUALIFICATION"
    assert report["release_row_count"] == 1
    assert report["synthetic_or_model_prediction_row_count"] == 1
    assert report["qualified_sidecar_row_count"] == 0
    row = report["artifacts"][0]
    assert row["release_shape_valid"] is True
    assert row["diagnostic_only"] is True
    assert row["qualification_bound"] is False
    assert row["qualification_sidecar_present"] is False
    assert row["closure_audit"]["closure_ready"] is False
    assert row["closure_audit"]["blocking_reasons"]
    assert report["closure_ready_row_count"] == 0
    assert report["promotion_policy"]["provider_release_packet_promoted"] is False


def test_external_release_intake_walks_release_set_and_nearby_qualification(tmp_path: Path) -> None:
    path = tmp_path / "resolved_release_set.json"
    path.write_text(json.dumps({"releases": [_release("provider_actual")]}), encoding="utf-8")
    sidecar = tmp_path / "qualification.json"
    sidecar.write_text(
        json.dumps({
            "schema_version": "prism.provider_qualification_evidence.v1",
            "status": "qualified_actual",
            "provider_origin": "reviewed_actual",
            "evidence_id": "evidence-1",
            "exact_digest_binding": True,
            "event_id": "tank/leak-1",
            "component_id": "tank-1",
            "port_ids": ["tank-1.out"],
            "provider_source_digests": ["a" * 64],
            "provider_result_digests": ["b" * 64],
        }),
        encoding="utf-8",
    )

    report = audit_external_release_artifacts(paths=[path])

    assert report["release_row_count"] == 1
    assert report["actual_origin_row_count"] == 1
    assert report["qualified_sidecar_row_count"] == 1
    row = report["artifacts"][0]
    assert row["qualification_sidecar_present"] is True
    assert row["qualification_bound"] is True
    assert row["closure_audit"]["closure_ready"] is False


def test_external_release_intake_discovers_resolved_release_files_under_root(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    path = tmp_path / "nested" / "resolved_releases.json"
    path.write_text(json.dumps({"case-1": _release()}), encoding="utf-8")

    report = audit_external_release_artifacts(roots=[tmp_path])

    assert report["artifact_file_count"] == 1
    assert report["release_row_count"] == 1
    assert report["artifacts"][0]["item_pointer"] == "$.case-1"


def test_external_release_intake_accepts_exact_sidecar_from_separate_root(tmp_path: Path) -> None:
    release_dir = tmp_path / "exports"
    sidecar_dir = tmp_path / "qualification"
    release_dir.mkdir()
    sidecar_dir.mkdir()
    release_path = release_dir / "resolved_release.json"
    release_path.write_text(json.dumps(_release("provider_actual")), encoding="utf-8")
    sidecar_path = sidecar_dir / "reviewed_packet.json"
    sidecar_path.write_text(
        json.dumps({
            "schema_version": "prism.provider_qualification_evidence.v1",
            "status": "qualified_actual",
            "provider_origin": "reviewed_actual",
            "evidence_id": "separate-evidence-1",
            "exact_digest_binding": True,
            "event_id": "tank/leak-1",
            "component_id": "tank-1",
            "port_ids": ["tank-1.out"],
            "provider_source_digests": ["a" * 64],
            "provider_result_digests": ["b" * 64],
        }),
        encoding="utf-8",
    )

    report = audit_external_release_artifacts(
        paths=[release_path],
        qualification_paths=[sidecar_path],
    )

    assert report["qualification_file_count"] == 1
    assert report["qualified_sidecar_row_count"] == 1
    assert report["artifacts"][0]["qualification_bound"] is True
