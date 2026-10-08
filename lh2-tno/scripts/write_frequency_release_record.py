"""Record v0.3.0 implementation/evidence beside its authoritative code."""
from pathlib import Path
import hashlib
import json
import re
import shutil
ROOT=Path(__file__).resolve().parents[1]
if json.loads((ROOT/'CURRENT_STATUS.json').read_text(encoding='utf-8'))['package_version'] != '0.3.0':
    raise RuntimeError('This refreshes the v0.3.0 frequency record only. Preserve later release status and use its matching record script.')
OUT=ROOT/'results/20261008/frequency_v030'
verification=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
cli=json.loads((OUT/'cli_actual_g3_chain.json').read_text(encoding='utf-8'))
assert cli['frequency_event']['annual_frequency_per_year']==1e-5
assert cli['data']['full_chain_executed']
assert cli['release_termination']['basis']=='synthetic_diagnostic_horizon'
cli_events=json.loads((OUT/'cli_generic_events.json').read_text(encoding='utf-8'))
assert len(cli_events['events'])==16
verification.update(unit_tests_passed=100,unit_tests_elapsed_s=.75,
    cli_event_generation_verified=True,cli_actual_chain_verified=True,
    cli_actual_chain_elapsed_ms=cli['elapsed_ms'])
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')

data_root=Path(r'C:\Users\lyul\Desktop\DocuData\액화수소검사지원센터 데이터')
data_files=[str(p.relative_to(data_root)) for p in data_root.rglob('*') if p.is_file()]
experience=dict(review='file inventory only; not a full audit of workbook contents',
    files=data_files,confirmed_leak_register_identified=False,
    component_year_or_metre_year_exposure_identified=False,
    field_frequency_update_applied=False,
    reason='인수/저장벤트/공급 시나리오·예측/원본 학습 자료는 확인했지만, 누출사건 대장과 설비별 관찰노출 장부는 파일목록에서 확인하지 못함. 내용에 없다고 단정하지 않음.')
(OUT/'field_experience_availability.json').write_text(json.dumps(experience,ensure_ascii=False,indent=2),encoding='utf-8')

status_path=ROOT/'CURRENT_STATUS.json'
status=json.loads(status_path.read_text(encoding='utf-8'))
status.update(package_version='0.3.0',unit_contract_conservation_tests_passed=100,
    field_frequency_data_availability='unavailable_user_confirmed',
    field_frequency_data_required_for_development=False,
    field_frequency_data_required_for_first_manuscript=False,
    default_frequency_research_mode='literature-based baseline and uncertainty/sensitivity assessment',
    field_frequency_update_role='optional future extension, inactive without confirmed events and exposure',
    frequency_catalogue_profiles=17,frequency_catalogue_event_rows=55,
    new_lh2_path_reviewed_frequency_catalogue_implemented=True,
    new_lh2_path_single_tank_hole_event_binding_implemented=True,
    new_lh2_path_automatic_frequency_to_actual_chain_demonstrated=True,
    new_lh2_path_legacy_frequency_and_event_generator_connected=False,
    frequency_catalogue_uses_reviewed_legacy_lh2_table_snapshot=True,
    complete_tno_purple_chapter3_loc_baseline_implemented=False,
    frequency_field_update_contract_implemented=True,frequency_field_update_applied=False,
    frequency_field_validation=False,frequency_record='docs/TNO_LH2_v030_빈도모듈_개발기록_20261008.md',
    frequency_results='results/20261008/frequency_v030',
    total_facility_annual_risk_complete=False,
    automated_event_generation_scope='Reviewed 17 profiles; explicit inventory ownership/length/count and applicability. No implicit proxies.',
    current_scope='Outdoor diagnostic chain plus reviewed frequency catalogue; one matching tank-hole event may be bound. Full event portfolio/facility twin and field-qualified risk remain incomplete.')
status['unsupported']=[x for x in status['unsupported'] if x!='sensor_inverse_leak_size_or_learned_frequency']
status['unsupported']+=['sensor_inverse_leak_size_or_automatic_alarm_to_frequency',
    'instantaneous_inventory_consequences_in_new_chain','600s_inventory_release_in_new_chain',
    'two_sided_pipe_rupture_in_new_chain','atmospheric_storage_frequency_profile',
    'vacuum_loss_initiation_frequency','normal_vent_demand_frequency']
