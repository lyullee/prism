"""Record tested resolved-equipment coupling without modifying old evidence."""
from pathlib import Path
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import sys
ROOT=Path(__file__).resolve().parents[1]
if json.loads((ROOT/'CURRENT_STATUS.json').read_text(encoding='utf-8'))['package_version']!='0.4.0':
    raise RuntimeError('Historical v0.4.0 record: use the current version record script instead.')
sys.path.insert(0,str(ROOT/'src'))
from lh2_tno.backend import tree_digest
OUT=ROOT/'results/20261008/equipment_coupling_v040'
result=json.loads((OUT/'actual_equipment_to_harm.json').read_text(encoding='utf-8'))
assert result['adapter_source_digest']==tree_digest(ROOT/'src/lh2_tno'),'new run required after source change'
verification=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
suites=ET.parse(OUT/'unit_tests.xml').getroot().findall('.//testsuite')
count=sum(int(s.get('tests','0')) for s in suites)
assert count==136 and all(int(s.get('failures','0'))==int(s.get('errors','0'))==0 for s in suites)
verification.update(unit_tests_passed=count,adapter_source_digest=result['adapter_source_digest'])
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
status_file=ROOT/'CURRENT_STATUS.json'
status=json.loads(status_file.read_text(encoding='utf-8'))
status.update(package_version='0.4.0',unit_contract_conservation_tests_passed=count,
    github_repository='https://github.com/lyullee/tno-lh2',github_repository_private=True,
    github_main_baseline='v0.3.0',github_development_branch='codex/tno-lh2-development',
    module_structure='separate integration package/add-on to legacy TNO and external LH2 providers',
    equipment_resolved_atmospheric_gas_source_supported=True,
    equipment_PH_to_gas_exit_checked=True,equipment_flow_recalculation_in_resolved_path=False,
    equipment_resolved_exit_to_final_harm_actual_execution=True,
    equipment_provider_clock_and_mass_static_enthalpy_ledger_checked=True,
    equipment_normal_vent_excluded_from_random_leak_frequency=True,
    equipment_upstream_service_frequency_compatibility_checked=True,
    actual_equipment_coupling_scope='Native VentStack/SteadyNetwork: two prescribed synthetic steady PH states, 0.37 s closure, horizontal atmospheric gas exit Mach<=0.3; no tank feedback or field calibration.',
    current_scope='Outdoor diagnostic integrated source chain plus resolved horizontal atmospheric low-Mach gas exits; frequency catalogue and single matched accident binding; full facility annual QRA and twin feedback remain incomplete.',
    equipment_coupling_record='docs/TNO_LH2_v040_설비경계연결_개발기록_20261008.md',
    equipment_coupling_results='results/20261008/equipment_coupling_v040')
status['unsupported']=list(dict.fromkeys(status['unsupported']+[
    'resolved_liquid_or_two_phase_exit','underexpanded_or_high_Mach_resolved_exit',
    'PH_upstream_nozzle_discharge_for_saturated_liquid','bidirectional_dynamic_leak_inventory_energy_feedback']))
status_file.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')

