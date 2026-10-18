"""Independent invariants for the 2026-08-31 audit; not copied baselines."""
from dataclasses import replace
from types import SimpleNamespace
import math

import numpy as np
import pytest

import damage as D
import digital_twin_validation as DT
import equipment_damage as E
import field as FIELD
import fire as F
import gh2_jet as G
import pipeline as P
import source_evidence as SE
import source_term as S
import taxonomy as T
import transient as TR
import uncertainty as U
from gating import RefusePolicy, RefusedError
from ignition import Outcome
from result_comparison import differences
from risk import PdRoute, RiskContribution


@pytest.fixture(scope="module")
def release():
    d = S.discharge(350e5, 288.15, "Hydrogen", .006)
    n = F.notional_nozzle(d.rate_kg_s, d.throat_pressure_pa,
                         d.velocity_m_s, d.mass_flux_kg_m2s / d.velocity_m_s,
                         .006)
    return d, F.flame_length(d.rate_kg_s, n, .006)


@pytest.mark.parametrize("q", [0., 20000., D.Q_IGNITION_W_M2, 40000., math.inf])
@pytest.mark.parametrize("duration", [0., 1., 20., 100.])
def test_scalar_and_directional_damage_have_one_contract(q, duration):
    scalar = D.heat_radiation(q, duration)
    fields = {Outcome.JET_FIRE: FIELD.DirectionalFlux(np.array([[[q]]]))}
    values = P._damage_field(Outcome.JET_FIRE, fields, duration)
    assert [v.item() for v in values] == pytest.approx(
        [scalar.pe, scalar.fe_in, scalar.fe_out])
    pool = P._damage_field(Outcome.POOL_FIRE,
                          {Outcome.POOL_FIRE: np.array([[q]])}, duration)
    assert [v.item() for v in pool] == pytest.approx([v.item() for v in values])


def test_directional_probability_is_averaged_after_damage(release):
    _, flame = release
    fields = FIELD.directional_flux_field(flame, np.array([[5.]]), np.array([[0.]]))
    actual = P._damage_field(Outcome.JET_FIRE, {Outcome.JET_FIRE: fields}, 20.)
    expected = [D.heat_radiation(F.heat_flux(flame, 5., bearing_deg=30*j), 20.)
                for j in range(12)]
    for value, attr in zip(actual, ("pe", "fe_in", "fe_out")):
        assert value.item() == pytest.approx(np.mean([getattr(v, attr) for v in expected]))
    mean, _ = FIELD.flux_field(flame, np.array([[5.]]), np.array([[0.]]))
    with pytest.raises(TypeError, match="per-bearing"):
        P._damage_field(Outcome.JET_FIRE, {Outcome.JET_FIRE: (mean, mean*0)}, 20.)


def test_fixed_azimuth_rotates_field_and_preserves_contact(release):
    _, flame = release
    a = FIELD.directional_flux_field(flame, np.array([5.]), np.array([0.]), azimuth_deg=0.)
    b = FIELD.directional_flux_field(flame, np.array([0.]), np.array([5.]), azimuth_deg=90.)
    assert a.by_bearing.shape == (1, 1)
    np.testing.assert_allclose(a.by_bearing, b.by_bearing)
    c = FIELD.directional_flux_field(flame, np.array([5.]), np.array([0.]), azimuth_deg=180.)
    assert not np.array_equal(a.by_bearing, c.by_bearing)


def _contribution(receptor, probability):
    return RiskContribution("s", "D", (0., 360.), "JET_FIRE", 1., 1.,
                            probability, 1e-5, PdRoute.FLAMMABLE,
                            receptor_id=receptor)


def test_uncertainty_frozen_frequencies_returns_max_not_grid_sum(monkeypatch):
    monkeypatch.setattr(U, "sample_library", lambda rng: {})
    cs = [_contribution((0,0), .1), _contribution((1,0), .2)]
    iv = U.propagate_linear(cs, n=3)
    assert (iv.median, iv.p05, iv.p95) == pytest.approx((2e-6,)*3)
    assert U.propagate_linear(cs, n=3, receptor_id=(0,0)).median == pytest.approx(1e-6)
    # Duplicating a receptor location at a new grid index must not double max IR.
    assert U.propagate_linear(cs + [_contribution((2,0), .2)], n=3).median == iv.median