status['unsupported']=list(dict.fromkeys(status['unsupported']))
status_path.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')

doc=f'''# TNO-LH2 v0.3.0 — 빈도 모듈 개발 기록

기준일 2026-10-08. **빈도 자체를 외부에서 매번 입력하던 새 LH2 경로에, 설비 목록에서 사고와 빈도를 생성하는 기능을 추가했다.** 전체 시설 QRA 완료 판정은 아니다.

## 아주 쉽게 설명하면

공정 모델은 “지금 탱크 안에 얼마나 있고, 압력·온도는 얼마인가?”를 계산한다. SLABx-LH2는 “수소가 나오면 어디로 퍼지는가?”를 계산한다. 이번 빈도 모듈은 “어떤 부품에서 어떤 크기의 사고가 1년에 얼마나 생길 것으로 보는가?”를 계산한다. 세 역할이 다르다.

예를 들어 밸브 4개의 한 누출 구간 빈도가 각각 2.2×10⁻⁵/년이면 그 그룹의 개시 빈도는 8.8×10⁻⁵/년이다. 배관은 개수 대신 길이를 사용한다. **작은 연간 빈도는 누출이 이미 확인된 현장의 피해를 작게 만드는 할인율이 아니다.** 누출 확인 후에는 해당 누출이 지속될 때의 피해를 계산한다.

## 구현한 범위

| 기능 | 구현 내용 | 한계 |
|---|---|---|
| 빈도 표 | 17 설비 프로파일·55 LOC/누출구간 행 | Chapter 3 전체 및 LH2 전체 고장모드 아님 |
| TNO 용기 | 압력/공정/반응 용기의 G1 전량 순간방출·G2 600초 전량방출·G3 10 mm 구멍 | 사고 정의/빈도 생성; 새 피해 경로는 G3만 연결 |
| TNO 배관 | 직경 3구간, 양단 파열·10% 직경 누설, 최대 50 mm | 지하 장거리 수송관 제외; 양단 방출 피해 미연결 |
| TNO 펌프 | 일반/강재 containment/canned, 가장 큰 연결 배관 기준 | LH2 실측 고장률로 검증된 값 아님 |
| TNO 열교환기 | 위험물의 관 안/밖, 외부 쉘 압력 등급에 따라 3종 | 실제 기화기 구조를 확인한 후 선택; 단순 자동 매핑 금지 |
| TNO 압력방출장치 | 최대 대기 방출 LOC 2×10⁻⁵/년 | 정상 벤트 횟수·안전밸브 작동 실패확률이 아님 |
| LH2 문헌 | flange/hose/joint/pipe/valve/vessel 6종×5 면적 구간 | GH2/LNG 정보를 이용한 추정이며 현장 LH2 누출 대조 미완료 |
| 빈도 단위 | 부품은 개수, 배관은 m, 발생률×노출 | 같은 장치의 물리 범위를 중복 등록하면 거절 |
| 불확실성 | LH2 ln-rate μ·σ와 한 구간의 5/95% 분위수 유지 | 구간 간 상관자료 없음; 분위수 합계를 시설 신뢰구간으로 표시하지 않음 |
| 새 물리 연결 | 동일 설비·동일 구멍 크기의 단일 탱크 구멍 사건을 연결 | 여러 설비/길이에 대한 빈도를 한 점에 몰아넣지 않음 |
| 사건 분기 | 명시한 배타적 점화/차단 등 분기 확률×개시 빈도 | 자동 사건수목·기존 점화/차단 정책 재사용은 미완료 |
| 요구시 실패 | 연간 요구 횟수×요구당 실패확률 | 값·출처는 별도 시험/신뢰성 자료 필요 |
| 실증 업데이트 | 확인 누출 건수+설비년/m년을 받는 별도 Gamma-Poisson 함수 | Brooks의 lognormal을 자동 Gamma로 변환하지 않음; 실제 센터 자료에 적용 안 함 |
| 단기 개시 확률 | 미발생 사고의 정상 Poisson 가정, 365.25일/년 명시 | 신호 기반 상태 의존 hazard 모델 아님 |

## 두 빈도 기준을 어떻게 사용하나

`TNO_PURPLE_LOC`는 TNO 원문 사고 정의를 그대로 유지한다. `LH2_LITERATURE`는 문헌의 0.01/0.1/1/10/100% **유로 면적** 누출 구간을 유지한다. 면적 1%는 직경 1%가 아니라 **직경 10%**다.

같은 탱크/부품의 TNO 사건과 LH2 문헌 사건을 모두 더하면 고장을 중복 집계한다. `physical_scope_ids`로 실제 장치/배관 구간을 소유하도록 하고 동일 범위의 두 프로파일을 거절한다. 서로 다른 실제 부품에 TNO/문헌을 선택적으로 적용하는 조합은 가능하지만 선택 근거를 남긴다. 이 ID 검사는 사용자가 다른 ID로 같은 장치를 잘못 등록한 것을 자동으로 알아내지는 못한다.

TNO 배관은 flanges 포함 조건 때문에 **배관별 최소 10 m**가 적용된다. LH2 문헌 배관은 실제 길이를 사용한다. TNO 배관에 포함한 flange를 따로 다시 넣지 않는다. 파열 위치를 상류/중앙/하류로 나누면 위치 가중치 합이 1이 되어야 하며 전체 빈도를 위치마다 반복 적용하면 안 된다. 위치 분할 생성기는 후속 항목이다.

TNO 용기는 외부 충격/운전 오류가 배제되지 않으면 G1·G2에 각각 5×10⁻⁶/년을 추가한다. 적용 여부 입력은 필수다. 극저온·이중벽이라는 이유만으로 자동 감소시키지 않는다. 대기압에 가까운 극저온 탱크는 압력용기라고 자동 분류하지 않는다.

## 실제로 확인한 결과

- 자동/기존 회귀 검사 **100개 통과**, 약 0.75초. 68개는 v0.2.0 기록이며 이번 총 검사 수는 100개다.
- 일반 시설 합성 예제 6개 설비 그룹에서 **16개 개시 사건** 생성; 이번 실행 약 {verification['generic_generation_elapsed_ms']:.2f} ms. 외부 물리 계산 시간과 별개다.
- 한 탱크의 **G3 10 mm, 1×10⁻⁵/년**을 새 경로에 자동 연결했다. source·SLAB·화재/폭발·수용점 피해·해당 기상 연간 기여까지 실행했다.
- Python 경로 약 {verification['actual_chain_elapsed_ms']/1000:.2f}초, CLI 경로 약 {cli['elapsed_ms']/1000:.2f}초. 질량 폐합과 연간 기여=빈도×조건부 피해×체류를 확인했다.
- 방출 시간은 **0.2초로 선언한 합성 연결 시험**이다. 실제 G3의 방출 지속시간·차단 성공·재고 소진을 검증한 것은 아니다. `release_termination` 없이는 자동 빈도를 연결하지 않는다.
- G1 순간 전량 및 G2 10분 전량 사건도 빈도는 생성되지만, 이 시험에서 피해는 **미계산**이다. 따라서 시설 전체 위험을 반환하지 않는다.
- CLI 사건 생성 및 물리 계산 두 진입점도 실행했다. 결과와 버전/해시는 `results/20261008/frequency_v030`에 있다.

## 센터 실증 자료와 빈도의 관계

**사용자가 현장 사고빈도 자료가 없음을 확인했다. 이 자료의 확보는 현재 개발이나 첫 논문의 필수 조건이 아니다.** 현재 기본 경로는 TNO/LH2 문헌 빈도와 불확실성·민감도 평가다. 현장 빈도 업데이트는 나중에 자료가 생겼을 때의 선택적 확장이다. 공정·방출·분산의 실증 검증과 사고빈도 검증을 분리한다.

파일목록에서 인수·저장벤트·공급 운전/예측/원본 학습자료를 확인했다. 현재 확인한 파일목록만으로는 누출사건 대장과 설비년/m년 노출을 식별하지 못했다. 파일 내용에 사고 기록이 없다는 확정 판정은 아니다. [`field_experience_availability.json`](../results/20261008/frequency_v030/field_experience_availability.json)에 확인 범위를 남겼다.

온도·압력·밸브 신호는 공정 상태와 방출량·차단 시간을 검증하는 데 사용한다. 정상 벤트 100번을 사고 누출 100건으로 세지 않는다. 반복 경보 역시 실제 사건 하나인지 확인해야 한다. 별도 정비/고장 대장에는 설비 종류, 실제 누출 구간, 유체/상, 확인 사건 수, 설비 개수/배관 길이, 관찰 기간, 관찰 완전성, 요구시 작동/실패, 출처가 필요하다. 설비년과 운전시간을 무근거로 바꿔 섞지 않는다.

`updated_rate()`는 명시한 Gamma 사전분포와 완전한 누출 관찰 자료를 사용하는 선택적 모델이다. 누출 0건이 관찰됐어도 위험을 0으로 만들지 않는다. 누적 장부 snapshot을 원래 사전분포에서 다시 계산하여 같은 snapshot 재계산 시 이중 학습을 만들지 않는다. 서로 다른 observation window의 중복은 향후 장부 관리 계층에서 검사해야 한다. 신호를 학습한 상태 의존 고장률은 별도 독립 검증 전에는 넣지 않는다.

## 코드와 실행 방법

- [`frequency.py`](../src/lh2_tno/frequency.py): 입력 계약, 단위/범위 검사, 사건 생성, 피해 요청 연결, 요구시 실패, 선택적 현장 업데이트.
- [`frequency_catalogue.json`](../src/lh2_tno/data/frequency_catalogue.json): 출처·원본 해시를 포함한 표 snapshot. 패키지 데이터로 포함한다.
- [`pipeline.py`](../src/lh2_tno/pipeline.py): `frequency_events()`와 `consequences_for_event()`.
- [`consequences.py`](../src/lh2_tno/consequences.py): 빈도·구멍·설비·방출 종료·단기 intensity 일치 검사.
- [`test_frequency.py`](../tests/test_frequency.py): 단위, 중복, 결측, 원문 직경 경계, 실제 경로 입력 검사를 포함한 32개 신규 검사.
- [`validate_frequency.py`](../scripts/validate_frequency.py): 합성 시설 사건 생성과 외부 물리 모델 연결 재현. 센터 태그/용량을 기본값으로 사용하지 않는다.

```powershell
$env:PYTHONPATH = 'src'
python -m pytest -q
python -X utf8 scripts/validate_frequency.py
python -X utf8 -m lh2_tno.cli examples/lh2_frequency_facility.json --frequency-plan examples/lh2_frequency_plan.json --output events.json
python -X utf8 -m lh2_tno.cli results/20261008/frequency_v030/facility.json --backend results/20261008/frequency_v030/backend_config.json --frequency-plan results/20261008/frequency_v030/plan.json --event-id tank-g3-diagnostic/shell/G3 --consequences results/20261008/frequency_v030/template.json --output one_event.json
```

환경 interpreter·외부 모델 해시는 backend 설정에 명시한다. 같은 폴더의 이전 결과를 현재 검증으로 덮어 해석하지 않는다. 부품 ID와 공정 모델 상류 source ID가 다른 누출은 아직 포트 adapter가 필요하다. 현재 binding은 tank/vessel 단일 구멍으로 제한한다.

## 이어서 구현할 항목

1. 대기압/containment 탱크 LOC, 진공 상실·열유입·정상 벤트·하역 요구/실패의 원인별 모델과 출처를 보강한다. Vacuum jacket을 TNO full-containment로 자동 승격하지 않는다.
2. 별도 `lh2dt` 공정 모델에서 실제 고장 부품의 P,h·상·포트·유량을 받아 tank·pipe·valve·pump·vaporizer·vent와 각각 결합한다. 이미 계산한 유량을 두 번 계산하지 않는다.
3. G1/G2, 양단 배관 파열·다중 관 파열, 위치 분할, 개시원인 중복, 실제 차단 성공/실패 분기를 연결한다. 0.2초 진단을 실물 방출 종료로 사용하지 않는다.
4. 기존 TNO 점화/차단/기상·인구·IR/F-N 엔진을 새 event portfolio에 연결한다. 미계산 LOC가 있으면 전체 위험은 보류한다.
5. 확보된 독립 실증으로 source·농도·복사를 검증하고, 문헌 빈도에 따른 위험 범위·설비 기여도·우선순위/방호 판단의 안정성을 평가한다. 현장 사고빈도 자료 확보를 선행 조건으로 두지 않는다. 장래 자료가 생기면 관찰 장부 기반 업데이트를 별도 검증한다.

## IJHE 연구 방향과 참고 근거

현재 연구 비교군은 TNO LOC 기본선과 LH2 문헌 분포다. 확인 노출 장부 기반 현장 업데이트는 자료가 확보될 경우의 후속 연구로 둔다. 동일 물리 모델에서 빈도 가정이 위험 범위와 설비 순위/방호 판단에 주는 영향을 비교하며, 서로 다른 LOC의 포괄 범위도 표시한다. 서로 다른 LOC와 분포를 임의 평균내거나 같은 physical scope에 더하지 않는다. 센터는 확보된 물리 상태/공정 검증 사례로 사용하고 라이브러리의 시설 기본값은 범용 입력으로 유지한다. 구간 간 상관자료가 없는 합산 범위를 시설 신뢰구간으로 보고하지 않는다.

LH2 운전 누출 자료의 희소성과 GH2/LNG를 이용한 베이지안 추정의 한계는 [Brooks 등 원문](https://hysafe.info/uploads/papers/2021/44.pdf)을 따른다. 배관 노출의 metre 단위는 [Sandia HyRAM 기술 문서](https://www.osti.gov/servlets/purl/1784842/)에서도 명시한다. 이번 LH2 수치는 검토된 기존 프로젝트 표의 snapshot을 재사용했으며 현재 설치된 HyRAM의 모든 기본값을 실시간 가져오는 기능은 아니다. TNO 수치는 로컬 Purple Book 표 3.3/3.7/3.9/3.11/3.13을 이미지와 원문으로 확인했다.
'''
doc = re.sub(r'\]\((\.\./[^)]+)\)',
    lambda match: '](<' + (ROOT/'docs'/match.group(1)).resolve().as_posix() + '>)', doc)
