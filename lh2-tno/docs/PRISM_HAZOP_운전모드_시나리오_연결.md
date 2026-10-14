# PRISM HAZOP·운전 모드 시나리오 연결

통합 흐름도는 [`docs/figures/lh2_integrated_risk_flow.svg`](figures/lh2_integrated_risk_flow.svg)에서 확인할 수 있다. 현장 상태와 운전 모드가 HAZOP 판단으로 함께 들어가며, 이후 설비 공정 모델·방출/빈도 모델·SLABx-LH2·점화/노출 모델·통합 QRA가 같은 계산 계층에서 결합된다. PRISM은 특정 단일 모델을 대신하는 주인공이 아니라, 이 모델들을 동일한 시나리오 ID·설비 ID·운전 모드·시간축으로 연결하고 실행 순서를 조정하는 통합 실행 계층이다.

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

현장 tag 이름을 HAZOP 표와 맞춰야 할 때는 `values`의 tag를 그대로 쓰고 물리량을 함께 선언한다. 예를 들어 `{"tank_pressure": {"quantity": "pressure", "value_si": 650000.0}}`처럼 입력하면 runtime frame과 상태 snapshot 모두 `tank_pressure`를 보존한다. `pressure`·`mass_flow`처럼 물리량 이름을 key로 쓰는 기존 입력도 계속 지원한다. 임의 tag에 `quantity`가 없으면 상태 변환을 중단해 HAZOP가 다른 물리량을 추측하지 않도록 한다.

검증된 runtime frame은 `evaluate_hazop_runtime_frame(table, frame, now_s=...)`로 바로 선택기에 넣을 수 있다. 이 adapter는 먼저 frame/state digest와 상태 전용 필드를 검사한 뒤 모드를 HAZOP state로 옮긴다. 모드가 없으면 `HazopSelectionError`를 내고 계산을 진행하지 않는다.

실제 정량평가로 넘길 때는 `run_hazop_runtime_consequence(...)`를 사용한다. 이 함수는 먼저 HAZOP 결과가 하나의 활성 시나리오인지 확인하고, 그 다음에만 기존 runtime monitor의 `release_resolver`를 호출한다. resolver가 반환한 provider packet은 선택된 설비 종류·방출 형태·사고 family·종료 근거·source operator와 다시 대조된다. 불일치하거나 provider가 없으면 SLABx-LH2와 피해 계산을 호출하지 않는다. 여러 HAZOP 행이 동시에 활성화되면 각 사고 branch를 별도 provider 요청으로 분기해야 하므로 자동으로 하나로 합치지 않는다.

resolver가 반환한 `ConsequenceRequest` 또는 mapping에는 선택된 `operating_mode`가 자동으로 바인딩된다. 이미 다른 모드가 들어 있으면 gate가 `CONSEQUENCE_REJECTED`로 종료한다. 이 바인딩은 사고 빈도·누출량·차단 결과를 만들지 않고, HAZOP 선택 모드가 provider 방출 이후 피해 계산과 시설 원장까지 따라가는 식별자만 보존한다.

실시간 결과에서도 이 식별자를 확인할 수 있다. `RealtimeConsequenceMonitor`의 `telemetry_boundary.operating_mode`와 `equipment_release_path.operating_mode`가 같은 선택 모드를 보존하며, `FacilityRealtimeConsequenceMonitor`의 `equipment_release_path_accounting.component_rows`와 `operating_mode_counts`에도 설비별로 남는다. 저장된 synthetic mode trace 예제는 `receiving`·`supply`·`standby` 3개 설비를 모두 포함하고, 세 모드의 count가 각각 1인지 감사한다. 이 값은 화면·알람의 운전 맥락을 표시하기 위한 메타데이터이며, 누출 크기·방출 지속시간·빈도를 자동으로 만들지 않는다.

저장된 실시간 결과는 다음 감사기로 확인할 수 있다.

```powershell
python scripts/audit_realtime_hazop_mode_trace.py `
  --input results/realtime/current_facility_result.json `
  --output results/realtime/current_hazop_mode_trace_audit.json
```

