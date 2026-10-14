# PRISM HAZOP·운전 모드 시나리오 연결

통합 흐름도는 [`docs/figures/lh2_integrated_risk_flow.svg`](figures/lh2_integrated_risk_flow.svg)에서 확인할 수 있다. 현장 상태와 운전 모드가 HAZOP 판단으로 함께 들어가며, 이후 설비 공정 모델·방출/빈도 모델·SLABx-LH2·점화/노출 모델·통합 QRA가 같은 계산 계층에서 결합된다.

## 역할

현장 입력에는 압력·온도·유량 같은 값과 `operating_mode`가 함께 들어온다. `HazopTable`은 이 조합을 기준으로 HAZOP 이탈을 판정한다. 예를 들어 같은 높은 압력이라도 인수·공급·대기 모드에서 적용할 이탈 기준과 사고 시나리오가 다를 수 있다.

```text
센서/공정상태 + 운전모드
        ↓
HAZOP row의 component_id·mode·signal·threshold 비교
        ↓
정성 이탈과 원인·결과·기존 방호 기록
        ↓
사고 family와 release mode 선택
        ↓
외부 설비 provider의 사고방출 packet 요청
        ↓
SLABx-LH2/피해영향/점화/시설 IR·F-N 경로
```

이번 연결에서 HAZOP은 첫 네 단계만 담당한다. HAZOP 표만으로 누출 크기, 지속시간, 차단 성공률, 재고 소진 또는 빈도를 만들지 않는다. 선택된 행은 `provider_release_required=true`와 `REQUIRED_NOT_CREATED`를 가진다. provider packet이 없으면 downstream 결과는 `UNCOMPUTED` 또는 열린 증거 요청으로 남아야 한다.

## 입력 계약

`prism.hazop_operating_mode_selection.v1` 표에는 다음이 필요하다.

- 설비 ID와 일반 설비 종류(`storage_tank`, `pipe`, `valve`, `vent_stack`, `pump`, `vaporizer`, `reliquefier`)
- 적용 운전 모드 목록
- 읽을 상태 tag와 SI 물리량
- `above`, `below`, `at_or_above`, `at_or_below`, `outside_range` 중 하나와 명시적 기준값
- PRISM 사고 family와 release mode의 조합
- 이탈·원인·결과·방호·출처

`prism.hazop_state_frame.v1` 상태에는 `facility_id`, `component_id`, `operating_mode`, 계측 시각, 상태값과 출처가 필요하다. 각 값은 component와 quantity가 일치해야 한다. 운전 모드가 없거나 빈 문자열이면 HAZOP 선택을 수행하지 않는다.

정상 운전 runtime frame에도 `operating_mode`를 넣을 수 있다. `build_observed_state_runtime_frames`는 source 또는 최신 sample의 모드를 frame에 보존하고, `service_state_from_runtime_frame`은 provider resolver에 그대로 전달한다. 기존 mode 없는 정상 자료는 기존 상태 경로로 보존되지만, HAZOP 시나리오 선택에는 사용할 수 없다.

검증된 runtime frame은 `evaluate_hazop_runtime_frame(table, frame, now_s=...)`로 바로 선택기에 넣을 수 있다. 이 adapter는 먼저 frame/state digest와 상태 전용 필드를 검사한 뒤 모드를 HAZOP state로 옮긴다. 모드가 없으면 `HazopSelectionError`를 내고 계산을 진행하지 않는다.

실제 정량평가로 넘길 때는 `run_hazop_runtime_consequence(...)`를 사용한다. 이 함수는 먼저 HAZOP 결과가 하나의 활성 시나리오인지 확인하고, 그 다음에만 기존 runtime monitor의 `release_resolver`를 호출한다. resolver가 반환한 provider packet은 선택된 설비 종류·방출 형태·사고 family·종료 근거·source operator와 다시 대조된다. 불일치하거나 provider가 없으면 SLABx-LH2와 피해 계산을 호출하지 않는다. 여러 HAZOP 행이 동시에 활성화되면 각 사고 branch를 별도 provider 요청으로 분기해야 하므로 자동으로 하나로 합치지 않는다.

