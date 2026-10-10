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


def test_packet_identity_consumption_is_withheld_when_campaign_has_unbound_events(tmp_path):
    packet_path = tmp_path / "resolved_release.json"
    packet_path.write_text(
        '{"provider_source_digest":"' + "a" * 64 + '",'
        '"provider_result_digest":"' + "b" * 64 + '"}',
        encoding="utf-8",
    )
    packet_evidence = _packet_evidence()
    packet_evidence["rows"][0]["evidence"]["resolved_packet_paths"] = [str(packet_path)]
    campaign = _campaign_result()
    campaign["cases"][0]["provider_packet_identity"] = {
        "provider_source_digests": ["a" * 64],
        "provider_result_digests": ["b" * 64],
    }
    campaign["events"].append({
        "id": "unbound-event",
        "model_component_id": "tank-01",
        "release": {"hole_diameter_m": 0.2},
    })
    campaign["cases"].append({
        "event_id": "unbound-event",
        "status": "EXECUTED_OPERATOR_LIMITED",
        "provider_packet_identity": {
            "provider_source_digests": ["c" * 64],
            "provider_result_digests": ["d" * 64],
        },
    })
    campaign["risk_atoms"].append({"event_id": "unbound-event", "ignition_branch": "no_ignition"})

    report = build_diagnostic_campaign_binding(
        packet_evidence,
        campaign,
        {
            "work_items": [{
                "event_id": "scope/tank/AREA_1%",
                "component_id": "tank-01",
                "required_opening_diameter_m": 0.1,
            }],
        },
    )

    assert report["packet_scope_subset_complete"] is True
    assert report["packet_subset_identity_consumed"] is True
    assert report["packet_identity_consumed"] is False
    assert report["campaign_scope_packet_coverage_complete"] is False
    assert report["unbound_campaign_event_ids"] == ["unbound-event"]
    assert "full campaign packet consumption is withheld" in report["packet_identity_consumption_reason"]


def test_packet_release_aggregates_are_checked_against_facility_case_ledger(tmp_path):
    source_digest = "a" * 64
    result_digest = "b" * 64
    packet_path = tmp_path / "resolved_release.json"
    packet_path.write_text(
        "{"
        '"provider_export_schema":"prism.resolved_release.v1",'
        '"event_id":"scope/tank/AREA_1%",'
        '"component_id":"tank-01",'
        '"provider_source_digest":"' + source_digest + '",'
        '"provider_result_digest":"' + result_digest + '",'
        '"duration_s":2.0,'
        '"available_mass_kg":5.0,'
        '"cumulative_mass_out_kg":1.25,'
        '"termination_basis":"reviewed_isolation_success",'
        '"termination_provenance":"reviewed valve closure"'
        "}",
        encoding="utf-8",
    )
    packet_evidence = _packet_evidence()
    packet_evidence["rows"][0]["evidence"]["resolved_packet_paths"] = [
        str(packet_path)
    ]
    campaign = _campaign_result()
    campaign["cases"][0].update(
        provider_packet_identity={
            "provider_source_digests": [source_digest],
            "provider_result_digests": [result_digest],
            "duration_s": [2.0],
            "available_mass_kg": [5.0],
            "cumulative_mass_out_kg": [1.25],
            "termination_bases": ["reviewed_isolation_success"],
            "termination_provenances": ["reviewed valve closure"],
        },
        termination={
            "basis": "reviewed_isolation_success",
            "time_s": 2.0,
        },
        mass_ledger={"released_kg": 1.25},
    )
    report = build_diagnostic_campaign_binding(
        packet_evidence,
        campaign,
        {
            "work_items": [{
                "event_id": "scope/tank/AREA_1%",
                "component_id": "tank-01",
                "required_opening_diameter_m": 0.1,
            }],
        },
        tmp_path,
    )
    assert report["packet_subset_value_consumed"] is True
    assert report["diagnostic_only"] is True
    assert report["packet_value_checked_event_count"] == 1
    assert report["packet_value_consumed_event_count"] == 1
    assert report["packet_value_mismatch_event_ids"] == []

    campaign["cases"][0]["mass_ledger"]["released_kg"] = 1.0
    mismatched = build_diagnostic_campaign_binding(
        packet_evidence,
        campaign,
        {
            "work_items": [{
                "event_id": "scope/tank/AREA_1%",
                "component_id": "tank-01",
                "required_opening_diameter_m": 0.1,
            }],
        },
        tmp_path,
    )
    assert mismatched["packet_subset_value_consumed"] is False
    assert mismatched["packet_value_mismatch_event_ids"] == ["scope/tank/AREA_1%"]