def test_uncertainty_rejects_ambiguous_legacy_grid():
    cs = [_contribution(None, .1)]
    with pytest.raises(ValueError, match="receptor_id"):
        U.propagate_linear(cs, n=3)
    assert U.propagate_linear(cs, n=3, single_point=True).median == pytest.approx(1e-6)


def test_uncertainty_recomputes_maximizer_for_every_sample(monkeypatch):
    entries = {name:SimpleNamespace(mu=(0.,),sigma=(1.,),medians=(1.,))
               for name in ("a","b")}
    monkeypatch.setattr(T,"FREQUENCY_LIBRARY",entries)
    draws = iter([{"a":[10.],"b":[1.]},{"a":[1.],"b":[10.]}])
    monkeypatch.setattr(U,"sample_library",lambda rng:next(draws))
    cs = [replace(_contribution((0,0),.1),source_key=("a",0)),
          replace(_contribution((1,0),.2),source_key=("b",0))]
    # First draw: maximum at receptor 0 (1e-5); second: receptor 1 (2e-5).
    assert U.propagate_linear(cs,n=2).median == pytest.approx(1.5e-5)


def _exposure(flame=None, distance=1., r03=0., r01=0., azimuth=None):
    source = SimpleNamespace(tag="source", position=T.Position(x=0., y=0.),
                             orientation=T.Orientation.HORIZONTAL,
                             release_azimuth_deg=azimuth)
    target = SimpleNamespace(tag="target", position=T.Position(x=distance,y=0.))
    store = {}
    P._record_equipment_exposures(store, source, [target],
        SimpleNamespace(relative_humidity=50.), 0., r03, r01,
        flame, None, None, None, 20., False)
    return store[("source", "target")]


def test_equipment_does_not_drop_partial_flame_contact(release):
    _, flame = release
    exposure = _exposure(flame)
    assert exposure.possible_flame_contact
    verdict = E.assess("s", "t", exposure, T.Primitive.VALVE, T.Service.GH2)
    assert verdict.verdict is not E.DamageVerdict.NOT_AFFECTED
    assert any("contact" in reason for reason in verdict.reasons)


def test_equipment_retains_pressure_lower_bound_not_false_exact_value():
    exposure = _exposure(r03=10., r01=20.)
    assert exposure.overpressure_pa == 30000.
    assert exposure.overpressure_is_lower_bound
    verdict = E.assess("s", "t", exposure, T.Primitive.VALVE, T.Service.GH2)
    assert any("lower bound" in reason for reason in verdict.reasons)
    assert verdict.verdict is E.DamageVerdict.POTENTIALLY_AFFECTED


def _site():
    return T.Site(name="public-audit", sections=[T.Section(id="HP",inventory_kg=2.,
        isolation_time_s=1.,service=T.Service.GH2)],components=[T.ComponentSpec(
        primitive=T.Primitive.VALVE,service=T.Service.GH2,count=1,tag="V",
        nominal_diameter_m=.006,pressure_pa=350e5,temperature_k=288.15,
        position=T.Position(x=0.,y=0.),section_id="HP")])


def test_societal_only_damage_is_not_dropped_by_zero_individual_probability(monkeypatch):
    def only_indoor(outcome, fields, duration):
        return np.zeros((3,3)), np.full((3,3),.025), np.zeros((3,3))
    monkeypatch.setattr(P, "_damage_field", only_indoor)
    result = P.run(_site(), half_extent_m=10., cell_size_m=10., population_per_cell=100.)
    assert result.max_ir == 0.
    assert result.societal
    assert all(outcome.n_deaths > 0. for outcome in result.societal)


