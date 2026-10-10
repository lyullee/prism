import pytest

from lh2_tno.equipment_family_case_bridge_audit import (
    EquipmentFamilyCaseBridgeAuditError,
    audit_equipment_family_case_bridge,
)


def _coverage():
    return {
        "schema_version": "prism.equipment_scenario_coverage_audit.v1",
        "assets": [
            {
                "asset_id": "storage-shell",
                "component_kind": "storage_tank",
                "scenario_families": ["vessel_hole", "inventory_depletion"],
            },
            {
                "asset_id": "transfer-line",
                "component_kind": "pipe",
                "scenario_families": ["pipe_hole", "vertical_handoff"],
            },
        ],
        "scenario_families": [
            {"family": "vessel_hole", "applicable_asset_ids": ["storage-shell"]},
            {"family": "inventory_depletion", "applicable_asset_ids": ["storage-shell"]},
            {"family": "pipe_hole", "applicable_asset_ids": ["transfer-line"]},
            {"family": "vertical_handoff", "applicable_asset_ids": ["transfer-line"]},
        ],
    }


def _case(asset_id="storage-shell", family="vessel_hole", request_id="case-1"):
    return {
        "request_id": request_id,
        "asset_id": asset_id,
        "scenario_families": [family],
        "closure_status": "TERMINATION_OPEN",
        "closure_gaps": ["ISOLATION_OPEN", "PROVIDER_QUALIFICATION_OPEN"],
    }


def _worklist(*cases):
    return {
        "schema_version": "prism.release_closure_worklist.v1",
        "cases": list(cases),
    }


def test_bridge_reports_case_asset_outside_scope_without_inference():
    report = audit_equipment_family_case_bridge(
        _coverage(),
        _worklist(_case("inventory-depletion-pipe", "pipe_hole")),
    )
    assert report["status"] == "CASE_SCOPE_MISMATCH_RELEASE_CLOSURE_OPEN"
    assert report["case_assets_outside_scope"] == ["inventory-depletion-pipe"]
    assert report["scope_mismatch_case_count"] == 1
    assert report["promotion_gates"]["facility_qra_allowed"] is False
    assert report["frequency_inference_performed"] is False


def test_bridge_reports_family_asset_mismatch_and_open_closure_gaps():
    report = audit_equipment_family_case_bridge(
        _coverage(),
        _worklist(_case("transfer-line", "vessel_hole")),
    )
    assert report["scope_mismatch_case_count"] == 1
    family = next(row for row in report["scenario_families"] if row["family"] == "vessel_hole")
    assert family["status"] == "CASE_SCOPE_MISMATCH"
    assert family["case_assets_outside_family_scope"] == ["transfer-line"]
    assert report["release_closure_gap_counts"]["ISOLATION_OPEN"] == 1


def test_bridge_keeps_a_valid_case_bound_but_release_open():
    report = audit_equipment_family_case_bridge(
        _coverage(),
        _worklist(
            _case(),
            _case("storage-shell", "inventory_depletion", "case-2"),
            _case("transfer-line", "pipe_hole", "case-3"),
            _case("transfer-line", "vertical_handoff", "case-4"),
        ),
    )
    assert report["status"] == "CASE_BOUND_RELEASE_CLOSURE_OPEN"
    assert report["scope_mismatch_case_count"] == 0
    assert report["promotion_gates"]["equipment_case_bridge_allowed"] is True
    assert report["promotion_gates"]["release_boundary_promotion_allowed"] is False


def test_bridge_rejects_wrong_schema():
    with pytest.raises(EquipmentFamilyCaseBridgeAuditError):
        audit_equipment_family_case_bridge(
            {"schema_version": "wrong", "assets": [], "scenario_families": []},
            _worklist(),
        )
