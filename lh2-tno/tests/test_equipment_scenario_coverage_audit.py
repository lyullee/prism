import pytest

from lh2_tno.equipment_scenario_coverage_audit import (
    CROSSWALK_SCHEMA,
    EquipmentScenarioCoverageAuditError,
    audit_equipment_scenario_coverage,
)


def _equipment():
    return {
        "schema_version": "prism.external_equipment_model_audit.v1",
        "status": "STATE_MODEL_INPUTS_READY_RELEASE_BOUNDARY_UNVERIFIED",
        "assets": [
            {
                "asset_id": "TK-1",
                "component_model": "stratified_tank",
                "ready_for_state_model_input": True,
            },
            {
                "asset_id": "PIPE-1",
                "component_model": "pipe",
                "ready_for_state_model_input": False,
            },
        ],
    }


def _crosswalk(*rows):
    return {
        "schema_version": CROSSWALK_SCHEMA,
        "facility_neutral": True,
        "rows": list(rows),
    }


def test_missing_crosswalk_fails_closed_without_inference():
    report = audit_equipment_scenario_coverage(_equipment())
    assert report["status"] == "CROSSWALK_REQUIRED"
    assert report["mapped_asset_count"] == 0
    assert report["scenario_family_count"] == 12
    assert report["promotion_gates"]["accident_release_packet_allowed"] is False
    assert report["frequency_inference_performed"] is False
    assert "no facility-neutral asset-to-component crosswalk was supplied" in report["blocking_reasons"]


def test_resolved_crosswalk_maps_families_but_keeps_release_boundary_closed():
    report = audit_equipment_scenario_coverage(
        _equipment(),
        kind_crosswalk=_crosswalk(
            {
                "asset_id": "TK-1",
                "component_kind": "storage_tank",
                "identity_status": "resolved",
                "identity_basis": "P&ID tank tag and port schedule",
                "accident_port_ids": ["TK-1.accident-out"],
            },
            {
                "asset_id": "PIPE-1",
                "component_kind": "pipe",
                "identity_status": "resolved",
                "identity_basis": "isometric line list and port schedule",
            },
        ),
    )
    assert report["status"] == "SCENARIO_CATALOG_BOUND_RELEASE_BOUNDARY_UNVERIFIED"
    assert report["resolved_asset_count"] == 2
    assert report["state_model_ready_mapped_asset_count"] == 1
    tank = next(row for row in report["assets"] if row["asset_id"] == "TK-1")
    assert "vessel_hole" in tank["scenario_families"]
    assert tank["reviewed_accident_port_ids"] == ["TK-1.accident-out"]
    families = {row["family"]: row for row in report["scenario_families"]}
    assert families["vessel_hole"]["status"] == "STATE_MODEL_READY_RELEASE_BOUNDARY_UNVERIFIED"
    assert families["pipe_hole"]["status"] == "RELEASE_BOUNDARY_UNVERIFIED"
    assert report["promotion_gates"]["promotion_allowed"] is False


def test_unknown_kind_and_duplicate_crosswalk_are_rejected():
    with pytest.raises(EquipmentScenarioCoverageAuditError):
        audit_equipment_scenario_coverage(
            _equipment(),
            kind_crosswalk=_crosswalk({
                "asset_id": "TK-1",
                "component_kind": "unknown",
                "identity_status": "resolved",
                "identity_basis": "drawing",
            }),
        )
    with pytest.raises(EquipmentScenarioCoverageAuditError):
        audit_equipment_scenario_coverage(
            _equipment(),
            kind_crosswalk=_crosswalk(
                {
                    "asset_id": "TK-1",
                    "component_kind": "storage_tank",
                    "identity_status": "resolved",
                    "identity_basis": "drawing",
                },
                {
                    "asset_id": "TK-1",
                    "component_kind": "storage_tank",
                    "identity_status": "resolved",
                    "identity_basis": "drawing",
                },
            ),
        )
