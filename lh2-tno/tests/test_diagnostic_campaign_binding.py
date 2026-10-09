from lh2_tno.diagnostic_campaign_binding import build_diagnostic_campaign_binding


def _packet_evidence():
    return {
        "rows": [
            {
                "event_id": "scope/tank/AREA_1%",
                "component_id": "tank-01",
                "evidence": {
                    "exact_opening_match": True,
                    "strict_packet_valid": True,
                },
            },
        ],
        "qualified_provider_packet_count": 0,
        "frequency_bound": False,
        "facility_qra_claim": False,
        "physical_validation_claim": False,
    }


def _campaign_result():
    return {
        "events": [{
            "id": "scope/tank/AREA_1%",
            "model_component_id": "tank-01",
            "release": {"hole_diameter_m": 0.1},
        }],
        "cases": [{"event_id": "scope/tank/AREA_1%", "status": "EXECUTED_OPERATOR_LIMITED"}],
        "risk_atoms": [
            {"event_id": "scope/tank/AREA_1%", "ignition_branch": "direct_fire"},
        ],
        "complete_facility_qra_claim": False,
        "physical_validation_claim": False,
    }


def test_structural_binding_is_reported_without_packet_consumption_claim():
    report = build_diagnostic_campaign_binding(
        _packet_evidence(),
        _campaign_result(),
        {
            "work_items": [{
                "event_id": "scope/tank/AREA_1%",
                "component_id": "tank-01",
                "required_opening_diameter_m": 0.1,
            }],
        },
    )
    assert report["status"] == "PARTIAL_DIAGNOSTIC_CAMPAIGN_BINDING"
    assert report["structural_binding_complete"] is True
    assert report["packet_identity_consumed"] is False
    assert report["frequency_from_provider_packet"] is False
    assert report["opening_geometry_match_count"] == 1


def test_binding_fails_closed_when_a_campaign_case_is_missing():
    campaign = _campaign_result()
    campaign["cases"] = []
    report = build_diagnostic_campaign_binding(_packet_evidence(), campaign)
    assert report["status"] == "BLOCKED_DIAGNOSTIC_CAMPAIGN_BINDING"
    assert report["missing_campaign_case_ids"] == ["scope/tank/AREA_1%"]


def test_binding_preserves_physical_claim_gate():
    campaign = _campaign_result()
    campaign["physical_validation_claim"] = True
    report = build_diagnostic_campaign_binding(_packet_evidence(), campaign)
    assert report["status"] == "BLOCKED_DIAGNOSTIC_CAMPAIGN_BINDING"
    assert report["packet_claims_preserved"] is False
