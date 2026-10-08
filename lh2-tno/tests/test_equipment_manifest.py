import json
from pathlib import Path

from lh2_tno.equipment_manifest import EquipmentManifest, audit_manifest
from lh2_tno.contracts import Receptor


def _basis():
    return {"fluid": "Hydrogen", "energy_reference": "CoolProp-HEOS:Hydrogen:native"}


def _complete_manifest(**overrides):
    data = {
        "facility_id": "generic-outdoor-lh2",
        "environment": "outdoor",
        "configuration_origin": "synthetic",
        "components": [
            {"id": "tank", "kind": "storage_tank", "position_enu_m": [0, 0, 1],
             "property_basis": _basis(), "parameters_si": {"volume_m3": 10}},
            {"id": "boundary", "kind": "boundary", "position_enu_m": [10, 0, 1],
             "property_basis": _basis()},
        ],
        "ports": [
            {"id": "tank-out", "component_id": "tank", "phase": "liquid", "direction": "out"},
            {"id": "boundary-in", "component_id": "boundary", "phase": "liquid", "direction": "in"},
        ],
        "edges": [{"id": "e1", "source_port": "tank-out", "target_port": "boundary-in"}],
        "receptors": [{"id": "r1", "position_enu_m": [20, 0, 1]}],
        "scenarios": [{"id": "fill", "required_ports": ["tank-out", "boundary-in"],
                       "required_controls": ["valve_position"],
                       "observed_controls": ["valve_position"]}],
    }
    data.update(overrides)
    return EquipmentManifest.model_validate_json(json.dumps(data))


def test_complete_generic_manifest_promotes_to_facility():
    manifest = _complete_manifest()
    result = audit_manifest(manifest)
    assert result["status"] == "EXECUTABLE"
    facility = manifest.to_facility()
    assert facility.id == "generic-outdoor-lh2"
    assert facility.edges[0].id == "e1"


def test_missing_port_and_control_are_explicitly_uncomputed():
    manifest = _complete_manifest(ports=(), edges=())
    result = audit_manifest(manifest)
    assert result["status"] == "PARTIAL"
    assert any("no declared port mapping" in reason for reason in result["blocking_reasons"])


def test_candidate_provider_data_cannot_promote():
    manifest = _complete_manifest(components=[
        {"id": "tank", "kind": "storage_tank", "position_enu_m": [0, 0, 1],
         "property_basis": _basis(), "parameters_si": {"volume_m3": 10}, "source_status": "candidate"},
        {"id": "boundary", "kind": "boundary", "position_enu_m": [10, 0, 1],
         "property_basis": _basis()},
    ])
    result = audit_manifest(manifest)
    assert result["status"] == "PARTIAL"
    assert any("source_status=candidate" in reason for reason in result["blocking_reasons"])


def test_indoor_manifest_is_excluded_from_outdoor_scope():
    manifest = _complete_manifest(environment="indoor")
    result = audit_manifest(manifest)
    assert result["status"] == "EXCLUDED"
    assert "declared scope is outdoor only" in result["blocking_reasons"]


def test_shipped_manifest_example_is_executable():
    path = Path(__file__).parents[1] / "examples" / "equipment_manifest.json"
    manifest = EquipmentManifest.from_json(path)
    result = audit_manifest(manifest)
    assert result["status"] == "EXECUTABLE"
    assert manifest.to_facility().id == "generic-lh2-manifest-example"
