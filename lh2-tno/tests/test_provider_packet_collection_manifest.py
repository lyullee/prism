from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from lh2_tno.provider_packet_collection_manifest import (
    build_provider_packet_collection_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_REQUEST = ROOT / (
    "results/20261026/native_full_scope_union_assessment/facility_evidence_request.json"
)


def _request() -> dict:
    return json.loads(EVIDENCE_REQUEST.read_text(encoding="utf-8"))


def test_current_facility_requests_become_open_case_rows() -> None:
    report = build_provider_packet_collection_manifest(_request())

    assert report["schema"] == "prism.provider_packet_collection_manifest.v1"
    assert report["status"] == "OPEN_PROVIDER_PACKET_COLLECTION"
    assert report["request_count"] == 44
    assert report["open_request_count"] == 44
    assert report["qualified_packet_count"] == 0
    assert len(report["rows"]) == 44
    assert all(row["status"] == "OPEN" for row in report["rows"])
    assert all(row["release_path"] is None for row in report["rows"])
    assert all(row["qualification_path"] is None for row in report["rows"])
    assert all(row["strict_gate_requirements"] for row in report["rows"])
    assert report["promotion_gate"]["facility_ir_fn_remains_withheld_until_all_true"] is True
    assert report["strict_gate_catalog"]["MISSING_PROVIDER_CASES"]
    assert all(row["event_id"] and row["component_id"] for row in report["rows"])


def test_missing_case_identity_is_invalid_and_fail_closed() -> None:
    request = copy.deepcopy(_request())
    request["case_requests"][0]["event_id"] = None
    request["case_requests"][0]["component_id"] = None

    report = build_provider_packet_collection_manifest(request)

    assert report["status"] == "INVALID_PROVIDER_PACKET_COLLECTION_MANIFEST"
    assert report["qualified_packet_count"] == 0
    assert any("event_id is missing" in reason for reason in report["blocking_reasons"])
    assert any("component_id is missing" in reason for reason in report["blocking_reasons"])
    assert report["rows"][0]["blocking_reasons"]


def test_wrong_request_schema_is_rejected() -> None:
    request = _request()
    request["schema_version"] = "wrong.schema.v1"

    with pytest.raises(ValueError, match="schema_version"):
        build_provider_packet_collection_manifest(request)
