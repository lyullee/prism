from lh2_tno.workbook_header_units import (
    extract_header_unit_claims,
    summarize_header_claims,
)


def test_extracts_only_explicit_header_units():
    claims = extract_header_unit_claims(
        ["PT1105A (MPa)", "TT1106 (℃)", "DPT1101", "PT1107 (bar)"]
    )
    assert claims == [
        {"tag": "PT1105A", "unit": "mpa", "header": "PT1105A (MPa)"},
        {"tag": "TT1106", "unit": "degc", "header": "TT1106 (℃)"},
        {"tag": "PT1107", "unit": "bar", "header": "PT1107 (bar)"},
    ]


def test_conflicting_explicit_headers_are_not_resolved():
    summary = summarize_header_claims(
        [
            {"tag": "PT1", "unit": "MPa", "file": "a"},
            {"tag": "PT1", "unit": "bar", "file": "b"},
        ]
    )
    assert summary["conflict_tags"] == ["PT1"]
    assert summary["by_tag"]["PT1"]["units"] == ["bar", "mpa"]
