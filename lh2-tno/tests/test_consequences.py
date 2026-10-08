"""Conservation, clock, event semantics, and invalid boundary checks."""
import copy
import json
from pathlib import Path
import numpy as np
import pytest
from lh2_tno.chain_worker import box_fractions, branch_mass, dose_harm, mole_fraction, pulse_mass, weighted_union_harm
from lh2_tno.consequences import ConsequenceRequest

EXAMPLE=Path(__file__).parents[1]/'examples/consequence_request.json'


@pytest.mark.parametrize('shift',[0.,.1,.83,2.4])
def test_exact_grid_inventory_under_translation_and_refinement(shift):
    amount=2.3;size=np.array([1.3,2.1,.4]);rho=amount/np.prod(size)
    for spacing in [.5,.2,.07]:
        edges=[np.linspace(-5,5,round(10/spacing)+1) for _ in range(3)]
        fraction=box_fractions(edges,[shift,0.,0.],size)
        dv=np.diff(edges[0])[:,None,None]*np.diff(edges[1])[None,:,None]*np.diff(edges[2])[None,None,:]
        assert np.sum(fraction*rho*dv)==pytest.approx(amount,abs=1e-12)


def test_grid_boundary_preserves_known_half_inventory():
    edges=[np.linspace(0,5,21),np.linspace(-5,5,21),np.linspace(-5,5,21)]
    f=box_fractions(edges,[0.,0.,0.],[2.,2.,2.])
    dv=np.diff(edges[0])[:,None,None]*np.diff(edges[1])[None,:,None]*np.diff(edges[2])[None,None,:]
    assert np.sum(f*dv)==pytest.approx(4.)


def test_release_stop_retains_exact_emitted_inventory():
    rows=[{'time_s':0.,'flow':2.},{'time_s':.3,'flow':1.}]
    assert branch_mass(rows,.5,'flow',.2)==pytest.approx(.4)
    assert branch_mass(rows,.5,'flow',20.)==pytest.approx(.8)


def test_ground_arrival_is_causal_and_preserves_mass_after_delay():
    pulse=[{'start':.1,'end':.3,'rate':2.}]
    assert pulse_mass(pulse,.05)==0.
    assert pulse_mass(pulse,.2)==pytest.approx(.2)
    assert pulse_mass(pulse,20.)==pytest.approx(.4)


def test_air_mixture_is_molar_not_mass_fraction():
    # One mole hydrogen plus one mole air must give 50 mol%, although the
    # hydrogen mass fraction is only about 6.5%.
    c=mole_fraction(np.array([.002016,0.]),np.array([.028965,.028965]))
    assert c.tolist()==pytest.approx([.5,0.])


def test_combined_damage_uses_valid_union_upper_bound_without_independence():
    assert weighted_union_harm(.4,.3)==pytest.approx(.7)
    assert weighted_union_harm(.8,.6)==1.


def test_thermal_stop_does_not_drop_last_interval():
    class Risk:
        class ThermalProbit:
            a=-36.38;b=2.56
        @staticmethod
        def probit_to_probability(pr):return .1
    samples=[{'time_s':0.,'flux_w_m2':10000.,'flame_contact':False},
             {'time_s':.2,'flux_w_m2':0.,'flame_contact':False}]
    out=dose_harm(samples,20.,Risk)
    assert out['dose']==pytest.approx(.2*10000**(4/3))


@pytest.mark.parametrize('fault',['wind','budget','ignition_clock','radiation','footprint','frequency','vertical','release_clock'])
def test_invalid_chain_inputs_are_rejected(fault):
    d=json.loads(EXAMPLE.read_text(encoding='utf-8'))
    if fault=='wind':d['weather']['wind_from_bearing_deg']=90.
    if fault=='budget':d['domain']['cell_size_m']=.001
    if fault=='ignition_clock':d['ignition']['delayed_time_s']=.123
    if fault=='radiation':d['radiative_fraction_range']=[.12,.06]
    if fault=='footprint':d['pool']={'footprint_origin':'declared_sensitivity','radius_m':.1,'conductivity_w_mk':.88,
        'diffusivity_m2_s':1e-7,'initial_temperature_k':288.,'domain_radius_m':1.,'radial_step_m':.5}
    if fault=='frequency':d['annual_frequency_provenance']=None
    if fault=='vertical':d['source_input']['nozzle']['direction_enu']=[0.,0.,1.]
    if fault=='release_clock':d['evaluation_times_s'].remove(.2)
    with pytest.raises(ValueError):ConsequenceRequest.model_validate_json(json.dumps(d))


def test_event_branches_partition_probability_without_repeated_leaks():
    d=json.loads(EXAMPLE.read_text(encoding='utf-8'))
    request=ConsequenceRequest.model_validate_json(json.dumps(d))
    probabilities=request.ignition.probabilities()
    assert sum(probabilities.values())==pytest.approx(1.)
    assert probabilities['delayed_explosion']==pytest.approx(.9*.2*.4)


def test_model_natural_duration_requires_explicit_pressure_equalization_basis():
    d=json.loads(EXAMPLE.read_text(encoding='utf-8'))
    d['source_duration_mode']='model_natural'
    d['release_termination']={'basis':'model_pressure_equalization','time_s':.2,
                              'provenance':'pinned source model natural-stop contract'}
    request=ConsequenceRequest.model_validate_json(json.dumps(d))
    assert request.source_duration_mode=='model_natural'
    d['release_termination']['basis']='synthetic_diagnostic_horizon'
    with pytest.raises(ValueError,match='pressure-equalization'):
        ConsequenceRequest.model_validate_json(json.dumps(d))