이 감사기는 단일 모니터 결과와 시설 batch 결과를 모두 지원한다. 각 설비의 `telemetry_boundary`와 `equipment_release_path`가 같은 운전 모드를 가져야 하며, 시설 batch에서는 `operating_mode_counts`와 설비별 원장도 다시 일치해야 한다. 입력 결과가 없거나 모드가 빠지면 `REALTIME_HAZOP_MODE_TRACE_BLOCKED`로 남고, 정상 운전 자료에서 모드를 추정하지 않는다. 완료 감사에 연결할 때는 `scripts/build_ijhe_completion_audit.py --realtime-hazop-mode-trace ...`를 사용한다.

여러 행을 실제로 병렬 분기할 때는 `run_hazop_runtime_consequence_branches(...)`에 `scenario_id`별 resolver를 넘긴다. 각 행은 한 행짜리 HAZOP 계약으로 다시 평가되고, 각각의 provider 종료 근거와 source operator를 독립적으로 확인한 뒤 기존 consequence monitor를 호출한다. resolver가 없는 branch는 `CONSEQUENCE_BRANCHES_PARTIAL` 아래에서 별도로 보류되며 다른 branch의 결과를 0 위험으로 채우지 않는다.

여러 설비의 현재 상태를 함께 처리할 때는 `run_hazop_facility_runtime(...)`을 사용한다. 이 조정기는 설비별 HAZOP 선택, branch 결과, provider identity와 현재 기상 IR 기여를 하나의 원장으로 묶는다. 단일 branch와 검토된 빈도 바인딩이 있는 경우에만 현재 조건의 receptor별 IR 기여를 표시하며, HAZOP가 활성화한 branch를 시설 연간 IR/F-N으로 자동 승격하지 않는다. 시설 연간 결과는 전체 문헌 사건 목록·기상·인구·방호·미계산 사고 원장을 별도로 닫아야 한다.

다설비에서 같은 HAZOP 행 ID가 반복될 수 있으므로 현재 branch dispatch도 `(component_id, scenario_id)` resolver 키를 먼저 찾고, 없을 때만 기존 `scenario_id` 키를 사용한다. 실행 원장에는 선택된 키 범위를 남겨 설비 간 provider 방출이 섞이지 않았는지 확인할 수 있다.

## 현재·예측 경로를 한 번에 연결하기

디지털트윈 호스트가 현재 측정값과 미래 시뮬레이션값을 한 요청에서 관리해야 할 때는 `run_hazop_integrated_risk(...)`를 사용한다.

```python
from lh2_tno.integrated_risk import (
    build_hazop_facility_campaign_evaluator,
    run_hazop_integrated_risk,
)

facility_campaign_evaluator = build_hazop_facility_campaign_evaluator(
    annual_conditions=annual_conditions,
    scenario_bindings=scenario_bindings,
    expected_component_ids=tuple(component_bindings),
)

ledger = run_hazop_integrated_risk(
    hazop_table,
    current_frames,
    now_s=now_s,
    component_bindings=component_bindings,
    release_resolvers=release_resolvers,
    forecast_frames=predicted_frames,
    forecast_tables_by_component=tables_by_component,
    forecast_component_ids=tuple(tables_by_component),
    forecast_quantitative_evaluator=forecast_evaluator,
    facility_campaign_evaluator=facility_campaign_evaluator,
    # caller-owned callback: receives the completed forecast scan
    forecast_facility_campaign_evaluator=forecast_facility_campaign_evaluator,
)
```

이 호출은 먼저 `run_hazop_facility_runtime(...)`으로 현재 상태를 평가하고, 예측 frame이 제공된 경우 `run_hazop_forecast_risk_scan(...)`을 이어서 실행한다. `ledger.current`와 `ledger.forecast`는 원래 각 함수의 원장을 그대로 포함하고, `ledger.linkage`에는 현재·예측 설비 ID, 각 경로에서 확인된 운전 모드, 공통 `scenario_id`, 그리고 설비 범위가 포함된 `shared_component_scenario_keys`가 남는다. 따라서 같은 HAZOP 행 ID를 여러 설비가 재사용해도 화면이나 알람 시스템은 “지금 인수 모드에서 선택된 TK-01 시나리오”와 “예측 시점에 TK-02에서 도달한 같은 행 ID”를 서로 다른 사건으로 추적할 수 있다.

