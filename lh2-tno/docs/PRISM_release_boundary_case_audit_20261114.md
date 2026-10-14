# 케이스별 방출 경계 승격 표 (2026-11-14)

시설 평가 결과에는 계산이 끝난 사고와 시설 위험도에 사용할 수 있는 사고가 섞일 수
있습니다. 이번 감사는 그 둘을 케이스 단위로 분리합니다. 각 행에 설비, 포트, 운전
모드, HAZOP 시나리오, 종료 기준, 종료 시간, 질량 잔차, provider 입력 원점을 함께
기록합니다.

## 현재 권위 실행

IJHE용 권위 입력은 전체 union 시설 평가입니다.

`results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_assessment.json`

재현 명령:

```powershell
python scripts/audit_release_boundary_cases.py `
  --facility-assessment results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_assessment.json `
  --output results/20261114/release_boundary_case_audit_union_fullscope_hazop_port_bound_state_bound.json
```

전체 union 결과는 [`release_boundary_case_audit_union_fullscope_hazop_port_bound_state_bound.json`](../results/20261114/release_boundary_case_audit_union_fullscope_hazop_port_bound_state_bound.json)이며, 24개 native isolation subset 결과도 [`release_boundary_case_audit_fullscope_hazop_port_bound.json`](../results/20261114/release_boundary_case_audit_fullscope_hazop_port_bound.json)으로 보존합니다. IJHE 완료 감사는 전체 union 결과를 사용하고, 44개 case 요청과 복합키 정렬도 함께 확인합니다.

- 전체 union 총 44개 case
- 개별 방출 경계 조건을 만족한 case 3개
- 방출 경계에서 보류된 case 41개
- provider qualification, 독립 물리검증, 빈도 추론, 시설 IR/F-N 승격은 0건
- 전체 상태: `CASE_BOUNDARY_PARTIAL`

여기서 3개는 `reviewed_isolation_success` 또는 `inventory_depletion`이라는 종료 기준,
질량 잔차, 계산 상태를 개별적으로 통과했다는 뜻입니다. 실제 현장 자료라는 뜻은
아닙니다. 현재 세 행도 provider 원점이 `model_prediction`이고 독립 물리검증 주장이
없으므로 시설 QRA에 자동으로 들어가지 않습니다.

## 보류 사유를 읽는 법

- `status_executed_operator_limited`: 수치 계산은 실행됐지만 설비 모델의 일정한 상태,
  운영자 선언 또는 관측 종료 한계가 남아 있습니다.
- `termination_basis_inventory_over_600s_is_not_allowed`: 600초 계산 한계로 끝난 행입니다.
  재고 소진이나 검토된 차단 성공으로 바꾸어 쓰지 않습니다.
- `termination_basis_emergency_relief_discharge_is_not_allowed`: 비상 방출은 계산됐지만
  현재 strict release boundary 정책의 종료 기준에 포함되지 않습니다.
- `termination_basis_two_sided_rupture_is_not_allowed`: 양단 파열의 양쪽 재고와 종료
  경계가 닫히지 않았습니다.
- `provider_inventory_residual_not_depleted`: 재고 소진이라고 적혔지만 provider 잔여
  질량이 허용 잔차 안으로 닫히지 않았습니다.
- `consequence_domain_truncated`: 피해 계산 영역 밖의 가연성 여부가 완전히 입증되지
  않았습니다.

case 식별자는 `event_id` 하나가 아니라 `event_id × release_branch_id × annual_condition_id`
복합키입니다. 서로 다른 기상 조건이나 handoff branch가 같은 event ID를 공유할 수
있기 때문입니다.

`strict_release_boundary_eligible`은 방출 종료 경계의 국소 검사 결과일 뿐입니다.
이 값은 사고 빈도를 학습하거나 시설 전체 IR/F-N을 계산해도 된다는 뜻이 아닙니다.
그 다음의 provider qualification과 독립 검증이 닫힐 때까지 모든 행의
`facility_qra_promotion_eligible`은 `false`입니다.

