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


def test_external_model_root_review_keeps_match_section_structured_without_closure_audit(
    tmp_path: Path,
) -> None:
    root = tmp_path / "empty-model"
    root.mkdir()
    report = review_external_lh2_model_root(root)
    assert report["external_match_review"] == {
        "status": "NOT_EVALUATED_NO_CLOSURE_AUDIT",
        "candidate_count": 0,
        "exact_match_count": 0,
        "qualification_artifact_count": 0,
        "physical_validation_artifact_count": 0,
        "complete_facility_qra_artifact_count": 0,
    }


def test_anonymized_model_validation_is_recorded_without_qra_promotion(tmp_path: Path) -> None:
    root = tmp_path / "model"
    benchmark_dir = root / "docs" / "benchmarks"
    benchmark_dir.mkdir(parents=True)
    (benchmark_dir / "sci_minimal_release_packet.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "artifact_id": "anonymous_lh2_minimal_sci_release_v1",
                "disclosure_level": "minimum",
                "model_scope": ["mass conservation", "two-phase thermodynamic state closure"],
                "validation_protocol": {
                    "blind_prediction": True,
                    "held_out_dates": True,
                    "primary_metric": "nMAPE; accuracy = 100 - nMAPE",
                    "unscored_units_excluded_from_aggregate": True,
                },
                "aggregate_validation": {
                    "declared_unit_count": 12,
                    "independently_scored_unit_count": 3,
                    "observed_unit_macro_accuracy_percent": 95.4,
                    "full_unit_macro_accuracy_percent": None,
                    "full_unit_target_met": False,
                    "unscored_units_imputed": False,
                },
                "data_availability": {
                    "raw_historian_records": "not publicly released",
                    "facility_identifying_drawings": "not publicly released",
                    "instrument_tags_and_addresses": "not publicly released",
                    "operating_logs": "not publicly released",
                    "reproducibility_material": "synthetic benchmark",
                },
                "publication_claim_boundary": "Only independently scored observed units may be reported.",
            }
        ),
        encoding="utf-8",
    )

    report = review_external_lh2_model_root(root)

    assert len(report["benchmark_reviews"]) == 1
    review = report["benchmark_reviews"][0]
    assert review["evidence_class"] == "RESTRICTED_ANONYMIZED_MODEL_VALIDATION"
    assert review["aggregate_validation"] == {
        "declared_unit_count": 12,
        "independently_scored_unit_count": 3,
        "observed_unit_macro_accuracy_percent": 95.4,
        "full_unit_macro_accuracy_percent": None,
        "full_unit_target_met": False,
        "unscored_units_imputed": False,
    }
    assert review["promotion_boundary"] == {
        "provider_packet": False,
        "frequency": False,
        "facility_qra": False,
        "physical_validation": False,
        "reason": (
            "Anonymized aggregate model validation is retained as restricted "
            "evidence; it does not qualify an accident-release provider, a "
            "facility QRA, or independent end-to-end physical validation."
        ),
    }
    assert report["restricted_model_validation"] == {
        "artifact_count": 1,
        "artifact_ids": ["anonymous_lh2_minimal_sci_release_v1"],
        "independently_scored_unit_count": 3,
        "observed_unit_macro_accuracy_percent": [95.4],
        "full_unit_target_met": False,
        "promotion": {
            "provider_packet": False,
            "frequency": False,
            "facility_qra": False,
            "physical_validation": False,
        },
    }
    assert report["promotion"]["physical_validation"] is False