예측 frame을 넘길 때는 설비별 HAZOP 표를 반드시 함께 넘겨야 하며, 예측 정량평가기를 생략하면 위험조건 도달은 기록하되 `WITHHELD_NO_QUANTITATIVE_EVALUATOR`로 남는다. `facility_campaign_evaluator`를 연결하면 callback이 현재 runtime 원장을 기존 `build_hazop_facility_campaign_result(...)`에 넘겨 연간 기상·인구·점화·시설 ledger를 붙일 수 있다. 예측 결과를 시설 ledger에 연결할 때는 별도의 `forecast_facility_campaign_evaluator(forecast_scan)`를 넘긴다. 이 callback은 모든 예측 trigger와 정량평가 결과가 들어 있는 `ledger.forecast`를 받으며, scan에 보류 결과가 하나라도 있으면 통합 실행기가 callback을 호출하지 않고 `WITHHELD_FORECAST_FACILITY_CAMPAIGN_SCAN_WITHHELD`로 남긴다. callback이 없는 경우 `FORECAST_FACILITY_CAMPAIGN_NOT_REQUESTED`로 남고, unsafe frequency·physical-validation·facility-QRA claim은 `WITHHELD_UNSAFE_FORECAST_FACILITY_CAMPAIGN_RESULT`로 차단한다. 통합 함수의 결과는 `diagnostic_only=true`, `frequency_inference_performed=false`, `facility_qra_promotion=false`를 유지한다. 즉 이 함수는 두 계산 경로와 현재·예측 시설 handoff를 연결하는 실행 계층이며, 누출 packet·문헌 빈도·SLABx-LH2 계산·시설 IR/F-N의 자격을 대신 만들어 주지 않는다. `timing.wall_elapsed_ms`도 한 번의 호출을 측정한 값이므로 1 Hz 운영 보장을 뜻하지 않는다.

HAZOP 결과를 이 기존 시설 원장으로 넘겨야 할 때는 `build_hazop_facility_campaign_result(...)`를 사용한다. 이 handoff는 설비마다 정확히 하나의 `CONSEQUENCE_EVALUATED` branch, provider 방출 종료·재고 경계, 현재 기상 IR, 점화 branch를 요구한다. `scenario_bindings`에는 반드시 `hazop_scenario_id`를 넣어야 하며, 선택된 운전 모드 시나리오 ID와 다르면 캠페인을 만들지 않는다. 연간 기상·인구·차단 branch별 피해는 호출자가 명시적으로 공급하고, 누락된 branch나 빈도는 0으로 채우지 않는다. 여러 HAZOP branch가 동시에 활성화된 경우에는 이 handoff가 보류되며, 먼저 branch별 사건 빈도와 release/isolation partition을 별도로 닫아야 한다. 성공하면 `campaign`와 함께 기존 `merge_facility_campaign_results(...)`가 계산한 `facility_ledger`도 반환한다. 이 ledger는 설비별 risk atom을 시설 조건부 IR/F-N으로 합산하되, 결과 상태는 `HAZOP_CAMPAIGN_BUILT_OPERATOR_LIMITED`이고 qualified provider, 독립 물리 검증, 전체 사고범위가 닫히기 전에는 시설 QRA 승격이 계속 `false`다.

실시간 운전 모드의 연결은 이 handoff에서 끝나지 않는다. `run_hazop_facility_runtime(...)`이 선택한 mode는 campaign binding의 `operating_mode`와 정확히 일치해야 하며, 일치한 값은 campaign event·case·risk atom 및 `facility_evidence_request`의 provider 요청과 `exact_match_required.operating_mode`에 그대로 보존된다. HAZOP handoff가 제공한 `hazop_scenario_id`도 event·case·risk atom·provider 요청·`exact_match_required`에 함께 전달되어, 같은 운전 모드라도 다른 HAZOP 행이 섞이지 않게 한다. 같은 event/condition/branch가 여러 원장 행에 나타날 때 mode 또는 HAZOP scenario ID가 다르면 첫 값을 임의로 덮어쓰지 않고 명시적인 충돌 차단 사유를 남긴다. 이 추적은 scenario identity를 보존하기 위한 것으로, 빈도 추정이나 누출·피해 계산을 새로 만들지 않는다.

