"""Probe the delivered tank package without modifying the provider project."""
from pathlib import Path
from dataclasses import asdict
import contextlib,io,json,runpy,sys,hashlib
from external_paths import required_external_path
ROOT=Path(__file__).resolve().parents[1]
MODEL=required_external_path('PRISM_LH2DT_ROOT', 'the equipment digital-twin model root')
PACKAGE=MODEL/'outputs/lh2dt_test_package_20261008'
OUT=ROOT/'results/20261008/equipment_coupling_review'
sys.path.insert(0,str(PACKAGE/'src'))
sys.path.insert(0,str(required_external_path('PRISM_SLABX_LH2_ROOT', 'the optional SLABx-LH2 source root')))
from lh2dt import HydrogenProperties,HorizontalVesselGeometry,LayeredTank,LayeredTankParameters
from slabx_lh2.lh2_critical_flow import CriticalFlowInput,hem_critical_flow
import lh2dt
assert Path(lh2dt.__file__).resolve().is_relative_to(PACKAGE.resolve())

capture=io.StringIO()
with contextlib.redirect_stdout(capture):runpy.run_path(str(PACKAGE/'run_smoke_test.py'),run_name='__main__')
(OUT/'delivered_tank_smoke_test.txt').write_text(capture.getvalue(),encoding='utf-8')
assert 'TANK_SMOKE_TEST_PASS' in capture.getvalue()
results={'package_import_path':lh2dt.__file__,'smoke_passed':True,'property_boundaries':[]}
for fluid in ('ParaHydrogen','Hydrogen'):
    props=HydrogenProperties(fluid)
    # Export actual, explicitly selected liquid/vapor cells of the layered tank.
    tank=LayeredTank(HorizontalVesselGeometry(2.4892,12.0666,.6223,quadrature_order=48),
        LayeredTankParameters(liquid_cell_count=3,vapor_cell_count=3,wall_node_count=12,wall_heat_capacity_J_K=3e6),properties=props)
    initial=tank.initialize_saturated(350000.,.35)
    state=tank.thermo(initial)
    for region,selected in [('liquid',state.liquid[0]),('vapor',state.vapor[-1])]:
        ph=props.from_ph(selected.pressure_Pa,selected.specific_enthalpy_J_kg)
        row={'fluid':fluid,'region':region,'cell_index':0 if region=='liquid' else len(state.vapor)-1,
            'thermo_state':asdict(selected),'ph_roundtrip_enthalpy_residual_j_kg':ph.specific_enthalpy_J_kg-selected.specific_enthalpy_J_kg,
            'ph_roundtrip_quality':ph.quality}
        try:
            out=hem_critical_flow(CriticalFlowInput(selected.pressure_Pa,selected.temperature_K,.0127,1.,101325.,fluid))
            row['direct_pt_hem']={'accepted':True,'result':asdict(out)}
        except Exception as e:row['direct_pt_hem']={'accepted':False,'error':f'{type(e).__name__}: {e}'}
        results['property_boundaries'].append(row)

results['interpretation']='Actual packaged tank states exported with explicit fluid and phase; PH preserves boundary, direct saturated PT source compatibility separately tested. Not facility-to-consequence coupling execution.'
(OUT/'actual_tank_boundary_probe.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print(capture.getvalue())
print(json.dumps({'states':len(results['property_boundaries']),'direct_pt_accepted':sum(r['direct_pt_hem']['accepted'] for r in results['property_boundaries']),
    'details':[{k:r[k] for k in ('fluid','region','ph_roundtrip_quality','direct_pt_hem')} for r in results['property_boundaries']]},ensure_ascii=False,indent=2))
