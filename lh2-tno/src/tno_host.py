"""PRISM optional-mode launcher. Standard mode is stdlib-only.

The legacy engine stays external and hash-pinned. The LH2 package is imported
only when mode=lh2 is explicitly selected; neither mode falls back to the other.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import subprocess
import sys


class ModeError(ValueError):
    pass


def python_tree_digest(root: Path) -> str:
    paths=sorted(p for p in root.rglob('*.py') if '__pycache__' not in p.parts)
    if not paths:raise ModeError('TNO engine has no Python source')
    values={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    encoded=json.dumps(values,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def read_mode_config(path):
    if path is None:return {}
    config=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(config,dict) or set(config)-{'mode','backend'}:
        raise ModeError('mode config allows only mode and backend')
    if config.get('mode','standard') not in ('standard','lh2'):
        raise ModeError('mode config requires standard or lh2')
    if config.get('backend') is not None:
        if not isinstance(config['backend'],str) or not config['backend'].strip():
            raise ModeError('mode backend must be a nonempty file path')
        value=Path(config['backend'])
        config['backend']=value if value.is_absolute() else path.resolve().parent/value
    return config


def legacy_specification(config_path):
    if config_path is None:raise ModeError('standard mode requires --backend with the pinned TNO root and interpreter')
    data=json.loads(config_path.read_text(encoding='utf-8'))
    pins=[p for p in data.get('packages',[]) if p.get('name')=='tno']
    if len(pins)!=1:raise ModeError('standard mode requires exactly one tno source pin')
    pin=pins[0]
    root=Path(pin['root']).resolve()
    digest=pin['sha256']
    if not isinstance(digest,str) or len(digest)!=64 or any(x not in '0123456789abcdef' for x in digest):
        raise ModeError('invalid TNO source SHA-256')
    interpreter=data.get('interpreter')
    if not isinstance(interpreter,str) or not interpreter.strip():raise ModeError('explicit TNO interpreter required')
    qra=root/'qra.py'
    if not qra.is_file():raise ModeError('pinned TNO root has no qra.py')
    if python_tree_digest(root)!=digest:raise ModeError('TNO source revision mismatch; standard mode not executed')
    deadline=data.get('timeout_s',120.)
    if isinstance(deadline,bool) or not isinstance(deadline,(int,float)) or not math.isfinite(deadline) or deadline<=0:
        raise ModeError('positive finite standard-mode deadline required')
    return interpreter,root,qra,digest,float(deadline)


def run_standard(config_path,arguments):
    interpreter,root,qra,digest,deadline=legacy_specification(config_path)
    # No shell expansion, and no imports of LH2/SLAB/provider packages here.
    try:
        result=subprocess.run([interpreter,'-B','-X','utf8',str(qra),*arguments],check=False,timeout=deadline)
    except subprocess.TimeoutExpired as error:
        raise ModeError('standard TNO deadline exceeded; no qualified result') from error
    if python_tree_digest(root)!=digest:raise ModeError('TNO source changed during execution; discard this result')
    if result.returncode==0 and arguments and arguments[0]=='run':
        outputs=argparse.ArgumentParser(add_help=False)
        outputs.add_argument('--out',type=Path,default=Path('result.json'))
        options,_=outputs.parse_known_args(arguments[1:])
        if not options.out.is_file():raise ModeError('legacy QRA reported success without a result file')
        data=json.loads(options.out.read_text(encoding='utf-8'))
        if not isinstance(data,dict):raise ModeError('legacy QRA result must be a JSON object')
        data['execution_mode']='standard'
        data['mode_dispatch']={'entrypoint':'prism','engine':'legacy_tno','engine_source_sha256':digest,
                               'lh2_extension_selected':False,'automatic_fallback':False}
        options.out.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return result.returncode


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    parser=argparse.ArgumentParser(prog='prism',add_help=False)
    parser.add_argument('--mode',choices=('standard','lh2'),default=None)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--backend',type=Path)
    parser.add_argument('--describe-modes',action='store_true')
    options,remaining=parser.parse_known_args(argv)
    try:
        config=read_mode_config(options.config)
        mode=options.mode or config.get('mode','standard')
        backend=options.backend or config.get('backend')
        if options.describe_modes:
            print(json.dumps({'default_mode':'standard','selected_mode':mode,
                'modes':{'standard':{'engine':'unchanged external legacy TNO','input':'original qra subcommands/CSV'},
                         'lh2':{'engine':'optional LH2 extension','input':'facility JSON, optional frequency/consequence request'}},
                'automatic_fallback':False,'complete_facility_qra_claim':False},ensure_ascii=False,indent=2))
            return 0
        if not argv or (mode=='standard' and backend is None and remaining in (['--help'],['-h'],[])):
            print('PRISM: Process Risk Integration and Scenario Modeling\n\n'
                  '  prism --mode standard --backend backend.json <original qra arguments>\n'
                  '  prism --mode lh2 <facility.json> [--backend backend.json] [LH2 arguments]\n'
                  '  prism --config mode.json <mode-specific arguments>\n'
                  '  prism --describe-modes\n\n'
                  'Default: standard. LH2 is opt-in; there is no automatic fallback.\n'
                  'Modes use their own validated inputs and retain their current model limitations.')
            return 0
        if mode=='standard':return run_standard(backend,remaining)
        try:
            extension=importlib.import_module('lh2_tno.cli')
        except ImportError as error:
            raise ModeError('LH2 mode requires the prism-risk distribution (lh2_tno import) and its dependencies; install it in this interpreter') from error
        if backend is not None:remaining.extend(['--backend',str(backend)])
        value=extension.main(remaining)
        return 0 if value is None else value
    except (ModeError,OSError,ValueError,KeyError,TypeError,RuntimeError) as error:
        print(f'prism: {error}',file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