doc_path=ROOT/'docs/TNO_LH2_v030_빈도모듈_개발기록_20261008.md'
doc_path.write_text(doc,encoding='utf-8')
readme_path=ROOT/'README.md'
readme=readme_path.read_text(encoding='utf-8')
readme=readme.replace('새 `consequence_chain`은 아직 그 빈도/사건 생성기를 호출하지 않아 빈도·점화 확률 입력을 받는다.',
    'v0.3.0의 새 빈도 생성기는 TNO LOC와 검토된 LH2 문헌 snapshot에서 사건/빈도를 만들고 단일 탱크 구멍 사건을 `consequence_chain`에 연결한다. 기존 엔진의 전체 사건생성기·점화/차단·기상 적분을 그대로 호출하는 결합은 아직 미완료다.')
readme=readme.replace('점화 확률과 누출 빈도는 출처를 명시한 입력으로 받으며 센서에서 학습한 값이 아니다.',
    '점화 확률은 출처를 명시한 입력으로 받는다. 빈도는 v0.3.0의 검토된 catalogue 사건을 연결하거나 별도 명시 입력으로 받는다. 센서 경보에서 자동 학습한 값이 아니다.')
lead='''## v0.3.0 빈도 모듈

17 설비 프로파일·55 LOC/누출구간 행, 배관 m 단위/부품 개수, 물리 범위 중복 검사, LH2 문헌의 구간별 불확실성, 요구시 실패와 별도 확인 사건·관찰노출 업데이트 계약을 추가했다. TNO 10 mm 탱크 구멍의 자동 빈도→실제 피해 경로를 실행했으며 **100개 검사 통과**. 0.2초 합성 연결 시험이고 모든 LOC/시설 위험/현장 검증 완료를 뜻하지 않는다. [개발 기록·사용 방법·한계](docs/TNO_LH2_v030_빈도모듈_개발기록_20261008.md)를 먼저 확인한다.

'''
if '## v0.3.0 빈도 모듈' not in readme:readme=readme.replace('# LH2-TNO\n\n','# LH2-TNO\n\n'+lead,1)
readme_path.write_text(readme,encoding='utf-8')
policy='현장 사고빈도 자료가 없다는 사용자 확인에 따라, 현재 기본 경로는 문헌 빈도와 불확실성·민감도 평가다. 자료 수집은 개발/첫 논문의 필수 조건이 아니며 현장 빈도 업데이트는 선택적 후속 확장이다.'
if policy not in readme:
    readme=readme.replace('## v0.3.0 빈도 모듈\n\n','## v0.3.0 빈도 모듈\n\n'+policy+'\n\n',1)
    readme_path.write_text(readme,encoding='utf-8')