doc=f'''# TNO-LH2 v0.4.0 — 설비 경계에서 최종 피해까지 연결

2026-10-08. 실제 실행 근거를 포함한 연구 개발 기록. v0.3.0은 GitHub `main`에 보관했고 v0.4.0은 `codex/tno-lh2-development`에서 이어서 개발한다.

## 현재 구조

**TNO-LH2는 기존 TNO에 연결하는 별도 패키지/애드온**이다. 기존 TNO, lh2dt 공정 모델, SLABx-LH2/SLABx, 풀 모델의 계산 책임과 소스 버전을 나눠 관리한다. 사용자에게는 통합 계산 시스템을 제공하되 기존 TNO 코드에 모든 공급자 모델을 복제하지 않는다. 명칭 LH2는 액화수소이며 LN2는 액체질소다.

GitHub 저장소: https://github.com/lyullee/tno-lh2 (private). 업로드 범위는 연동 코드·표 snapshot·합성 예제·시험·문서다. 책 PDF, 센터 원계측/학습 파일, 외부 모델 소스, 원고 작업 파일은 제외했다. 기존 TNO 코드 폴더에는 문서/검증 보관본과 안내를 둔다.

## 이번에 구현한 것

1. `ResolvedGasRelease`가 실제 설비/포트 ID, 사건 종류, 상류 유체 서비스, 물성 기준, P,h·온도·밀도, 유량·면적·속도, 시간/종료와 누적 질량·정적 엔탈피를 받는다. 상태/유량 소유자는 설비 모델로 고정한다.
2. `ConsequenceRequest`는 기존 통합 source와 설비가 이미 계산한 source 중 하나만 선택한다. 두 모델을 동시에 호출하지 않는다. 탱크 전용 검사는 기존 경로에만 적용하고 새 경로는 실제 outward gas port를 확인한다.
3. worker가 P,h로 상태를 복원해 제공된 온도·밀도와 대조한다. 포화 P,T에 온도 offset을 주지 않는다. 다만 이 새 경로는 기체 출구만 허용하므로 액체/2상은 따로 거절한다.
4. 설비 유량을 그대로 받아 시간 구간·질량을 SLABx-LH2/SLABx와 화재·폭발·TNO 인명 피해에 전달한다. 설비가 제공한 기체 온도를 20 K 포화온도나 288 K 대기온도로 바꾸지 않는다.
5. 정상 벤트에 무작위 사고 빈도를 붙이지 않는다. 이미 계산된 유량을 raw P,T 태그로 덮어쓰는 것도 거절한다. 사고 빈도 연결에서는 failure opening과 expanded exit area를 구분하고, GH2/cold-GH2 설비에 LH2 문헌 빈도를 무조건 적용하지 않는다.
6. `equipment_network_exit`는 실제 lh2dt의 `VentStack`/`SteadyNetwork`를 PH 경계로 실행하여 link 유량·전달 엔탈피·실제 출구 상태를 내보낸다. 전체 설비 종류를 새로 구현한 exporter는 아니다.

## 실제 실행과 검사

- 단위/계약/회귀 검사 **{count}개 통과**. 이 중 새 설비 경계 검사는 36개다.
- 실제 ParaHydrogen 설비 모델을 두 조건의 합성 PH 경계에서 실행했다. 공급자 스냅샷 해시는 실행 전후 일치했다.
- 출구 면적은 명시한 Stack bore이고 속도는 native 유량·밀도·면적에서 연속식으로 산출했다. 측정된 출구 속도로 표시하지 않는다.
- 두 상태를 0–0.2초, 0.2–0.37초에 유지한 뒤 종료했다. **방출질량 {verification['provider_mass_kg']:.12g} kg**, 정적 엔탈피 수송 {verification['static_enthalpy_transport_j']:.6g} J를 보존했다.
- 실제 설비 출력→SLAB→화재/폭발→수용점 피해 계산 약 **{verification['elapsed_ms']/1000:.2f}초**. 유량 재계산·내부 탱크 전진 계산 없음. 동일 시계에 명시한 종료를 반영하고 전체 수소 질량 장부를 확인했다.
- 첫 진입 온도가 100 K 이상인 실제 설비 출력 온도를 유지한 것을 확인했다. 정상 벤트 사례의 연간 사고 위험 기여는 `None`이다.
- 앞선 400 kPa/150 K 전단의 큰 유량을 같은 대기압 bore에 붙이는 가정은 새 low-Mach 경계에서 거절했다. 해당 source plane의 추가 팽창/압축성 처리를 생략해 받아들이지 않는다.
- 기존 integrated-source 기체와 rainout/풀 사례도 이 개발 단계에서 다시 실행하여 이전 질량 장부와 수용점 피해를 재현했다. 별도의 `regression_verification.json`에 해당 실행 버전/결과를 보관했다.

## 적용 범위와 미완료

**새 resolved 경로는 수평·대기압·순수 기체·Mach≤0.3 출구로 제한한다.** vertical nozzle, liquid/two-phase, underexpanded/high-Mach source는 지원하지 않는다. 현재 사례는 두 native 정상상태 계산을 시간 구간별로 명시한 합성 입력이다. 전체 시설의 동적 누출과 압력/재고 피드백을 풀었다는 뜻이 아니다. 0.37초 종료도 선언한 진단 경계이며 실제 차단 성공률/동역학 검증은 아니다.

정적 엔탈피 수송과 별도 운동에너지를 기록한다. 공급자 모델과 외부 구름 사이의 총 에너지/운동량 폐합은 아직 승인하지 않았다. 상류 LH2 포트의 P,h 기반 HEM/HNEM source, 액적/flash, 양단 파열, 수직 벤트, 동적 leak edge 질량/에너지 피드백과 전체 시설 IR/F-N은 후속 구현이다. 이 기록으로 물리 검증·현장 사고빈도·1 Hz 신규 계산을 승격하지 않는다.

## 코드·재현

| 파일 | 역할 |
|---|---|
| `src/lh2_tno/equipment_boundary.py` | frozen provider 계약, 연속식·시계·누적 질량/엔탈피 검사 |
| `src/lh2_tno/resolved_gas_worker.py` | worker 독립 PH/EOS·기체·대기압·Mach 경계 검사 |
| `src/lh2_tno/consequences.py` | source owner 선택, 실제 gas port·상류 서비스/빈도 확인 |
| `src/lh2_tno/chain_worker.py` | 이미 계산된 유량/온도 보존 → 기존 분산/피해 경로 |
| `src/lh2_tno/worker.py` | 실제 lh2dt native network export |
| `tests/test_equipment_boundary.py` | 합성 6종 설비 port preflight, 잘못된 소유권/상/단위/빈도 거절 |
| `scripts/validate_equipment_coupling.py` | 외부 설비→최종 피해 실제 실행 및 고압 plane 거절 |
| `scripts/validate_v040_regression.py` | 기존 기체/풀 계산 재현 |

```powershell
python -m pytest -q --junitxml=results/20261008/equipment_coupling_v040/unit_tests.xml
python -X utf8 scripts/validate_equipment_coupling.py
python -X utf8 scripts/validate_v040_regression.py
python -X utf8 scripts/record_v040.py
```

외부 실행은 명시한 로컬 경로와 interpreter/버전/해시 설정을 필요로 한다. 일반 GitHub 검사는 합성 입력으로 실행하며 공급자 패키지나 센터 자료를 필요로 하지 않는다. 원격 CI 결과와 로컬 물리 실행은 별도 근거다.

## 다음 순서

1. LH2 전단 P,h/상·셀 경계 → 실제 누출 nozzle/flash 계산을 한 번만 수행하는 경로.
2. 액체/2상과 수직/팽창 출구, 주요 LOC 및 leak feedback 시계/질량/에너지.
3. 기존 TNO 점화·차단·기상·IR/F-N을 새 사건 포트폴리오에 연결.
4. 문헌 빈도 불확실성에 따른 설비 기여도·우선순위 안정성 분석.
5. 확보된 물리 실증 검증 및 처리시간 평가. 현장 사고빈도 수집은 개발/첫 논문의 필수 조건이 아니다.
'''
doc_file=ROOT/'docs/TNO_LH2_v040_설비경계연결_개발기록_20261008.md'
doc_file.write_text(doc,encoding='utf-8')
readme=ROOT/'README.md'
text=readme.read_text(encoding='utf-8')
lead='''## v0.4.0 설비 경계 연결

설비 모델이 이미 계산한 유량과 PH 기체 출구를 받아 다시 source를 풀지 않고 최종 피해까지 연결한다. 실제 native VentStack/SteadyNetwork 사례를 실행했고 **136개 검사 통과**. 현재는 수평·대기압·Mach≤0.3 기체와 명시 시계로 제한하며 전체 시설 동적 피드백은 미완료다. [개발 기록과 적용 범위](docs/TNO_LH2_v040_설비경계연결_개발기록_20261008.md).

'''
if '## v0.4.0 설비 경계 연결' not in text:text=text.replace('# LH2-TNO\n\n','# LH2-TNO\n\n'+lead,1)
text=text.replace('현재 전체 설비 디지털트윈을 TNO 경로에 결합한 상태는 아니다. 실제 탱크/네트워크 경계 추출은 재현했으며, P,h 입력·resolved 유량·수직 벤트·물성 기준 연결 등이 필요하다.',
    '현재 전체 설비 디지털트윈의 동적 누출 피드백을 결합한 상태는 아니다. v0.4.0은 실제 네트워크의 resolved atmospheric gas 출구를 최종 피해에 연결했다. 전단 LH2 P,h source·액체/2상·수직 벤트·전체 feedback은 추가 구현이 필요하다.')
