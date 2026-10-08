"""Persist optional-mode design and verification beside the code."""
from pathlib import Path
import json
import hashlib
import shutil
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
if json.loads((ROOT/'CURRENT_STATUS.json').read_text(encoding='utf-8'))['package_version'] != '0.5.0':
    raise SystemExit('Historical v0.5.0 recorder cannot overwrite a newer release.')
OUT=ROOT/'results/20261008/mode_v050'
verification=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
suites=ET.parse(OUT/'unit_tests.xml').getroot().findall('.//testsuite')
count=sum(int(x.get('tests','0')) for x in suites)
assert count==154 and all(int(x.get('failures','0'))==int(x.get('errors','0'))==0 for x in suites)
verification['unit_tests_passed']=count
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
status_path=ROOT/'CURRENT_STATUS.json'
status=json.loads(status_path.read_text(encoding='utf-8'))
status.update(package_version='0.5.0',unit_contract_conservation_tests_passed=count,
    module_structure='single TNO launcher with standard default and optional LH2 mode; internal providers remain separate',
    unified_tno_mode_launcher_implemented=True,default_execution_mode='standard',
    optional_execution_modes=['lh2'],automatic_mode_fallback=False,
    original_tno_source_modified_for_mode_selection=False,
    standard_mode_actual_legacy_qra_executed=True,lh2_mode_actual_consequence_execution=True,
    mode_record='docs/TNO_LH2_v050_옵셔널모드_개발기록_20261008.md',
    mode_results='results/20261008/mode_v050')