시설 원장으로 합산한 뒤에도 이 식별자는 사라지지 않는다. `scenario_branch_accounting`의 연간 조건·release branch·점화 branch, 설비별 `component_coverage`·`component_contributions`, 사고 family별 기여표가 각각 `hazop_scenario_ids`를 정렬된 목록으로 보존한다. 따라서 여러 설비와 운전 모드의 IR/F-N을 합산한 뒤에도 관리자 화면이나 논문용 표에서 어떤 HAZOP 행이 해당 기여를 만들었는지 되짚을 수 있다. ID가 없는 일반 campaign도 기존처럼 계산되지만, ID가 제공된 campaign에서 서로 다른 값이 같은 event에 섞이면 realtime campaign과 provider evidence request 단계에서 fail-closed로 남긴다.

이 보존을 별도로 감사하려면 다음 명령을 사용한다.

```powershell
python scripts/audit_hazop_scenario_trace.py `
  --campaign-result results/<campaign>.json `
  --facility-evidence-request results/<facility_evidence_request>.json `
  --output results/<hazop_scenario_trace_audit>.json
```

`HAZOP_SCENARIO_TRACE_COMPLETE`이면 event·case·risk atom·provider 요청의 ID가 일치한다는 뜻이고, `HAZOP_SCENARIO_TRACE_BLOCKED`이면 누락 또는 충돌을 뜻한다. 일반 campaign에서 ID를 사용하지 않으면 `NO_HAZOP_SCENARIO_ID_DECLARED`로 남으며 ID나 빈도를 추정하지 않는다.

`build_hazop_facility_campaign_result(...)`와 `build_hazop_facility_campaign_branches(...)`는 이 감사기를 handoff 안에서 자동 실행한다. 성공한 결과에는 `hazop_scenario_trace_audit`가 함께 들어가며, event·case·risk atom의 시나리오 ID가 완전하지 않으면 시설 원장을 반환하지 않고 `HazopFacilityCampaignError`로 중단한다. 이 검사는 HAZOP ID의 전달 경로를 닫는 연결 검사일 뿐이며, 문헌 빈도·provider 자격·SLABx-LH2 물리검증·시설 QRA를 승인하거나 PRISM 단독 모델로 대체하지 않는다.

시설 원장으로 병합된 뒤에도 mode를 잃지 않는다. `scenario_branch_accounting`의 `annual_conditions`, `release_branches`, `ignition_branches` 각 행에 `operating_modes` 목록을 보존하고, `component_contributions`, `component_coverage`, 설비 위험순위에도 같은 목록을 남긴다. 따라서 같은 방출·점화 branch가 `receiving`과 `supply`에서 모두 발생했는지, 어느 설비가 어떤 mode에 연결됐는지 확인할 수 있다. 목록은 위험 원자의 mode를 정렬해 보여주는 추적용 메타데이터이며, 조건부 빈도를 합산하거나 mode별 빈도를 추정하지 않는다. mode가 없는 legacy risk atom은 빈 목록으로 남아 기존 입력을 임의로 보완하지 않는다.

여러 HAZOP branch를 동시에 시설 원장에 연결해야 할 때는 `build_hazop_facility_campaign_branches(...)`를 사용한다. 이 함수는 branch별 `scenario_id`에 대한 문헌 사건 빈도와 `branch_partition_groups`를 호출자가 명시하도록 요구하고, 같은 분할 그룹 안의 확률 합이 정확히 1일 때만 branch별 캠페인을 만든다. 분할 확률은 각 연간 조건의 명시적 release branch 확률에 곱해지며, 센서 신호에서 빈도를 학습하거나 누락 branch를 0으로 대체하지 않는다. 사건 ID가 겹치거나 확률·분할 그룹·scenario binding이 빠지면 해당 결과를 합치지 않고 오류로 남긴다. 성공 결과의 schema는 `prism.hazop_facility_campaign_branches.v1`이며, 기존 시설 원장과 동일하게 `facility_annual_qra_promotion=false`를 유지한다.

예측 공정상태를 시간축으로 평가할 때는 `run_hazop_forecast_risk_scan(...)`을 사용한다. 시뮬레이터가 만든 각 frame은 `forecast_time_s`, `origin="model_prediction"`, `operating_mode`를 가져야 하며, 모든 예측 시각에 대상 설비 frame이 있어야 한다. 함수는 각 시각의 HAZOP 이탈을 판정하고, `evaluate_on="entry"`이면 위험조건에 처음 진입한 시점에만 정량평가기를 호출한다. `evaluate_on="each_step"`를 선택하면 조건이 유지되는 동안 매 예측 시각에 재평가를 요청한다. `build_hazop_forecast_runtime_evaluator(...)`를 사용하면 이 callback이 예측 frame을 기존 runtime frame 계약으로 감싸고 `run_hazop_runtime_consequence(...)`와 기존 monitor·provider resolver를 그대로 호출한다. 따라서 provider 방출·종료·재고·SLABx-LH2·점화/시설 원장은 기존 계산 계층이 계속 소유한다. callback이 없거나 실패하면 `WITHHELD_NO_QUANTITATIVE_EVALUATOR` 또는 오류 상태로 남는다. 각 scan은 `timing.wall_elapsed_ms`와 `timing.quantitative_evaluation_elapsed_ms`를 함께 기록해 디지털트윈 운영시간을 관찰할 수 있게 한다. 이 값은 해당 호출의 측정값이며 1 Hz 처리 보장을 뜻하지 않는다. scan은 예측값에서 빈도를 추정하지 않고, 예측 경로를 시설 QRA로 자동 승격하지 않는다.
각 forecast trigger와 조건 해제 원장에는 선택 시점의 `operating_mode`가 함께 기록된다. 따라서 동일한 `scenario_id`가 유지되는 동안에도 어떤 mode에서 정량평가가 요청되었고 어떤 mode가 해제되었는지 확인할 수 있다. 이 기록은 mode별 빈도나 방출을 추정하는 기능이 아니다.

```python
from lh2_tno.hazop_forecast import run_hazop_forecast_risk_scan

