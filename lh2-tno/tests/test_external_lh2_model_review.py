from __future__ import annotations

import json
from pathlib import Path

from lh2_tno.external_lh2_model_review import review_external_lh2_model_root


def test_external_model_root_review_is_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "model"
    (root / "docs" / "benchmarks").mkdir(parents=True)
    (root / "docs" / "benchmarks" / "center_observation_release_packet.json").write_text(
        json.dumps({
            "schema_version": "0.1",
            "status": "observation_release_packet_fail_closed",
            "release_ready_count": 0,
            "binding_count": 1,
            "metadata_confirmed_count": 0,
        }),
        encoding="utf-8",
    )
    response = root / "tmp" / "provider_response.json"
    response.parent.mkdir(parents=True)
    response.write_text(
        json.dumps({
            "provider_export_schema": "prism.external_accident_history.v1",
            "provider_model": "diagnostic",
            "data": {"event_id": "unmatched"},
        }),
        encoding="utf-8",
    )
    report = review_external_lh2_model_root(root)
    assert report["conclusion"] == "MODEL_ROOT_REVIEWED_NO_PRISM_PROMOTION"
    assert report["provider_like_artifacts"]["provider_response_count"] == 1
    assert report["provider_like_artifacts"]["exact_generic_identity_match_count"] == 0
    assert report["promotion"] == {
        "provider_packet": False,
        "frequency": False,
        "facility_qra": False,
        "physical_validation": False,
    }
    assert any("release-ready" in reason for reason in report["blocking_reasons"])
