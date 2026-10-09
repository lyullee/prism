from lh2_tno.campaign_namespace import rebind_campaign_result


def test_campaign_namespace_rebinds_event_component_and_collapsed_receptors():
    result = {
        "facility_id": "source-facility",
        "campaign_digest": "source-digest",
        "scope_provenance": "synthetic test",
        "events": [{
            "id": "source-facility/pipe/G1",
            "asset_id": "source-asset",
            "model_component_id": "source-component",
        }],
        "cases": [{
            "event_id": "source-facility/pipe/G1",
            "asset_id": "source-asset",
            "provider_packet_identity": {
                "event_id": "source-facility/pipe/G1",
                "component_id": "source-component",
            },
        }],
        "uncomputed_cases": [],
        "risk_atoms": [{
            "event_id": "source-facility/pipe/G1",
            "asset_id": "source-asset",
            "receptor_harm_low_high": {
                "near": [0.2, 0.3],
                "downwind": [0.4, 0.1],
            },
            "expected_deaths_low_high": [0.6, 0.4],
        }],
        "coverage": {"by_component": [{"component_id": "source-component"}]},
    }

    rebound = rebind_campaign_result(
        result,
        source_facility_id="source-facility",
        facility_id="target-facility",
        namespace="target-facility/two-sided",
        source_asset_id="source-asset",
        asset_id="target-asset",
        source_component_id="source-component",
        component_id="target-component",
        receptor_map={"near": "worker-01", "downwind": "worker-01"},
    )

    event_id = "target-facility/two-sided/pipe/G1"
    assert rebound["facility_id"] == "target-facility"
    assert rebound["events"][0]["id"] == event_id
    assert rebound["events"][0]["asset_id"] == "target-asset"
    assert rebound["events"][0]["model_component_id"] == "target-component"
    assert rebound["cases"][0]["event_id"] == event_id
    assert rebound["cases"][0]["provider_packet_identity"]["event_id"] == event_id
    assert rebound["risk_atoms"][0]["receptor_harm_low_high"] == {"worker-01": [0.4, 0.3]}
    assert rebound["risk_atoms"][0]["expected_deaths_low_high"] == [0.4, 0.3]
    assert rebound["coverage"]["by_component"][0]["component_id"] == "target-component"
    assert rebound["campaign_namespace_rebind"]["receptor_collapse_policy"] == "many_to_one_endpoint_maximum"
    assert rebound["campaign_namespace_rebind"]["diagnostic_only"] is True