readme.write_text(text,encoding='utf-8')
root_readme=ROOT.parent/'README.md'
text=root_readme.read_text(encoding='utf-8')
text=text.replace('Version 0.3.0 demonstrates one matching tank-hole event\'s automatically\ngenerated frequency connected to the diagnostic source-to-harm chain.',
    'Version 0.4.0 also connects native equipment-resolved horizontal atmospheric\nlow-Mach gas exits to dispersion and harm without recalculating discharge.\nThe v0.3.0 tank-hole frequency baseline is preserved on the initial main commit.')
root_readme.write_text(text,encoding='utf-8')

CODE=ROOT/'docs'
archive=CODE/'개발기록_20261008/PRISM_LH2_v040'
archive.mkdir(parents=True,exist_ok=True)
sources=[doc_file,status_file,OUT/'verification.json',OUT/'regression_verification.json',OUT/'actual_equipment_to_harm.json',
    OUT/'resolved_release.json',OUT/'high_pressure_plane_gate.json',OUT/'unit_tests.xml']
records=[]
for source in sources:
    target=archive/source.name;shutil.copyfile(source,target)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest==hashlib.sha256(target.read_bytes()).hexdigest()
    records.append({'source':str(source),'copy':target.name,'sha256':digest})
(archive/'manifest.json').write_text(json.dumps({'version':'0.4.0','code_root':str(ROOT/'src/lh2_tno'),
    'adapter_source_digest':result['adapter_source_digest'],'copies':records},ensure_ascii=False,indent=2),encoding='utf-8')
