from __future__ import annotations

import json

from scripts.build_provider_sidecar_manifest_template import build_manifest_template


def test_template_preserves_request_identity_and_groups_packet_paths(tmp_path):
    packet_path = tmp_path / "resolved_release_set.json"
    catalogue = tmp_path / "catalogue.json"
    current = {
        "event_id": "event-1",
        "component_id": "component-1",
        "port_id": "out-1",
        "provider_source_digest": "a" * 64,
        "provider_result_digest": "b" * 64,
    }
    catalogue.write_text(json.dumps({
        "schema_version": "prism.generic_provider_evidence_requests.v1",
        "requests": [
            {
                "request_id": "event-1::out-1",
                "packet_path": str(packet_path),
                "packet_index": 0,
                "request_kind": "qualification_only",
                "closure_status": "CLOSURE_READY_FOR_QUALIFICATION",
                "current_packet": current,
            },
            {
                "request_id": "event-1::out-2",
                "packet_path": str(packet_path),
                "packet_index": 1,
                "request_kind": "qualification_only",
                "closure_status": "CLOSURE_READY_FOR_QUALIFICATION",
                "current_packet": {**current, "port_id": "out-2", "provider_result_digest": "c" * 64},
            },
        ],
    }), encoding="utf-8")
    result = build_manifest_template(catalogue)
    assert result["schema_version"] == "prism.provider_qualification_sidecar_manifest.v1"
    assert result["status"] == "TEMPLATE_ONLY"
    assert result["entry_count"] == 2
    assert result["entries"][0]["qualification_sidecar_path"] == result["entries"][1]["qualification_sidecar_path"]
    assert result["entries"][0]["expected_identity"]["provider_source_digest"] == "a" * 64
    assert result["promotion_allowed"] is False


def test_template_flattens_native_full_scope_request_rows(tmp_path):
    packet_path = tmp_path / "resolved_release.json"
    catalogue = tmp_path / "native_requests.json"
    current = {
        "event_id": "native-event",
        "component_id": "native-component",
        "port_id": "out",
        "provider_source_digest": "c" * 64,
        "provider_result_digest": "d" * 64,
    }
    catalogue.write_text(json.dumps({
        "schema_version": "prism.native_full_scope_provider_qualification_requests.v1",
        "requests": [{
            "event_id": "native-event",
            "component_id": "native-component",
            "packet_path": str(packet_path),
            "requests": [{
                "request_schema": "prism.provider_qualification_request.v1",
                "request_id": "native-event",
                "request_kind": "qualification_only",
                "current_packet": current,
            }],
        }],
    }), encoding="utf-8")
    result = build_manifest_template(catalogue)
    assert result["catalogue_schema_version"] == (
        "prism.native_full_scope_provider_qualification_requests.v1"
    )
    assert result["entry_count"] == 1
    assert result["entries"][0]["expected_identity"]["component_id"] == "native-component"
    assert result["promotion_allowed"] is False


def test_template_accepts_facility_evidence_request_and_preserves_case_metadata(tmp_path):
    catalogue = tmp_path / "facility_request.json"
    catalogue.write_text(json.dumps({
        "schema_version": "prism.facility_evidence_request.v1",
        "case_requests": [{
            "request_id": "facility/event-1",
            "event_id": "event-1",
            "asset_id": "tank-1",
            "component_id": "tank-1",
            "hazop_scenario_id": "HZ-1",
            "operating_mode": "receiving",
            "scenario_families": ["vessel_hole"],
            "required_input_origin": "reviewed_measurement",
            "frequency_port_ids": ["tank.out"],
            "provider_packet_port_ids": ["tank.out"],
            "request_kind": "QUALIFIED_PROVIDER_PACKET",
            "current_status": "EXECUTED",
            "exact_match_required": {
                "event_id": "event-1",
                "component_id": "tank-1",
                "port_ids": ["tank.out"],
                "provider_source_digests": ["e" * 64],
                "provider_result_digests": ["f" * 64],
            },
        }],
    }), encoding="utf-8")
    result = build_manifest_template(catalogue)
    entry = result["entries"][0]
    assert result["catalogue_schema_version"] == "prism.facility_evidence_request.v1"
    assert result["entry_count"] == 1
    assert entry["facility_case_request_id"] == "facility/event-1"
    assert entry["operating_mode"] == "receiving"
    assert entry["requested_exact_identity"]["port_ids"] == ["tank.out"]
    assert entry["qualification_sidecar_path"].startswith(
        "REPLACE_WITH_REVIEWED_SIDECARS/"
    )
    assert entry["packet_path"].startswith(
        "REPLACE_WITH_REVIEWED_PROVIDER_PACKETS/"
    )
    assert result["promotion_allowed"] is False
