from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from lh2_tno.isolation_packet_manifest import (
    build_isolation_provider_packet_collection_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ROOT = ROOT / "results/20261026/native_full_scope_union_assessment/isolation_extension"


def _inputs() -> tuple[dict, dict]:
    return (
        json.loads((EXTENSION_ROOT / "isolation_rebound_result.json").read_text(encoding="utf-8")),
        json.loads((EXTENSION_ROOT / "verification.json").read_text(encoding="utf-8")),
    )


def test_isolation_manifest_exposes_all_open_case_requests_without_promotion() -> None:
    campaign, verification = _inputs()
    report = build_isolation_provider_packet_collection_manifest(campaign, verification)

    assert report["schema"] == "prism.provider_packet_collection_manifest.v1"
    assert report["status"] == "OPEN_PROVIDER_PACKET_COLLECTION"
    assert report["request_count"] == 20
    assert report["open_request_count"] == 20
    assert report["qualified_packet_count"] == 0
    assert report["promotion_policy"]["diagnostic_provider_response_is_not_promoted"] is True
    assert len({row["collection_id"] for row in report["rows"]}) == 20
    assert all(row["status"] == "OPEN" for row in report["rows"])
    assert all(row["release_path"] is None for row in report["rows"])
    assert all(row["qualification_path"] is None for row in report["rows"])
    assert all(
        row["exact_match_required"]["provider_result_digests"]
        for row in report["rows"]
    )


def test_isolation_manifest_rejects_a_case_count_mismatch() -> None:
    campaign, verification = _inputs()
    broken = copy.deepcopy(verification)
    broken["isolation_counts"]["cases"] = 19
    with pytest.raises(ValueError, match="case count"):
        build_isolation_provider_packet_collection_manifest(campaign, broken)
