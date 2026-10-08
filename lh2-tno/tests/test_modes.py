"""Optional mode routing, no cross-mode fallback, and pinned legacy execution."""
import json
from pathlib import Path
import subprocess
import sys
import pytest
import tno_host


def backend(tmp_path,source=None):
    engine=tmp_path/'legacy';engine.mkdir()
    if source is None:
        source='''import json,sys
from pathlib import Path
if sys.argv[1:2]==['run']:
    out=Path(sys.argv[sys.argv.index('--out')+1])
    out.write_text(json.dumps({'risk_value':.001,'claim_boundary':'unqualified'}),encoding='utf-8')
else:print('legacy only')
'''
    (engine/'qra.py').write_text(source,encoding='utf-8')
    path=tmp_path/'backend.json'
    path.write_text(json.dumps({'interpreter':sys.executable,'timeout_s':10.,
        'packages':[{'name':'tno','root':str(engine),'sha256':tno_host.python_tree_digest(engine)}]}),encoding='utf-8')
    return path,engine


def test_default_mode_runs_only_legacy_and_preserves_numeric_output(tmp_path,monkeypatch):
    config,engine=backend(tmp_path);out=tmp_path/'risk.json'
    def never_import(name):raise AssertionError('default mode must not import LH2')
    monkeypatch.setattr(tno_host.importlib,'import_module',never_import)
    code=tno_host.main(['--backend',str(config),'run','--out',str(out)])
    assert code==0
    data=json.loads(out.read_text(encoding='utf-8'))
    assert data['risk_value']==.001 and data['claim_boundary']=='unqualified'
    assert data['execution_mode']=='standard'
    assert data['mode_dispatch']['automatic_fallback'] is False


def test_lh2_mode_imports_selected_extension_only_and_forwards_backend(monkeypatch,tmp_path):
    received=[]
    class Extension:
        @staticmethod
        def main(argv):received.extend(argv)
    monkeypatch.setattr(tno_host.importlib,'import_module',lambda name:Extension if name=='lh2_tno.cli' else None)
    monkeypatch.setattr(tno_host.subprocess,'run',lambda *a,**k:pytest.fail('LH2 may not fall back to legacy'))
    assert tno_host.main(['--mode','lh2','site.json','--backend','models.json','--consequences','leak.json'])==0
    assert received==['site.json','--consequences','leak.json','--backend','models.json']


def test_missing_lh2_extension_does_not_run_standard(monkeypatch,capsys):
    def absent(name):raise ModuleNotFoundError('lh2_tno unavailable')
    monkeypatch.setattr(tno_host.importlib,'import_module',absent)
    monkeypatch.setattr(tno_host.subprocess,'run',lambda *a,**k:pytest.fail('no silent fallback'))
    assert tno_host.main(['--mode','lh2','site.json'])==2
    assert 'prism-risk distribution' in capsys.readouterr().err


def test_invalid_mode_is_not_inferred_from_filename():
    with pytest.raises(SystemExit) as error:tno_host.main(['--mode','ln2','site.json'])
    assert error.value.code==2


def test_config_lh2_and_explicit_cli_mode_override(tmp_path,monkeypatch):
    config,engine=backend(tmp_path)
    mode=tmp_path/'mode.json';mode.write_text(json.dumps({'mode':'lh2','backend':'backend.json'}),encoding='utf-8')
    def absent(name):raise ModuleNotFoundError('missing plugin')
    monkeypatch.setattr(tno_host.importlib,'import_module',absent)
    assert tno_host.main(['--config',str(mode),'site.json'])==2
    assert tno_host.main(['--config',str(mode),'--mode','standard','--help'])==0


@pytest.mark.parametrize('fault',['unknown_key','mode','backend'])
def test_invalid_mode_config_fails_before_dispatch(tmp_path,monkeypatch,fault):
    data={'mode':'lh2'}
    if fault=='unknown_key':data['auto_fallback']=True
    if fault=='mode':data['mode']='auto'
    if fault=='backend':data['backend']=False
    p=tmp_path/'config.json';p.write_text(json.dumps(data),encoding='utf-8')
    monkeypatch.setattr(tno_host.importlib,'import_module',lambda name:pytest.fail('invalid config'))
    assert tno_host.main(['--config',str(p),'site.json'])==2


def test_source_revision_mismatch_stops_legacy_before_run(tmp_path):
    config,engine=backend(tmp_path)
    marker=tmp_path/'invoked'
    (engine/'qra.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n',encoding='utf-8')
    assert tno_host.main(['--backend',str(config),'run'])==2
    assert not marker.exists()


def test_source_mutation_during_legacy_execution_is_not_qualified(tmp_path):
    config,engine=backend(tmp_path,"from pathlib import Path\nPath(__file__).write_text('changed')\n")
    assert tno_host.main(['--backend',str(config),'--help'])==2


def test_failed_legacy_mode_does_not_fallback_to_lh2(tmp_path,monkeypatch):
    config,_=backend(tmp_path,'import sys\nsys.exit(7)\n')
    monkeypatch.setattr(tno_host.importlib,'import_module',lambda name:pytest.fail('legacy failure cannot enable LH2'))
    assert tno_host.main(['--backend',str(config),'run'])==7


@pytest.mark.parametrize('deadline',[0.,-1.,True,float('inf')])
def test_standard_deadline_is_explicit_and_finite(tmp_path,deadline):
    config,_=backend(tmp_path)
    data=json.loads(config.read_text(encoding='utf-8'));data['timeout_s']=deadline
    config.write_text(json.dumps(data),encoding='utf-8')
    assert tno_host.main(['--backend',str(config),'--help'])==2


def test_standard_host_help_does_not_need_pydantic_or_optional_dependencies():
    host=Path(tno_host.__file__).resolve()
    result=subprocess.run([sys.executable,'-S',str(host),'--help'],capture_output=True,text=True)
    assert result.returncode==0 and 'Default: standard' in result.stdout


def test_modes_report_identifies_default_without_importing_extension(monkeypatch,capsys):
    monkeypatch.setattr(tno_host.importlib,'import_module',lambda name:pytest.fail('inspection is stdlib-only'))
    assert tno_host.main(['--describe-modes'])==0
    report=json.loads(capsys.readouterr().out)
    assert report['default_mode']=='standard' and report['automatic_fallback'] is False


def test_lh2_frequency_cli_uses_same_existing_event_generator(tmp_path):
    root=Path(__file__).parents[1]
    out=tmp_path/'events.json'
    assert tno_host.main(['--mode','lh2',str(root/'examples/lh2_frequency_facility.json'),
        '--frequency-plan',str(root/'examples/lh2_frequency_plan.json'),'--output',str(out)])==0
    report=json.loads(out.read_text(encoding='utf-8'))
    assert report['execution_mode']=='lh2' and len(report['events'])==16
    assert report['total_facility_annual_risk'] is None
