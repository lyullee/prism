# 조건부 시설 위험도와 방출 추적 view (2026-11-14)

`build_conditional_facility_risk_view.py`에 case별 방출 추적 출력을 연결했다. 이
출력은 디지털트윈 화면이나 API가 한 번의 결과에서 다음 항목을 함께 읽을 수 있게
한다.

- 설비·port·운전 모드·HAZOP 시나리오·기상 조건
- provider가 선언한 방출 종료 기준과 방출 지속시간
- 초기 재고, 누적 방출량, 잔여 재고, 잔여율
- 수치상 종료 상태와 strict 방출 경계 승격 상태
- 같은 case key를 사용한 risk atom 수와 비영 피해 atom 수

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
34개 event, 44개 case, 176개 risk atom과 방출 trace 44행이 일치하며, summary는
수치상 종료 15개·운영자 검토 필요 12개·수치상 열림 29개를 재현한다.

이 view는 **조건부 진단 출력**이다. `qualification.promotion_allowed`는 항상
`false`이며, qualified provider packet·독립 물리검증·전체 사고범위·시설 전체
IR/F-N이 확보될 때까지 시설 QRA 결과로 승격하지 않는다. 누락·운영자 제한·피해
영역 절단 사례를 0위험으로 대체하지 않는다.
