from __future__ import annotations

import json
from pathlib import Path

from lh2_tno.external_nasa_hem_benchmark import audit_nasa_hem_benchmark


ROOT = Path(__file__).resolve().parents[1]


def _result() -> dict:
    return json.loads(
        (ROOT / "examples" / "external_nasa_tn_d4171_hem_results_20261018.json").read_text(
            encoding="utf-8"
        )
    )


def test_nasa_hem_benchmark_is_negative_evidence_only():
    report = audit_nasa_hem_benchmark(
        _result(),
        result_record="examples/external_nasa_tn_d4171_hem_results_20261018.json",
        external_source_commit="7072374",
        external_source_tree_digest="3b186dff" + "0" * 56,
    )
    assert report["status"] == "NEGATIVE_BASELINE_VALIDATION_EVIDENCE"
    assert report["point_count"] == 21
    assert report["blocking_reasons"] == []
    assert report["physical_validation_claim"] is False
    assert report["promotion_allowed"] is False


def test_nasa_hem_benchmark_rejects_missing_test_point():
    result = _result()
    result["points"] = result["points"][:-1]
    report = audit_nasa_hem_benchmark(result)
    assert any("test numbers" in reason for reason in report["blocking_reasons"])
