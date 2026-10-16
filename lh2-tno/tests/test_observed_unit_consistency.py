from lh2_tno.observed_unit_consistency import audit_observed_unit_consistency


def _manifest(*, unit="MPa"):
    return {
        "schema_version": "prism.observed_state_input_manifest.v1",
        "sources": [{
            "source_id": "source-1",
            "signals": {
                "pressure": {"column": "PT1105A", "unit": unit},
                "temperature": {"column": "TT1106", "unit": "C"},
            },
        }],
    }


def test_unit_conflict_is_explicit_and_keeps_state_binding_closed():
    report = audit_observed_unit_consistency(
        _manifest(),
        {
            "schema_version": "prism.reviewed_signal_unit_map.v1",
            "signal_units": {
                "PT1105A": {"unit": "bar"},
                "TT1106": {"unit": "degC"},
            },
        },
    )
    assert report["status"] == "BLOCKED_UNIT_CONFLICT"
    assert report["conflict_count"] == 1
    assert report["matched_count"] == 1
    assert report["policy"]["state_snapshot_binding_allowed"] is False
    assert report["policy"]["numeric_range_unit_inference"] is False


def test_missing_reviewed_tag_is_not_inferred():
    report = audit_observed_unit_consistency(
        _manifest(),
        {"signal_units": {"PT1105A": {"unit": "MPa"}}},
    )
    assert report["status"] == "REVIEWED_UNIT_COVERAGE_INCOMPLETE"
    assert report["unreviewed_count"] == 1
    assert report["bindings"][1]["status"] == "MANIFEST_ONLY_UNREVIEWED"
