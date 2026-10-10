from __future__ import annotations

from copy import deepcopy

from lh2_tno.observed_component_mapping_audit import audit_observed_component_mapping


def _evidence() -> dict:
    return {
        "schema_version": "prism.observed_equipment_state_evidence.v1",
        "status": "OBSERVATION_STATE_EVIDENCE_ONLY",
        "source_rows": [
            {"source_id": "s-intake", "component_id": "intake", "sample_count": 2},
            {"source_id": "s-vent", "component_id": "vent", "sample_count": 2},
        ],
    }


def _manifest() -> dict:
    return {
        "schema_version": "prism.observed_component_mapping_manifest.v1",
        "mappings": [
            {
                "mapping_id": "m-intake",
                "observed_component_id": "intake",
                "source_ids": ["s-intake"],
                "candidate_component_class": "storage_tank",
                "candidate_facility_asset_aliases": ["TK-1101"],
                "review_status": "candidate",
                "evidence_refs": ["source:intake"],
                "mapping_basis": "scenario label",
            },
            {
                "mapping_id": "m-vent",
                "observed_component_id": "vent",
                "source_ids": ["s-vent"],
                "candidate_component_class": "operating_vent",
                "candidate_facility_asset_aliases": ["XV10"],
                "review_status": "unresolved",
                "evidence_refs": ["source:vent"],
                "mapping_basis": "scenario label",
            },
        ],
    }


def test_candidate_class_mappings_are_recorded_without_asset_promotion():
    report = audit_observed_component_mapping(_evidence(), _manifest())
    assert report["status"] == "CANDIDATE_COMPONENT_CLASS_MAPPINGS_ONLY"
    assert report["observed_component_count"] == 2
    assert report["candidate_mapping_count"] == 2
    assert report["exact_facility_component_count"] == 0
    assert report["policy"]["release_event_binding_is_not_created"] is True
    assert all(row["status"] == "CANDIDATE_CLASS_MAPPING" for row in report["rows"])


def test_mapping_with_facility_id_is_fail_closed():
    manifest = deepcopy(_manifest())
    manifest["mappings"][0]["facility_component_id"] = "TK-1101"
    report = audit_observed_component_mapping(_evidence(), manifest)
    assert report["status"] == "PARTIAL_OR_INVALID_COMPONENT_MAPPINGS"
    assert report["candidate_mapping_count"] == 1
    assert any("facility_component_id" in reason for reason in report["blocking_reasons"])


def test_field_confirmed_asset_identity_is_allowed_but_release_stays_closed():
    manifest = deepcopy(_manifest())
    mapping = manifest["mappings"][0]
    mapping["facility_component_id"] = "TK-1101"
    mapping["review_status"] = "field_confirmed"
    mapping["asset_identity_evidence_refs"] = ["pid:TK-1101"]
    report = audit_observed_component_mapping(_evidence(), manifest)
    assert report["status"] == "MIXED_COMPONENT_MAPPINGS_NO_RELEASE"
    assert report["candidate_mapping_count"] == 1
    assert report["exact_facility_component_count"] == 1
    row = next(item for item in report["rows"] if item["observed_component_id"] == "intake")
    assert row["status"] == "EXACT_COMPONENT_MAPPING_NO_RELEASE"
    assert row["facility_component_id"] == "TK-1101"
    assert report["policy"]["release_event_binding_is_not_created"] is True
