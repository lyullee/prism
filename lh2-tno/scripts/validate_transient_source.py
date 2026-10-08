"""Verify a bounded source time history and constitutive branches, not field accuracy."""
from pathlib import Path
import copy,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lh2_tno.backend import BackendConfig, IsolatedBackend
from lh2_tno.source import ledger_from_response, prescribed_source_history, PrescribedState
from lh2_tno.backend import BackendError
OUT=ROOT/'results'/'20261008'
config=BackendConfig.model_validate_json((OUT/'backend_config.json').read_text(encoding='utf-8'))
backend=IsolatedBackend(config)
base=json.loads((OUT/'source_request.json').read_text(encoding='utf-8'))
rows=[]
for mode,eta in [('HEM',None),('HNEM',0.)]:
    p=copy.deepcopy(base);p['duration_s']=1.;p['time_step_s']=.2
    p['choices']['phase_model']=mode;p['choices']['hnem_eta']=eta
    response=backend.run('integrated_source',p)
    try:
        ledger=ledger_from_response(p,response,available_mass_kg=10.,position_enu_m=(0.,0.,.05))
        state='complete_requested_horizon';error=None
        assert len(ledger.steps)==5
    except BackendError as e:
        ledger=None;state='blocked_incomplete_horizon';error=str(e)
    record={'mode':mode,'hnem_eta':eta,'source_request':p,'source_ledger':ledger.model_dump(mode='json') if ledger else None,
            'backend_response':response,'horizon_status':state,'blocking_reason':error,'returned_steps':len(response['data']['steps']),
            'elapsed_ms':response['elapsed_ms'],'physical_validation_claim':False}
    (OUT/f'transient_source_{mode}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    rows.append({k:record[k] for k in ['mode','horizon_status','blocking_reason','returned_steps','elapsed_ms','physical_validation_claim']})
states=(PrescribedState(time_s=0.,pressure_pa=600000.,temperature_k=20.893,vapour_quality=0.),
        PrescribedState(time_s=.2,pressure_pa=500000.,temperature_k=20.893,vapour_quality=0.),
        PrescribedState(time_s=.4,pressure_pa=400000.,temperature_k=20.893,vapour_quality=0.))
ledger,responses=prescribed_source_history(backend,base,states,end_s=.6,available_mass_kg=10.,position_enu_m=(0.,0.,.05))
assert len(ledger.steps)==3
assert abs(ledger.released_mass_kg-sum(ledger.branch_mass_kg(k) for k in ('gas_kg_s','airborne_liquid_kg_s','ground_liquid_kg_s')))<1e-10
(OUT/'prescribed_source_history.json').write_text(json.dumps({'input_origin':'synthetic prescribed upstream states; not measured tank dynamics',
    'ledger':ledger.model_dump(mode='json'),'responses':responses,'physical_validation_claim':False},ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'transient_source_summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