CODE=Path(r'C:\Users\lyul\Desktop\DocuData\TNO_위험분석모듈\TNO_SYSTEM\코드')
archive=CODE/'개발기록_20261008/TNO_LH2_v030'
archive.mkdir(parents=True,exist_ok=True)
sources=[doc_path,ROOT/'docs/IJHE_연구프로토콜.md',status_path,OUT/'verification.json',OUT/'generic_events.json',OUT/'actual_g3_chain.json',
    OUT/'cli_actual_g3_chain.json',OUT/'field_experience_availability.json',OUT/'plan.json',OUT/'bound_request.json',
    ROOT/'src/lh2_tno/data/frequency_catalogue.json']
records=[]
for source in sources:
    target=archive/source.name
    shutil.copyfile(source,target)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest==hashlib.sha256(target.read_bytes()).hexdigest()
    records.append({'source':str(source),'copy':target.name,'sha256':digest})
manifest={'version':'0.3.0','date_kst':'2026-10-08','authoritative_code':str(ROOT/'src/lh2_tno'),
    'snapshot_records':records,'code_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (ROOT/'src/lh2_tno').rglob('*') if p.is_file() and p.suffix in ('.py','.json')},
    'interpretation':'documentation/evidence snapshot, not an executable code fork'}
(archive/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
entry=CODE/'00_개발현황_먼저읽기.md'
text=entry.read_text(encoding='utf-8')
prefix='''## 최신 추가: TNO-LH2 v0.3.0 빈도 모듈

새 경로에 17 프로파일·55행의 TNO/LH2 문헌 빈도 catalogue와 사건 생성기를 추가했다. 단일 탱크 10 mm 구멍의 자동 빈도→물리 피해 연결을 실제 실행했고 총 100개 검사 통과. **0.2초 합성 연결 시험이며 G1/G2·양단 파열·전체 시설 위험은 미완료**다. 기존 엔진 전체 사건생성기의 재사용과는 구분한다.

[v0.3.0 개발 기록](개발기록_20261008/TNO_LH2_v030/TNO_LH2_v030_빈도모듈_개발기록_20261008.md) / [현재 상태](개발기록_20261008/TNO_LH2_v030/CURRENT_STATUS.json) / [실행 증거](개발기록_20261008/TNO_LH2_v030/verification.json). 코드 정본은 아래 링크의 lh2-tno이다. 아래 기존 현황은 v0.2.0 감사 시점의 기록이며, 새 빈도 연결 상태는 이 추가 기록을 우선 확인한다.

'''
if '## 최신 추가: TNO-LH2 v0.3.0 빈도 모듈' not in text:
    text=text.replace('# TNO 개발 현황 — 먼저 읽기\n\n','# TNO 개발 현황 — 먼저 읽기\n\n'+prefix,1)
entry.write_text(text,encoding='utf-8')
if policy not in text:
    text=text.replace('## 최신 추가: TNO-LH2 v0.3.0 빈도 모듈\n\n',
        '## 최신 추가: TNO-LH2 v0.3.0 빈도 모듈\n\n'+policy+'\n\n',1)
    entry.write_text(text,encoding='utf-8')
pointer=ROOT/'src/lh2_tno/개발기록_안내.md'
pointer.write_text(f'# TNO-LH2 개발 기록 안내\n\n최신 구현은 v0.3.0이다. [빈도 모듈 개발 기록](<{doc_path.as_posix()}>)과 [기존 TNO 코드 옆 전체 안내](<{entry.as_posix()}>)를 확인한다. 실행 코드의 정본은 이 폴더이며, 개발기록 폴더는 문서/증거 보관본이다.\n',encoding='utf-8')
print(json.dumps({'record':str(doc_path),'code_side_archive':str(archive),'hashes_verified':True,'tests_passed':100},ensure_ascii=False))
