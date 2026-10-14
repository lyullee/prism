from __future__ import annotations

import json

from lh2_tno.observed_hazop_consequence_chain import (
    audit_observed_hazop_consequence_preflight,
)


def _inputs(tmp_path, *, termination_basis="emergency_relief_discharge"):
    packet = {
        "event_id": "event-1",
        "component_id": "vent-01",
        "port_id": "vent-out",
        "event_kind": "emergency_relief",
        "termination_basis": termination_basis,
        "duration_s": 1.0,
        "available_mass_kg": 1.0,
        "cumulative_mass_out_kg": 0.5,
        "input_origin": "model_prediction",
    }
    path = tmp_path / "resolved_release.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    runtime = {
        "schema_version": "prism.observed_hazop_runtime_audit.v1",
        "rows": [{
            "selected_scenarios": [{
                "scenario_id": "scenario-1",
                "hazop_row_id": "hazop-1",
                "component_id": "observed-vent",
                "operating_mode": "standby",
                "scenario_family": "vent_hole",
                "release_mode": "maximum_relief_discharge",
            }],
        }],
    }
    binding = {
        "schema_version": "prism.observed_hazop_provider_event_binding.v1",
        "status": "OBSERVED_HAZOP_PROVIDER_EVENT_BINDINGS_DIAGNOSTIC",
        "rows": [{
            "scenario_id": "scenario-1",
            "provider_event_id": "event-1",
            "provider_component_id": "vent-01",
            "provider_port_id": "vent-out",
        }],
    }
    worklist = {"work_items": [{
        "event_id": "event-1",
        "component_id": "vent-01",
        "profile": "TNO_RELIEF_DEVICE",
    }]}
    evidence = {"rows": [{
        "event_id": "event-1",
        "evidence": {"resolved_packet_paths": ["resolved_release.json"]},
    }]}
    return runtime, binding, worklist, evidence, path.parent


def test_preflight_allows_contract_compatible_packet(tmp_path):
    runtime, binding, worklist, evidence, packet_root = _inputs(tmp_path)
    report = audit_observed_hazop_consequence_preflight(
        runtime,
        binding,
        worklist,
        evidence,
        packet_root=packet_root,
    )
    assert report["status"] == "OBSERVED_HAZOP_PROVIDER_CHAIN_PREFLIGHT_READY"
    assert report["ready_for_provider_chain_count"] == 1
    assert report["rows"][0]["provider_component_kind"] == "vent_stack"


def test_preflight_withholds_unsupported_termination(tmp_path):
    runtime, binding, worklist, evidence, packet_root = _inputs(
        tmp_path,
        termination_basis="synthetic_diagnostic_horizon",
    )
    report = audit_observed_hazop_consequence_preflight(
        runtime,
        binding,
        worklist,
        evidence,
        packet_root=packet_root,
    )
    assert report["status"] == "OBSERVED_HAZOP_PROVIDER_CHAIN_PREFLIGHT_WITHHELD"
    assert report["ready_for_provider_chain_count"] == 0
    assert report["rows"][0]["checks"]["termination_basis_compatible"] is False
