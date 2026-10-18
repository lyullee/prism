"""Read-only audit of the separate equipment project and its deliverables."""
from pathlib import Path
import hashlib,json,zipfile
import xml.etree.ElementTree as ET
import sys
from external_paths import required_external_path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from lh2_tno.backend import tree_digest

MODEL=required_external_path('PRISM_LH2DT_ROOT', 'the equipment digital-twin model root')
OUT=ROOT/'results/20261008/equipment_coupling_review'
OUT.mkdir(parents=True,exist_ok=True)
def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def abbreviated(obj,depth=0):
    if depth>3:
        if isinstance(obj,dict):return {'keys':list(obj)[:24]}
        if isinstance(obj,list):return {'count':len(obj)}
        return obj
    if isinstance(obj,dict):return {k:abbreviated(v,depth+1) for k,v in obj.items() if k not in {'rows','history','trajectory','time_series','snapshots','channels','file_manifest'}}
    if isinstance(obj,list):return {'count':len(obj),'first':abbreviated(obj[0],depth+1) if obj else None}
    return obj

files=[
 'docs/benchmarks/current_development_status.json',
 'docs/benchmarks/center_screening_full_topology_chain.json',
 'docs/benchmarks/center_screening_trajectory_conservation.json',
 'docs/benchmarks/center_cold_bog_connection_20261008.json',
 'docs/benchmarks/dynamic_command_event_quadrature_20261008.json',
 'docs/benchmarks/center_official_independent_validation_20261007.json',
 'docs/benchmarks/center_comparison_integrity_20261008.json',
 'configs/center_procedure_reference_20261008.json',
 'configs/center_screening_closure.json',
 'configs/center_tank_dpt_vacuum_physical_profile.json',
 'outputs/lh2dt_test_package_20261008/configs/tank_model_parameters.json',
 'outputs/lh2dt_test_package_20261008/configs/tank_observation_metadata.json',
]
records=[]
for relative in files:
    path=MODEL/relative
    if not path.exists():records.append({'path':str(path),'missing':True});continue
    raw=path.read_bytes();obj=json.loads(raw.decode('utf-8-sig'))
    save(path.stem+'_snapshot.json',obj)
    records.append({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
                    'modified_time_s':path.stat().st_mtime,'summary':abbreviated(obj)})

package=MODEL/'outputs/lh2dt_test_package_20261008'
manifest=json.loads((package/'manifest.json').read_text(encoding='utf-8-sig'))
checks=[]
for entry in manifest['files']:
    path=(package/entry['path']).resolve()
    if not path.is_relative_to(package.resolve()):raise ValueError('package manifest escapes root')
    exists=path.exists();actual=hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
    checks.append({'path':entry['path'],'exists':exists,'hash_matches':actual==entry['sha256'].lower()})
save('package_manifest_verification.json',{'scope':manifest.get('scope'),'file_count':len(checks),
    'all_hashes_match':all(x['hash_matches'] for x in checks),'files':checks})

doc=MODEL/'outputs/액화수소_디지털트윈_개발현황과_유닛_아주쉬운_설명서_20261008.docx'
if doc.exists():
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(doc) as z:xml=ET.fromstring(z.read('word/document.xml'))
    paragraphs=[''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in xml.findall('.//w:p',ns)]
    (OUT/'equipment_easy_guide_extracted.txt').write_text('\n'.join(x for x in paragraphs if x),encoding='utf-8')
    records.append({'path':str(doc),'sha256':hashlib.sha256(doc.read_bytes()).hexdigest(),
        'paragraph_count':len(paragraphs),'content_review_only':True,'layout_review_claim':False})

save('deliverable_audit.json',{'thread_title':'액화수소 설비 디지털 트윈 모델링#2',
    'thread_id':'01a0ef39-9210-7213-b372-8c7f666a39b1','project_root':str(MODEL),
    'live_source_digest_at_audit':tree_digest(MODEL/'src/lh2dt'),
    'provider_project_modified_by_reviewer':False,'artifacts':records})
print(json.dumps({'package_file_count':len(checks),'all_package_hashes_match':all(x['hash_matches'] for x in checks),
    'artifact_count':len(records),'output':str(OUT)},ensure_ascii=False,indent=2))