def test_real_pipeline_uncertainty_is_spatial_max(monkeypatch):
    result = P.run(_site(), half_extent_m=10., cell_size_m=5.)
    monkeypatch.setattr(U, "sample_library", lambda rng: {})
    assert all(c.receptor_id is not None for c in result.contributions)
    assert U.propagate_linear(result.contributions, n=3).median == pytest.approx(result.max_ir)
    import export
    payload = export.export(result)
    assert payload["claim_boundary"]["facility_validation"] == "WITHHELD"
    assert payload["claim_boundary"]["dual_evidence_gate"] == "NOT_INTEGRATED"
    assert "22.7" in payload["claim_boundary"]["open_model_issues"][0]


@pytest.mark.parametrize("basis,claim", [
    ("MANUFACTURER_CERTIFIED","CERTIFIED_SOURCE_TERM"),
    ("CAPACITY_TEST","CAPACITY_TEST_SOURCE_TERM"),
    ("CALIBRATED","CALIBRATED_SOURCE_TERM"),
])
def test_capacity_basis_cannot_be_promoted_to_certification(basis,claim):
    from test_source_evidence import _certificate, _geometry
    cert = SE.CapacityCertificate.model_validate({**_certificate().model_dump(),"basis":basis})
    assert SE.assess_source_evidence(_geometry(),certificate=cert).claim_level == claim


def test_raw_samples_without_flow_are_not_validated_flow():
    from test_source_evidence import _geometry, _metadata, _samples
    rows = [r.model_copy(update={"measured_mass_flow_kg_s":None}) for r in _samples()]
    assert SE.assess_source_evidence(_geometry(),_metadata(),rows).claim_level == "RAW_SERIES_ONLY"


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_evidence_geometry_rejects_nonfinite_values(value):
    from test_source_evidence import _geometry
    with pytest.raises(ValueError):
        SE.NozzleGeometry.model_validate({**_geometry().model_dump(),"limiting_bore_mm":value})
    with pytest.raises(ValueError):
        SE.assess_source_evidence(_geometry().model_copy(update={"limiting_bore_mm":value}))


@pytest.mark.parametrize("key", ["manufacturer","document_id","serial_number","test_standard"])
def test_certificate_rejects_blank_identifiers(key):
    from test_source_evidence import _certificate
    with pytest.raises(ValueError,match="blank"):
        SE.CapacityCertificate.model_validate({**_certificate().model_dump(),key:" "})


@pytest.mark.parametrize("delta", [.1, 1., 10., 100.])
def test_near_ambient_throat_never_crosses_downstream_pressure(delta):
    d = S.discharge(S.P_AMB+delta,288.15,"Hydrogen",.006)
    assert S.P_AMB <= d.throat_pressure_pa < S.P_AMB+delta
    # At this tiny pressure ratio the maximum is the downstream boundary.
    assert d.throat_pressure_pa == S.P_AMB


@pytest.mark.parametrize("isolation,limit", [(.15,2.), (None,.15), (.15,.15)])
def test_blowdown_hits_exact_time_event_and_mass_closes(isolation,limit):
    p = TR.gas_blowdown(.01,1e7,288.15,.006,isolation_time_s=isolation,
                        max_time_s=limit,dt_s=.1)
    assert p.duration_s == pytest.approx(.15,abs=1e-14)
    p.validate(rate_integral_relative_tolerance=1e-10)
    if isolation is not None:
        assert p.steps[-1].isolation is TR.IsolationState.CLOSED


def test_vacuum_profile_clips_final_step_and_uses_declared_rate_convention():
    p = TR.loss_of_vacuum(1.,.05,1e4,1.5e5,.008585,start_pressure_pa=1.5e5,
                          max_time_s=1.5,dt_s=1.)
    assert p.duration_s == 1.5
    p.validate(rate_integral_relative_tolerance=1e-10)


def test_short_release_refuses_impossible_cloud_mass(release):
    d,_ = release
    result = G.dispersion(d.rate_kg_s,5.,duration_s=.001,
        throat_pressure_pa=d.throat_pressure_pa,throat_velocity_m_s=d.velocity_m_s,
        throat_density_kg_m3=d.mass_flux_kg_m2s/d.velocity_m_s,hole_diameter_m=.006)
    assert result.status == "STEADY_REFERENCE_ONLY"
    with pytest.raises(RefusedError):
        _ = result.flammable_mass_kg.value
    assert result.flammable_mass_kg.resolve(RefusePolicy.BOUND) == pytest.approx(d.rate_kg_s*.001)
    assert any("transient" in flag for flag in result.lfl_distance_m.flags)


