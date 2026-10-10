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
