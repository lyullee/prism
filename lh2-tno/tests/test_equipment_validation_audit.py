import json
from pathlib import Path

import pytest

from lh2_tno.equipment_validation_audit import (
    EquipmentValidationAuditError,
    audit_equipment_validation_evidence,
)


def _write_package(tmp_path: Path, *, overlap: bool = False, promoted: bool = False):
    dataset = {
        "schema_version": "1.0",
        "purpose": "physics-model validation on quiescent closed-operation candidates",
        "model_class": "horizontal_vacuum_insulated_lh2_storage_tank",
        "fit_policy": {
            "default_physics_model": "no_fit",
            "holdout_refit": False,
            "fitted_values_modify_component_library": False,
        },
        "cleaning_policy": {"interpolation": False},
        "cases": [
            {"case_id": "FIT-01", "split": "fit_candidate", "start": "2026-05-08 17:00:00", "complete_primary_bins": 2},
            {"case_id": "HOLDOUT-01", "split": "holdout_validation", "start": ("2026-05-08" if overlap else "2026-07-13") + " 18:00:00", "complete_primary_bins": 3},
        ],
        "row_count": 5,
        "fit_candidate_row_count": 2,
        "holdout_row_count": 3,
        "channel_count": 3,
    }
    scenarios = [
        {
            "scenario_id": "S02_CLOSED_STORAGE",
            "status": "blocked",
            "simulator_invoked": promoted,
            "score_promoted": promoted,
            "blocker_count": 1,
        }
    ]
    gate = {
        "scope": "official independent validation release gate",
        "execution_type": "physics_only",
        "summary": {
            "scenario_count": 1,
            "released_scenario_count": 0,
            "simulator_invocation_count": 0 if not promoted else 1,
            "official_score": None if not promoted else 0.9,
            "official_score_status": "blocked_until_explicit_raw_historian_dcs_plc_export",
        },
        "checks": {
            "all_scenarios_audited": True,
            "closed_raw_gate_prevented_simulation": not promoted,
            "no_score_promoted": not promoted,
            "no_fitting": True,
        },
        "scenarios": scenarios,
    }
    paths = {}
    for name, value in (("dataset.json", dataset), ("gate.json", gate), ("topology.json", {
        "status": "screening_only", "screening_only": True,
        "center_binding_ready": False, "topology_node_count": 1,
        "topology_edge_count": 1, "node_constructable_count": 0,
        "edge_constructable_count": 0,
    })):
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    return paths


def test_equipment_validation_audit_keeps_observation_evidence_restricted(tmp_path):
    paths = _write_package(tmp_path)
    report = audit_equipment_validation_evidence(
        paths["dataset.json"], paths["gate.json"], topology_chain_path=paths["topology.json"]
    )

    assert report["status"] == "RESTRICTED_EQUIPMENT_OBSERVATION_EVIDENCE"
    assert report["dataset"]["fit_case_count"] == 1
    assert report["dataset"]["holdout_case_count"] == 1
    assert report["independent_validation"]["summary"]["released_scenario_count"] == 0
    assert report["physical_validation_claim"] is False
    assert report["full_chain_validation_claim"] is False
    assert report["frequency_inference_performed"] is False


def test_equipment_validation_audit_rejects_fit_holdout_date_overlap(tmp_path):
    paths = _write_package(tmp_path, overlap=True)
    with pytest.raises(EquipmentValidationAuditError, match="dates must be disjoint"):
        audit_equipment_validation_evidence(paths["dataset.json"], paths["gate.json"])


def test_equipment_validation_audit_blocks_promoted_release_gate(tmp_path):
    paths = _write_package(tmp_path, promoted=True)
    report = audit_equipment_validation_evidence(paths["dataset.json"], paths["gate.json"])

    assert report["status"] == "INVALID_EQUIPMENT_EVIDENCE"
    assert any("promoted execution" in reason for reason in report["blocking_reasons"])
    assert report["facility_qra_claim"] is False
