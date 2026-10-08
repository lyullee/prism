# PRISM

**Process Risk Integration and Scenario Modeling**

공정·설비 상태, 사고 시나리오, 발생 빈도와 피해영향을 연결하는 위험 분석 시스템.

**버전 0.6.2 / 기준일 2026-10-09** — 기본 `standard` 분석과 선택형 `lh2` 분석을 공통 실행기에서 선택합니다.
범용 액화수소시설에 적용하는 인터페이스이며 특정 실증센터의 설비·태그를 필수로 요구하지 않습니다.

> 현재는 연구용 진단 계산 시스템입니다. 방출부터 최종 피해까지 실행하는 경로는 구현했지만,
> 새 LH2 경로의 전체 시설 QRA, 현장 정확도와 매초 신규 물리 계산은 아직 검증되지 않았습니다.
> v0.6.2는 v0.6.0 이후의 설비 경계·문헌 빈도·매니페스트 진단을 포함한 연구용 알파 릴리스입니다. 전체 시설 QRA와 독립 물리 검증은 여전히 별도 상태로 표시됩니다.

**개발 소스 추가 사항 (2026-10-09):** 다중 LOC·기상·방호 분기 실행기와 기존 TNO IR/F-N 합산 연결, 빈도 민감도, 문헌 p05/중앙/p95 빈도 구간 재가중, 통합 LH2 source의 압력 평형 자연 종료, G1 instantaneous-inventory용 명시적 SLABx-LH2 liquid-jet operator, 외부 설비 twin의 PH/network 출구를 `ResolvedGasRelease`로 받아 시설 campaign에 연결하는 경로를 추가했습니다. 추가로 `LayeredTankNetworkSimulator`와 `CommandedValve`를 이용해 탱크 상태→밸브 차단 성공·실패→기체 출구 종료/진단시계까지 연결하고, `HomogeneousTank`의 양수 재고 threshold 종료를 문헌 `LH2_PIPE` 5개 누출 크기와 두 기상 조건에 연결해 **10건을 모두 실행**했습니다. 자연 종료는 모델이 반환한 실제 시간 이력만 사용하며 요청 시간까지 유량을 연장하지 않습니다. G1은 구멍 누출로 대체하지 않고 2초 finite-inventory 질량 폐합을 수행하지만 일정 upstream·open spray-energy 가정 때문에 operator-limited로 표시합니다. transient 설비 경로는 차단 성공·실패 두 분기를 두 기상 조건에 전달해 **20건을 모두 실행**했습니다. `TNO_PIPE` full-bore 양단은 `ResolvedGasReleaseSet`의 두 provider 출구를 한 사건으로 결합하고, 위치 배분은 `location_weight`로 명시합니다. 수직 전용 출구는 provider가 수평 handoff 단면·방향·혼합상태를 명시한 `VerticalGasHandoff`가 있을 때만 downstream 경로로 연결하며, PRISM이 수직 제트를 임의로 회전시키지 않습니다. **새로 provider가 계산한 액체·2상 대기 출구를 `ResolvedLiquidRelease`로 받아 flash 기체·지면 액체·액적 도착 시계를 그대로 SLABx-LH2/SLABx와 DynamicLH2PoolX에 전달하는 한 건의 전체 진단도 실행했습니다. airborne liquid은 검증된 별도 adapter가 없으면 거절합니다.** 이 액체 경계의 실제 개구가 문헌 `LH2_VESSEL` 0.01% bin과 일치하는 별도 campaign에서는 저장탱크·격리밸브·이송배관 15개 문헌 LOC를 생성하고, 정확히 일치하는 저장탱크 한 건만 빈도와 결합했습니다. 나머지 14개 LOC는 provider 이력 부재 또는 개구 불일치로 두 기상 조건에서 미계산 처리했습니다. `bind_event()`는 이제 `resolved_liquid_release`의 provider 개구를 직접 검사합니다. 장벽 성공확률 `0.99`와 재고 threshold·탱크 입력은 합성 진단값이며 현장 신뢰도·현장 재고 추정이 아닙니다. 추가로 DynamicLH2PoolX의 풀/확산 구성요소 hold-out 지표와 원자료 해시를 별도 장부로 확인했지만, protocol hash drift 때문에 제한 증거로만 기록했습니다. 빈도 구간은 자산별 공유 분위수 시나리오와 독립 event-bound 시나리오를 비교하고, catalogue에 공개된 로그정규 mu/sigma가 있는 LH2 사건에는 known-contribution p05/p50/p95 표본 구간도 계산할 수 있습니다. 이 구간은 물리 계산을 반복하지 않으며 불완전한 시설을 완전한 시설 신뢰구간으로 표시하지 않습니다. **추가로 일반 설비 매니페스트의 모든 부품을 명시적 문헌 FrequencyPlan으로 선택하거나 제외하고, 개구가 일치하는 방출 요청만 RiskCampaign에 연결하는 컴파일러를 넣었습니다.** 이번 0.6.2 개발 기능입니다. **304개 검사**와 LayeredTank-SLABx·문헌빈도 시설 연결 진단을 확인했습니다. [완성 목표](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_IJHE_완성목표_20261009.md) / [사용·검증·실패 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_시설위험_실행기_개발기록_20261009.md) / [액체·2상 경계 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_설비액체2상_연결_개발기록_20261009.md) / [LayeredTank 문헌빈도 연결 기록](docs/PRISM_LayeredTank_문헌빈도_시설연결_20261009.md) / [재고 소진 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_재고소진_연결_개발기록_20261009.md) / [물리 검증 근거](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_물리검증_근거_20261009.md). 실제 시설 연간 위험은 설비·운전·물리 검증 자료가 없으므로 계속 별도로 보류합니다.
**provider 재고 소진 연결 (개발 소스):** 설비 provider가 기체 전체 재고 소진 이력을 계산한 경우 `equipment_inventory_depletion`을 사용하고, 액체·2상 전체 재고 이력은 `equipment_liquid_release`를 사용해 `instantaneous_inventory` 문헌 사건과 결합할 수 있습니다. 정확히 600초 이력을 반환한 기체·액체 provider는 각각 `equipment_inventory_over_600s`·`equipment_liquid_over_600s`와 `inventory_over_600s` 종료근거를 사용합니다. PRISM은 짧은 누출을 전량 방출로 늘리거나 센서값에서 재고·빈도를 추정하지 않습니다.

**차단 branch 빈도 연결 (개발 소스):** 하나의 initiating event에 대한 provider 방출 이력(예: isolation-success/isolation-failure)은 `--request-branch-catalog`으로 조건부 확률과 함께 입력할 수 있습니다. 물리 개구가 맞는 branch만 연결하고, 확률 합이 1보다 작으면 누락분을 `UNCOMPUTED`로 보존하며 1을 넘으면 거부합니다.

**일반 설비 매니페스트 연결 (개발 소스):** `EquipmentManifest`는 특정 검사센터의 태그를 코드에 고정하지 않고, 임의의 옥외 액화수소 설비 모델이 부품·포트·연결·운전 시나리오를 내보내는 공통 JSON 계약입니다. 위치·물성 기준·포트·제어 신호가 빠지면 PRISM은 값을 추정하지 않고 `PARTIAL`/`UNCOMPUTED`로 남깁니다. `EXECUTABLE`일 때만 엄격한 `Facility`로 승격되며 시설 위험 캠페인에 사용할 수 있습니다. 현재 센터 자료를 이 어댑터로 읽은 결과는 **PARTIAL**이며, P&ID 포트·좌표·실제 밸브 상태·시나리오 제어가 확인되기 전에는 센터 QRA로 승격하지 않습니다. 자세한 결과는 [설비 매니페스트 연결 기록](docs/PRISM_일반설비매니페스트_연결_개발기록_20261009.md)과 `scripts/validate_equipment_manifest.py`에 있습니다. **304개 검사**를 통과했습니다.

**일반 LH2 설비 범위 진단:** 탱크·이송배관만 있는 기본 예제와 별도로, [일반 LH2 설비 범위 진단 기록](docs/PRISM_일반LH2_설비범위_진단_20261009.md)의 합성 매니페스트에는 탱크·배관·밸브·벤트·펌프·기화기·재액화기·경계를 포함했습니다. 현재 검토된 문헌 프로파일과 명시적인 열교환기 측면 분류로 24개 initiating event를 만들고, 경계 컴포넌트는 사고 빈도에서 제외합니다. 이 진단은 빈도 범위 연결만 확인하며 provider 방출 장부나 시설 IR/F-N을 생성하지 않습니다. 실제 설비에서 열교환기 측면 분류가 확인되지 않으면 기화기·재액화기는 자동 대체하지 않고 다시 미계산으로 둡니다.

**빈도→방출 요청 작업목록:** [방출 요청 작업목록 기록](docs/PRISM_방출요청_작업목록_20261009.md)과 `scripts/build_provider_release_worklist.py`는 위 24개 사건을 설비별 provider packet 요청으로 펼칩니다. 현재 packet은 0건이므로 24건 모두 `UNCOMPUTED_PROVIDER_PACKET`이며, 정상 유량·센서 시계열을 사고 방출로 승격하지 않습니다. packet이 들어오면 개구·설비·포트·종료 basis를 exact-match한 뒤에만 피해영향 campaign으로 보냅니다.

**비상 릴리프 방출 경로:** `TNO_RELIEF_DEVICE`의 `maximum_relief_discharge`는 일반 벤트나 임의 누출로 대체하지 않고, `event_kind=emergency_relief`인 provider 기체 방출 이력과 `equipment_emergency_relief`·`emergency_relief_discharge` 근거가 모두 있을 때만 빈도와 결합합니다. 실제 provider 패킷이 없으면 해당 벤트 사고는 `NO_CASE_EXECUTED`/`UNCOMPUTED`로 남습니다.

실제 릴리프 packet catalog를 request template로 바꿀 때는 `build_provider_request_catalog.py`에 `--release-kind emergency_relief`를 지정합니다. 기본값 `accidental_leak`와 catalog를 섞지 않으며, 출력에 `provider_release_kind`를 남깁니다.

