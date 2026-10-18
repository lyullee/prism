import json
from pathlib import Path

import pytest

from lh2_tno.external_provider_response_gap_audit import (
    ExternalProviderResponseGapAuditError,
    audit_external_provider_response_gaps,
)


def _response(*, event_id: str, termination_basis: str) -> dict:
    return {
        "provider_export_schema": "prism.external_accident_history.v1",
        "provider_model": "example.Model",
        "provider_source_digest": "a" * 64,
        "data": {
            "event_id": event_id,
            "component_id": "component-1",
            "port_id": "port-1",
            "event_kind": "accidental_leak",
            "duration_s": 0.2,
            "termination_basis": termination_basis,
            "cumulative_mass_out_kg": 0.2,
            "provider_meta": {
                "initial_mass_kg": 1.0,
                "final_mass_kg": 0.8,
                "residual_mass_kg": 0.0,
            },
        },
    }


def test_gap_audit_separates_termination_from_qualification(tmp_path: Path):
    root = tmp_path / "external"
    root.mkdir()
    (root / "qualified_candidate.json").write_text(
        json.dumps(_response(event_id="event-1", termination_basis="inventory_depletion")),
        encoding="utf-8",
    )
    (root / "horizon.json").write_text(
        json.dumps(_response(event_id="event-2", termination_basis="synthetic_diagnostic_horizon")),
        encoding="utf-8",
    )
    scan = {
        "schema_version": "prism.provider_artifact_audit.v1",
        "roots": {
            "equipment": {
                "source_root_provided": str(root),
                "artifacts": [
                    {"file": "qualified_candidate.json", "kind": "provider_response"},
                    {"file": "horizon.json", "kind": "provider_response"},
                ],
            }
        },
    }
    report = audit_external_provider_response_gaps(scan, root_label="equipment")
    assert report["provider_response_count"] == 2
    assert report["strict_termination_candidate_count"] == 1
    assert report["mass_ledger_present_count"] == 2
    assert report["qualification_sidecar_count"] == 0
    assert report["origin_metadata_missing_count"] == 2
    assert report["promotion"]["provider_packet_promoted"] is False
    horizon = next(row for row in report["rows"] if row["event_id"] == "event-2")
    assert any("strict provider closure" in reason for reason in horizon["blocking_reasons"])


def test_gap_audit_rejects_path_escape(tmp_path: Path):
    root = tmp_path / "external"
    root.mkdir()
    scan = {
        "schema_version": "prism.provider_artifact_audit.v1",
        "roots": {
            "equipment": {
                "source_root_provided": str(root),
                "artifacts": [{"file": "../outside.json", "kind": "provider_response"}],
            }
        },
    }
    with pytest.raises(ExternalProviderResponseGapAuditError, match="escapes"):
        audit_external_provider_response_gaps(scan, root_label="equipment")