scan = run_hazop_forecast_risk_scan(
    facility_id="generic-outdoor-lh2",
    tables_by_component={"TK-01": hazop_table},
    forecast_frames=predicted_frames,
    expected_component_ids=("TK-01",),
    evaluate_on="entry",
    quantitative_evaluator=provider_slabx_facility_evaluator,
)
```

정량평가기를 붙이지 않은 구조 점검은 다음 CLI로 실행할 수 있다. 이 명령은 위험조건 도달 시점을 표시하지만, provider 방출·SLABx-LH2·시설 QRA 결과를 임의로 만들지 않고 정량평가 요청을 보류한다.

```powershell
python scripts/scan_hazop_forecast.py `
  --tables examples/generic_hazop_tables_by_component.json `
  --frames examples/generic_hazop_forecast_frames.json `
  --facility-id generic-outdoor-lh2 `
  --components TK-01 `
  --output results/hazop_current/forecast_scan.json
```

생성된 scan은 `scripts/build_ijhe_completion_audit.py --hazop-forecast-scan`으로 IJHE 감사 원장에 넣을 수 있다. 감사 결과는 예측 trigger의 입력 모드·시간축·보류 회계와 `timing.wall_elapsed_ms`·`timing.quantitative_evaluation_elapsed_ms`의 존재를 확인한다. `fresh_physics_claim=true`이거나 처리시간이 없으면 진단 check를 통과시키지 않는다. 이 진단 check 자체로 시설 QRA를 승격하지 않는다.
감사기는 trigger·재평가·해제 항목의 `operating_mode` 존재와 각 scenario row의 mode 일치를 함께 확인한다. mode가 빠지거나 scenario와 다르면 예측 경로 check는 차단되며, 누락 mode를 다른 시점의 값으로 보정하지 않는다.

현재·예측 통합 원장을 완료 감사에 연결할 때는 다음처럼 `--hazop-integrated-risk`를 추가한다.

```powershell
python scripts/build_ijhe_completion_audit.py `
  --current-status CURRENT_STATUS.json `
  --scope-matrix <scope-matrix.json> `
  --campaign-result <campaign-result.json> `
  --hazop-integrated-risk results/20261108/hazop_integrated_risk_diagnostic.json `
  --output results/20261108/ijhe_completion_audit_with_integrated_hazop_diagnostic.json
