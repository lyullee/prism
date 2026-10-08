import json
from pathlib import Path


def test_workspace_provider_artifact_search_keeps_legacy_outputs_unpromoted():
    root = Path(__file__).parents[1]
    evidence = json.loads(
        (root / "examples" / "provider_artifact_search_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    current, legacy = evidence["searches"]
    assert current["json_files_scanned"] == 559
    assert current["qualified_accident_release_files"] == 0
    assert legacy["accident_release_candidate_files"] == 42
    assert legacy["qualified_accident_release_files"] == 0
    assert legacy["missing_field_counts"] == {"provider_export_schema": 42}
    assert evidence["promotion_policy"]["facility_ir_fn_allowed"] is False
