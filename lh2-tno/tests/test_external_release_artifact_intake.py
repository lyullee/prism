from __future__ import annotations

import json
from pathlib import Path

from lh2_tno.external_release_artifact_intake import audit_external_release_artifacts
from lh2_tno.external_release_normalization import (
    audit_external_release_response,
    audit_external_release_set_response,
    build_diagnostic_release_rebind,
)
from lh2_tno.contracts import canonical_digest


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


def test_external_release_intake_expands_release_set_container(tmp_path: Path) -> None:
    path = tmp_path / "resolved_release_set.json"
    path.write_text(
        json.dumps({
            "provider_export_schema": "prism.resolved_release_set.v1",
            "releases": [_release()],
        }),
        encoding="utf-8",
    )

    report = audit_external_release_artifacts(paths=[path])

    assert report["release_row_count"] == 1
    assert report["artifacts"][0]["item_pointer"] == "$.releases[0]"


def test_external_release_intake_normalizes_nearby_provider_response_without_promotion(
    tmp_path: Path,
) -> None:
    release = _release("model_prediction")
    release.update(
        {
            "termination_provenance": "native model ledger",
            "provider_source_digest": "a" * 64,
            "cumulative_mass_out_kg": 2.0,
        }
    )
    release_path = tmp_path / "resolved_release.json"
    release_path.write_text(json.dumps(release), encoding="utf-8")
    response_path = tmp_path / "provider_response.json"
    response_path.write_text(
        json.dumps(
            {
                "provider_export_schema": "prism.native_provider_response.v1",
                "provider_model": "native-test-model",
                "provider_source_digest": "a" * 64,
                "provider_state_snapshot_digest": "c" * 64,
                "data": {
                    "event_id": release["event_id"],
                    "component_id": release["component_id"],
                    "port_id": release["port_id"],
                    "duration_s": release["duration_s"],
                    "available_mass_kg": release["available_mass_kg"],
                    "cumulative_mass_out_kg": release["cumulative_mass_out_kg"],
                    "termination_basis": release["termination_basis"],
                    "termination_provenance": release["termination_provenance"],
                    "provider_meta": {
                        "initial_mass_kg": 10.0,
                        "final_mass_kg": 8.0,
                        "residual_mass_kg": 0.0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    report = audit_external_release_artifacts(paths=[release_path])

    assert report["provider_response_pair_count"] == 1
    assert report["provider_response_normalized_count"] == 1
    assert report["provider_response_mismatch_count"] == 0
    audit = report["artifacts"][0]["provider_response_audit"]
    assert audit["status"] == "NORMALIZED_PROVIDER_RESPONSE"
    assert audit["diagnostic_only"] is True
    assert audit["closure_ready"] is False
    assert audit["promotion_policy"]["provider_result_digest_synthesized"] is False
    assert audit["checks"]["mass_ledger_closed"] is True


def test_external_release_response_mismatch_is_explicit(tmp_path: Path) -> None:
    release = _release("model_prediction")
    release.update(
        {
            "termination_provenance": "native model ledger",
            "cumulative_mass_out_kg": 2.0,
        }
    )
    release_path = tmp_path / "resolved_release.json"
    release_path.write_text(json.dumps(release), encoding="utf-8")
    (tmp_path / "provider_response.json").write_text(
        json.dumps(
            {
                "provider_source_digest": "z" * 64,
                "data": {
                    "event_id": "different-event",
                    "component_id": release["component_id"],
                    "port_id": release["port_id"],
                    "duration_s": release["duration_s"],
                    "available_mass_kg": release["available_mass_kg"],
                    "cumulative_mass_out_kg": release["cumulative_mass_out_kg"],
                    "termination_basis": release["termination_basis"],
                    "termination_provenance": release["termination_provenance"],
                },
            }
        ),
        encoding="utf-8",
    )

    report = audit_external_release_artifacts(paths=[release_path])

    audit = report["artifacts"][0]["provider_response_audit"]
    assert audit["status"] == "PROVIDER_RESPONSE_MISMATCH"
    assert audit["checks"]["identity_matches"] is False
    assert audit["checks"]["source_digest_matches"] is False
    assert audit["closure_ready"] is False


def test_external_release_response_binds_canonical_result_digest() -> None:
    release = _release("model_prediction")
    release.update(
        {
            "termination_provenance": "native model ledger",
            "cumulative_mass_out_kg": 2.0,
        }
    )
    response = {
        "provider_export_schema": "prism.native_provider_response.v1",
        "provider_model": "native-test-model",
        "provider_source_digest": "a" * 64,
        "provider_state_snapshot_digest": "c" * 64,
        "data": {
            "event_id": release["event_id"],
            "component_id": release["component_id"],
            "port_id": release["port_id"],
            "duration_s": release["duration_s"],
            "available_mass_kg": release["available_mass_kg"],
            "cumulative_mass_out_kg": release["cumulative_mass_out_kg"],
            "termination_basis": release["termination_basis"],
            "termination_provenance": release["termination_provenance"],
        },
    }
    release["provider_result_digest"] = canonical_digest(response)

    audit = audit_external_release_response(release, response)

    assert audit["status"] == "NORMALIZED_PROVIDER_RESPONSE"
    assert audit["checks"]["result_digest_rebound"] is True
    assert audit["provider_result_digest_binding"] == "canonical_response_digest"
    assert audit["computed_provider_result_digest"] == release["provider_result_digest"]


def test_diagnostic_release_rebind_attaches_only_exported_mass_ledger() -> None:
    release = _release("model_prediction")
    release.update({
        "termination_provenance": "native model ledger",
        "cumulative_mass_out_kg": 2.0,
    })
    response = {
        "provider_export_schema": "prism.external_accident_history.v1",
        "provider_model": "native-test-model",
        "provider_source_digest": "a" * 64,
        "data": {
            "event_id": release["event_id"],
            "component_id": release["component_id"],
            "port_id": release["port_id"],
            "duration_s": release["duration_s"],
            "available_mass_kg": release["available_mass_kg"],
            "cumulative_mass_out_kg": release["cumulative_mass_out_kg"],
            "termination_basis": release["termination_basis"],
            "termination_provenance": release["termination_provenance"],
            "provider_meta": {
                "initial_mass_kg": 10.0,
                "cumulative_mass_in_kg": 0.5,
                "final_mass_kg": 8.5,
                "native_inventory_owner": "DynamicHEMPipe",
                "cumulative_mass_out_kg": 2.0,
                "isolation_time_s": 0.5,
                "post_isolation_observation_s": 0.25,
                "pressure_equalization_time_s": 1.25,
                "post_pressure_equalization_observation_s": 0.75,
                "pressure_equalization_success": True,
                "terminal_source_pressure_pa_abs": 101325.0,
                "ambient_pressure_pa_abs": 101325.0,
                "max_post_pressure_equalization_flow_kg_s": 0.0,
            },
        },
    }
    release["provider_result_digest"] = canonical_digest(response)

    rebound = build_diagnostic_release_rebind(release, response)

    assert rebound["status"] == "DIAGNOSTIC_RELEASE_REBOUND"
    assert rebound["mass_balance_attached"] is True
    assert rebound["release"]["provider_mass_balance"]["final_mass_kg"] == 8.5
    assert rebound["release"]["provider_mass_balance"]["mass_basis_id"] == "DynamicHEMPipe"
    assert rebound["release"]["provider_mass_balance"]["cumulative_mass_in_kg"] == 0.5
    assert rebound["release"]["provider_mass_balance"]["pressure_equalization_success"] is True
    assert rebound["release"]["provider_mass_balance"]["pressure_equalization_time_s"] == 1.25
    assert rebound["release"]["provider_mass_balance"]["max_post_pressure_equalization_flow_kg_s"] == 0.0
    assert rebound["release"]["termination_basis"] == "inventory_depletion"
    assert rebound["promotion"]["qualified_provider_packet_allowed"] is False
    assert rebound["promotion"]["frequency_inference_allowed"] is False


def test_diagnostic_release_rebind_merges_legacy_mass_balance_shape() -> None:
    """A legacy packet may carry a partial ledger alongside the same provider response."""
    release = _release("model_prediction")
    release.update({
        "termination_provenance": "native model ledger",
        "cumulative_mass_out_kg": 2.0,
        "provider_mass_balance": {
            "schema_version": "prism.provider_mass_balance.v1",
            "initial_mass_kg": 10.0,
            "cumulative_mass_in_kg": None,
            "cumulative_mass_out_kg": 2.0,
            "final_mass_kg": 8.0,
            "reported_residual_mass_kg": 0.0,
            "derived_accounting_residual_kg": 0.0,
        },
    })
    response = {
        "provider_export_schema": "prism.external_accident_history.v1",
        "provider_model": "native-test-model",
        "provider_source_digest": "a" * 64,
        "data": {
            "event_id": release["event_id"],
            "component_id": release["component_id"],
            "port_id": release["port_id"],
            "duration_s": release["duration_s"],
            "available_mass_kg": release["available_mass_kg"],
            "cumulative_mass_out_kg": release["cumulative_mass_out_kg"],
            "termination_basis": release["termination_basis"],
            "termination_provenance": release["termination_provenance"],
            "provider_meta": {
                "native_inventory_owner": "native-test-model",
                "initial_mass_kg": 10.0,
                "final_mass_kg": 8.0,
                "residual_mass_kg": 0.0,
                "cumulative_mass_out_kg": 2.0,
            },
        },
    }
    release["provider_result_digest"] = canonical_digest(response)

    rebound = build_diagnostic_release_rebind(release, response)

    assert rebound["mass_balance_attached"] is True
    merged = rebound["release"]["provider_mass_balance"]
    assert merged["mass_basis_id"] == "native-test-model"
    assert merged["cumulative_mass_in_kg"] == 0.0


def test_external_release_set_response_keeps_two_endpoints_and_shared_inventory() -> None:
    endpoints = []
    responses = {}
    for port_id in ("pipe.out.a", "pipe.out.b"):
        response = {
            "provider_export_schema": "prism.external_accident_history.v1",
            "provider_model": "native-two-sided-test",
            "provider_source_digest": "a" * 64,
            "provider_state_snapshot_digest": "c" * 64,
            "data": {
                "event_id": "pipe/rupture-1",
                "component_id": "pipe-1",
                "port_id": port_id,
                "event_kind": "accidental_leak",
                "duration_s": 2.0,
                "available_mass_kg": 10.0,
                "cumulative_mass_out_kg": 1.0,
                "termination_basis": "two_sided_rupture",
                "termination_provenance": "native shared inventory",
                "provider_meta": {
                    "shared_initial_mass_kg": 10.0,
                    "shared_final_mass_kg": 8.0,
                    "shared_total_cumulative_mass_kg": 2.0,
                },
            },
        }
        response_digest = canonical_digest(response)
        endpoints.append({
            "provider_export_schema": "prism.resolved_release.v1",
            "event_id": "pipe/rupture-1",
            "event_kind": "accidental_leak",
            "boundary_kind": "resolved_atmospheric_gas_exit",
            "component_id": "pipe-1",
            "port_id": port_id,
            "input_origin": "model_prediction",
            "termination_basis": "two_sided_rupture",
            "termination_provenance": "native shared inventory",
            "failure_opening_diameter_m": 0.1,
            "duration_s": 2.0,
            "available_mass_kg": 10.0,
            "cumulative_mass_out_kg": 1.0,
            "provider_source_digest": "a" * 64,
            "provider_result_digest": response_digest,
            "steps": [],
        })
        responses[port_id] = response
    release_set = {
        "provider_export_schema": "prism.resolved_release_set.v1",
        "event_id": "pipe/rupture-1",
        "component_id": "pipe-1",
        "rupture_mode": "two_sided_rupture",
        "releases": endpoints,
        "available_mass_kg": 10.0,
        "cumulative_mass_out_kg": 2.0,
        "provider_source_digest": "a" * 64,
        "provider_result_digest": "b" * 64,
    }

    audit = audit_external_release_set_response(release_set, responses)

    assert audit["status"] == "NORMALIZED_PROVIDER_RELEASE_SET"
    assert audit["endpoint_contracts_valid"] is True
    assert audit["shared_inventory_evidence_attached"] is True
    assert audit["shared_inventory_checks"]["shared_mass_closes"] is True
    assert audit["qualified_provider_packet_allowed"] is False
    assert audit["facility_qra_allowed"] is False


def test_external_release_set_response_missing_endpoint_is_fail_closed() -> None:
    release = _release("model_prediction")
    release.update({
        "event_id": "pipe/rupture-2",
        "component_id": "pipe-2",
        "port_id": "pipe-2.out.a",
        "termination_basis": "two_sided_rupture",
        "termination_provenance": "native shared inventory",
        "failure_opening_diameter_m": 0.1,
    })
    release["provider_result_digest"] = "b" * 64
    other = dict(release, port_id="pipe-2.out.b")
    release_set = {
        "provider_export_schema": "prism.resolved_release_set.v1",
        "event_id": "pipe/rupture-2",
        "component_id": "pipe-2",
        "rupture_mode": "two_sided_rupture",
        "releases": [release, other],
        "available_mass_kg": 10.0,
        "cumulative_mass_out_kg": 2.0,
    }

    audit = audit_external_release_set_response(
        release_set,
        {"pipe-2.out.a": {}},
    )

    assert audit["status"] == "PROVIDER_RELEASE_SET_MISMATCH"
    assert audit["endpoint_contracts_valid"] is False
    assert audit["shared_inventory_evidence_attached"] is False
    assert any("missing for port pipe-2.out.b" in reason for reason in audit["blocking_reasons"])


def test_external_release_response_marks_optional_gas_handoff_blocked_without_source_state() -> None:
    release = _release("model_prediction")
    release.update(
        {
            "termination_provenance": "native model ledger",
            "cumulative_mass_out_kg": 2.0,
            "steps": [
                {
                    "time_s": 0.0,
                    "mass_flow_kg_s": 1.0,
                    "effective_area_m2": 1.0e-4,
                }
            ],
        }
    )
    response = {
        "provider_export_schema": "prism.native_provider_response.v1",
        "provider_model": "native-gas-test-model",
        "provider_source_digest": "a" * 64,
        "provider_state_snapshot_digest": "c" * 64,
        "data": {
            "event_id": release["event_id"],
            "component_id": release["component_id"],
            "port_id": release["port_id"],
            "duration_s": release["duration_s"],
            "available_mass_kg": release["available_mass_kg"],
            "cumulative_mass_out_kg": release["cumulative_mass_out_kg"],
            "termination_basis": release["termination_basis"],
            "termination_provenance": release["termination_provenance"],
            "provider_meta": {
                "initial_mass_kg": 10.0,
                "final_mass_kg": 8.0,
                "cumulative_mass_out_kg": 2.0,
            },
            "steps": release["steps"],
        },
    }
    release["provider_result_digest"] = canonical_digest(response)

    audit = audit_external_release_response(release, response)

    source = audit["compressible_source_state_audit"]
    assert source["handoff_candidate"] is True
    assert source["status"] == "BLOCKED_MISSING_PROVIDER_SOURCE_STATE"
    assert source["provider_source_state_interval_count"] == 0
    assert audit["closure_ready"] is False
    assert any("atmospheric packet velocity cannot be substituted" in reason for reason in audit["blocking_reasons"])


def test_external_release_intake_counts_optional_gas_handoff_gap(tmp_path: Path) -> None:
    release = _release("model_prediction")
    release.update(
        {
            "termination_provenance": "native model ledger",
            "cumulative_mass_out_kg": 2.0,
            "steps": [{"time_s": 0.0, "mass_flow_kg_s": 1.0}],
        }
    )
    release_path = tmp_path / "resolved_release.json"
    release_path.write_text(json.dumps(release), encoding="utf-8")
    response = {
        "provider_export_schema": "prism.native_provider_response.v1",
        "provider_model": "native-gas-test-model",
        "provider_source_digest": "a" * 64,
        "provider_state_snapshot_digest": "c" * 64,
        "data": {
            "event_id": release["event_id"],
            "component_id": release["component_id"],
            "port_id": release["port_id"],
            "duration_s": release["duration_s"],
            "available_mass_kg": release["available_mass_kg"],
            "cumulative_mass_out_kg": release["cumulative_mass_out_kg"],
            "termination_basis": release["termination_basis"],
            "termination_provenance": release["termination_provenance"],
            "provider_meta": {
                "initial_mass_kg": 10.0,
                "final_mass_kg": 8.0,
                "cumulative_mass_out_kg": 2.0,
            },
            "steps": release["steps"],
        },
    }
    response_path = tmp_path / "provider_response.json"
    response_path.write_text(json.dumps(response), encoding="utf-8")
    release["provider_result_digest"] = canonical_digest(response)
    release_path.write_text(json.dumps(release), encoding="utf-8")

    report = audit_external_release_artifacts(paths=[release_path])

    assert report["compressible_handoff_candidate_count"] == 1
    assert report["provider_source_state_complete_count"] == 0
    assert report["provider_source_state_incomplete_count"] == 1
    assert report["compressible_handoff_blocked_count"] == 1
