from lh2_tno.observed_origin_provenance import audit_manifest_origin


def test_prediction_named_source_declared_as_measured_requires_review():
    report = audit_manifest_origin({
        "sources": [{
            "source_id": "predicted",
            "path": "scenario/예측데이터.xlsx",
            "origin": "historian_measured",
        }],
    })
    assert report["status"] == "ORIGIN_REVIEW_REQUIRED"
    assert report["conflict_count"] == 1
    assert report["policy"]["origin_changed_automatically"] is False


def test_unmarked_path_does_not_infer_origin():
    report = audit_manifest_origin({
        "sources": [{
            "source_id": "source",
            "path": "scenario/data.xlsx",
            "origin": "historian_measured",
        }],
    })
    assert report["status"] == "NO_FILENAME_CONFLICTS"
    assert report["sources"][0]["filename_origin_signal"] == "no_filename_origin_signal"