`inventory_over_600s`는 600초 전체 provider 이력과 전용 종료 근거가 모두 있을 때만 사건 빈도와 피해를 결합합니다. 짧은 진단 이력은 이 사고의 대체 계산으로 인정하지 않습니다.

주요 사고의 범위는 `scripts/build_accident_scope_matrix.py`로 별도 감사할 수 있습니다. 이 보고서는 저장탱크·배관·밸브·벤트·펌프·증발기·재액화기·액체/2상·재고소진·양단 파열·수직 handoff를 행으로 만들고, 각 행을 `EXECUTED`, `PARTIAL`, `UNCOMPUTED`, `NO_EVENT_GENERATED`로 표시합니다. 행별 문헌 빈도는 사고 가족 간에 중복될 수 있으므로 합산하지 않으며, 시설 전체 IR/F-N 승격 여부와 차단 이유도 함께 기록합니다. 자세한 기준은 [주요 사고 범위 매트릭스 기록](docs/PRISM_주요사고_범위매트릭스_20261009.md)을 참고합니다.

IJHE 제출 준비 상태는 `scripts/build_ijhe_completion_audit.py`로 자동 판정합니다. 이 감사기는 일부 case가 실행됐다는 이유로 전체 시설 QRA를 승격하지 않고, 사고 범위·시설 IR/F-N·물리 검증·빈도 불확실성·처리시간 증거를 모두 요구합니다. 현재 합성 provider 경로는 `INCOMPLETE_EVIDENCE`입니다.

## 목차