```

감사기의 `diagnostic_hazop_integrated_risk`는 `current`·`forecast` 원장의 schema와 상태, 설비 ID 목록, `shared_component_scenario_keys`, 운전 모드 추적 플래그, 빈도·시설 QRA 승격 차단 정책을 다시 확인한다. 통합 원장이 partial이어도 정량평가 보류를 숨기지 않고 진단 PASS로 기록할 수 있지만, unsafe promotion flag가 있거나 설비 범위가 없으면 BLOCKED가 된다.

다설비 예측을 연결할 때 release resolver는 `(component_id, scenario_id)` 튜플을 키로 사용할 수 있다. 이 키가 있으면 같은 HAZOP 행 ID가 여러 설비에 재사용되어도 설비별 provider 방출이 섞이지 않는다. 단일 설비 예제에서는 기존 `scenario_id` 키도 호환되며, 실행 결과에는 실제로 선택된 resolver 키 범위가 기록된다.

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

현재 HAZOP·runtime mode·forecast 연결 집중 검사와 현재·예측 통합 오케스트레이터를 포함한 전체 패키지 검사는 **1058 passed**이다. 예제 실행은 `receiving` 모드의 고압 이탈 1건을 선택했으며, 방출 packet 0건·빈도추정 false·시설 QRA false를 기록했다. 별도 통합검사는 provider liquid packet이 기존 SLABx-LH2 consequence monitor까지 전달되는 경로, 두 개의 활성 HAZOP branch를 독립적으로 dispatch하는 경로, 명시적 branch 확률·분할 합계로 여러 branch를 시설 원장에 연결하는 경로, 예측 공정상태가 위험조건에 처음 도달한 시점의 정량평가 trigger와 기존 runtime consequence gate 재사용 경로, 조건 해제 경로, 여러 설비 원장 조정 경로, HAZOP branch에서 연간 조건·점화·인구·IR/F-N 원장으로 넘어가는 명시적 handoff, 운전 모드와 HAZOP scenario ID가 campaign·provider evidence request·시설 branch accounting·consequence request까지 보존되는 경로와 중복 identity 충돌 차단을 실행했다. 별도 HAZOP scenario trace 감사기는 event·case·risk atom·provider 요청의 시나리오 ID가 일치하는지 확인하며, 누락·충돌을 추정 없이 차단한다. 이 감사 결과는 `build_ijhe_completion_audit.py --hazop-scenario-trace-audit`로 IJHE 완료 감사에 연결할 수 있다. `run_hazop_integrated_risk()` 회귀검사는 현재·예측 결과의 공통 설비·운전 모드·scenario identity를 묶고, 예측 정량평가가 보류되면 통합 상태도 `INTEGRATED_DIAGNOSTIC_PARTIAL`로 남기는지 확인한다. 실제 custom HAZOP tag를 관측 runtime frame으로 만들고 현재·예측 path에 넘기는 end-to-end 회귀검사도 포함한다. 선택형 facility campaign evaluator와 `build_hazop_facility_campaign_evaluator()` factory가 기존 연간 조건·시설 ledger handoff를 붙일 때 unsafe promotion claim을 보류하는 회귀검사도 포함한다. `build_ijhe_completion_audit(..., hazop_integrated_risk=...)` 검사는 이 통합 원장의 설비 범위·scoped scenario key·호출 처리시간과 시설 campaign 정책, 빈도·시설 QRA 승격 차단 플래그를 다시 검증한다. 추가로 사고 export 요청의 명시적 `isolation_time_s`·`post_isolation_observation_s`가 provider로 전달되고 결과 `provider_meta`에서 echo되는지 검사한다. 실제 provider가 연결된 경우에도 HAZOP family와 packet의 source operator·종료 근거가 맞을 때만 기존 SLABx-LH2 consequence monitor로 전달된다.

남은 엄격 문턱은 실제 설비별 HAZOP·P&ID identity, provider의 차단·재고·종료 이력, 문헌 빈도 event binding, SLABx-LH2 독립 비교, 시설 전체 사고 family coverage와 IR/F-N 승격이다. 현재 scope matrix가 수치적으로 계산된 가족과 qualification-only gap을 구분해 기록하므로, 진단 계산이 존재한다는 이유로 미계산 사고나 자격화된 위험으로 표시하지 않는다. 현재 검사센터 자료는 정상 상태 신호의 후보 입력으로만 취급한다.
