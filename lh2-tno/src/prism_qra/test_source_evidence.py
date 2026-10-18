"""Tests for the facility source-evidence acceptance gate."""

import pytest

import source_evidence as S


def _geometry(inlet=S.InletGeometry.SHARP_EDGED):
    return S.NozzleGeometry(
        equipment_tag="PRV-101",
        drawing_id="DWG-101",
        drawing_revision="A",
        limiting_bore_mm=6.4,
        bore_length_mm=12.0,
        inlet_geometry=inlet,
        surface_roughness_um=3.2,
        outlet_geometry_note="straight outlet",
        measurement_method="drawing plus calibrated pin gauge",
        source_file="vendor/DWG-101-A.pdf",
        reviewer="reviewer",
        review_date="2026-08-29",
    )


def _metadata():
    return S.DischargeTestMetadata(
        test_id="COM-001",
        equipment_tag="PRV-101",
        raw_data_file="COM-001.csv",
        raw_data_sha256="a" * 64,
        clock_source="DAQ-01 PTP clock",
        nominal_sampling_interval_s=1.0,
        timestamp_uncertainty_s=0.01,
        synchronization_method="shared DAQ clock",
        measured_sync_offset_s=0.01,
        maximum_allowed_sync_offset_s=0.1,
        pressure_sensor_id="PT-101",
        pressure_location="tank",
        pressure_uncertainty_pa=10_000,
        temperature_sensor_id="TT-101",
        temperature_location="tank",
        temperature_uncertainty_k=0.5,
        mass_sensor_id="WT-101",
        mass_resolution_kg=0.001,
        mass_uncertainty_kg=0.002,
        differentiation_method=S.DifferentiationMethod.CENTRAL_DIFFERENCE,
        differentiation_window_s=3.0,
        filter_note="no prefilter",
        valve_signal_note="position feedback on the same DAQ",
        operator="operator",
        test_date="2026-08-29",
    )


def _samples():
    return [
        S.DischargeSample(
            time_s=float(i), tank_pressure_pa=20e6 - i * 1e6,
            nozzle_upstream_pressure_pa=19.9e6 - i * 1e6,
            tank_temperature_k=293.0, nozzle_upstream_temperature_k=292.5,
            tank_mass_kg=10.0 - 0.1 * i, measured_mass_flow_kg_s=0.1,
            valve_position_pct=100.0,
        )
        for i in range(6)
    ]


def _certificate(*, valid_for_hydrogen=True):
    return S.CapacityCertificate(
        equipment_tag="PRV-101",
        manufacturer="Vendor",
        model="Model-1",
        serial_number="SN-1",
        document_id="CERT-1",
        revision="A",
        test_standard="capacity test standard",
        basis=S.CapacityBasis.MANUFACTURER_CERTIFIED,
        test_fluid="air",
        set_pressure_barg=10.0,
        inlet_temperature_k=288.0,
        backpressure_barg=0.0,
        certified_capacity_kg_s=0.1,
        valid_for_hydrogen=valid_for_hydrogen,
        source_file="vendor/CERT-1.pdf",
    )


def test_geometry_alone_is_only_an_engineering_sensitivity(tmp_path):
    result = S.assess_source_evidence(_geometry())
    assert result.claim_level == "ENGINEERING_SENSITIVITY_ONLY"
    assert "cannot validate Cd" in result.warnings[0]
    path = tmp_path / "geometry.csv"
    path.write_text(
        "equipment_tag,drawing_id,drawing_revision,limiting_bore_mm,"
        "bore_length_mm,inlet_geometry,chamfer_angle_deg,chamfer_length_mm,"
        "surface_roughness_um,outlet_geometry_note,measurement_method,"
        "source_file,reviewer,review_date\n"
        "PRV-101,DWG-101,A,6.4,12,SHARP_EDGED,,,3.2,straight,pin gauge,"
        "drawing.pdf,reviewer,2026-08-29\n",
        encoding="utf-8",
    )
    assert S.read_geometry_csv(path)[0].chamfer_angle_deg is None


def test_unknown_inlet_geometry_blocks_source_claim():
    result = S.assess_source_evidence(
        _geometry(S.InletGeometry.UNKNOWN), _metadata(), _samples()
    )
    assert result.claim_level == "BLOCKED"
    assert "UNKNOWN" in result.blockers[0]


def test_synchronized_mass_closing_series_is_measured_evidence():
    result = S.assess_source_evidence(_geometry(), _metadata(), _samples())
    assert result.claim_level == "MEASURED_SOURCE_TERM"
    assert result.time_series.flow_mass_closure_relative == pytest.approx(0)
    assert not result.blockers


def test_partial_flow_column_is_rejected():
    rows = _samples()
    rows[2] = rows[2].model_copy(update={"measured_mass_flow_kg_s": None})
    with pytest.raises(ValueError, match="complete or entirely blank"):
        S.audit_discharge_timeseries(_metadata(), rows)


def test_mass_flow_must_integrate_back_to_tank_mass():
    rows = [
        row.model_copy(update={"measured_mass_flow_kg_s": 0.01})
        for row in _samples()
    ]
    with pytest.raises(ValueError, match="does not close tank mass"):
        S.audit_discharge_timeseries(_metadata(), rows)


def test_clock_offset_cannot_be_hidden_inside_a_sample():
    with pytest.raises(ValueError, match="clock offset"):
        S.DischargeTestMetadata.model_validate({
            **_metadata().model_dump(),
            "measured_sync_offset_s": 0.2,
            "maximum_allowed_sync_offset_s": 0.1,
        })


def test_certificate_not_valid_for_hydrogen_cannot_be_certified_claim():
    result = S.assess_source_evidence(
        _geometry(), certificate=_certificate(valid_for_hydrogen=False))
    assert result.claim_level == "BLOCKED"
    assert "not declared valid for hydrogen" in result.blockers[0]


def test_nonvalid_sample_quality_blocks_the_measured_claim():
    rows = _samples()
    rows[2] = rows[2].model_copy(update={"quality_flag": "BAD"})
    with pytest.raises(ValueError, match="non-VALID"):
        S.audit_discharge_timeseries(_metadata(), rows)
