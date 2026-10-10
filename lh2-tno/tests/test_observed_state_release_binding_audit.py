from __future__ import annotations

from lh2_tno.observed_state_evidence import build_observed_state_evidence
from lh2_tno.observed_state_release_binding_audit import (
    MANIFEST_SCHEMA,
    audit_observed_state_release_binding,
)


def _observed() -> dict:
    return build_observed_state_evidence([
        {
            "source_id": "historian-tank",
            "component_id": "observed-tank",
            "origin": "historian_measured",
            "samples": [
                {"captured_at_s": 0.0, "values": {"pressure": 100000.0}},
                {"captured_at_s": 1.0, "values": {"pressure": 101000.0}},
            ],
        }
    ])


def _provider(event_id: str = "event-1", component_id: str = "facility-tank") -> dict:
    return {
        "event_id": event_id,
        "component_id": component_id,
        "port_ids": ["tank-accident-out"],
        "provider_source_digests": ["0" * 64],
        "provider_result_digests": ["1" * 64],
        "evidence_id": "actual-1",
    }


def test_missing_binding_and_provider_packet_are_explicit():
    report = audit_observed_state_release_binding(
        _observed(),
        {"provider_packet_evidence": []},
        {"schema_version": MANIFEST_SCHEMA, "bindings": []},
    )

    assert report["status"] == "NO_STATE_TO_RELEASE_BINDING"
    assert report["observed_component_count"] == 1
    assert report["mapped_component_count"] == 0
    assert report["unmapped_component_count"] == 1
    assert report["provider_packet_evidence_count"] == 0


def test_reviewed_binding_requires_provider_event_and_exact_component():
    report = audit_observed_state_release_binding(
        _observed(),
        {"provider_packet_evidence": [_provider()]},
        {
            "schema_version": MANIFEST_SCHEMA,
            "bindings": [{
                "binding_id": "tank-binding",
                "observed_component_id": "observed-tank",
                "facility_component_id": "facility-tank",
                "source_ids": ["historian-tank"],
                "provider_event_ids": ["event-1"],
                "review_status": "reviewed",
            }],
        },
    )

    assert report["status"] == "STATE_AND_PROVIDER_RELEASE_BOUND_DIAGNOSTIC"
    assert report["mapped_component_count"] == 1
    assert report["bound_provider_event_count"] == 1
    assert report["policy"]["frequency_is_not_assigned"] is True


def test_component_mismatch_does_not_promote_state_to_release():
    report = audit_observed_state_release_binding(
        _observed(),
        {"provider_packet_evidence": [_provider(component_id="other-tank")]},
        {
            "schema_version": MANIFEST_SCHEMA,
            "bindings": [{
                "observed_component_id": "observed-tank",
                "facility_component_id": "facility-tank",
                "source_ids": ["historian-tank"],
                "provider_event_ids": ["event-1"],
                "review_status": "field_confirmed",
            }],
        },
    )

    assert report["status"] == "NO_STATE_TO_RELEASE_BINDING"
    assert report["rows"][0]["status"] == "STATE_MAPPING_UNQUALIFIED"
    assert any("component_id disagrees" in reason for reason in report["rows"][0]["blocking_reasons"])
