from lh2_tno.inspection_timeseries import classify_signal, normalise_unit_map, resolve_unit, summarise_numeric


def test_signal_classification_does_not_infer_units_from_tag_name():
    assert classify_signal("PT1105A") == {"category": "pressure", "basis": "tag_prefix"}
    assert classify_signal("DPT1101")["category"] == "differential_pressure"
    assert classify_signal("TT1106")["category"] == "temperature"


def test_unit_map_requires_exact_reviewed_mapping():
    unit_map = normalise_unit_map({"signal_units": {"PT1105A": "bar"}})
    assert resolve_unit("PT1105A", unit_map) == ("bar", "CONFIRMED_BY_REVIEWED_MAP")
    assert resolve_unit("PT1105B", unit_map) == (None, "MISSING_OR_UNCONFIRMED")


def test_numeric_summary_keeps_only_aggregate_values():
    assert summarise_numeric([1, 2.5, None, "3", True]) == {"numeric_count": 2, "min": 1.0, "max": 2.5}

