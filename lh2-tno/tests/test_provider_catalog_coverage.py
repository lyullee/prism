from lh2_tno.equipment_boundary import ResolvedGasRelease, ResolvedGasStep, ResolvedLiquidRelease, ResolvedLiquidStep
from lh2_tno.campaign import ProviderPacketEvidence
from lh2_tno.provider_catalog_coverage import audit_provider_catalog_coverage


def _gas(event_id="event-1", component_id="tank-1", opening=0.01):
    return ResolvedGasRelease(
        component_id=component_id,
        port_id="accident-out",
        event_id=event_id,
        event_kind="accidental_leak",
        upstream_service="GH2",
        upstream_service_provenance="test",
        enthalpy_convention="static_exit_enthalpy",
        property_basis={"fluid": "Hydrogen", "energy_reference": "CoolProp-HEOS:Hydrogen:native"},
        provider_source_digest="0" * 64,
        provider_result_digest="1" * 64,
        provider_boundary_reference="test-boundary",
        input_origin="model_prediction",
        position_enu_m=(0.0, 0.0, 1.0),
        direction_enu=(1.0, 0.0, 0.0),
        ambient_pressure_pa_abs=101325.0,
        ambient_temperature_k=288.15,
        duration_s=0.2,
        available_mass_kg=1.0,
        cumulative_mass_out_kg=0.2,
        cumulative_static_enthalpy_out_j=200.0,
        steps=(ResolvedGasStep(
            time_s=0.0, mass_flow_kg_s=1.0, pressure_pa_abs=101325.0,
            specific_enthalpy_j_kg=1000.0, temperature_k=288.15,
            density_kg_m3=1.0, effective_area_m2=1.0, velocity_m_s=1.0,
            area_provenance="test", velocity_origin="provider_resolved",
        ),),
        termination_provenance="test termination",
        failure_opening_diameter_m=opening,
    )


def _liquid(event_id="event-liquid"):
    return ResolvedLiquidRelease(
        component_id="tank-1", port_id="accident-out", event_id=event_id,
        event_kind="accidental_leak", upstream_service="LH2",
        upstream_service_provenance="test", phase_basis="two_phase",
        enthalpy_convention="provider_total_outlet_enthalpy",
        property_basis={"fluid": "Hydrogen", "energy_reference": "CoolProp-HEOS:Hydrogen:native"},
        provider_source_digest="2" * 64, provider_result_digest="3" * 64,
        provider_boundary_reference="test-liquid-boundary", input_origin="model_prediction",
        position_enu_m=(0.0, 0.0, 1.0), direction_enu=(1.0, 0.0, 0.0),
        ambient_pressure_pa_abs=101325.0, ambient_temperature_k=288.15,
        duration_s=0.2, available_mass_kg=1.0, cumulative_mass_out_kg=0.2,
        cumulative_specific_enthalpy_out_j=200.0, reference_area_m2=1.0,
        reference_area_provenance="test", steps=(ResolvedLiquidStep(
            time_s=0.0, total_mass_flow_kg_s=1.0, gas_mass_flow_kg_s=1.0,
            ground_liquid_mass_flow_kg_s=0.0, airborne_liquid_mass_flow_kg_s=0.0,
            specific_enthalpy_j_kg=1000.0, gas_pressure_pa_abs=101325.0,
            gas_temperature_k=288.15, gas_density_kg_m3=1.0,
            gas_effective_area_m2=1.0, gas_velocity_m_s=1.0,
            gas_velocity_origin="provider_resolved",
        ),), termination_provenance="test termination",
        droplet_partition_provenance="test partition", failure_opening_diameter_m=0.01,
    )


def _item(event_id, mode="hole", boundary=("resolved_atmospheric_gas_exit",), opening=0.01):
    return {
        "event_id": event_id, "component_id": "tank-1", "release_mode": mode,
        "provider_event_kind": "accidental_leak", "provider_endpoint_count": 1,
        "accident_port_ids": ["accident-out"],
        "provider_boundary_variants": list(boundary),
        "required_opening_diameter_m": opening if mode == "hole" else None,
        "required_duration_s": None,
    }


def test_coverage_exact_matches_liquid_and_gas_boundaries():
    report = audit_provider_catalog_coverage(
        {"status": "READY_FOR_PROVIDER_PACKETS", "work_items": [
            _item("event-1"),
            _item("event-liquid", mode="instantaneous_inventory", boundary=("resolved_atmospheric_liquid_exit",)),
        ]},
        (_gas(), _liquid()),
    )

    assert report["status"] == "FULLY_MATCHED"
    assert report["exact_match_count"] == 2
    assert report["status_counts"] == {"EXACT_MATCH": 2}
    assert all(row["reasons"] == [] for row in report["work_items"])


def test_coverage_preserves_missing_and_extra_packets():
    report = audit_provider_catalog_coverage(
        {"status": "READY_FOR_PROVIDER_PACKETS", "work_items": [_item("event-1"), _item("event-2")]},
        (_gas(), _gas(event_id="event-extra")),
    )

    assert report["status"] == "PARTIAL_EXACT_MATCH"
    assert report["exact_match_count"] == 1
    assert report["status_counts"]["UNMATCHED_NO_PROVIDER_PACKET"] == 1
    assert report["extra_packet_count"] == 1
    assert "provider catalog contains packets outside" in report["blocking_reasons"][-1]


def test_coverage_rejects_opening_substitution():
    report = audit_provider_catalog_coverage(
        {"work_items": [_item("event-1", opening=0.02)]},
        (_gas(opening=0.01),),
    )

    assert report["status"] == "NO_EXACT_MATCH"
    row = report["work_items"][0]
    assert row["status"] == "UNMATCHED_PACKET_CONTRACT"
    assert any("opening" in reason for reason in row["reasons"])


def test_coverage_counts_only_exact_non_synthetic_qualification_evidence():
    packet = _gas()
    evidence = ProviderPacketEvidence(
        event_id=packet.event_id,
        component_id=packet.component_id,
        port_ids=(packet.port_id,),
        provider_source_digests=(packet.provider_source_digest,),
        provider_result_digests=(packet.provider_result_digest,),
        evidence_id="provider-actual-001",
    )
    report = audit_provider_catalog_coverage(
        {"work_items": [_item("event-1")]},
        (packet,),
        provider_packet_evidence=(evidence,),
    )

    assert report["qualification_status"] == "QUALIFIED_FULL_WORKLIST"
    assert report["qualified_provider_packet_count"] == 1
    assert report["work_items"][0]["qualification_status"] == "QUALIFIED_EXACT_MATCH"


def test_coverage_does_not_qualify_synthetic_packet_even_with_matching_evidence():
    packet = _gas()
    packet = packet.model_copy(update={"input_origin": "synthetic"})
    evidence = ProviderPacketEvidence(
        event_id=packet.event_id,
        component_id=packet.component_id,
        port_ids=(packet.port_id,),
        provider_source_digests=(packet.provider_source_digest,),
        provider_result_digests=(packet.provider_result_digest,),
        evidence_id="provider-synthetic-001",
    )
    report = audit_provider_catalog_coverage(
        {"work_items": [_item("event-1")]},
        (packet,),
        provider_packet_evidence=(evidence,),
    )

    assert report["qualified_provider_packet_count"] == 0
    assert report["work_items"][0]["qualification_status"] == "UNQUALIFIED_SYNTHETIC_PACKET"
