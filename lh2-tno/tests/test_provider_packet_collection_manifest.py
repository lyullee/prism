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
CURRENT_EVIDENCE_REQUEST = ROOT / (
    "results/20261115/"
    "native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/"
    "facility_evidence_request.json"
)
CURRENT_MANIFEST = ROOT / (
    "results/20261115/"
    "native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/"
    "provider_packet_collection_manifest.json"
)
EXAMPLE_MANIFEST = ROOT / "examples/provider_packet_collection_manifest_current.json"


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
    assert report["provider_input_origin_policy"]["required_for_qualification"] == "reviewed_measurement"
    assert all(row["required_input_origin"] == "reviewed_measurement" for row in report["rows"])
    assert report["promotion_policy"]["required_provider_input_origin"] == "reviewed_measurement"
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


def test_current_authoritative_and_example_manifests_match_contract() -> None:
    """Keep the checked-in collection worksheet and its example synchronized."""
    request = json.loads(CURRENT_EVIDENCE_REQUEST.read_text(encoding="utf-8"))
    generated = build_provider_packet_collection_manifest(request)
    authoritative = json.loads(CURRENT_MANIFEST.read_text(encoding="utf-8"))
    example = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))

    row_keys = (
        "collection_id",
        "event_id",
        "component_id",
        "release_branch_id",
        "required_provider_evidence",
        "strict_gate_requirements",
        "exact_match_required",
    )
    assert authoritative["status"] == generated["status"] == example["status"]
    assert (
        authoritative["request_count"]
        == generated["request_count"]
        == example["request_count"]
    )
    assert (
        authoritative["open_request_count"]
        == generated["open_request_count"]
        == example["open_request_count"]
    )
    assert (
        authoritative["qualified_packet_count"]
        == generated["qualified_packet_count"]
        == example["qualified_packet_count"]
    )
    for generated_row, authoritative_row, example_row in zip(
        generated["rows"], authoritative["rows"], example["rows"]
    ):
        for key in row_keys:
            assert authoritative_row[key] == generated_row[key] == example_row[key]
        assert any("mass_basis_id" in item for item in generated_row["required_provider_evidence"])