status_path.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
doc=f'''# TNO v0.5.0 — 옵셔널 LH2 모드

2026-10-08. 사용자의 “TNO LH2 mode” 요청에 따라 **사용자는 하나의 TNO 실행기에서 모드를 선택하고, 내부 모델 코드는 분리해 유지하는 구조**를 구현했다. 계산 경로의 물리 적용범위를 넓힌 변경은 아니다.

## 모드 선택

| 모드 | 기본/선택 | 실제 실행 경로 | 입력 |
|---|---|---|---|
| `standard` | 기본값 | 원래 TNO의 `qra.py` 그대로 실행 | 기존 template/run 명령과 sections/components/assemblies CSV |
| `lh2` | 명시 선택 | 새 LH2 빈도/설비경계/분산/피해 경로 | 범용 facility JSON, frequency plan, consequence request |

기존 TNO도 GH2/LH2 screening을 포함하므로 standard를 “액화수소를 전혀 계산하지 못하는 모드”로 해석하지 않는다. 새 `lh2`는 개발 중인 상세 연동 경로를 선택한다. 모드마다 현재 입력/지원 범위를 유지하며 CSV를 새 LH2 시설/포트 JSON으로 자동 변환하지 않는다.

원래 TNO의 실행 코드를 수정하지 않았다. 공통 launcher가 원래 TNO를 별도 interpreter에서 실행하며 TNO 소스 해시를 실행 전후 대조한다. 선택한 LH2 모드에서는 optional extension만 import한다. 확장이 없거나 실패하면 오류를 반환하고 standard로 조용히 전환하지 않는다.

## 사용자 실행

저장소 루트에서:

```powershell
python tno.py --describe-modes
python tno.py --mode standard --backend lh2-tno/results/20261008/mode_v050/standard_backend.json --help
python tno.py --mode lh2 lh2-tno/examples/lh2_frequency_facility.json --frequency-plan lh2-tno/examples/lh2_frequency_plan.json --output events.json
python tno.py --config lh2-tno/examples/tno_lh2_mode.json lh2-tno/examples/storage_terminal.json
```

패키지를 설치한 환경에서는 같은 명령을 `tno --mode ...`로 실행한다. 기존 `lh2-tno ...` 및 `python -m lh2_tno.cli ...` 호출도 유지한다.

설정은 `{{"mode":"lh2"}}` 또는 `{{"mode":"standard","backend":"backend.json"}}`이다. 설정 파일의 backend 상대경로는 설정 파일 위치에서 해석한다. CLI에서 명시한 mode/backend가 설정값보다 우선한다. standard 물리 계산은 legacy interpreter와 `tno` root/SHA-256 pin이 있는 backend 설정이 필요하다. 입력 예제와 raw 결과는 보통 로컬 산출물이므로 다른 PC에서는 명시 경로를 새로 설정한다.

std mode 출력 JSON에는 `execution_mode=standard`와 엔진 소스 해시를 추가한다. 기존 수치·모델/근거 정책은 그대로 둔다. LH2 CLI 출력에는 `execution_mode=lh2`를 기록한다. `--describe-modes`는 설치/물리 검증 완료를 주장하는 기능이 아니다.

## 검증

- **{count}개 검사 통과**. 새 모드 검사 18개 포함.
- standard mode로 실제 TNO template 생성 및 작은 합성 GH2 QRA를 실행했다. 단순 출력 stub 결과만으로 실제 엔진 실행을 주장하지 않는다. 실제 결과에 standard 모드 표기가 있고 legacy TNO의 소스 해시는 전후 일치했다.
- lh2 mode로 16개 문헌 빈도 사건을 생성했다.
- lh2 mode로 v0.4.0에서 기록한 실제 설비 출구 상태를 다시 분산·최종 피해에 전달했다. 소비자 물리 계산 약 **{verification['lh2_chain_elapsed_ms']/1000:.2f}초**. 설비 유량 재계산 없음.
- 이번 모드 시험은 기록된 provider 경계를 재생했다. 동시에 개발 중인 lh2dt의 현재 소스로 설비 계산을 다시 실행한 시험은 아니다. consumer-only 설정에는 실행하지 않는 lh2dt/pool을 pin하지 않고 원래 provider digest를 경계 기록에 보존했다.
- standard launcher 도움말은 `python -S`에서 실행해 LH2/Pydantic import 없이 동작하는 것을 확인했다. 실제 standard 물리는 기존 TNO 자체의 의존성을 필요로 한다.
- mode 오타·잘못된 설정·없어진 extension·엔진 해시 불일치·실행 중 소스 변화·시간 초과를 거절한다. fallback 없음. 기존 direct LH2 호출의 backward-compatible 입력도 검사를 통과했다.

## 코드 책임

`tno.py`는 저장소 진입점, `src/tno_host.py`는 stdlib-only 공통 mode dispatcher, `src/lh2_tno/cli.py`는 LH2 경로다. `pyproject.toml`에 `tno` console entrypoint와 host module을 포함했다. 외부 TNO/설비/SLAB 모델을 이 저장소에 복제하거나 원본 코드를 수정하지 않았다.

현재 배포 archive는 host와 LH2 extension을 함께 포함한다. runtime에서 LH2 경로를 선택적으로 로드하는 구조이며 두 개의 독립 PyPI 배포본으로 분리한 것은 아니다. 향후 기존 TNO UI가 있다면 같은 mode 옵션을 연결하면 된다. 현재 데스크톱 UI toggle을 구현했다고 주장하지 않는다.

## 남은 개발

LH2 전단 PH nozzle/flash, 액체/2상·수직/팽창 출구, 동적 leak feedback, 전체 LH2 사건의 기존 TNO 점화/차단/기상·IR/F-N 연결, 문헌 빈도 불확실성 분석과 물리 검증은 계속 개발한다. 모드 추가만으로 전체 시설 위험평가·현장 정확도·1 Hz 신규 물리 계산을 완료한 것은 아니다. 현장 사고빈도 수집은 개발/첫 논문의 필수 조건으로 두지 않는다.
'''
doc_path=ROOT/'docs/TNO_LH2_v050_옵셔널모드_개발기록_20261008.md'
doc_path.write_text(doc,encoding='utf-8')
readme_path=ROOT/'README.md';readme=readme_path.read_text(encoding='utf-8')
lead='''## v0.5.0 옵셔널 TNO LH2 모드

공통 실행기 `tno`/`python tno.py`에서 기본 `standard` 또는 명시한 `--mode lh2`를 선택한다. standard는 원래 TNO의 QRA를 실행하고 LH2는 새 연동 경로를 선택한다. 내부 코드는 분리하며 자동 fallback은 없다. 154개 검사와 두 모드의 실제 실행을 확인했다. [모드 사용·검증 기록](docs/TNO_LH2_v050_옵셔널모드_개발기록_20261008.md). 모드 선택이 전체 LH2 시설 QRA 완료를 뜻하지 않는다.

'''
if '## v0.5.0 옵셔널 TNO LH2 모드' not in readme:readme=readme.replace('# LH2-TNO\n\n','# LH2-TNO\n\n'+lead,1)
readme_path.write_text(readme,encoding='utf-8')
root_readme_path=ROOT.parent/'README.md';text=root_readme_path.read_text(encoding='utf-8')
if '## Optional execution modes' not in text:
    text+='''\n## Optional execution modes

Use `python tno.py --mode standard --backend backend.json <qra arguments>`
for the pinned original TNO engine, or `python tno.py --mode lh2 <facility.json>`
for the LH2 extension. Standard is the default; modes never silently fall back.
After installation, `tno --mode ...` provides the same launcher. Internal
providers stay separated, and each mode retains its current input and physics
limits. See [v0.5.0 mode record](lh2-tno/docs/TNO_LH2_v050_옵셔널모드_개발기록_20261008.md).
'''
root_readme_path.write_text(text,encoding='utf-8')
CODE=Path(r'C:\Users\lyul\Desktop\DocuData\TNO_위험분석모듈\TNO_SYSTEM\코드')
archive=CODE/'개발기록_20261008/TNO_LH2_v050';archive.mkdir(parents=True,exist_ok=True)
sources=[doc_path,status_path,OUT/'verification.json',OUT/'standard_result.json',OUT/'lh2_events.json',
         OUT/'lh2_result.json',OUT/'unit_tests.xml']
