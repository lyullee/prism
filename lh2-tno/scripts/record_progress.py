from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results'/'20261008'
original=ROOT.parent/'LH2_TNO_개발점검_20261007'/'development_backlog.json'
backlog=json.loads(original.read_text(encoding='utf-8'))
states={'D01':'partial','D02':'software_verified','D03':'partial','D04':'partial','D05':'partial',
        'D07':'partial','D08':'partial','D09':'partial','D12':'partial','D17':'partial','D18':'partial'}
notes={'D01':'External code trees and dependency versions pinned; complete legacy environment/full-suite/transfer integrity still pending.',
       'D02':'Three generic synthetic facility schemas round-tripped; topology/phase/direction/property contracts tested.',
       'D03':'Partition/inventory/time/property identity checks implemented; total energy and momentum handoff not qualified.',
       'D04':'Transactional normalization implemented; field metadata binding and reconstructed data replay pending.',
       'D05':'New facility-source route invokes existing TNO registry; remains diagnostic/withheld. Legacy full pipeline unchanged.',
       'D07':'Steady VentStack component connected; complete dynamic tank/PSV/stack chain pending.',
       'D08':'Real integrated LH2 source call and prescribed-state history; early native transient termination withheld.',
       'D09':'Real declared-ground DynamicLH2PoolX call; jet deposition/footprint connection pending.',
       'D12':'Time-dependent prescribed thermal-dose transformation; validated radiation source pending.',
       'D17':'Missing-frequency and annual weather-partition rules; component/exposure prior library pending.',
       'D18':'First-event and already-observed release probability semantics implemented; sensor/physical branches pending.'}
for item in backlog['items']:
    item['status']=states.get(item['id'],'planned')
    if item['id'] in notes:item['implementation_note']=notes[item['id']]
backlog.update(date_kst='2026-10-08',target_journal='International Journal of Hydrogen Energy',implementation_complete=False)
(OUT/'development_status.json').write_text(json.dumps(backlog,ensure_ascii=False,indent=2),encoding='utf-8')
manifest={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
          for folder in ('src','tests','scripts','examples','docs') for p in (ROOT/folder).rglob('*')
          if p.is_file() and '__pycache__' not in p.parts}
record={'date_kst':'2026-10-08','new_package_tests':{'passed':46,'seconds':.22},
        'legacy_targeted_tests':{'passed':79,'seconds':.96},'full_legacy_suite_executed':False,
        'external_models_modified':False,'full_physics_chain_completed':False,'field_validation_completed':False,
        'real_time_requirement_demonstrated':False,'source_manifest':manifest,
        'evidence_records_registered_as_experiment':0,'python':sys.version}
(OUT/'verification_record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
for p in OUT.glob('*.json'):json.loads(p.read_text(encoding='utf-8'))
print('Saved development status and verified result JSON files. Original 20261007 backlog preserved.')
