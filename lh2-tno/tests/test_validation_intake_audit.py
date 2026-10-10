from lh2_tno.validation_intake_audit import (
    ValidationIntakeAuditError,
    audit_validation_intake,
)


def _inspection(*, reviewed_unit_map_supplied=False, errors=0):
    return {
        "schema_version": "prism.inspection_center_timeseries_audit.v1",
        "status": "SCREENING_ONLY_UNIT_BASIS_UNCONFIRMED",
        "source_file_count": 2,
        "aggregate": {
            "workbook_count": 2,
            "sheet_count": 3,
            "workbook_or_sheet_error_count": errors,
            "reviewed_unit_map_supplied": reviewed_unit_map_supplied,
        },
        "files": [
            {
                "relative_path": "receipt/predicted.xlsx",
                "scenario_group": "receipt",
                "sheet_count": 2,
                "sheets": [
                    {
                        "row_count": 10,
                        "nonempty_row_count": 9,
                        "numeric_candidate_column_count": 4,
                        "unit_unconfirmed_numeric_column_count": 4,
                    },
                    {
                        "row_count": 3,
                        "nonempty_row_count": 3,
                        "numeric_candidate_column_count": 4,
                        "unit_unconfirmed_numeric_column_count": 4,
                    },
                ],
            },
            {
                "relative_path": "vent/predicted.xlsx",
                "scenario_group": "vent",
                "sheet_count": 1,
                "sheets": [
                    {
                        "row_count": 5,
                        "nonempty_row_count": 5,
                        "numeric_candidate_column_count": 2,
                        "unit_unconfirmed_numeric_column_count": 2,
                    }
                ],
            },
        ],
    }


def _equipment(*, released=0):
    return {
        "schema_version": "prism.equipment_validation_audit.v1",
        "status": "RESTRICTED_EQUIPMENT_OBSERVATION_EVIDENCE",
        "physical_validation_claim": False,
        "accident_release_validation_claim": False,
        "independent_validation": {
            "summary": {
                "released_scenario_count": released,
                "simulator_invocation_count": 0,
                "official_score": None,
                "official_score_status": "blocked_until_explicit_raw_historian_dcs_plc_export",
            }
        },
        "topology": {
            "center_binding_ready": False,
            "forward_comparison_allowed": False,
        },
    }


def test_validation_intake_aggregates_groups_without_promotion():
    report = audit_validation_intake(_inspection(), _equipment())
    assert report["status"] == "SCREENED_NO_PROMOTION"
    assert report["scenario_groups"]["receipt"]["row_count"] == 13
    assert report["scenario_groups"]["vent"]["numeric_candidate_column_count"] == 2
    assert report["promotion_gates"]["promotion_allowed"] is False
    assert report["frequency_inference_performed"] is False
    assert "normal_process_time_series_is_not_a_release_packet" in report["policy"]


def test_validation_intake_keeps_units_and_release_gate_separate():
    report = audit_validation_intake(
        _inspection(reviewed_unit_map_supplied=True),
        _equipment(released=0),
    )
    assert report["promotion_gates"]["reviewed_unit_map_supplied"] is True
    assert report["promotion_gates"]["state_snapshot_binding_allowed"] is False
    assert report["promotion_gates"]["accidental_release_packet_allowed"] is False
    assert "inspection_unit_basis_unconfirmed" not in report["blocking_reasons"]
    assert "independent_accident_release_scenarios_not_released" in report["blocking_reasons"]


def test_validation_intake_records_audit_read_errors():
    report = audit_validation_intake(_inspection(errors=1), None)
    assert report["promotion_gates"]["inspection_audit_read_complete"] is False
    assert "inspection_workbook_or_sheet_errors" in report["blocking_reasons"]
    assert report["inputs"]["equipment_validation"]["status"] == "NOT_SUPPLIED"


def test_validation_intake_rejects_wrong_schema():
    bad = _inspection()
    bad["schema_version"] = "wrong"
    try:
        audit_validation_intake(bad)
    except ValidationIntakeAuditError as error:
        assert "unsupported inspection audit schema" in str(error)
    else:
        raise AssertionError("wrong schema must be rejected")
