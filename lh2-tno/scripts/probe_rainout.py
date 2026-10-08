from pathlib import Path
from dataclasses import asdict
import copy,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,r'C:\Users\lyul\Desktop\DocuData\SLABx_LH2\slabx-lh2\source\slabx-lh2')
from slabx_lh2.integrated_lh2_source import *
common=json.loads((ROOT/'results/20261008/source_request.json').read_text(encoding='utf-8'))
records=[]
for correlation in ['rescigno_yellow_book','henk2007_phaseII','henk2007_weber_ccps']:
    for height in [.05,.001,.00001]:
        p=copy.deepcopy(common)
        p['nozzle'].update(height_m=height,direction_enu=(1.,0.,-1.))
        p['ambient'].update(wind_speed_m_s=3.,wind_from_bearing_deg=270.)
        p['choices']['droplet_correlation']=correlation
        inp=IntegratedSourceInput(TankState(**p['tank']),(),NozzleGeometry(**p['nozzle']),AmbientState(**p['ambient']),ModelChoices(**p['choices']),.2,.2)
        r=asdict(evaluate_integrated_lh2_source(inp))['steps'][0]
        row={'correlation':correlation,'height_m':height,'gas':r['gas_mass_flow_kg_s'],
             'ground':r['ground_liquid_mass_flow_kg_s'],'smd':r['droplet']['smd_m'],'impact':r['impact_position_m']}
        records.append(row);print(json.dumps(row),flush=True)
(ROOT/'results/20261008/full_chain/rainout_probe.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
