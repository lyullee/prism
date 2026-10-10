import pytest

from lh2_tno.equipment_frequency_binding_audit import (
    EquipmentFrequencyBindingAuditError,
    audit_equipment_frequency_binding,
)
from lh2_tno.equipment_scenario_coverage_audit import audit_equipment_scenario_coverage


def _coverage(*, resolved=True):
    equipment = {
        "schema_version": "prism.external_equipment_model_audit.v1",
        "status": "STATE_MODEL_INPUTS_READY_RELEASE_BOUNDARY_UNVERIFIED",
        "assets": [{
            "asset_id": "TK-1",
            "component_model": "stratified_tank",
            "ready_for_state_model_input": True,
        }],
    }
    return audit_equipment_scenario_coverage(
        equipment,
        kind_crosswalk={
            "schema_version": "prism.equipment_kind_crosswalk.v1",
            "facility_neutral": True,
            "rows": [{
                "asset_id": "TK-1",
                "component_kind": "storage_tank",
                "identity_status": "resolved" if resolved else "candidate",
                "identity_basis": "P&ID tank tag and port schedule",
            }],
        },
    )


def _event(event_id="freq/TK-1/G1"):
    return {
        "id": event_id,
        "asset_id": "TK-1",
        "model_component_id": "TK-1",
        "profile": "LH2_STORAGE_TANK",
        "basis": "LH2_LITERATURE",
        "source": "reviewed-literature",
        "source_sha256": "a" * 64,
        "annual_frequency_per_year": 1.0e-5,
        "release": {"mode": "hole", "hole_diameter_m": 0.01},
        "limitations": ["literature baseline; not field validated"],
    }


def test_no_resolved_assets_withhold_frequency_without_zero_fallback():
    report = audit_equipment_frequency_binding(_coverage(resolved=False))
    assert report["status"] == "FREQUENCY_BINDING_WITHHELD"
    assert report["frequency_event_count"] == 0
    assert report["uncomputed_family_count"] == 12
    assert report["promotion_gates"]["frequency_inference_allowed"] is False
    assert report["promotion_gates"]["facility_qra_allowed"] is False
    assert report["policy"]["unresolved_assets_do_not_receive_zero_frequency"] is True


def test_literature_event_binds_to_resolved_family_but_release_stays_open():
    report = audit_equipment_frequency_binding(
        _coverage(),
        frequency_events=[_event()],
    )
    assert report["status"] == "LITERATURE_FREQUENCY_BOUND_RELEASE_UNVERIFIED"
    assert report["valid_frequency_event_count"] == 1
    assert report["bound_family_count"] == 2
    assert "vessel_hole" not in report["uncomputed_families"]
    assert "liquid_two_phase" not in report["uncomputed_families"]
    assert report["promotion_gates"]["literature_frequency_binding_allowed"] is True
    assert report["promotion_gates"]["provider_release_required"] is True
    assert report["promotion_gates"]["consequence_binding_allowed"] is False


def test_reliquefier_two_sided_event_matches_catalog_family():
    equipment = {
        "schema_version": "prism.external_equipment_model_audit.v1",
        "status": "SYNTHETIC_GENERIC_MANIFEST_DECLARED",
        "assets": [{
            "asset_id": "RELIQ-1",
            "component_model": "reliquefier",
            "ready_for_state_model_input": True,
        }],
    }
    coverage = audit_equipment_scenario_coverage(
        equipment,
        kind_crosswalk={
            "schema_version": "prism.equipment_kind_crosswalk.v1",
            "facility_neutral": True,
            "rows": [{
                "asset_id": "RELIQ-1",
                "component_kind": "reliquefier",
                "identity_status": "resolved",
                "identity_basis": "generic manifest reliquefier ports",
            }],
        },
    )
    event = _event("freq/RELIQ-1/G4")
    event.update({
        "asset_id": "RELIQ-1",
        "profile": "TNO_HX_INSIDE_WEAK_SHELL",
        "release": {"mode": "two_sided_rupture", "hole_diameter_m": 0.025},
    })
    report = audit_equipment_frequency_binding(coverage, frequency_events=[event])
    assert report["valid_frequency_event_count"] == 1
    assert "two_sided_rupture" not in report["uncomputed_families"]


def test_event_for_unknown_asset_is_blocked():
    event = _event()
    event["asset_id"] = "TK-404"
    report = audit_equipment_frequency_binding(_coverage(), frequency_events=[event])
    assert report["status"] == "PARTIAL_FREQUENCY_BINDING"
    assert report["valid_frequency_event_count"] == 0
    assert any("absent from scenario coverage" in reason for reason in report["blocking_reasons"])


def test_candidate_asset_does_not_mark_family_frequency_bound():
    report = audit_equipment_frequency_binding(
        _coverage(resolved=False),
        frequency_events=[_event()],
    )
    assert report["status"] == "FREQUENCY_BINDING_WITHHELD"
    assert report["valid_frequency_event_count"] == 0
    assert report["bound_family_count"] == 0
    assert "vessel_hole" in report["uncomputed_families"]
    assert "liquid_two_phase" in report["uncomputed_families"]
    assert all(not row["frequency_bound"] for row in report["scenario_families"])


def test_port_scoped_frequency_requires_an_explicit_external_port_crosswalk():
    coverage = _coverage()
    coverage["assets"][0]["reviewed_accident_port_ids"] = ["TK-1.accident-out"]
    event = _event()
    event["port_ids"] = ["TK-1.accident-out"]
    report = audit_equipment_frequency_binding(coverage, frequency_events=[event])
    assert report["valid_frequency_event_count"] == 1
    assert report["frequency_port_binding"]["reviewed_port_bound_event_count"] == 1
    assert report["events"][0]["port_binding_status"] == "BOUND_REVIEWED_PORT"

    event["port_ids"] = ["TK-1.wrong-out"]
    mismatch = audit_equipment_frequency_binding(coverage, frequency_events=[event])
    assert mismatch["valid_frequency_event_count"] == 0
    assert mismatch["frequency_port_binding"]["port_binding_withheld_event_count"] == 1
    assert any("accident-port crosswalk" in reason for reason in mismatch["blocking_reasons"])


def test_bad_frequency_provenance_schema_is_rejected():
    with pytest.raises(EquipmentFrequencyBindingAuditError):
        audit_equipment_frequency_binding(
            _coverage(),
            frequency_provenance={"schema_version": "wrong", "generated_events": []},
        )


def test_non_object_provenance_event_is_rejected():
    with pytest.raises(EquipmentFrequencyBindingAuditError, match="must be an object"):
        audit_equipment_frequency_binding(
            _coverage(),
            frequency_provenance={
                "schema_version": "prism.frequency_provenance.v1",
                "generated_events": ["malformed"],
            },
        )
