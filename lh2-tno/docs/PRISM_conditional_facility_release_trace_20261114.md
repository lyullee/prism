# 조건부 시설 위험도와 방출 추적 view (2026-11-14)

`build_conditional_facility_risk_view.py`에 case별 방출 추적 출력을 연결했다. 이
출력은 디지털트윈 화면이나 API가 한 번의 결과에서 다음 항목을 함께 읽을 수 있게
한다.

- 설비·port·운전 모드·HAZOP 시나리오·기상 조건
- provider가 선언한 방출 종료 기준과 방출 지속시간
- 초기 재고, 누적 방출량, 잔여 재고, 잔여율
- case별 전체 처리시간과 source·pool·확산·점화/피해 단계별 처리시간
- 수치상 종료 상태와 strict 방출 경계 승격 상태
- 같은 case key를 사용한 risk atom 수와 비영 피해 atom 수
- 문헌 빈도 p05·published·p95 및 상관 가정별 시나리오
- 설비·사고군 순위 안정성과 포트 결합 상태

case key는 `event_id|release_branch_id|annual_condition_id`이며, 방출 trace의
`risk_atom_count`는 해당 case가 피해영향·점화 계산에 실제로 사용된 atom 수를
뜻한다. 0은 물리적 위험이 0이라는 뜻이 아니라, 그 case에서 비영 피해 atom이
연결되지 않았거나 해당 수신점의 조건부 결과가 0이라는 뜻이다.

## 재현

```powershell
python scripts/build_conditional_facility_risk_view.py `
  --facility-assessment results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_assessment.json `
  --release-boundary-case-audit results/20261114/release_boundary_case_audit_union_fullscope_hazop_port_bound_state_bound.json `
  --output results/20261114/conditional_facility_risk_view_with_release_trace.json
```

권위 실행 결과는 [`conditional_facility_risk_view_with_release_trace.json`](../results/20261114/conditional_facility_risk_view_with_release_trace.json)이다.
34개 event, 44개 case, 176개 risk atom과 방출 trace 44행이 일치하며, 각 행의
`calculation_timing`에 실제 assessment 처리시간이 복사된다. summary는
수치상 종료 32개·운영자 검토 필요 19개·수치상 열림 12개를 재현한다. 이 중
32개 case는 별도 provider 종료 evidence catalog의 digest·질량·격리/endpoint·질량
잔차가 일치하여 닫혔고, 임계값을 넘은 잔여량을 0으로 바꾸지 않았다. 단,
emergency-relief와 600초 horizon evidence는 unsupported basis로 기록만 유지한다.

같은 view의 `frequency_uncertainty`는 5개 문헌 빈도 시나리오
(`published`, `p05`, `p95`, independent-event low/high)을 보존한다. 각 시나리오는
자산·사건 분위수 출처, 상관 가정, 조건부 IR/F-N, 미계산 case와 순위 안정성을
포함한다. `frequency_port_binding.status=ALIGNED`와
`frequency_inference_allowed=false`를 함께 기록하므로, 문헌 값을 센서값에서
추론하거나 시설 credible interval로 과장하지 않는다.

각 시나리오에는 30개의 `uncomputed_cases` 행(29개 고유 case key)이 남아 있으며,
상태별로 `EXECUTED_OPERATOR_LIMITED` 29개와 `EXECUTED_DOMAIN_INCOMPLETE` 1개를
구분한다. 중복 행은 삭제하지 않고 그대로 보존하므로, “계산되지 않음”과 “계산은
실행됐지만 자격 또는 계산영역이 닫히지 않음”을 소비자가 구별할 수 있다.

view의 `promotion_gates`에는 방출경계·provider 자격·독립 물리검증·시설 IR/F-N의
네 gate가 각각 기록된다. 현재 네 gate 모두 `BLOCKED`이고
`all_gates_closed=false`, `promotion_allowed=false`이다.

이 view는 **조건부 진단 출력**이다. `qualification.promotion_allowed`는 항상
`false`이며, qualified provider packet·독립 물리검증·전체 사고범위·시설 전체
IR/F-N이 확보될 때까지 시설 QRA 결과로 승격하지 않는다. 누락·운영자 제한·피해
영역 절단 사례를 0위험으로 대체하지 않는다.