1. [쉽게 이해하는 PRISM](#쉽게-이해하는-prism)
2. [시스템 구조와 개발 상태](#시스템-구조와-개발-상태)
3. [설치와 첫 실행](#설치와-첫-실행)
4. [입력 파일 작성](#입력-파일-작성)
5. [외부 모델 연결](#외부-모델-연결)
6. [기본 분석 모드](#기본-분석-모드)
7. [LH2 피해영향 계산](#lh2-피해영향-계산)
8. [빈도 산출과 적용](#빈도-산출과-적용)
9. [설비와 디지털트윈 연결](#설비와-디지털트윈-연결)
10. [출력 해석](#출력-해석)
11. [검증과 후속 개발](#검증과-후속-개발)
12. [문제 해결과 개발 기록](#문제-해결과-개발-기록)

## 쉽게 이해하는 PRISM

탱크에서 수소가 새는 상황을 생각하면 세 가지 질문이 생깁니다.

- **얼마나 자주 생길까?** 사고 빈도 모듈이 설비 종류·수량·배관 길이와 문헌 자료를 이용합니다.
- **발생하면 어떻게 퍼질까?** 공정/방출 모델과 SLABx-LH2·SLABx가 방출량, 극저온 전이와 확산을 계산합니다.
- **불이 붙으면 사람에게 어떤 피해가 생길까?** 점화 분기, 화재 방사열, 폭발 피해 구역과 인명 피해 변환을 연결합니다.

빈도와 피해는 다른 값입니다. 압력이 올라가면 누출량과 피해가 달라질 수 있지만,
현재 PRISM은 압력 센서만 보고 사고 빈도가 몇 배 증가했다고 추정하지 않습니다.
이미 누출이 관측됐다면 누출 발생확률을 다시 곱하지 않고 **그 누출의 조건부 피해**를 계산합니다.

PRISM은 각 모델을 연결하고 입력·질량·시간·출처가 맞는지 검사합니다.
모든 설비의 물리 모델을 자체 구현한 단일 공정 시뮬레이터는 아닙니다.

## 시스템 구조와 개발 상태

| 기능 | 현재 구현 | 범위/한계 |
|---|---|---|
| 모드 선택 | 기본 `standard`, 선택형 `lh2` | 내부 모델 분리 관리, 실패 시 자동 모드 전환 없음 |
| 시설 구성 | 부품·포트·연결·수용점 JSON과 검증 | 구성 등록이 모든 부품의 물리 해석 지원을 뜻하지 않음 |
| 누출→피해 | 방출, 지면 도달/풀, 극저온 전이, 확산, 점화, 화재/폭발, 인명 피해 | 제한된 옥외 진단 경로 |
| 사고 빈도 | 17개 설비 프로파일, 55개 LOC/누출구간 행 | 문헌 기본선, 현장 사고빈도 검증 없음 |
| 빈도→피해 | 문헌 LH2 배관 5개 area-bin과 LayeredTank 문헌 `LH2_VESSEL` 정확 개구 1개를 설비 방출·기상·점화 경로에 결합 | 실제 설비 수·위치·장벽 근거가 없어 일반 시설 전체 QRA는 미완료; 개구가 다른 bin은 자동 보간하지 않고 미계산 |
| 설비 출구 연결 | PH/network 출구, 5개 transient LH2 pipe area-bin, 양수 재고 threshold 종료, 양단 파열, provider-resolved vertical handoff, provider-resolved liquid/two-phase exit 수용 | 기체는 수평 또는 명시적 수평 handoff가 있는 대기압·Mach≤0.3 경계, 액체/2상은 provider flash·지면 분할이 완결된 경계만 수용; 유량 재계산 없음; airborne liquid·실제 설비의 LayeredTank 액체 재고 feedback은 미지원이며, 합성 대기 probe와 양수 임계값 feedback 진단만 별도 SLABx 브리지로 연결 |
| 일반 설비 매니페스트 | 부품·포트·연결·시나리오 제어를 시설 중립 JSON으로 검사하고 `EXECUTABLE/PARTIAL/EXCLUDED/UNCOMPUTED`를 명시 | 누락된 P&ID 태그·좌표·물성·제어를 추정하지 않음; `EXECUTABLE` 전에는 시설 위험 캠페인 승격 불가 |
| 센서 연결 | 단위·위치·품질·시간 검증, 알려진 누출의 P/T 갱신 | 누출 크기 역추정·경보 빈도 학습 없음 |
| 결과 캐시 | 동일 입력·시설·모델 버전의 결과 재사용 | 변경 상태는 신규 계산, 신규 계산 1 Hz 미검증 |
| 기존 엔진 QRA | 빈도 조회, 사건 생성, 점화·차단·기상, IR/F-N | 외부 엔진 기능, 새 LH2 전체 시설 결합은 미완료 |

```text
PRISM -> standard / LH2
LH2 -> source / resolved equipment exit -> pool/cryogenic transition
-> SLABx dispersion -> ignition/fire/blast -> human harm -> conditional risk
Literature frequency -> exact physical opening match -> initiating event -> risk contribution
```

| 모델 | 책임 | 이 저장소에 포함 |
|---|---|---|
| PRISM / `lh2_tno` | 모드 선택, 입력 계약, 실행 연결, 빈도, 센서 정규화, 출처 기록 | 예 |
| 기존 TNO 기반 엔진 | 기존 QRA, 열/폭발 인명 피해 변환, 근거 gate | 외부 경로 연결 |
| `lh2dt` | 설비 압력·엔탈피·상·유량·재고/사건 시계 | 외부 경로 연결 |
| SLABx-LH2 / SLABx | 상세 방출, 근거리 전이와 분산 | 외부 경로 연결 |
| DynamicLH2PoolX | 지면에 도달한 LH2 풀과 증발 | 외부 경로 연결 |

**제품 이름은 PRISM**입니다. TNO 표기는 방법·원자료·외부 엔진의 출처를 설명할 때 유지합니다.
HyRAM을 현재 LH2 전체 경로에 도입했다고 주장하지 않습니다. 필요성이 검토되면 별도 모델로 추가할 수 있습니다.

## 설치와 첫 실행

### 설치

GitHub 접근 권한이 있는 계정으로 새 비공개 저장소를 복제합니다. **Python 3.12 이상**이 필요합니다.
아래는 Windows PowerShell 기준이며 명령은 저장소 루트에서 실행합니다.

```powershell
git clone https://github.com/lyullee/prism.git
cd prism
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e "./lh2-tno[test]" setuptools wheel
```

배포 이름은 `prism-risk`, 실행 명령은 `prism`입니다. PyPI 설치 명령은 `python -m pip install prism-risk==0.6.2`입니다.
공개 배포 파일에는 외부 물리 모델이 포함되지 않습니다. GitHub는 비공개이며 접근 권한이 필요합니다.

### 설비 매니페스트 사전 점검

외부 디지털트윈은 먼저 설비 중립 매니페스트로 내보냅니다. 이 명령은 누락된 태그나 제어 신호를 자동으로 채우지 않고, 위험 계산에 넘겨도 되는지 판정합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_manifest.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --output manifest_audit.json
```

구조 점검이 `EXECUTABLE`이 된 뒤에도 빈도 범위는 별도로 확인합니다. 아래 감사기는 모든 설비에 검토된 문헌 profile을 배정하거나 명시적 제외 사유를 요구합니다. 설비 이름·압력·크기만으로 빈도를 추정하지 않으며, 방출 provider나 피해 계산을 자동으로 만들지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_frequency_scope.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --output frequency_scope_audit.json
```

예제의 `EXECUTABLE`은 구조와 빈도 범위가 갖추어졌다는 뜻입니다. 실제 시설 위험을 계산하려면 각 사건에 설비 provider 방출 이력과 명시적 `ConsequenceRequest`를 연결해야 하며, 빠진 사건은 `UNCOMPUTED`로 남겨야 합니다. 자세한 정책은 [일반 설비 빈도 범위 연결 기록](docs/PRISM_일반설비_빈도범위_연결_개발기록_20261009.md)을 참고합니다.

빈도 사건과 방출 요청 템플릿을 캠페인으로 묶을 때는 다음 컴파일러를 사용합니다. 개구나 설비가 맞지 않는 사건은 자동 대체하지 않고 미계산 경로로 남깁니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_equipment_campaign.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --request-template lh2-tno/examples/equipment_consequence_template.json `
  --annual-conditions lh2-tno/examples/equipment_annual_conditions.json `
  --scope-provenance "synthetic generic manifest campaign" `
  --output equipment_campaign.json
```

이 명령은 선언만 컴파일하며 물리 backend는 실행하지 않습니다. 실행 기록과 합성 예제의 1건 실행·9건 미계산 결과는 [일반 설비 방출경로 캠페인 기록](docs/PRISM_일반설비_방출경로_캠페인컴파일_개발기록_20261009.md)에 남깁니다.

설비가 여러 개의 실제 방출 경계를 제공하면 `--request-template` 대신 `--request-catalog`을 사용할 수 있습니다. JSON 배열 또는 `{"templates": [...]}` 객체에 설비별 `ConsequenceRequest`를 넣습니다. PRISM은 각 빈도 사건에 대해 설비 ID와 실제 개구가 모두 일치하는 요청만 선택하고, 여러 요청이 동시에 맞거나 일치하는 요청이 없으면 각각 오류 또는 `UNCOMPUTED`로 남깁니다. 다른 설비의 방출량·개구·지속시간을 복사하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_equipment_campaign.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --request-catalog equipment_request_catalog.json `
  --annual-conditions lh2-tno/examples/equipment_annual_conditions.json `
  --scope-provenance "reviewed equipment provider catalog" `
  --output equipment_campaign.json
```

차단 성공·실패처럼 하나의 initiating event에 여러 provider 방출 history가 있으면 `--request-branch-catalog`을 사용합니다. 각 행은 `id`, `probability_given_event`, `provenance`, `request`를 포함합니다. 같은 사건에 맞는 branch 확률의 합이 1보다 작으면 남은 확률을 `uncomputed-provider-branch-remainder`로 보존하고, 1보다 크면 컴파일을 거부합니다. 따라서 차단 실패 packet을 누락한 채 성공 branch만으로 시설 위험을 계산하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_equipment_campaign.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --request-branch-catalog equipment_request_branch_catalog.json `
  --annual-conditions lh2-tno/examples/equipment_annual_conditions.json `
  --scope-provenance "reviewed provider isolation branches" `
  --output equipment_branch_campaign.json
```

외부 설비 모델이 `prism.resolved_release.v1` packet을 직접 내보내면 중간 request catalog 파일을 만들지 않고도 선택형 경로로 연결할 수 있습니다. 이 경로는 packet을 strict 검증한 뒤 defaults의 종료근거·source operator를 붙이고, 같은 exact-match 규칙으로 설비와 문헌 빈도를 연결합니다. packet 하나라도 문맥과 맞지 않으면 캠페인을 만들지 않으며, 실제 packet이 없는 설비에는 아무 값도 추정하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_equipment_campaign.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --provider-release-catalog provider_releases.json `
  --release-kind accidental_leak `
  --request-defaults request_defaults.json `
  --annual-conditions lh2-tno/examples/equipment_annual_conditions.json `
  --scope-provenance "reviewed provider release campaign" `
  --output equipment_campaign.json
```

같은 initiating event의 provider packet이 차단 성공·실패처럼 여러 개라면 `--provider-release-branch-catalog`을 사용합니다. 각 행은 `id`, `probability_given_event`, `provenance`, `release`를 가지며, 일반 누출 branch는 `prism.resolved_release.v1`, 양단 파열 branch는 `prism.resolved_release_set.v1` packet을 넣습니다. 양단 파열 branch는 `--release-kind two_sided_rupture`를 함께 지정해야 두 endpoint를 공유 사건으로 보존하는 전용 adapter가 선택됩니다. packet은 각각 실제 개구와 상태 이력을 보존하고, PRISM은 initiating frequency를 한 번만 부여합니다. branch 확률 합이 부족하면 `UNCOMPUTED` remainder를 남기고, 초과하면 거부합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_equipment_campaign.py `
  --manifest lh2-tno/examples/equipment_manifest.json `
  --frequency-plan lh2-tno/examples/equipment_frequency_plan.json `
  --provider-release-branch-catalog provider_release_branches.json `
  --request-defaults request_defaults.json `
  --annual-conditions lh2-tno/examples/equipment_annual_conditions.json `
  --scope-provenance "reviewed provider barrier branches" `
  --output equipment_provider_branch_campaign.json
```

설비별 campaign을 따로 실행한 뒤 시설 장부로 합칠 때는 `merge_facility_campaigns.py`를 사용합니다. 이 단계는 물리 계산을 다시 하지 않고 각 campaign의 검증된 risk atom만 한 번씩 합칩니다. 전체 시설 component 목록을 `--expected-component-id`로 명시해야 하며, event ID·asset 소유권·수용점 집합이 겹치거나 기대한 설비·사고 가족이 빠지면 known contribution만 남기고 `total_facility_*`를 `null`로 유지합니다. 출력의 `component_contributions`에서는 event의 `model_component_id`별 IR/F-N 기여도를 확인할 수 있으며, 미계산 설비에 빈도 0을 배정하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/merge_facility_campaigns.py `
  --campaign-result tank_campaign_result.json `
  --campaign-result transfer_campaign_result.json `
  --expected-component-id storage-tank-01 `
  --expected-component-id liquid-transfer-line-01 `
  --output facility_risk_ledger.json
```

결합된 ledger에 문헌 빈도 구간을 재가중할 때는 `compute_frequency_uncertainty.py`에 명시적인 자산별 또는 사건별 시나리오 JSON을 전달합니다. 이 명령은 물리를 다시 실행하지 않고, 공개된 p05/published/p95 빈도만 risk atom에 적용합니다. `facility_credible_interval=false`는 통계적 신뢰구간을 주장하지 않는다는 뜻이며, 불완전한 scope는 그대로 보류됩니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/compute_frequency_uncertainty.py `
  --ledger facility_risk_ledger.json `
  --scenarios frequency_scenarios.json `
  --output facility_frequency_uncertainty.json
```

시설 ledger와 빈도 시나리오를 한 파일로 묶으려면 `build_facility_assessment.py`를 사용합니다. 이 실행기는 이미 계산된 campaign 결과를 한 번만 합치고, 선택한 문헌 빈도 시나리오를 저장된 risk atom에만 적용합니다. `fresh_physics_executed=false`이며, 미완성 범위에서는 시설 total을 승격하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/build_facility_assessment.py `
  --campaign-result tank_campaign_result.json `
  --campaign-result transfer_campaign_result.json `
  --expected-component-id storage-tank-01 `
  --expected-component-id liquid-transfer-line-01 `
  --scope-matrix tank_scope_matrix.json `
  --scope-matrix transfer_scope_matrix.json `
  --required-accident-family pipe_hole `
  --scenarios frequency_scenarios.json `
  --output facility_assessment.json
```

비상 릴리프 packet은 `--release-kind emergency_relief`로 분리합니다. 이 옵션은 일반 누출이나 정상 벤트를 사고로 바꾸지 않으며, `equipment_emergency_relief`와 `emergency_relief_discharge` 근거가 없으면 연결되지 않습니다.

합성 저장탱크·이송배관 catalog를 현재 backend로 실행한 진단은 2개 요청 연결, 2개 물리 실행(1개 `EXECUTED`, 1개 `EXECUTED_OPERATOR_LIMITED`), 8개 미계산으로 기록되며 전체 시설 IR/F-N은 보류됩니다. 상세 수치와 해석 한계는 [일반 설비 방출경로 캠페인 기록](docs/PRISM_일반설비_방출경로_캠페인컴파일_개발기록_20261009.md)을 봅니다.

현재 액화수소검사지원센터 모델의 진단은 외부 자료를 변경하지 않고 다음처럼 실행할 수 있습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_manifest.py `
  --center-root "<디지털트윈 모델 루트>" `
  --manifest-output center_manifest.json `
  --output center_manifest_audit.json
```

`PARTIAL` 결과는 연결 검토용이며 시설 연간 위험의 숫자로 해석하지 않습니다. 모든 부품의 위치·물성 기준·포트·연결·필수 운전 제어가 실제 자료로 채워져 `EXECUTABLE`이 된 뒤에만 `Facility`와 피해 계산으로 승격합니다.

외부 물리모델 자체의 검증 결과와 실제 설비 연결 준비 상태는 별도로 감사해야 합니다. 다음 명령은 provider의 JSON 증거와 `검증결과.md`를 읽기만 하며, provider solver를 가져오거나 screening 값을 PRISM에 복사하지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/audit_external_provider.py `
  --provider-root "<외부 LH2 디지털트윈 모델 루트>" `
  --output provider_evidence_audit.json
```

현재 검사센터 provider에는 자체 회귀검증 822건 통과 기록이 있지만, 센터 자산 바인딩과 전방 비교 허용이 모두 `false`이고 파라미터 89건·운전시퀀스 52행의 물리시간이 미확정이어서 결과는 `PARTIAL_PROVIDER_EVIDENCE`입니다. 이 숫자는 solver 검증 범위이며 센터 QRA 완료나 시설 IR/F-N을 뜻하지 않습니다. 상세한 원자료 해시·차단 사유·승격 규칙은 [외부 provider 검증 감사 기록](docs/PRISM_외부설비_provider_검증감사_20261009.md)에 보관합니다.

외부 모델 담당자가 실제 사고 packet을 만들 때 필요한 공통 필드·시계·질량/엔탈피 장부·소유권·exact opening 규칙은 [provider 방출 packet 요청 사양](docs/PRISM_provider_resolved_release_v1_요청사양_20261009.md)에 정리했습니다. `audit_external_provider.py`도 같은 사양을 `release_evidence.provider_export_request`로 출력합니다.

감사기는 이제 provider 루트의 JSON을 재귀적으로 인벤토리하여 사고 방출 계약도 확인합니다. `event_kind=accidental_leak`, 고장 개구, 시간별 `steps`, 지속시간, 누적 질량·엔탈피, 설비·포트·위치·방출 digest, 그리고 명시적인 `provider_export_schema`가 모두 있는 packet만 `QUALIFIED_ACCIDENT_RELEASE_EXPORT` 후보로 셉니다. 필드가 모두 있어도 `ResolvedGasRelease`/`ResolvedLiquidRelease` strict 검증을 다시 실행해 출구 연속성, 질량·엔탈피 장부, provider 시계, 수직 handoff와 유한값을 확인하며, 실패는 `strict_validation_failures`로 보존합니다. 일반 운전·스크리닝 JSON에 유량 열이 있어도 사고 계약이 없으면 `normal_or_screening_flow_file_count`로만 기록하며, 최신 감사에서 센터 JSON **556개**를 확인했지만 사고 방출 후보 0건·적격 0건으로 시설 위험 계산 승격이 차단됩니다.

센터 폴더의 시나리오 CSV와 Excel도 별도로 감사합니다. 현재 CSV 3개 52행에서 `pipe_hole` 11, `valve_hole` 23, `vaporizer_hole` 4, `vent_hole` 4, `vessel_hole` 1, `inventory_over_600s` 1개의 사고 후보 family를 확인했고, Excel 17개에서 sequence 시트 21개와 time-series 시트 43개를 확인했습니다. time-series 43개 시트의 timestamp/일시와 PT·TT·DPT 센서 열, 관측 샘플 간격(중앙값 1초 7개, 60초 26개, 900초 10개)도 읽기 전용으로 기록했습니다. 이 파일들은 설비 운전상태·위험 후보 근거로 보존하지만 방출량·종료시각·위치·질량/엔탈피 장부가 없어 provider packet으로 승격하지 않습니다. 센서 기반 빈도도 학습하지 않습니다. 결과는 [센터 시나리오 증거 감사 기록](docs/PRISM_센터_시나리오_증거감사_20261009.md)과 `results/20261009/provider_evidence/center_scenario_evidence_audit.json`에 기록합니다. 후보 family 38행은 별도의 provider packet 요청 catalog로 정리했지만 `qualified_packet_count=0`, 빈도 미부여 상태를 유지합니다 (`scripts/build_provider_packet_request_catalog.py`, `center_provider_packet_request_catalog.json`).

provider가 `prism.resolved_release.v1` packet을 내보내면 다음 adapter로 명시된 피해 계산 문맥에 연결할 수 있습니다. adapter는 packet의 상·개구·시간·질량/엔탈피 장부를 strict contract로 검증하고, `weather`, `ignition`, `domain`, 평가시계, 종료근거를 담은 defaults와 결합합니다. 빈도는 이 단계에서 부여하지 않으며, 이후 `--request-catalog`와 `bind_event()`의 설비·개구 exact-match에서만 연결됩니다.

```powershell
python lh2-tno/scripts/build_provider_request_catalog.py `
  --provider-release-catalog provider_releases.json `
  --request-defaults lh2-tno/examples/provider_request_defaults.json `
  --output provider_request_catalog.json
```

저장소의 `examples/provider_release_catalog_synthetic.json`은 adapter 실행을 확인하기 위한 합성 packet이다. 실제 설비·실측·빈도 근거가 아니며, 외부 provider가 생성한 packet으로 교체해야 한다.

합성 액체 packet(`examples/provider_release_catalog_synthetic_liquid.json`)은 request adapter 뒤에 기존 설비 campaign과 backend를 이어 보는 진단도 제공합니다. `LH2_VESSEL AREA_0.01%` 개구와 정확히 맞는 1건을 source→SLABx-LH2/DynamicLH2PoolX→확산→점화·피해까지 실행했고, 9개 다른 개구 사건은 `UNCOMPUTED`로 남겼습니다. case 약 1.61초, campaign 약 1.81초였지만 packet·기상·종료근거가 합성이라 시설 전체 IR/F-N은 보류하고 `EXECUTED_OPERATOR_LIMITED`로 표시합니다. 결과는 `results/20261009/provider_release_full_chain_diagnostic/`에 기록합니다.

같은 결과에 `examples/provider_full_chain_frequency_uncertainty.json`을 적용하면 물리를 다시 실행하지 않고 문헌 p05/p95와 within-asset shared / independent-event 상관 가정을 비교합니다. 네 시나리오가 생성되며 known-contribution IR은 p05 `3.7383e-06`, p95 `1.1303e-03`/년으로 재가중됩니다. 이 값은 미계산 사건과 합성 물리를 포함한 시설 전체 credible interval이 아니므로 `facility_credible_interval=false`로 남습니다.

`request-defaults`의 `source_operator`와 `release_termination`은 설비별로 검토해 작성해야 합니다. provider duration과 종료시각이 일치하지 않거나, 두 양단 파열 set을 단일 packet으로 넣거나, source/frequency를 defaults에 넣으면 해당 packet은 `uncomputed`로 남습니다. 예제 defaults의 합성 확률·기상·종료근거는 실제 시설 값이 아닙니다.

공개 소스/예제/문서는 [Zenodo 소프트웨어 기록](https://doi.org/10.5281/zenodo.23241358)의 배포 파일을 사용합니다. 버전별 DOI는 릴리스 후 이 문서와 `CITATION.cff`에 기록합니다.
내부 폴더 `lh2-tno`, import `lh2_tno`, host 모듈 `tno_host`는 기존 연동 호환성을 위해 유지합니다.
과거 `lh2-tno` 배포본을 설치한 환경과 혼용하지 않도록 새 가상환경 사용을 권장합니다.

### 외부 물리 모델 없이 실행

```powershell
# 모드 확인
.venv\Scripts\python.exe prism.py --describe-modes

# 시설 구성만 검증: 물리 계산은 실행하지 않음
.venv\Scripts\python.exe prism.py --mode lh2 lh2-tno/examples/storage_terminal.json

# 문헌 기반 사고 사건/빈도 생성
.venv\Scripts\python.exe prism.py --mode lh2 lh2-tno/examples/lh2_frequency_facility.json --frequency-plan lh2-tno/examples/lh2_frequency_plan.json --output events.json

# 도움말
.venv\Scripts\python.exe prism.py --help
.venv\Scripts\python.exe prism.py --mode lh2 --help
```

빈도 예제는 **16개 사건**을 생성하며 `total_facility_annual_risk=null`입니다.
빈도를 계산했지만 모든 사건의 피해와 전체 시설 위험을 합산하지 않았다는 뜻입니다.
모든 예제는 합성 입력이며 실측 데이터나 검증된 시설 설계값이 아닙니다.

설치된 명령은 `.venv\Scripts\prism.exe --mode lh2 ...`로 실행합니다.
Linux/macOS에서는 `.venv/bin/python`, `.venv/bin/prism`을 사용합니다.
기존 `python tno.py`, `tno`, `lh2-tno`, `python -m lh2_tno.cli`도 호환용으로 유지합니다.
마지막 두 명령은 모드 선택 없이 LH2 경로를 직접 실행합니다.

### 모드 설정 파일

```json
{"mode": "lh2"}
```

```powershell
.venv\Scripts\python.exe prism.py --config lh2-tno/examples/prism_lh2_mode.json lh2-tno/examples/storage_terminal.json
```

설정은 `mode`, `backend`만 허용합니다. backend 상대경로는 **설정 파일 위치** 기준입니다.
CLI의 `--mode`·`--backend`가 설정값보다 우선합니다. 모드는 파일명으로 추정하지 않습니다.
CLI 시설·요청 상대경로는 작업 폴더 기준이며 backend 내부 모델 경로는 절대경로를 권장합니다.

## 입력 파일 작성

| 파일 | 내용 | 대응 예제 |
|---|---|---|
| `facility.json` | 환경, 부품, 포트, 연결, 수용점, 물성 기준 | [저장기지](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/storage_terminal.json), [충전시설](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/refuelling_station.json), [이송시설](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/transfer_station.json) |
| `frequency_plan.json` | 문헌 프로파일, 분류 근거, 수량/길이, 물리 범위, 제외 이유 | [계획](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/lh2_frequency_plan.json) + [시설](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/lh2_frequency_facility.json) |
| `consequence_request.json` | source 또는 설비 출구, 재고, 기상, 점화, 풀, 평가 시각/영역 | [요청](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/consequence_request.json) + [시설](https://github.com/lyullee/prism/blob/main/lh2-tno/examples/consequence_facility.json) |

**다른 예제 파일을 임의로 섞지 않습니다.** 부품 ID, 탱크 체적, 물성 기준, 출구와 재고가 일치해야 합니다.
일반 저장기지 예제의 탱크와 짧은 0.2 m³ 계산 예제는 다른 입력입니다.

| 시설 필드 | 작성 기준 |
|---|---|
| `configuration_origin` | `synthetic`, `reviewed_design`, `field_confirmed`: 실제 출처대로 선택 |
| `environment` | 스키마에는 여러 환경이 있으나 현재 전체 LH2 물리 경로는 `outdoor` |
| `components` | 고유 ID, 종류, ENU 좌표, 물성 기준, SI 설비 치수 |
| `ports` / `edges` | 실제 연결과 유동 방향·상 정의 |
| `property_basis` | Hydrogen/ParaHydrogen, CoolProp-HEOS와 엔탈피 기준 |
| `receptors` | 사람/피해 평가 지점의 ID·ENU 좌표 |

ENU는 동쪽(E)·북쪽(N)·위쪽(U)입니다. 길이 m, 온도 K, 압력 Pa, 유량 kg/s, 비엔탈피 J/kg을 사용합니다.
중복 ID, 잘못된 포트·상·방향과 물성/엔탈피 혼용을 거절합니다. 구성 검증만으로 전체 설비 동역학을 풀지는 않습니다.
정확한 필드는 [시설 계약](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/contracts.py), [피해 요청](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/consequences.py), [빈도 계약](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/frequency.py) 또는 스키마로 확인합니다.

```powershell
.venv\Scripts\python.exe -c "import json; from lh2_tno.consequences import ConsequenceRequest; print(json.dumps(ConsequenceRequest.model_json_schema(), ensure_ascii=False, indent=2))"
```

## 외부 모델 연결

시설 검증과 빈도 생성은 이 저장소만으로 가능합니다. 실제 방출·분산·화재/폭발에는 **외부 모델 소스와 실행 환경**이 필요합니다.
일반 source→풀→피해 경로는 `tno`, `slabx_lh2`, `slabx`, 그리고 풀 발생 시 `dynamiclh2poolx`를 사용합니다.
설비 출구 생성 operation에는 `lh2dt`도 필요합니다. 기록된 기체 출구만 소비하면 실행하지 않는 provider/pool은 필요 없습니다.

아래 코드를 `configure_backend.py`로 저장하고 실제 경로와 interpreter를 수정한 뒤 실행합니다.
`tno`는 qra.py/fire.py/risk.py 등이 있는 코드 폴더, 나머지는 각 Python 패키지 디렉터리 자체입니다.

```python
import json
from pathlib import Path
from lh2_tno.backend import tree_digest

roots = {
    "tno": Path("D:/models/legacy-qra/code"),
    "slabx_lh2": Path("D:/models/slabx-lh2/slabx_lh2"),
    "slabx": Path("D:/models/slabx/slabx"),
    "dynamiclh2poolx": Path("D:/models/pool/src/dynamiclh2poolx"),
}
config = {
    "interpreter": "D:/models/runtime/Scripts/python.exe",
    "timeout_s": 180.0,
    "packages": [
        {"name": name, "root": str(root.resolve()), "sha256": tree_digest(root)}
        for name, root in roots.items()
    ],
    "required_versions": {},
}
Path("backend.json").write_text(
    json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
)
```

`required_versions`에는 재현 실험에서 확인한 CoolProp/NumPy/SciPy 등의 실제 버전 문자열을 추가합니다.
위 예제는 비어 있으며 외부 runtime의 의존성을 PRISM 최소 설치가 자동 설치해 주지는 않습니다.
모델 연결 뒤 실제 계산과 출처를 확인해야 합니다. 소스 pin만으로 물리 호환성/정확도가 보증되지 않습니다.
실행 전후 소스 SHA-256, 실제 import 위치, 지정 버전과 timeout을 검사합니다.
소스가 변경되면 검토·검증·기록 후 pin을 갱신하고 매 센서 갱신마다 자동으로 새 해시를 승인하지 않습니다.

## 기본 분석 모드

`standard`는 외부 엔진의 `qra.py` 명령을 그대로 전달합니다. 기존 CSV와 LH2 JSON 입력은 서로 다릅니다.
backend에는 `tno` pin과 기존 엔진을 실행할 interpreter가 필요합니다.

```powershell
# 외부 엔진 옵션 확인
.venv\Scripts\python.exe prism.py --mode standard --backend standard_backend.json --help

# CSV 템플릿 생성
.venv\Scripts\python.exe prism.py --mode standard --backend standard_backend.json template --directory standard_inputs

# 입력을 검토·수정한 뒤 실행
.venv\Scripts\python.exe prism.py --mode standard --backend standard_backend.json run --name my-facility --sections standard_inputs/sections.csv --components standard_inputs/components.csv --ignition purple --blocking none --samples 0 --extent 100 --cell 10 --out standard_result.json
```

엔진 버전의 `--help`와 생성된 파일명을 확인하고 실제 설비로 입력을 수정합니다.
점화·차단·격자 옵션은 명시 선택한 예시이며 모든 시설의 추천 기본값이 아닙니다.
기존 엔진에는 GH2/LH2 screening도 있으므로 standard를 “고압수소 전용”으로 해석하지 않습니다.
결과에 `execution_mode=standard`와 소스 해시를 더하고 기존 수치·근거 판정을 유지합니다.

## LH2 피해영향 계산

```powershell
.venv\Scripts\python.exe prism.py --mode lh2 lh2-tno/examples/consequence_facility.json --backend backend.json --consequences lh2-tno/examples/consequence_request.json --output consequence_result.json
```

예제는 0.2초 방출의 합성 진단 계산입니다. 입력 빈도·점화·복사율을 시설 기본값으로 복사하지 않습니다.
지면 도달량이 없으면 풀을 만들지 않습니다. LH2가 지면에 도달하면 footprint와 바닥 물성/수치 격자를 별도 지정해야 합니다.

요청 작성 시 다음을 검토합니다.

- `source_input` 또는 `resolved_release` 중 정확히 하나 선택.
- 탱크 상태, 누출 구경·방향·높이, 재고와 방출 종료 근거.
- source와 dispersion의 동일 기상. 현재 무풍·실내·provider handoff 없는 수직 전용 출구는 미지원.
- 시계에 방출 종료/지연점화 시각 포함, 지연 연소 종료까지 평가.
- 점화 분기, 복사율 범위, 장애물 에너지 분율과 출처.
- 공간 영역·격자. 영역 밖 질량은 기록하지만 그 영역 밖의 피해는 계산하지 않음.

현재 피해 시계는 120초/500노드 이하, 공간 250,000셀 이하, source 100구간 이하 등의 예산을 적용합니다.
한도만 늘려 큰 시설의 정확도/실행시간 문제가 해결되지는 않습니다.
폭발은 multi-energy의 **두 압력 기준 구역**을 사용하며 연속 압력/충격량 곡선, DDT·폭굉은 지원하지 않습니다.

### 설비 provider의 액체·2상 출구 연결

설비 모델이 액체 방출을 직접 계산했다면 `ResolvedLiquidRelease`를 사용합니다. 이 경계에는 provider가 소유한 총 유량, flash된 대기압 기체 유량, 지면 액체 유량, 액적 도착 위치·시간, 전체 질량·엔탈피 장부가 들어갑니다. PRISM은 이 값을 다시 nozzle/flash 계산으로 바꾸지 않고, 기체는 근거리 전이와 SLABx로, 지면 액체는 DynamicLH2PoolX로 전달합니다. airborne liquid이 남아 있으면 암묵적으로 기체로 바꾸지 않고 중단합니다.

```powershell
# 외부 provider pin과 runtime을 검토한 뒤 한 건의 연결 진단 실행
$env:PYTHONPATH = "lh2-tno/src"
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_liquid_release.py
```

진단 산출물은 `lh2-tno/results/20261009/equipment_liquid_release/`에 저장됩니다. `verification.json`의 `full_chain_executed=true`는 설비 경계부터 피해 계산까지 연결됐다는 뜻이고, `physical_validation_claim=false`, `operator_limited=true`는 SLABx-LH2의 일정 upstream·분무 에너지·ballistic rainout 가정과 합성 시설 입력이 남아 있음을 뜻합니다. 이 경로는 실제 LayeredTank의 액체/2상 재고 소진, airborne droplet adapter, 현장 빈도와 시설 전체 연간 IR을 대신하지 않습니다.

### Python API

```python
import json
from pathlib import Path
from lh2_tno.contracts import Facility
from lh2_tno.backend import BackendConfig, IsolatedBackend
from lh2_tno.consequences import ConsequenceRequest
from lh2_tno.pipeline import ResearchPipeline

facility = Facility.model_validate_json(Path("facility.json").read_text(encoding="utf-8"))
config = BackendConfig.model_validate_json(Path("backend.json").read_text(encoding="utf-8"))
request = ConsequenceRequest.model_validate_json(Path("consequence_request.json").read_text(encoding="utf-8"))
pipeline = ResearchPipeline(facility, IsolatedBackend(config))
result = pipeline.consequences(request)
Path("result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
)
```

API 호출에는 CLI가 덧붙이는 `execution_mode` 표기가 자동 추가되지 않습니다.

## 빈도 산출과 적용

[빈도 catalogue](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/data/frequency_catalogue.json)는 검토한 Purple Book LOC 표와 기존 LH2 문헌 표 snapshot을 사용합니다.
각 행에 출처·원자료 해시·통계 의미·단위·한계를 보관하며 기관 인증이나 현장 빈도 검증을 뜻하지 않습니다.
원자료 검토는 [빈도 개발 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_LH2_v030_빈도모듈_개발기록_20261008.md)을 참고합니다.

| 항목 | 계산 |
|---|---|
| 부품당 빈도 | 문헌의 부품당 연간 빈도 × 수량 |
| 배관 길이당 빈도 | m당 연간 빈도 × 적용 길이 × 수량 × 근거 있는 보정계수 |
| 요구시 실패 | 요구 빈도 × PFD, 별도 계약 제공 |
| LH2 불확실성 | 문헌 중앙값과 로그정규 분산 근거로 구간별 주변 p05/p95 및 명시적 표본화 |

Purple 배관에는 최소 적용 길이 10 m와 flange 포함 범위가 있습니다. 포함 flange를 다시 더하지 않습니다.
`physical_scope_ids`로 동일 실물의 중복을 거절합니다. 같은 탱크의 Purple LOC와 LH2 면적구간 빈도를 모두 더하지 않습니다.
구간별 p05/p95를 합쳐 시설 전체 p05/p95라고 표시하지 않습니다. 로그정규 mu/sigma 표본화는 known contribution에만 적용하며, 모든 물리·기상·방호·점화 항은 고정합니다.
대기압 근처 극저온 탱크에 압력용기 프로파일을 자동 적용하지 않습니다.
진공 상실·정상 벤트 요구·대기압 저장탱크 전용 기인 빈도는 보완 항목입니다.
미지원 프로파일은 GH2/OREDA로 암묵 대체하거나 0으로 만들지 않습니다.

### 사건별 피해와 결합

먼저 생성한 events에서 실제 ID·부품·구멍 크기·범위를 확인합니다. 다음 placeholder를 실제 사건 ID로 바꿉니다.

```powershell
.venv\Scripts\python.exe prism.py --mode lh2 facility.json --frequency-plan frequency_plan.json --event-id 검토한_사건_ID --backend backend.json --consequences matching_request.json --output matched_result.json
```

빈도 계획과 피해 요청을 함께 주면 `--event-id`가 필수입니다. 현재 기본 binding은 일치하는 **단일 부품 구멍 사건**이며,
누출 구경·부품·노출 범위·방출 종료·service를 대조합니다. source는 탱크/용기 구멍 사건,
설비 경계는 명시된 accidental leak이어야 합니다. GH2/cold-GH2에 LH2 빈도를 붙이지 않습니다.
순간 전량과 최대 relief는 사건을 생성해도 새 피해 경로에 자동 결합하지 않습니다. 양단 파단은 `ResolvedGasReleaseSet`에 두 provider 출구를 모두 선언하고
`equipment_two_sided_rupture`를 선택하면 두 출구를 각각 피해 계산한 뒤 한 사건의 Frechet 상한으로 결합합니다. `TNO_PIPE` 길이/수량 빈도를 한 위치에 배정할 때는 `location_weight`와 근거를 함께 선언해야 합니다. 교차 plume·압력·재고 상호작용은 아직 operator-limited로 기록됩니다. 600초 전량은 기체 provider의 `equipment_inventory_over_600s` 또는 액체·2상 provider의 `equipment_liquid_over_600s` operator와 `inventory_over_600s` 종료 근거를 선언하고 provider가 600초 전체 이력을
반환해야 binding할 수 있습니다. 현재 합성 campaign은 이 완전 이력을 제공하지 않아 G2를 미계산으로 유지합니다.
빈도만으로 임의의 짧은 누출 시간은 정당화되지 않습니다.

양단 파열 provider 입력은 `prism.resolved_release_set.v1` 최상위 packet으로 묶습니다. `releases`에 두 개의 `prism.resolved_release.v1` endpoint를 넣고 공유 재고·사건 ID를 한 번 선언하면, `scripts/build_provider_request_catalog.py`와 `scripts/build_equipment_campaign.py`의 `--release-kind two_sided_rupture`가 전용 adapter를 사용합니다. endpoint를 복사해 단일 누출로 바꾸거나 사건 빈도를 두 번 부여하지 않습니다.

### 문헌 빈도 불확실성과 상관 가정

현재 현장 사고 건수와 관찰 노출 자료는 없습니다. **문헌 기본선 + 불확실성·민감도를 사용하며
개발/첫 IJHE 논문에 현장 빈도 수집을 필수 조건으로 두지 않습니다.** `literature_frequency_uncertainty`
는 자산별로 같은 분위수를 모든 LOC에 적용하는 `within_asset_shared_quantile`과, 각 사건에
분위수를 따로 지정하는 `independent_event_bounds`를 명시적으로 비교할 수 있습니다. 이는 상관 가정
민감도 비교이며, 별도 distribution API는 catalogue에 공개된 로그정규 mu/sigma가 있는 사건만 표본화합니다. 현재 사례처럼 미계산·operator-limited 경로가 있으면 known-contribution 구간으로만 보고하고 시설 전체 credible interval로 부르지 않습니다.

분포 표본화는 다음처럼 실행합니다. 입력 파일은 `examples/frequency_distribution_diagnostic.json` 형식의 두 시나리오 배열입니다.

```powershell
python prism.py --mode lh2 facility.json --backend backend.json --risk-campaign campaign.json `
  --frequency-distribution examples/frequency_distribution_diagnostic.json `
  --frequency-distribution-draws 2000 --frequency-distribution-seed 20261009 `
  --output distribution_result.json
```

출력의 `literature_frequency_distribution.scenarios[*]`는 known contribution의 p05/p50/p95와 사건별 표본 빈도를 담습니다. `asset_rank_stability`에는 각 빈도 표본에서 계산된 기대 사망 기여도의 평균 순위와 1위 확률을 낮은/높은 복사율 끝점별로 기록합니다. 동률은 자산 ID로 결정해 재현성을 확보합니다. 표본화는 저장된 피해 원자를 다시 가중하므로 SLABx-LH2나 확산 물리를 반복 실행하지 않습니다. 이 순위는 계산된 known contribution 안에서만 유효하며, 미계산 사고를 포함한 시설 전체 우선순위를 뜻하지 않습니다.
캠페인 기본 결과의 `coverage.by_component`에는 시설의 각 탱크·배관·밸브·펌프 등에 대해 생성된 사건 수, 개시빈도, 실행/미계산 건수와 명시적 제외 사유가 들어갑니다. `PARTIAL` 또는 `EXCLUDED` 설비가 남아 있으면 합산값을 전체 시설 위험으로 표시하지 않습니다.
실증 P/T/유량은 물리 검증에 쓰지만 사고 건수·관찰 설비수·기간을 대신하지 않습니다.
확인된 사고와 동일 범위의 관찰 노출이 생기면 선택형 Gamma-Poisson 업데이트 계약을 적용할 수 있습니다.
경보 건수를 누출 건수로 세거나 문헌 로그정규 분포를 근거 없이 Gamma로 바꾸지 않습니다.

## 설비와 디지털트윈 연결

### 설비별 결합

시설 부품/포트 ID를 설비 모델 출구에 대응시켜 **지원되는 방출 경계를 사건별로** 전달합니다.
이미 계산된 기화기·벤트 출구 유량을 받으면 탱크 누출식을 다시 풀지 않습니다.
등록한 모든 부품의 임의 누출을 즉시 지원하는 것은 아닙니다.

`ResolvedGasRelease`에는 PH·엔탈피 기준·단면적·밀도·속도·유량·시계·누적 질량/정적 엔탈피와 provider 해시가 필요합니다. 포트에 `position_enu_m`을 선언하면 provider 방출 좌표도 같은 위치여야 합니다. 양단 파열은 `ResolvedGasReleaseSet`이 동일 사건 ID·공유 재고·서로 다른 outward 포트·두 위치를 검증합니다.
현재 수평 또는 `VerticalGasHandoff`로 수평 단면을 선언한 수직 출구의 대기압·Mach≤0.3 기체와, provider가 flash·지면 액체·액적 도착을 완결한 `ResolvedLiquidRelease`를 허용합니다. 액체/2상 경계에는 `phase=liquid` 또는 `phase=two_phase`인 outward facility port가 필요합니다. airborne liquid, 실제 설비의 LayeredTank 액체/2상 재고 feedback, provider handoff 없는 수직 제트·고압 팽창 출구는 추가 adapter가 필요합니다. 합성 LayeredTank는 별도 양수 임계값 진단으로 재고 feedback 경로를 확인했습니다. 수직 handoff와 provider liquid 경로도 synthetic provider 경계와 downstream 교차상호작용 미해결 때문에 operator-limited입니다.
외부 `LayeredTankNetworkSimulator` 결과는 `scripts/audit_layered_tank_boundary.py`로 먼저 감사할 수 있습니다. 탱크 재고·포트·링크 유량이 있어도 대기압 출구, flash/지면/비산 액체 분할, 출구 형상, 종료 계약이 없으면 `ResolvedLiquidRelease`로 승격하지 않습니다. 액체 포트를 101,325 Pa 경계에 연결한 probe는 대기 경계까지 확인했지만 동일한 누락으로 승격이 보류되었습니다. 실제 provider 실행 결과와 판정은 [LayeredTank 경계 감사 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_LayeredTank_경계감사_개발기록_20261009.md)에 보존합니다.
`liquid_atmospheric_probe_export.json`은 `scripts/validate_layered_tank_slabsx_bridge.py`로 SLABx-LH2에 넘길 수 있습니다. 이 브리지는 LayeredTank의 전체 유량을 최종 질량 장부로 유지하고, SLABx의 flash·액적/지면 분할만 사용합니다. 첫 구간 유량 상대 오차는 2.4529%로 5% gate 안에 있었고, `ResolvedLiquidRelease` 검증과 풀·확산·점화·피해까지 전체 진단을 실행했습니다. 결과는 `results/20261009/equipment_layered_tank_slabsx/`에 저장되며, 책임 분리와 한계는 [LayeredTank–SLABx 브리지 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_LayeredTank_SLABx_브리지_개발기록_20261009.md)에 설명합니다. 이 결과는 합성 probe의 연결 검증이며 LayeredTank 전체 설비 모델·현장 보정·시설 전체 연간 위험 완성을 의미하지 않습니다.
`validate_layered_tank_inventory_slabsx.py`는 외부 `lh2dt.LayeredTankNetworkSimulator`를 0.5초씩 다시 실행하며 탱크 상태를 다음 구간에 feedback합니다. 누적 provider 질량 장부로 구간 평균 유량을 만들고 양수 재고 임계값에서 종료한 뒤 같은 SLABx·PRISM 체인을 실행합니다. 16개 구간/8초, provider 최대 질량 잔차 `5.65e-18 kg`, 최대 에너지 잔차 `1.34e-8 J`, PRISM 최종 잔차 `0 kg`을 확인했습니다. 결과는 `results/20261009/layered_tank_inventory_slabsx/`와 [재고 feedback 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_LayeredTank_SLABx_브리지_개발기록_20261009.md)에 보존합니다. 임계값·형상·밸브는 합성값이며 실제 설비의 완전 재고 소진이나 시설 전체 QRA를 뜻하지 않습니다.
`validate_layered_tank_frequency_campaign.py`는 provider 개구를 문헌 사건의 개구와 대조한 뒤 정확히 일치하는 한 개 사건만 `bind_event()`로 연결합니다. 이번 진단은 저장탱크·격리밸브·이송배관 15개 LOC를 생성하고, 0.001 m 개구와 저장탱크 `AREA_0.01%`만 연결했습니다. 나머지 14개 LOC는 두 기상 조건에서 미계산으로 기록했습니다. 문헌 p05/중앙/p95와 공개 로그정규 표본은 저장된 위험 원자를 재가중하며 물리를 다시 계산하지 않습니다. 결과는 `results/20261009/layered_tank_frequency_campaign/`와 [문헌빈도 연결 기록](docs/PRISM_LayeredTank_문헌빈도_시설연결_20261009.md)에 보존합니다.
정상 벤트에 사고누출 빈도를 붙이지 않습니다. emergency relief도 기인 사건/요구 의미를 별도 검토합니다.
상세: [경계 계약](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/equipment_boundary.py), [설비 연결 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_LH2_v040_설비경계연결_개발기록_20261008.md).

### 탱크·밸브 차단 과도 경로

개발 진단에서는 `scripts/validate_equipment_isolation.py`가 외부 `lh2dt`의 `LayeredTankNetworkSimulator`와 `CommandedValve`를 호출합니다. 합성 LH2 탱크를 초기화하고, 각 문헌 `LH2_PIPE` area-bin마다 밸브 면적을 독립적으로 계산합니다. 각 area-bin에서 하나의 provider 실행은 밸브를 0.25초까지 열어 둔 뒤 닫고, 다른 실행은 차단 실패로 0.5초 진단시계까지 열어 둡니다. provider가 반환한 각 시간구간의 유량·출구 PH·밀도·면적·속도를 `ResolvedGasRelease`로 변환하고, 5개 LOC의 두 분기를 시설 campaign에 연결합니다.

이 경로에서 확인한 것은 **5개 누출 크기 각각에서 명령된 차단 성공과 명시적 차단 실패가 서로 다른 방출 이력으로 피해계산에 전달되는지**입니다. 성공 분기는 0.25초 뒤 유량이 0이 되고, 실패 분기는 0.5초 진단시계 동안 유량이 남습니다. 질량·에너지 잔차도 각 분기에 기록됩니다. 5개 LOC × 2개 차단 분기 × 2개 기상으로 20건이 실행되며 `UNCOMPUTED` 사례는 0건입니다. 차단 성공확률 `0.99`는 합성 분기값이며, 실제 actuator 지연·고장확률·재고 소진을 추정하지 않습니다. 이 transient campaign 자체에는 액체·2상 경계가 없지만 별도 `validate_equipment_liquid_release.py`가 provider liquid/two-phase 출구 1건을 pool·피해까지 연결합니다. 결과는 `results/20261009/equipment_isolation_campaign/`와 `results/20261009/equipment_liquid_release/`에 저장하며, 합성 진단시계와 합성 장벽 때문에 시설 전체 연간 위험도는 `null`로 남깁니다.

개발 환경에서 이 진단을 다시 실행하려면 외부 provider 경로가 현재 스크립트와 같아야 합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_isolation.py
```

이 명령은 provider transient 성공·실패 이력을 각각 계산한 뒤 두 기상 조건의 시설 사례에 전달합니다. 실행시간은 PC·격자·시계에 따라 달라지며, 결과의 `verification.json`과 `campaign_result.json`을 함께 확인합니다.

600초 전량방출의 연결 진단은 다음 명령으로 재현합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_long_horizon_inventory.py --allow-pin-refresh
```

이 진단은 합성 10 m³ 탱크와 100000 W 벽면열을 사용해 600초 provider 이력을 만들고 전체 피해 체인을 실행합니다. 결과는 `EXECUTED_DIAGNOSTIC_ONLY`와 `facility_validation=WITHHELD`로 기록되며 실제 설비 QRA로 해석하지 않습니다.

### 양수 재고 기준으로 방출을 끝내는 경로

`scripts/validate_equipment_inventory.py`는 외부 `lh2dt`의 `HomogeneousTank`와 `DynamicNetworkSimulator`를 한 provider 구간씩 실행합니다. 탱크 질량이 선언한 양수 `threshold_mass_kg` 이하가 되면 그 구간의 실제 유량·엔탈피를 저장하고 종료합니다. 0 kg 상태를 강제로 만들거나 마지막 유량을 40초까지 늘리지 않습니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_equipment_inventory.py
```

현재 다섯 `LH2_PIPE` area-bin을 두 기상 조건에 연결하여 **10건 실행·0건 미계산**으로 기록했습니다. provider는 모두 `inventory_depletion`으로 종료했고, `AREA_100%`의 남은 질량은 `1.0793e-4 kg`, 다섯 사례의 최대 질량 잔차는 `1.34e-20 kg`, 최대 에너지 잔차는 `1.69e-13 J`였습니다. 이번 신규 물리 계산시간은 약 1.59–2.31초/건, 전체 약 20.85초였습니다. 결과는 `results/20261009/equipment_inventory_campaign/`에 저장합니다. declared-scope IR/F-N은 계산되지만 합성 시설 입력이므로 실제 시설 QRA로 보고하지 않습니다.

이 경로는 탱크 상태에서 피해까지 연결되는 종료 계약을 검증한 것입니다. 초기 상태·탱크 크기·밸브·기체 offset은 합성값이며, 액체/2상 flash, high-Mach jet, actuator 신뢰도, 실제 설비 calibration과 독립 물리검증은 포함하지 않습니다. 자세한 경계와 산출물은 [재고 소진 연결 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_재고소진_연결_개발기록_20261009.md)을 봅니다.

### 수직 벤트 handoff 진단

수직 포트 자체를 downstream 모델이 자동으로 수평으로 바꾸지 않습니다. 설비 provider가 수직 출구와 함께 수평 handoff 위치·방향·속도·밀도·온도·수소 질량분율·단면 크기를 `VerticalGasHandoff`로 제공할 때만 PRISM이 그 단면부터 SLABx-LH2/SLABx 경로를 시작합니다. handoff가 없는 수직 출구, 수직·수평이 섞인 방향, 음의 downwind 성분은 오류 또는 `UNCOMPUTED`로 남습니다.

현재 synthetic handoff 진단은 다음과 같이 실행합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/validate_vertical_vent.py
```

`AREA_100%` 경로와 두 기상 조건의 2건을 실행하고, 나머지 네 area-bin은 provider handoff가 없다는 이유로 명시적 `UNCOMPUTED`로 남깁니다. 결과는 `results/20261009/vertical_vent/`의 `campaign_result.json`, `resolved_release.json`, `verification.json`에 저장합니다. 이 경로는 variable-state synthetic adapter이므로 실제 수직 제트 부력·장애물·교차 plume와 현장 handoff를 검증한 것이 아닙니다.

새 프로세스로 처리시간을 반복 측정하려면 다음을 실행합니다.

```powershell
.venv\Scripts\python.exe lh2-tno/scripts/benchmark_vertical_vent_timing.py --repeats 3
```

이번 3회 탐색 측정에서 campaign 내부 신규 물리시간은 p50 `7.170 s`, p95 `7.352 s`, p99 `7.368 s`였고, 프로세스 시작·외부 provider 로딩을 포함한 wall time은 p50 `12.005 s`, p95 `12.245 s`, p99 `12.266 s`였습니다. 이는 1 Hz 실시간 처리나 운영 SLA를 입증하지 않으며 `results/20261009/vertical_vent_timing/benchmark.json`에 저장합니다.

### 센서 갱신

```text
센서 → 단위/위치/품질/시간 검증 → 알려진 누출의 탱크 P/T 갱신
→ 동일 조건이면 캐시, 변경이면 새 계산 → 결과와 자료 나이 표시
```

`TelemetryNormalizer`는 절대압/게이지압·대기압·위치·단위·품질·시간순서·나이를 검사합니다.
현재 서비스가 source 갱신에 사용하는 것은 지정한 탱크 P/T입니다. 수위/농도 정규화가 자동 역추정을 뜻하지 않습니다.
설비 resolved 출구를 원시 P/T로 덮어쓸 수 없고 provider가 새 경계를 생성해야 합니다.
위 API의 `pipeline`, `request`에 이어서 사용할 수 있습니다.

외부 설비 디지털 트윈을 실제 갱신 경계로 사용할 때는 `release_resolver`를
명시적으로 넘깁니다. resolver는 정규화된 센서 상태를 받아 이미 검증된
`ConsequenceRequest`를 반환해야 하며, 그 안에는 `ResolvedGasRelease`,
`ResolvedGasReleaseSet` 또는 `ResolvedLiquidRelease` 중 정확히 하나와 종료근거가
있어야 합니다. PRISM은 이 경계에서 누출 크기·지속시간·빈도·방출 프로파일을
추정하지 않습니다.

```python
from lh2_tno.service import ConsequenceService

def equipment_release_resolver(template, normalized):
    # 외부 lh2dt/공정 모델이 normalized를 사용해 계산하고,
    # provider_release adapter로 만든 ConsequenceRequest를 반환한다.
    return provider_request_from_equipment_model(template, normalized)

result = service.update_from_telemetry(
    request, normalized, pressure_tag="P", temperature_tag="T",
    release_resolver=equipment_release_resolver,
)
```

이 경로의 결과에는 `telemetry_boundary.equipment_release_resolved=true`가
남습니다. resolver가 일반 source 입력을 반환하거나, provider 경계를 넣지 않거나,
빈도를 함께 넣으면 즉시 거절됩니다. 따라서 센서 기반 빈도 학습과 알려지지 않은
누출 크기 역추정은 여전히 수행되지 않습니다.

```python
from lh2_tno.service import ConsequenceService
from lh2_tno.telemetry import Frame, TagMapping, TelemetryNormalizer

mappings = (
    TagMapping(tag="P", component_id="storage", quantity="pressure", source_unit="Pa",
               pressure_basis="absolute", sensor_location="tank"),
    TagMapping(tag="T", component_id="storage", quantity="temperature", source_unit="K",
               sensor_location="tank"),
)
normalizer = TelemetryNormalizer(mappings, maximum_age_s=2.0)
frame = Frame.model_validate_json('''{
  "stream_id":"demo", "sequence":1, "source_time_s":100.0, "arrival_time_s":100.1,
  "origin":"synthetic",
  "values":{"P":{"value":600000.0,"unit":"Pa","quality":"valid"},
            "T":{"value":20.893,"unit":"K","quality":"valid"}}
}''')
normalized = normalizer.normalize(frame, now_s=100.2)
service = ConsequenceService(pipeline, capacity=16)
result = service.update_from_telemetry(request, normalized, pressure_tag="P", temperature_tag="T")
```

frame 단위 deadline 장부가 필요하면 같은 서비스를 monitor로 감쌉니다.

```python
from lh2_tno.service import RealtimeConsequenceMonitor

monitor = RealtimeConsequenceMonitor(service, period_s=1.0, deadline_s=1.0)
result = monitor.update_from_frame(
    request, normalizer, frame, now_s=100.2,
    pressure_tag="P", temperature_tag="T",
)
print(result["realtime"]["deadline_status"])  # MET 또는 MISSED
```

시간은 동일 시계 기준이며 synthetic을 실측으로 표시하지 않습니다. 현재는 동기 API입니다.
`RealtimeConsequenceMonitor`를 사용하면 정규화된 frame마다 처리시간·입력자료 age·정확한 cache hit/fresh physics 여부·deadline 초과를 한 장부에 기록할 수 있습니다. deadline을 넘긴 결과는 오래된 결과로 조용히 대체하지 않고 `realtime.deadline_status=\"MISSED\"`로 남깁니다. 이 monitor는 빈도 학습·누출 크기 역추정·스케줄러를 제공하지 않으며, OPC-UA/MQTT 수집기·HTTP 서버·운영 화면과 비동기 스케줄러는 별도 개발해야 합니다.
이전 짧은 로컬 사례는 신규 기체 약 3초, 풀 약 7–10초, 동일 요청 캐시 약 20–40 ms였습니다.
모든 시설/PC의 성능을 보장하지 않으며 **캐시 응답속도가 신규 물리 계산 1 Hz를 뜻하지 않습니다.**

## 출력 해석

`--output` 파일에 전체 결과를 저장합니다. 콘솔의 짧은 status만으로 피해를 판정하지 않습니다.

| 필드 | 뜻 |
|---|---|
| `data.status=END_TO_END_DIAGNOSTIC_EXECUTED` | 지원 가정에서 전체 경로 실행 완료 |
| `physical_validation_claim=false`, `facility_validation=WITHHELD` | 물리/시설 검증 완료 주장 보류 |
| `data.mass_ledger` | 방출·기체·풀·잔류·영역 이탈 질량 장부 |
| `data.explosion.domain_truncated` | 영역 밖 질량으로 폭발 평가가 잘렸는지 |
| `data.receptors` | 지점별 농도, 열유속/용량, 압력 구역과 피해 |
| `harm_given_observed_release_low_high` | 이미 누출이 발생한 조건의 점화 반영 피해 |
| `annual_current_weather_contribution_low_high` | 단일 사건 현재 기상 연간 기여, 빈도 결측은 null |
| `first_initiation_harm_probability_low_high` | 아직 미발생 사건의 시간 내 첫 발생·피해, initiation 결측은 null |
| `elapsed_ms`, `stage_elapsed_ms` | 전체 backend와 단계 실행시간 |
| `service.exact_cache_hit` / `fresh_physics_this_update` | 서비스 캐시와 새 계산 구별 |
| digest / `environment` | 입력·모델 소스·설정·의존성 출처 |

지점별 필드는 `data.receptors` 안에 있습니다. low/high는 주로 지정한 복사율 범위 결과이며 통합 95% 신뢰구간이 아닙니다.
질량 폐합은 전체 에너지 폐합 증명과 다릅니다.
단일 사건 현재 기상 연간 기여는 개념적으로 `빈도 × 사건조건부 피해 × 재실확률`입니다.
전체 연간 IR에는 모든 기인 사건·점화/차단·연간 기상 분포가 필요합니다.
[risk.py](https://github.com/lyullee/prism/blob/main/lh2-tno/src/lh2_tno/risk.py)의 합산 산술은 기상 합·중복·결측을 검사하지만 전체 시나리오 자동 계산기는 아닙니다.
F-N에는 인구 분포와 같은 사건의 피해자수 정의도 필요합니다. LH2 한 요청 결과를 시설 IR/F-N으로 표시하지 않습니다.

## 검증과 후속 개발

```powershell
.venv\Scripts\python.exe -m pytest -q lh2-tno/tests -c lh2-tno/pyproject.toml
.venv\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation ./lh2-tno -w wheelhouse
```

### 물리 검증 근거의 범위

외부 DynamicLH2PoolX Stage-C 자료는 지면에 도달한 유입의 축대칭 풀 증발·확산 구성요소를 hold-out 자료로 제한 검증합니다. 물 Trial 4 반경 RMSE는 `0.1374 m`, 알루미늄 Trial 6은 `0.1016 m`, 두 영상 구간 포함률은 `1.0`, HSE Test 6 질량 잔차는 `8.24e-13 kg`입니다. PRISM은 이 자료의 원자료 목록과 모델·manifest 해시를 [물리 검증 근거 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_물리검증_근거_20261009.md)으로 보관합니다.

현재 외부 snapshot의 `dynamic_validation_protocol.json` 선언 해시가 evidence JSON과 달라 상태를 `DECLARED_EVIDENCE_WITH_SOURCE_HASH_DRIFT`로 기록했습니다. 엄격 검증은 중단하고, 감사 모드만 지표와 불일치 파일을 보존합니다. 이 구성요소 증거는 설비 방출·대기 확산·점화·IR/F-N 전체 체인의 물리 검증이나 현장 절대위험 검증을 의미하지 않습니다.

공개 v0.6.0은 단위·계약·보존·모드 검사 154개로 고정되어 있고, 현재 0.6.2 개발 소스는 LayeredTank 경계 감사·유량 gate·endpoint enthalpy·액체 빈도 binding·일반 설비 매니페스트 계약·CLI 승격·빈도 범위 감사·외부 provider evidence audit·센터 시나리오 증거 감사·주요 사고 범위 매트릭스·양단 provider release-set adapter 검사를 포함해 **304개**를 통과합니다. 별도 실행 진단은 steady 설비 경계와 5개 transient LH2 pipe LOC의 성공·실패 분기 20건, 다섯 area-bin 양수 재고 종료 경로의 두 기상 조건 10건, LayeredTank의 문헌 `LH2_VESSEL` 정확 개구 1개와 두 기상 조건의 시설 campaign을 통과시켰습니다. 어느 숫자도 독립 실험 검증을 대신하지 않습니다.
GitHub Actions에서 portable 검사와 wheel catalogue/명령 포함을 확인합니다.
새 안내의 도움말·시설·빈도 예제도 깨끗한 소스 export에서 확인합니다.
`validate_*.py`는 개발 PC 경로와 이전 결과를 참조할 수 있어 클론 직후의 일반 사용 명령이 아닙니다.
v0.5 모드 검증의 설비 경계는 v0.4 기록 재생이며 최신 live provider를 재실행한 결과가 아닙니다.

우선 개발 항목:

1. 전체 시설 LH2 사건/source/종료·위치 배분, 점화·차단·기상과 IR/F-N 결합.
2. LayeredTank PH nozzle/flash와 액체·2상 재고 feedback, airborne droplet adapter, provider handoff 없는 수직·팽창/high-Mach 출구 확장과 handoff 물리검증.
3. 양수 재고 종료 경계를 실제 탱크·배관·밸브·펌프 조건과 액체/2상 flash, actuator 지연·실패 분기로 확장하고 전량 방출·양단 교차상호작용·실제 수직 jet을 별도 사건으로 검증.
4. 방출·풀·확산·화재/폭발 독립 검증과 관측 연산자.
5. 프로파일 적용 민감도·상관을 반영한 전체 위험 불확실성.
6. 신규 계산 가속, 검증된 surrogate/사전 계산, 비동기 요청·유효시간 정책.

IJHE 연구는 설비 경계·질량/시간 일관성·문헌 빈도·조건부 피해의 연결과 검증 범위를 명시합니다.
현장 빈도 학습/1 Hz 완료를 선행 주장하지 않습니다. [IJHE 프로토콜](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/IJHE_연구프로토콜.md).

## 문제 해결과 개발 기록

| 문제 | 확인 사항 |
|---|---|
| 명령 못 찾음 | 설치한 가상환경 실행 파일 또는 그 Python의 prism.py 사용 |
| backend 요구 | 기존 엔진/외부 모델 경로·해시·interpreter 설정 |
| source revision mismatch | 실제 소스 변경 검토·검증 후 pin 갱신 |
| import/version mismatch | 패키지 디렉터리·runtime·버전 확인 |
| event-id 오류 | 계획+피해 요청에는 실제 일치 사건 ID 필수 |
| 물리 범위 중복 | 같은 실물의 대체 빈도를 중복 합산하지 않음 |
| PH/유량/시계/질량 오류 | 단위·엔탈피·경계·명령/종료 시간·누적 장부 대조 |
| stale/duplicate/unknown tag | 시계·나이·품질·매핑 확인 |
| deadline exceeded | 원인/격자/환경 검토, 오래된 결과로 자동 대체하지 않음 |
| null/WITHHELD | 결측·미검증 표시이며 0/안전 판정이 아님 |

- [현재 상태 JSON](https://github.com/lyullee/prism/blob/main/lh2-tno/CURRENT_STATUS.json)
- [구조와 저장소 관리](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/모듈구조와_GitHub_관리.md)
- [PRISM v0.6.0 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_v060_명칭과사용안내_20261008.md)
- [기존 기능 66개 목록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_위험성평가_구축기능_상세목록_20261008.md)
- [전체 연결](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/방출부터_최종피해_연결완료_20261008.md)
- [빈도 v0.3](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_LH2_v030_빈도모듈_개발기록_20261008.md)
- [설비 경계 v0.4](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_LH2_v040_설비경계연결_개발기록_20261008.md)
- [모드 v0.5](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/TNO_LH2_v050_옵셔널모드_개발기록_20261008.md)

이전 문서의 TNO-LH2 명칭·로컬 경로는 당시 기록입니다. 제품과 새 저장소 이름은 PRISM이고 이전 Git 이력은 보존합니다.
외부 소스·책·원계측 자료·로컬 원고는 이 저장소에 포함하지 않습니다.

## 배포와 인용

- [PRISM 0.6.2 PyPI·DOI 배포 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_v062_PyPI_DOI_배포기록_20261009.md) / [이전 0.6.0 기록](https://github.com/lyullee/prism/blob/main/lh2-tno/docs/PRISM_v060_PyPI_DOI_배포완료_20261008.md)
- Python 배포명: **prism-risk**, 버전 **0.6.2**, 라이선스 **MIT**.
- [PyPI 프로젝트](https://pypi.org/project/prism-risk/0.6.2/) / [Zenodo v0.6.2 DOI](https://doi.org/10.5281/zenodo.23246944).
- 버전 고정 인용은 **10.5281/zenodo.23246944**, 전체 버전 인용은 [10.5281/zenodo.23241358](https://doi.org/10.5281/zenodo.23241358)입니다.
- [CITATION.cff](https://github.com/lyullee/prism/blob/main/CITATION.cff)에 소프트웨어 인용 정보를 보관합니다.
- DOI는 소프트웨어 버전 기록이며 IJHE 논문 DOI나 물리 검증 인증이 아닙니다.
- v0.6.2의 PyPI 공개 배포와 DOI 발행·연결 확인을 완료했습니다. 등록 상태와 commit/workflow 영수증은 `CURRENT_STATUS.json`과 [배포 기록](docs/PRISM_v062_PyPI_DOI_배포기록_20261009.md)에 보관합니다.

```powershell
python -m pip install prism-risk==0.6.2
prism --describe-modes
```

외부 모델 없이 시설 검증과 문헌 빈도 생성이 가능합니다. source/확산/피해 물리 계산은 별도 검토된 provider가 필요합니다.
MIT는 PRISM 자체 배포 파일에 적용하며 외부 모델과 원자료의 라이선스·재배포 권한을 변경하지 않습니다.
