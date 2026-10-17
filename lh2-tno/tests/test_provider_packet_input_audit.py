from __future__ import annotations

import json
from pathlib import Path

from lh2_tno.provider_packet_input_audit import audit_provider_packet_inputs


ROOT = Path(__file__).parents[1]


def _release() -> dict:
    catalog = json.loads(
        (ROOT / "examples" / "provider_release_catalog_synthetic.json").read_text(
            encoding="utf-8"
        )
    )
    release = dict(catalog["releases"][0])
    release["input_origin"] = "reviewed_measurement"
    return release


def _qualification() -> dict:
    return {
        "schema_version": "prism.provider_qualification_evidence.v1",
        "status": "qualified_actual",
        "provider_origin": "reviewed_actual",
        "evidence_id": "actual-001",
        "provider_source_digest": "0" * 64,
    }


def test_empty_manifest_is_explicitly_blocked():
    report = audit_provider_packet_inputs({"records": []})

    assert report["status"] == "NO_PROVIDER_PACKET_INPUT"
    assert report["accepted_provider_packet_count"] == 0
    assert report["rejected_record_count"] == 0
    assert "manifest contains no records" in report["blocking_reasons"][0]


def test_valid_pair_is_promoted_only_after_strict_sidecar_match():
    report = audit_provider_packet_inputs({
        "records": [{
            "record_id": "actual-001",
            "release": _release(),
            "qualification": _qualification(),
        }]
    })

    assert report["status"] == "QUALIFIED_PROVIDER_PACKET_CATALOG"
    assert report["accepted_provider_packet_count"] == 1
    assert report["rejected_record_count"] == 0
    assert report["provider_packet_evidence"][0]["event_id"] == "provider-accident-01"
    assert report["records"][0]["release_closure_audit"]["status"] == (
        "CLOSURE_EVIDENCE_OPEN"
    )


def test_strict_manifest_mode_rejects_open_release_closure():
    report = audit_provider_packet_inputs(
        {
            "records": [{
                "record_id": "actual-001",
                "release": _release(),
                "qualification": _qualification(),
            }]
        },
        require_release_closure=True,
    )
    assert report["status"] == "NO_PROVIDER_PACKET_INPUT"
    assert report["rejected_record_count"] == 1
    assert "release closure audit is open" in report["records"][0]["blocking_reasons"][0]
    assert report["promotion_policy"]["release_closure_audit_required"] is True


def test_rejected_synthetic_and_bad_digest_records_remain_visible():
    synthetic = _release()
    synthetic["input_origin"] = "synthetic"
    bad = _qualification()
    bad["provider_source_digest"] = "2" * 64
    report = audit_provider_packet_inputs({
        "records": [
            {"record_id": "synthetic", "release": synthetic, "qualification": _qualification()},
            {"record_id": "bad-digest", "release": _release(), "qualification": bad},
        ]
    })

    assert report["status"] == "NO_PROVIDER_PACKET_INPUT"
    assert report["accepted_provider_packet_count"] == 0
    assert report["rejected_record_count"] == 2
    assert len(report["records"]) == 2
    assert all(row["blocking_reasons"] for row in report["records"])


def test_duplicate_event_ids_are_fail_closed():
    report = audit_provider_packet_inputs({
        "records": [
            {"record_id": "first", "release": _release(), "qualification": _qualification()},
            {"record_id": "second", "release": _release(), "qualification": _qualification()},
        ]
    })

    assert report["status"] == "PARTIAL_PROVIDER_PACKET_CATALOG"
    assert report["accepted_provider_packet_count"] == 1
    assert report["rejected_record_count"] == 1
    assert report["duplicate_event_ids"] == ["provider-accident-01"]


def test_distinct_packets_for_one_event_are_kept_for_release_branches():
    second_release = _release()
    second_release["provider_result_digest"] = "2" * 64
    second_qualification = _qualification()
    second_qualification["evidence_id"] = "actual-002"
    second_qualification["provider_result_digest"] = "2" * 64
    report = audit_provider_packet_inputs({
        "records": [
            {"record_id": "branch-a", "release": _release(), "qualification": _qualification()},
            {"record_id": "branch-b", "release": second_release, "qualification": second_qualification},
        ]
    })

    assert report["status"] == "QUALIFIED_PROVIDER_PACKET_CATALOG"
    assert report["accepted_provider_packet_count"] == 2
    assert report["accepted_provider_event_count"] == 1
    assert report["duplicate_event_ids"] == []
