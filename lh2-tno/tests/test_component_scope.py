from lh2_tno.component_scope import expected_component_ids_for_release


def test_explicit_interface_exclusion_is_not_reported_as_missing_release_component():
    assert expected_component_ids_for_release(
        ("tank-01", "receiving-boundary-01", "pipe-01"),
        excluded_model_components={
            "receiving-boundary-01": "interface boundary has no accidental release mode",
        },
    ) == ("tank-01", "pipe-01")


def test_release_component_helper_preserves_extensions_and_deduplicates():
    assert expected_component_ids_for_release(
        ("tank-01", "pipe-01"),
        excluded_model_components=(),
        additional_component_ids=("pipe-01", "vertical-handoff-pipe-01"),
    ) == ("tank-01", "pipe-01", "vertical-handoff-pipe-01")
