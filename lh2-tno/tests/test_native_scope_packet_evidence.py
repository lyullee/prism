import json

from scripts.build_native_scope_packet_evidence import build_evidence


def test_native_scope_packet_evidence_requires_bound_snapshot_and_exact_packet(tmp_path):
    catalog_dir = tmp_path / "catalog"
    event_dir = catalog_dir / "events" / "000_tank"
    event_dir.mkdir(parents=True)
    (event_dir / "resolved_release.json").write_text("{}", encoding="utf-8")
    catalog = {
        "event_rows": [{
            "event_id": "event-1",
            "component_id": "tank-1",
            "event_dir": "events/000_tank",
            "status": "EXACT_NATIVE_PACKET",
        }],
    }
    audit = {"rows": [{
        "event_id": "event-1",
        "component_id": "tank-1",
        "status": "BOUND_AND_ECHOED",
    }]}
    catalog_path = catalog_dir / "verification.json"
    audit_path = catalog_dir / "state_snapshot_binding_audit.json"
    output_path = catalog_dir / "packet_evidence.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    result = build_evidence(catalog_path, audit_path, output_path)
    assert result["status"] == "EXACT_NATIVE_SCOPE_PACKET_EVIDENCE"
    assert result["exact_event_count"] == 1
    assert result["rows"][0]["evidence"]["strict_packet_valid"] is True
