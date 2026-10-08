"""Place a reviewable development handoff beside the existing TNO code."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[1]
if json.loads((ROOT/'CURRENT_STATUS.json').read_text(encoding='utf-8'))['package_version'] != '0.2.0':
    raise RuntimeError('This packages the historical v0.2.0 handoff only. For v0.3.0 use write_frequency_release_record.py; preserve the original archive.')
CODE=Path(r'C:\Users\lyul\Desktop\DocuData\TNO_위험분석모듈\TNO_SYSTEM\코드').resolve()
ARCHIVE=(CODE/'개발기록_20261008').resolve()
assert ARCHIVE.is_relative_to(CODE)
ARCHIVE.mkdir(exist_ok=True)

mapping={
 'docs/TNO_위험성평가_구축기능_상세목록_20261008.md':'01_TNO_구축기능_66항목.md',
 'docs/방출부터_최종피해_연결완료_20261008.md':'02_LH2_방출부터_최종피해_연결.md',
 'docs/별도설비모델과_액화수소유닛_결합검토_20261008.md':'03_별도_설비디지털트윈_결합검토.md',
 'docs/IJHE_연구프로토콜.md':'04_IJHE_연구와_검증계획.md',
 'docs/개발진행_20261008.md':'05_개발진행_기록.md',
 'CURRENT_STATUS.json':'현재상태.json',
 'results/20261008/tno_function_inventory/function_matrix.json':'기능목록.json',
 'results/20261008/tno_function_inventory/function_matrix.csv':'기능목록.csv',
 'results/20261008/tno_function_inventory/frequency_library.json':'기존_빈도라이브러리_점검.json',
 'results/20261008/tno_function_inventory/actual_frequency_enumeration.json':'실행증거_기존_자동빈도생성.json',
 'results/20261008/full_chain/verification.json':'실행증거_LH2_전체연결.json',
 'results/20261008/full_chain/edgecase_verification.json':'실행증거_LH2_경계조건_센서_캐시.json',
 'results/20261008/full_chain/gas_release_summary.json':'실행요약_기체방출.json',
 'results/20261008/full_chain/rainout_pool_summary.json':'실행요약_지면도달_풀증발.json',
 'results/20261008/full_chain/backend_config.json':'실행환경_모델버전_고정값.json',
 'results/20261008/equipment_coupling_review/coupling_review_verdict.json':'설비결합_검토판정.json',
 'results/20261008/equipment_coupling_review/package_manifest_verification.json':'설비_전달패키지_무결성.json',
 'results/20261008/equipment_coupling_review/actual_tank_boundary_probe.json':'실행증거_설비탱크_PH_PT_경계.json',
 'results/20261008/equipment_coupling_review/actual_network_outlet_probe.json':'실행증거_설비네트워크_출구.json',
}
records=[]
for relative,name in mapping.items():
    source=ROOT/relative;target=ARCHIVE/name
    if not source.is_file():raise FileNotFoundError(source)
    shutil.copyfile(source,target)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
    records.append({'source':str(source.resolve()),'copy':name,'sha256':digest,'bytes':target.stat().st_size})

backlog=[
 {'id':'P01','priority':'P0','task':'TNO Purple Book Chapter 3 LOC/빈도 기본선 완전 구현',
  'details':'용기·대기압 탱크·배관·펌프·열교환기·압력방출장치의 원문 정의/조건/단위/포함 범위. 수소 문헌 대안과 별도 선택; 서로 다른 LOC를 임의 5bin에 배분하지 않음.',
  'done':False},
 {'id':'P02','priority':'P0','task':'기존 빈도·사건생성기를 새 LH2 경로에 연결',
  'details':'고장 부품과 상류 source 설비 구분, 누출 크기와 위치, count/배관 길이/노출 단위, 출처·등급 전달.',
  'done':False},
 {'id':'P03','priority':'P0','task':'기존 점화·차단·기상·IR/F-N 엔진 재사용',
  'details':'Purple 정책 기본선, 점화원 기반 방식, 차단 성공/실패, 기상/인구 분할, 관측된 누출의 조건부 피해와 연간 위험 구분.',
  'done':False},
 {'id':'P04','priority':'P0','task':'별도 lh2dt 설비 경계 결합',
  'details':'P,h·상/셀·재고·시계·물성 기준. 이미 계산한 유량은 재계산하지 않음. leak-edge 질량/엔탈피 피드백, 수직 벤트, ParaHydrogen 경로.',
  'done':False},
 {'id':'P05','priority':'P1','task':'LH2 source-to-cloud 물리 전달 고도화',
  'details':'분포된 액적 증발 위치/시간, 수직 운동량, 이동 deposition, packet 공기/압력/온도 재평형, 화재→풀 열피드백.',
  'done':False},
 {'id':'P06','priority':'P1','task':'독립 실증·근거 gate·처리시간 검증',
  'details':'실측 출처·압력/온도 센서 위치·원계측 품질 확인. source/농도/복사/피해/위험 근거를 구분. 1 Hz 신규 계산과 캐시 조회를 구분.',
  'done':False},
 {'id':'P07','priority':'P2','task':'나머지 미지원 현상과 통계 기능',
  'details':'실내/수직 전용 full-chain, DDT/벤트 내부 반응유동, 진공외피 취성파괴·확률 도미노, 냉화상·질식, 센서 고장빈도 posterior 등은 별도 개발/검증.',
  'done':False},
]
(ARCHIVE/'후속개발_우선순위.json').write_text(json.dumps({'date_kst':'2026-10-08','items':backlog},ensure_ascii=False,indent=2),encoding='utf-8')

body=f'''# TNO 개발 현황 — 먼저 읽기

정리 기준일: 2026-10-08 KST. 이 파일은 코드 옆에 둔 개발 인수인계 진입점이다. 실행 코드와 과거 VERIFICATION.md의 검증 기록을 대체하지 않는다.

## 현재 상태

1. **기존 TNO 엔진:** 문헌 빈도 자동 조회, 부품 수량 반영, 사고 생성, 차단/점화 분기, 피해 모델, 기상 적분 개인위험 IR, 사회적 위험 F-N, 출력과 근거 관리가 존재한다.
2. **새 LH2 유닛 v0.2.0:** 방출→지면 도달/풀 증발→극저온 전이→SLAB 분산→화재/폭발→인명 피해→조건부 위험의 진단 계산을 실제 실행했다.
3. **아직 미연결:** 기존 빈도/사건생성/점화정책/차단/전시설 기상 적분/F-N과 새 LH2 유닛의 완전한 결합.
4. **TNO 북 기준 미완료:** Purple Book Chapter 3의 전체 LOC/빈도 기본선. 현재 빈도 library는 Sandia GH2 9종, Brooks LH2 6종, 미확인 pump proxy 1종이다.
5. **별도 설비 디지털트윈:** “액화수소검사지원센터 모델링” 프로젝트, “액화수소 설비 디지털 트윈 모델링#2” 세션의 lh2dt를 설비 상태 계산의 기준으로 사용한다. 결합 가능한 구조와 경계 추출을 확인했지만 실제 전체 결합은 미완료다.
6. **검증 상태:** 합성/진단 계산과 코드 검사가 통과했다. 현장 절대위험 검증과 매초 신규 물리 계산은 미완료다. 새 계산은 기체 약 3초, 풀 포함 약 7–10초; 동일 입력 캐시 조회 약 20–40 ms였다.

“빈도는 전부 외부 입력”은 새 wrapper에만 해당했던 설명이다. 기존 TNO 전체에 빈도 기능이 없다는 설명으로 사용하지 않는다. 또 “방출부터 피해까지 연결 완료”를 전체 설비 디지털트윈/모든 TNO QRA 기능/현장 검증 완료로 확대하지 않는다.

## 필요할 때 확인할 파일

| 확인 목적 | 이 폴더에 저장한 자료 |
|---|---|
| 기능별 구현·근거·코드 위치·새 경로 연결 여부 | [01 — 구축 기능 66항목](개발기록_20261008/01_TNO_구축기능_66항목.md) |
| LH2 전체 계산과 적용범위 | [02 — 방출부터 최종 피해](개발기록_20261008/02_LH2_방출부터_최종피해_연결.md) |
| 별도 설비 모델과의 결합 | [03 — 설비 디지털트윈 결합 검토](개발기록_20261008/03_별도_설비디지털트윈_결합검토.md) |
| IJHE 연구 범위·비교군·독립 검증 | [04 — 연구/검증 계획](개발기록_20261008/04_IJHE_연구와_검증계획.md) |
| 초기 구현부터의 진행 기록 | [05 — 개발 기록](개발기록_20261008/05_개발진행_기록.md) |
| 기계가 읽을 현재 상태 | [현재상태.json](개발기록_20261008/현재상태.json) |
| 바로 이어서 개발할 항목 | [후속개발 우선순위](개발기록_20261008/후속개발_우선순위.json) |
| 입력·시험·실행 결과 | 같은 개발기록 폴더의 실행증거/실행요약 JSON |
| 보관본과 원본의 해시·위치 | [보관 manifest](개발기록_20261008/manifest.json) |

## 코드 정본 위치

| 역할 | 위치 |
|---|---|
| 기존 TNO QRA 엔진 | 이 파일이 있는 `코드` 폴더 |
| 새 범용 LH2 패키지 | [lh2-tno README](<{(ROOT/'README.md').as_posix()}>) |
| 새 LH2 입력 계약 | [consequences.py](<{(ROOT/'src/lh2_tno/consequences.py').as_posix()}>) |
| 새 LH2 물리 계산 연결 | [chain_worker.py](<{(ROOT/'src/lh2_tno/chain_worker.py').as_posix()}>) |
| 센서 상태 갱신·정확 일치 캐시 | [service.py](<{(ROOT/'src/lh2_tno/service.py').as_posix()}>) |
| 외부 모델 버전 고정·격리 실행 | [backend.py](<{(ROOT/'src/lh2_tno/backend.py').as_posix()}>) |
| 별도 설비 모델 | `C:/Users/lyul/Desktop/DocuData/액화수소 저장탱크_밴트 시스템/06_액화수소_디지털트윈_물리모델/src/lh2dt` |
| SLABx-LH2 | `C:/Users/lyul/Desktop/DocuData/SLABx_LH2/slabx-lh2/source/slabx-lh2/slabx_lh2` |

새 코드는 링크한 lh2-tno 위치가 정본이다. 이 개발기록 폴더는 문서·상태·검증 증거의 보관본이며 실행 코드 복제본이 아니다. 외부 설비 모델의 개발을 여기서 중복 수행하지 않는다.

## 기존 TNO에서 바로 찾아볼 코드

- 빈도·부품 분류·조립·사고 생성: `taxonomy.py`의 `resolve_frequency`, `enumerate_scenarios`.
- 전체 위험 계산: `pipeline.py`의 `run`; 위험 적분/IR 격자/F-N은 `risk.py`.
- 차단/점화: `blocking.py`, `ignition.py`, `ignition_sources.py`.
- source/과도: `source_term.py`, `transient.py`.
- 분산·화재·폭발·피해: `gh2_jet.py`, `slabx_adapter.py`, `fire.py`, `spill_fire.py`, `blast.py`, `damage.py` 등.
- 설비 노출/확대·판정·근거: `equipment_damage.py`, `decision.py`, `gating.py`, `physics_assurance.py`, `evidence_registry.py`.
- 입력/출력/CLI: `siteio.py`, `export.py`, `qra.py`.

## 재실행

기존 엔진의 공식 시험 수집 목록은 상위 TNO_SYSTEM/pytest.ini를 따른다. 오래된 수동 `test_ignition.py`는 현재 PURPLE_SOURCES의 필수 입력과 맞지 않으며 공식 수집 목록에 포함돼 있지 않다.

새 패키지 폴더에서 다음을 실행한다. 외부 모델 interpreter와 고정 hash는 `results/20261008/full_chain/backend_config.json`에 있다.

```powershell
python -m pytest -q
python -B -X utf8 scripts/validate_chain.py
python -B -X utf8 scripts/validate_chain_edgecases.py
```

현재 확인한 신규 단위/계약/보존 검사는 68개, 실제 backend 경계조건 검사는 7개다. 기존 TNO 선택 회귀 묶음 44/101/70개는 중복이 있어 합산 고유 시험 수로 사용하지 않는다. 이번 정리는 시험의 재실행을 뜻하지 않으며, 기존 결과를 보관한 것이다.

## 이어서 개발할 순서

1. TNO Purple LOC 기본선과 수소 문헌 대안을 분리해서 구현.
2. 기존 빈도/사건 생성기를 실제 고장 부품과 새 LH2 source에 연결.
3. 기존 점화·차단·기상·인구·IR/F-N 재사용.
4. 별도 설비 모델의 P,h·상/셀·물성·시계·재고·기계산 유량과 결합. 탱크나 방출량 이중 계산 금지.
5. 액적/구름/복사/폭발의 물리 전달과 근거 고도화.
6. 독립 실증과 신규 계산 처리시간 검증.

센서가 이미 누출을 확인한 경우에는 개시 빈도를 다시 곱하지 않는다. 정상 벤트, 사고 누출, PSV 사건, 고장시 요구불응확률은 서로 다른 값으로 관리한다. 설계·합성·복원·예측·원계측을 구분하고 센터 태그나 용량을 범용 기본값으로 승격하지 않는다.

## 갱신 방법

이 문서는 2026-10-08의 보관 기록이다. 후속 개발에서는 구현/실행/현장 검증 상태, source revision, 검사 날짜와 증거를 함께 갱신한다. 과거 수치·계산 설정을 새 검증값으로 재표시하지 않는다. 저장한 manifest로 보관본 무결성을 확인할 수 있다.
'''
(CODE/'00_개발현황_먼저읽기.md').write_text(body,encoding='utf-8')
(ARCHIVE/'00_안내.md').write_text('# 개발기록 안내\n\n상위 코드 폴더의 [00_개발현황_먼저읽기.md](../00_개발현황_먼저읽기.md)부터 확인한다. 이 폴더는 2026-10-08 개발 내용과 검증 증거의 보관본이다.\n',encoding='utf-8')

all_files=[]
for path in sorted(ARCHIVE.iterdir()):
    if path.is_file() and path.name!='manifest.json':
        all_files.append({'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
manifest={'date_kst':'2026-10-08','prepared_at_kst':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
    'scope':'development documentation and evidence archive; no executable model changes',
    'code_directory':str(CODE),'new_lh2_code_authority':str(ROOT),
    'index':{'path':'../00_개발현황_먼저읽기.md','sha256':hashlib.sha256((CODE/'00_개발현황_먼저읽기.md').read_bytes()).hexdigest()},
    'source_copies':records,'archive_files':all_files}
(ARCHIVE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

# Put an entry point beside the new Python files as well, without duplicating code.
pointer=ROOT/'src/lh2_tno/개발기록_안내.md'
pointer.write_text(f'# 개발기록 안내\n\n현재 개발 인수인계는 기존 TNO 코드 폴더의 [00_개발현황_먼저읽기.md](<{(CODE/"00_개발현황_먼저읽기.md").as_posix()}>)에 정리했다. 새 LH2 패키지의 정본은 이 src/lh2_tno 폴더다.\n',encoding='utf-8')

for record in all_files:
    assert hashlib.sha256((ARCHIVE/record['path']).read_bytes()).hexdigest()==record['sha256']
print(json.dumps({'index':str(CODE/'00_개발현황_먼저읽기.md'),'archive':str(ARCHIVE),
    'archive_file_count_including_manifest':len(all_files)+1,'copied_source_files':len(records),
    'archive_hashes_verified':True,'new_code_pointer':str(pointer)},ensure_ascii=False,indent=2))
