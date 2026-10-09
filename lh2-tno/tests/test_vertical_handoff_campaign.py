from lh2_tno.vertical_handoff_campaign import rebind_vertical_handoff_campaign_result


def test_vertical_handoff_campaign_rebind_namespaces_all_facility_references():
    result = {
        "facility_id": "vertical-vent-campaign",
        "campaign_digest": "source-digest",
        "scope_provenance": "vertical diagnostic",
        "events": [{
            "id": "vertical-vent-campaign/terminal-valve/AREA_100%",
            "asset_id": "terminal-valve",
            "model_component_id": "terminal_pipe",
        }],
        "cases": [{
            "event_id": "vertical-vent-campaign/terminal-valve/AREA_100%",
            "asset_id": "terminal-valve",
            "provider_packet_identity": {
                "event_id": "vertical-vent-campaign/terminal_pipe/AREA_100%",
                "component_id": "terminal_pipe",
            },
        }],
        "uncomputed_cases": [],
        "risk_atoms": [{
            "event_id": "vertical-vent-campaign/terminal-valve/AREA_100%",
            "asset_id": "terminal-valve",
            "receptor_harm_low_high": {
                "near_worker": [0.1, 0.2],
                "downwind_worker": [0.3, 0.4],
            },
            "expected_deaths_low_high": [0.4, 0.6],
        }],
        "coverage": {"by_component": [{"component_id": "terminal_pipe"}]},
    }

    rebound = rebind_vertical_handoff_campaign_result(
        result,
        facility_id="generic-lh2-full-scope-example",
        namespace="generic-lh2-full-scope-example/vertical-handoff",
        asset_id="vertical-handoff-vent",
        component_id="vertical-handoff-terminal-pipe-01",
        receptor_map={"near_worker": "worker-01", "downwind_worker": "worker-01"},
    )

    event_id = "generic-lh2-full-scope-example/vertical-handoff/terminal-valve/AREA_100%"
    provider_event_id = "generic-lh2-full-scope-example/vertical-handoff/provider/terminal_pipe/AREA_100%"
    assert rebound["facility_id"] == "generic-lh2-full-scope-example"
    assert rebound["events"][0]["id"] == event_id
    assert rebound["events"][0]["asset_id"] == "vertical-handoff-vent"
    assert rebound["events"][0]["model_component_id"] == "vertical-handoff-terminal-pipe-01"
    assert rebound["cases"][0]["event_id"] == event_id
    assert rebound["cases"][0]["provider_packet_identity"]["event_id"] == provider_event_id
    assert rebound["cases"][0]["provider_packet_identity"]["component_id"] == "vertical-handoff-terminal-pipe-01"
    assert rebound["risk_atoms"][0]["event_id"] == event_id
    assert rebound["risk_atoms"][0]["receptor_harm_low_high"] == {"worker-01": [0.3, 0.4]}
    assert rebound["risk_atoms"][0]["expected_deaths_low_high"] == [0.3, 0.4]
    assert rebound["coverage"]["by_component"][0]["component_id"] == "vertical-handoff-terminal-pipe-01"
    assert rebound["vertical_handoff_rebind"]["diagnostic_only"] is True
    assert rebound["vertical_handoff_rebind"]["facility_qra_claim"] is False
    assert rebound["vertical_handoff_rebind"]["receptor_collapse_policy"] == "many_to_one_endpoint_maximum"
