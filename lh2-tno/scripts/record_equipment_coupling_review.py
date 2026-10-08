from pathlib import Path
import json,platform
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/20261008/equipment_coupling_review'
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
package=read('package_manifest_verification.json')
tank=read('actual_tank_boundary_probe.json')
network=read('actual_network_outlet_probe.json')
states=tank['property_boundaries']
assert package['all_hashes_match'] and tank['smoke_passed']
assert all(abs(x['ph_roundtrip_enthalpy_residual_j_kg'])<1e-7 for x in states)
assert not any(x['direct_pt_hem']['accepted'] for x in states)
assert abs(network['energy_residual_w'])<1e-6
verdict={'date':'2026-10-08','thread_title':'액화수소 설비 디지털 트윈 모델링#2',
    'thread_id':'01a0ef39-9210-7213-b372-8c7f666a39b1',
    'scope':'output review and actual boundary compatibility probes, not production integration',
    'coupling_feasible':True,'current_full_equipment_twin_integrated_into_tno':False,
    'direct_plug_in_compatible':False,'provider_project_modified_by_reviewer':False,
    'tests':{'package_manifest_files':package['file_count'],'manifest_hashes_all_match':True,
        'delivered_tank_smoke_reproduced':True,'actual_tank_states_exported':len(states),
        'pressure_enthalpy_roundtrips_passed':len(states),'direct_saturated_pressure_temperature_hem_inputs_passed':0,
        'actual_network_outlet_exported':True,'network_outlet_energy_residual_w':network['energy_residual_w']},
    'responsibility':{'equipment_state_and_dynamics':'separate lh2dt project',
        'source_dispersion_consequences_risk':'lh2-tno/SLABx-LH2',
        'coupled_leak_discharge':'single shared leak-edge calculation; avoid duplicate flow or tank evolution'},
    'required_work':['PH and phase/cell-aware upstream boundary input',
        'resolved-mdot/outlet-state input that does not solve discharge a second time',
        'same fluid/EOS/energy reference; ParaHydrogen pool support where needed',
        'physical release geometry and vertical vent adapter',
        'shared event clock and per-release mass/transport-energy ledger',
        'leak-edge feedback into equipment mass/energy for accident transients',
        'generic unit/port binding beyond current storage_tank-only entry'],
    'field_validation_claim':False,'fresh_physics_realtime_claim':False,
    'python':platform.python_version(),
    'report':'docs/별도설비모델과_액화수소유닛_결합검토_20261008.md'}
(OUT/'coupling_review_verdict.json').write_text(json.dumps(verdict,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps(verdict['tests'],ensure_ascii=False,indent=2))