entry=CODE/'00_개발현황_먼저읽기.md'
text=entry.read_text(encoding='utf-8')
prefix='''## 최신 추가: TNO-LH2 v0.4.0 설비 경계

실제 설비 native network의 이미 계산된 PH 기체 출구·유량을 SLAB→최종 피해에 연결했다. 136개 검사 통과, 0.37초 종료/질량/정적 엔탈피 보존, 정상 벤트와 사고빈도 구분. **수평·대기압·low-Mach 기체이며 전체 동적 시설/수직 벤트/액체 source는 미완료**다.

[v0.4.0 개발 기록](개발기록_20261008/TNO_LH2_v040/TNO_LH2_v040_설비경계연결_개발기록_20261008.md) / [현재 상태](개발기록_20261008/TNO_LH2_v040/CURRENT_STATUS.json) / [실행 증거](개발기록_20261008/TNO_LH2_v040/verification.json). GitHub private 저장소는 https://github.com/lyullee/tno-lh2 이며 기존 TNO에 붙이는 별도 패키지다. 아래 v0.3/v0.2 자료는 이전 구현 기록이다.

'''
if '## 최신 추가: TNO-LH2 v0.4.0 설비 경계' not in text:text=text.replace('# TNO 개발 현황 — 먼저 읽기\n\n','# TNO 개발 현황 — 먼저 읽기\n\n'+prefix,1)
entry.write_text(text,encoding='utf-8')
(ROOT/'src/lh2_tno/개발기록_안내.md').write_text(f'# 개발 기록 안내\n\n최신 구현은 v0.4.0이다. [설비 경계 개발 기록](<{doc_file.as_posix()}>)과 [TNO 코드 옆 전체 안내](<{entry.as_posix()}>)를 확인한다. 이 폴더가 연동 코드 정본이며 기록 폴더는 문서/증거 보관본이다.\n',encoding='utf-8')
print(json.dumps({'version':'0.4.0','tests':count,'record':str(doc_file),'code_side_archive':str(archive),'hashes_verified':True},ensure_ascii=False))