여러 행을 실제로 병렬 분기할 때는 `run_hazop_runtime_consequence_branches(...)`에 `scenario_id`별 resolver를 넘긴다. 각 행은 한 행짜리 HAZOP 계약으로 다시 평가되고, 각각의 provider 종료 근거와 source operator를 독립적으로 확인한 뒤 기존 consequence monitor를 호출한다. resolver가 없는 branch는 `CONSEQUENCE_BRANCHES_PARTIAL` 아래에서 별도로 보류되며 다른 branch의 결과를 0 위험으로 채우지 않는다.

## 결과 읽기

| 결과 | 뜻 |
|---|---|
| `SCENARIOS_SELECTED` | 모드와 이탈이 일치했고 선언된 사고 family를 선택함 |
| `SCENARIOS_SELECTED_WITH_OPEN_INPUTS` | 일부 다른 HAZOP 행이 신호 누락 등으로 열려 있으나 하나 이상의 시나리오는 선택함 |
| `NO_DEVIATION` | 적용 행의 값이 기준 안에 있음 |
| `NO_APPLICABLE_MODE_ROW` | 해당 설비·운전 모드 행이 없음. 다른 모드의 행을 재사용하지 않음 |
| `BLOCKED_OPEN_INPUTS` | 필요한 신호나 값이 없어 안전 상태로 판정하지 않음 |

선택된 시나리오에는 `scenario_id`, 설비·모드·family·release mode·측정값·기준값·출처가 포함된다. `policy`는 빈도추정, 센서 빈도학습, 방출 packet 생성, 피해 계산, 시설 QRA를 모두 `false`로 고정한다.

## 실행 예

```powershell
python scripts/evaluate_hazop_operating_mode.py `
  --table examples/generic_hazop_operating_modes.json `
  --state examples/generic_hazop_state_frame.json `
  --output results/hazop_current/selection.json
```

예제는 `receiving` 모드에서 저장탱크 고압 행을 선택한다. 이 결과는 synthetic diagnostic input이므로 실제 시설 HAZOP 검토나 QRA 자격을 의미하지 않는다. 실제 사용에서는 검토된 P&ID, HAZOP 회의 기록, mode/state tag 매핑과 provider 사고 export를 함께 공급해야 한다.

## 현재 범위와 다음 연결

이 모듈은 설비-neutral HAZOP 판단과 scenario dispatch boundary를 닫는다. 사고 family catalog와 provider packet catalog에 없는 사건은 선택하지 않으며, HAZOP 이탈이 있어도 빈도와 피해 결과를 자동으로 만들지 않는다.

현재 HAZOP·runtime mode 회귀검사는 27개, 전체 패키지 검사는 **961 passed**이다. 예제 실행은 `receiving` 모드의 고압 이탈 1건을 선택했으며, 방출 packet 0건·빈도추정 false·시설 QRA false를 기록했다. 별도 통합검사는 provider liquid packet이 기존 SLABx-LH2 consequence monitor까지 전달되는 경로와 두 개의 활성 HAZOP branch를 독립적으로 dispatch하는 경로를 실행했다. 실제 provider가 연결된 경우에도 HAZOP family와 packet의 source operator·종료 근거가 맞을 때만 기존 SLABx-LH2 consequence monitor로 전달된다.

남은 엄격 문턱은 실제 설비별 HAZOP·P&ID identity, provider의 차단·재고·종료 이력, 문헌 빈도 event binding, SLABx-LH2 독립 비교, 시설 전체 사고 family coverage와 IR/F-N 승격이다. 현재 검사센터 자료는 정상 상태 신호의 후보 입력으로만 취급한다.