records=[]
for source in sources:
    target=archive/source.name;shutil.copyfile(source,target)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest==hashlib.sha256(target.read_bytes()).hexdigest()
    records.append({'source':str(source),'copy':target.name,'sha256':digest})
(archive/'manifest.json').write_text(json.dumps({'version':'0.5.0','mode_host_sha256':hashlib.sha256((ROOT/'src/tno_host.py').read_bytes()).hexdigest(),
    'source_root':str(ROOT/'src'),'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
entry=CODE/'00_개발현황_먼저읽기.md';text=entry.read_text(encoding='utf-8')
prefix='''## 최신 추가: v0.5.0 옵셔널 TNO LH2 모드

현재 권장 구조는 **하나의 TNO 실행기 + standard 기본/LH2 선택 모드 + 분리된 내부 모델**이다. 기존 TNO 소스는 그대로이고 mode launcher가 두 경로를 선택한다. 154개 검사와 실제 standard QRA/LH2 피해 경로 확인. 전체 LH2 시설 QRA의 완전 연결은 별도 개발 사항이다.

[v0.5.0 모드 사용/개발 기록](개발기록_20261008/TNO_LH2_v050/TNO_LH2_v050_옵셔널모드_개발기록_20261008.md) / [현재 상태](개발기록_20261008/TNO_LH2_v050/CURRENT_STATUS.json) / [실행 근거](개발기록_20261008/TNO_LH2_v050/verification.json).

'''
if '## 최신 추가: v0.5.0 옵셔널 TNO LH2 모드' not in text:text=text.replace('# TNO 개발 현황 — 먼저 읽기\n\n','# TNO 개발 현황 — 먼저 읽기\n\n'+prefix,1)
entry.write_text(text,encoding='utf-8')
(ROOT/'src/lh2_tno/개발기록_안내.md').write_text(f'# 개발 기록 안내\n\n최신 구조는 v0.5.0의 옵셔널 TNO LH2 모드다. [모드 개발 기록](<{doc_path.as_posix()}>) / [TNO 코드 옆 전체 안내](<{entry.as_posix()}>). 내부 계산 모듈은 분리하고 공통 진입점에서 선택한다.\n',encoding='utf-8')
print(json.dumps({'version':'0.5.0','tests':count,'record':str(doc_path),'archive':str(archive),'hashes_verified':True},ensure_ascii=False))