def test_transient_inventory_overrides_rate_times_duration(release):
    d,_ = release
    result = G.dispersion(d.rate_kg_s,5.,duration_s=100.,available_mass_kg=.01,
        throat_pressure_pa=d.throat_pressure_pa,throat_velocity_m_s=d.velocity_m_s,
        throat_density_kg_m3=d.mass_flux_kg_m2s/d.velocity_m_s,hole_diameter_m=.006)
    assert result.flammable_mass_kg.refused
    assert result.flammable_mass_kg.bound == .01


@pytest.mark.parametrize("current,old", [(1.,0.), (True,False), (1,True),
    ({"grade":"MEASURED"},{"grade":"PLACEHOLDER"}),
    ({"source":"b"},{"source":"a"}), ({"claim":"b"},{"claim":"a"}),
    ({"added":0},{}), ({},{"removed":0}), (math.nan,math.nan), (math.inf,math.inf)])
def test_regression_comparison_detects_mutations(current,old):
    assert differences(current,old)


def test_regression_comparison_accepts_serialized_tuples_and_float_roundoff():
    assert not differences({"value":(1.,2.)},{"value":[1.+1e-12,2.]})


def _monitor():
    return DT.DigitalTwinMonitor(DT.default_tag_specs(),lambda values:{"rate":1.},
                                  constraints=(DT.pressure_agreement,))


def test_second_stream_cannot_rewind_shared_plant_state():
    monitor = _monitor()
    first = DT.TelemetryFrame(1,100.,100.025,DT.make_values(unloading_flow_kg_s=.2),"a")
    assert monitor.process(first).accepted
    previous = dict(monitor.state)
    stale = DT.TelemetryFrame(1,10.,10.025,DT.make_values(),"b")
    result = monitor.process(stale)
    assert not result.accepted and "CLOCK_REVERSED" in result.reasons
    assert monitor.state == previous and monitor.plant_state is DT.PlantState.UNLOADING


def test_same_timestamp_conflicting_redundant_stream_is_rejected():
    monitor = _monitor()
    assert monitor.process(DT.TelemetryFrame(1,1.,1.025,DT.make_values(),"a")).accepted
    conflict = DT.TelemetryFrame(1,1.,1.026,DT.make_values(unloading_flow_kg_s=.2),"b")
    result = monitor.process(conflict)
    assert not result.accepted
    assert any("conflicting values" in reason for reason in result.reasons)


def test_runtime_version_is_bound_to_source_files():
    from gen_digital_twin_validation import new_monitor
    from runtime_manifest import source_fingerprint
    identity = source_fingerprint()
    assert identity["sha256"] in new_monitor().model_version
    assert "source_term.py" in identity["files"]


@pytest.mark.parametrize("values", [None, [], {1:"bad"}, {"TANK_PRESSURE_PA":None}])
def test_malformed_container_or_sample_is_rejected_transactionally(values):
    monitor = _monitor()
    assert monitor.process(DT.TelemetryFrame(1,1.,1.025,DT.make_values())).accepted
    before = dict(monitor.state)
    assert not monitor.process(DT.TelemetryFrame(2,2.,2.025,values)).accepted
    assert monitor.state == before


def test_log_radiation_is_unscaled_and_grade_does_not_claim_validation():
    group = F.residence_time(.1,100.) * float(F.A_P_MOLINA_H2) * float(F.T_ADIABATIC_H2)**4
    expected = max(0.,min(.4,.085*math.log10(group)-1.16))
    assert F.radiant_fraction(.1,100.,form="log") == pytest.approx(expected)
    assert F.FIRE_PROV.grade is T.Grade.ENGINEERING_JUDGEMENT
    with pytest.raises(ValueError,match="unknown"):
        F.radiant_fraction(.1,1.,form="typo")
