"""Exercise unified standard/LH2 modes against the public PRISM paths."""
from pathlib import Path
import csv
import io
import json
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lh2_tno.backend import tree_digest

OUT=ROOT/'results/20261008/mode_v050'
OUT.mkdir(parents=True,exist_ok=True)
host=ROOT/'src/prism_cli.py'
def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def execute(label,args):
    completed=subprocess.run([sys.executable,'-X','utf8',str(host),*args],capture_output=True,text=True,encoding='utf-8',timeout=180)
    (OUT/(label+'.log')).write_text(completed.stdout+'\n'+completed.stderr,encoding='utf-8')
    if completed.returncode:raise RuntimeError(f'{label} failed: {completed.stderr[-1500:]}')
    return completed

engine=ROOT/'src/prism_qra'
before=tree_digest(engine)
config={'interpreter':sys.executable,'timeout_s':120.,'packages':[{'name':'prism_qra','root':str(engine),'sha256':before}]}
save('standard_backend.json',config)
execute('standard_template',['--mode','standard','--backend',str(OUT/'standard_backend.json'),
    'template','--directory',str(OUT/'templates')])
# Small synthetic GH2 case verifies that standard mode really calls the old
# QRA engine. No template/default site data are promoted to field measurements.
(OUT/'sections.csv').write_text('section_id,service,inventory_kg,isolation_time_s\nS,GH2,1,120\n',encoding='utf-8')
row=dict(tag='V1',primitive='VALVE',service='GH2',count=1,diameter_mm=2.5,pressure_barg=10,
    temperature_k=288.15,orientation='HORIZONTAL',release_azimuth_deg=0,x_m=0,y_m=0,z_m=1,section_id='S')
buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=list(row));writer.writeheader();writer.writerow(row)
(OUT/'components.csv').write_text(buffer.getvalue(),encoding='utf-8')
execute('standard_qra',['--mode','standard','--backend',str(OUT/'standard_backend.json'),
    'run','--name','synthetic-standard-mode-check','--sections',str(OUT/'sections.csv'),
    '--components',str(OUT/'components.csv'),'--ignition','purple','--blocking','none',
    '--samples','0','--extent','10','--cell','10','--out',str(OUT/'standard_result.json')])
standard=json.loads((OUT/'standard_result.json').read_text(encoding='utf-8'))
assert standard['execution_mode']=='standard' and standard['mode_dispatch']['lh2_extension_selected'] is False
execute('lh2_frequency',['--mode','lh2',str(ROOT/'examples/lh2_frequency_facility.json'),
    '--frequency-plan',str(ROOT/'examples/lh2_frequency_plan.json'),'--output',str(OUT/'lh2_events.json')])
events=json.loads((OUT/'lh2_events.json').read_text(encoding='utf-8'))
assert events['execution_mode']=='lh2' and len(events['events'])==16
# Same actual provider packet as v0.4.0. Only routing changes here.
base=ROOT/'results/20261008/equipment_coupling_v040'
consumer=json.loads((base/'backend_config.json').read_text(encoding='utf-8'))
# Replay the recorded, digest-identified provider boundary. The resolved gas
# worker does not execute lh2dt or the pool. Their live source revisions are
# therefore not pins of this consumer-only replay; old evidence is preserved.
consumer['packages']=[p for p in consumer['packages'] if p['name'] in ('tno','slabx_lh2','slabx')]
save('lh2_mode_backend.json',consumer)
execute('lh2_actual_chain',['--mode','lh2',str(base/'facility.json'),'--backend',str(OUT/'lh2_mode_backend.json'),
    '--consequences',str(base/'request.json'),'--output',str(OUT/'lh2_result.json')])
lh2=json.loads((OUT/'lh2_result.json').read_text(encoding='utf-8'))
assert lh2['execution_mode']=='lh2' and lh2['data']['full_chain_executed']
assert lh2['data']['source']['discharge_recalculated'] is False
assert before==tree_digest(engine)
save('verification.json',{'version':'0.5.0','default_mode':'standard',
    'actual_standard_template_executed':True,'actual_standard_qra_executed':True,
    'actual_lh2_frequency_executed':True,'actual_lh2_provider_to_harm_executed':True,
    'provider_boundary_replayed_from_v040_record':True,'live_equipment_provider_reexecuted':False,
    'lh2_initiating_events':len(events['events']),'legacy_tno_source_unchanged':True,
    'automatic_fallback':False,'lh2_flow_recalculated':False,
    'lh2_chain_elapsed_ms':lh2['elapsed_ms'],'physical_validation_claim':False,
    'integration_scope':'Common mode launcher; each mode retains its native inputs/model limits. Not a completed new LH2 total facility QRA.'})
print((OUT/'verification.json').read_text(encoding='utf-8'))
