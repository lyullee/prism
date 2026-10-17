import copy

import pytest

from lh2_tno.provider_request_rebaseline import (
    ProviderRequestRebaselineError,
    rebaseline_provider_request_catalog,
    rebaseline_provider_request_catalog_batch,
)


OLD_SOURCE = "a" * 64
OLD_RESULT = "b" * 64
NEW_SOURCE = "c" * 64
NEW_RESULT = "d" * 64
EVENT = "facility/line/AREA_100%"


def _catalog():
    return {
        "schema_version": "prism.native_full_scope_provider_qualification_requests.v1",
        "status": "OPEN_PROVIDER_QUALIFICATION_REQUESTS",
        "qualified_provider_packet_count": 0,
        "frequency_inference_allowed": False,
        "facility_qra_allowed": False,
        "physical_validation_claim": False,
        "requests": [{
            "event_id": EVENT,
            "component_id": "line-01",
            "requests": [{
                "request_schema": "prism.provider_qualification_request.v1",
                "request_id": EVENT,
                "status": "OPEN",
                "current_packet": {
                    "event_id": EVENT,
                    "component_id": "line-01",
                    "port_id": "line-out",
                    "event_kind": "accidental_leak",
                    "provider_source_digest": OLD_SOURCE,
                    "provider_result_digest": OLD_RESULT,
                },
                "blocking_reasons": ["qualification_sidecar_missing"],
                "qualification_sidecar_required": {
                    "provider_source_digests": [OLD_SOURCE],
                    "provider_result_digests": [OLD_RESULT],
                },
                "acceptance": {
                    "qualification_sidecar_digest_bound": True,
                    "frequency_inference_allowed": False,
                    "facility_qra_allowed": False,
                },
            }],
        }],
    }


def _packet():
    return {
        "event_id": EVENT,
        "component_id": "line-01",
        "port_id": "line-out",
        "event_kind": "accidental_leak",
        "input_origin": "model_prediction",
        "termination_basis": "model_pressure_equalization",
        "termination_provenance": "provider boundary",
        "duration_s": 0.24,
        "available_mass_kg": 1.0,
        "cumulative_mass_out_kg": 0.5,
        "provider_source_digest": NEW_SOURCE,
        "provider_result_digest": NEW_RESULT,
    }


def test_rebaseline_requires_explicit_acknowledgement():
    with pytest.raises(ProviderRequestRebaselineError, match="acknowledgement"):
        rebaseline_provider_request_catalog(_catalog(), _packet(), event_id=EVENT)


def test_rebaseline_preserves_old_digests_and_keeps_promotion_closed():
    report = rebaseline_provider_request_catalog(
        _catalog(),
        _packet(),
        event_id=EVENT,
        acknowledged=True,
        additional_blockers=["native_isolation_clock_invalid"],
    )
    assert report["rebaseline"]["previous_provider_source_digest"] == OLD_SOURCE
    assert report["rebaseline"]["current_provider_source_digest"] == NEW_SOURCE
    request = report["current_request"]
    assert request["current_packet"]["provider_result_digest"] == NEW_RESULT
    assert request["qualification_sidecar_required"]["provider_source_digests"] == [NEW_SOURCE]
    assert "native_isolation_clock_invalid" in request["blocking_reasons"]
    assert report["catalog"]["facility_qra_allowed"] is False
    assert report["catalog"]["frequency_inference_allowed"] is False
    assert report["rebaseline"]["promotion_allowed"] is False


def test_rebaseline_rejects_identity_mismatch():
    packet = copy.deepcopy(_packet())
    packet["component_id"] = "other-line"
    with pytest.raises(ProviderRequestRebaselineError, match="identity mismatch"):
        rebaseline_provider_request_catalog(
            _catalog(), packet, event_id=EVENT, acknowledged=True
        )


def test_batch_rebaseline_updates_all_requests_without_promotion():
    second_event = "facility/line/AREA_10%"
    catalog = _catalog()
    second = copy.deepcopy(catalog["requests"][0])
    second["event_id"] = second_event
    second["requests"][0]["request_id"] = second_event
    second["requests"][0]["current_packet"]["event_id"] = second_event
    catalog["requests"].append(second)
    packet = _packet()
    packet2 = copy.deepcopy(packet)
    packet2["event_id"] = second_event
    packet2["provider_source_digest"] = "e" * 64
    packet2["provider_result_digest"] = "f" * 64
    report = rebaseline_provider_request_catalog_batch(
        catalog,
        {EVENT: packet, second_event: packet2},
        acknowledged=True,
    )
    assert report["event_count"] == 2
    assert report["identity_match_count"] == 2
    assert report["result_digest_changed_count"] == 2
    assert report["catalog"]["facility_qra_allowed"] is False


def test_batch_rebaseline_updates_two_endpoint_requests_separately():
    catalog = _catalog()
    endpoint = copy.deepcopy(catalog["requests"][0]["requests"][0])
    endpoint["current_packet"]["port_id"] = "line-out-2"
    endpoint["current_packet"]["provider_result_digest"] = "e" * 64
    catalog["requests"][0]["requests"].append(endpoint)
    packet1 = _packet()
    packet2 = copy.deepcopy(packet1)
    packet2["port_id"] = "line-out-2"
    packet2["provider_result_digest"] = "f" * 64
    report = rebaseline_provider_request_catalog_batch(
        catalog,
        {f"{EVENT}::line-out": packet1, f"{EVENT}::line-out-2": packet2},
        acknowledged=True,
    )
    assert report["event_count"] == 2
    requests = report["catalog"]["requests"][0]["requests"]
    assert {row["current_packet"]["provider_result_digest"] for row in requests} == {
        NEW_RESULT,
        "f" * 64,
    }
