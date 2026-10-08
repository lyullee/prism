"""Inventory the existing TNO implementation, not just the LH2 wrapper."""
from pathlib import Path
import ast,hashlib,json,sys,platform
ROOT=Path(__file__).resolve().parents[1]
TNO=Path(r'C:\Users\lyul\Desktop\DocuData\TNO_위험분석모듈\TNO_SYSTEM')
CODE=TNO/'코드'
OUT=ROOT/'results/20261008/tno_function_inventory'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(CODE))
import taxonomy as T

modules=[]
for path in sorted(CODE.glob('*.py')):
    if path.name.startswith(('test_','gen_','verify_','refine_','build_')):continue
    raw=path.read_bytes();tree=ast.parse(raw.decode('utf-8-sig'))
    defs=[]
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)):
            defs.append({'name':node.name,'line':node.lineno,'kind':type(node).__name__,
                'doc':(ast.get_docstring(node) or '').split('\n\n')[0][:600],
                'methods':[{'name':m.name,'line':m.lineno} for m in node.body if isinstance(m,ast.FunctionDef)] if isinstance(node,ast.ClassDef) else []})
    modules.append({'path':str(path),'file':path.name,'sha256':hashlib.sha256(raw).hexdigest(),
        'module_doc':(ast.get_docstring(tree) or '')[:1600],'definitions':defs})
(OUT/'code_inventory.json').write_text(json.dumps({'python':platform.python_version(),'modules':modules},ensure_ascii=False,indent=2),encoding='utf-8')

frequency=[]
for (primitive,fuel),entry in T.FREQUENCY_LIBRARY.items():
    frequency.append({'primitive':primitive.value,'fuel':fuel.value,'medians':dict(zip(T.BIN_LABELS,entry.medians)),
        'mu':entry.mu,'sigma':entry.sigma,'conservatism_factor':entry.conservatism_factor,
        'provenance':entry.provenance.model_dump(mode='json')})
(OUT/'frequency_library.json').write_text(json.dumps({'entries':frequency,'no_data':[x.value for x in T.NO_DATA]},ensure_ascii=False,indent=2),encoding='utf-8')

section=T.Section(id='GENERIC-LH2',service=T.Service.LH2,inventory_kg=100.,isolation_time_s=120.)
comp=T.ComponentSpec(tag='GENERIC-VALVE',primitive=T.Primitive.VALVE,service=T.Service.LH2,count=10,
    nominal_diameter_m=.025,pressure_pa=600000.,temperature_k=20.893,
    position=T.Position(x=0.,y=0.),section_id=section.id)
site=T.Site(name='frequency-library-proof',sections=[section],components=[comp])
rows=T.enumerate_scenarios(site)
assert len(rows)==5
expected=[.00012,.000052,.000022,.0000093,.0000039]
assert all(abs(s.frequency_per_year-10*f)<1e-15 for s,f in zip(rows,expected))
proof={'scope':'actual frequency resolver and scenario enumeration; not a physical consequence calculation',
    'input_origin':'synthetic','component':'10 identical LH2 valves','nominal_bore_m':.025,
    'scenarios':[s.model_dump(mode='json') for s in rows],
    'automatic_frequency_lookup_and_count_scaling_passed':True,
    'not_the_new_wrapper_frequency_path':True}
(OUT/'actual_frequency_enumeration.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps({'module_count':len(modules),'frequency_entries':len(frequency),
    'lh2_entries':sum(x['fuel']=='LH2' for x in frequency),'automatic_frequency_proof':True,
    'valve_bin_frequencies_per_year':{s.bin_label:s.frequency_per_year for s in rows}},ensure_ascii=False,indent=2))
