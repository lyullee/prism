# 케이스별 방출 경계 승격 표 (2026-11-14)

시설 평가 결과에는 계산이 끝난 사고와 시설 위험도에 사용할 수 있는 사고가 섞일 수
있습니다. 이번 감사는 그 둘을 케이스 단위로 분리합니다. 각 행에 설비, 포트, 운전
모드, HAZOP 시나리오, 종료 기준, 종료 시간, 질량 잔차, provider 입력 원점을 함께
기록합니다.

각 행의 `required_evidence`에는 현재 보류 사유를 닫기 위해 필요한 자료가 자동으로
적혀 있습니다. 예를 들어 운영자 제한 행은 provider 소유 시간 이력과 차단 또는
재고소진 종료 근거를 요구하고, `two_sided_rupture`는 양쪽 출구의 재고·결합 이력을
요구합니다. 모든 행은 실제 source/result digest, qualification sidecar, 독립 검증이
들어오기 전까지 `evidence_request_status=OPEN`으로 남습니다.

이번 버전부터 `strict_release_boundary_eligible`과 별도로
`numerical_closure_status`를 기록합니다. 이 값은 방출 종료 기준·격리/재고 상태·질량
잔차가 수치상 닫혔는지만 보여주며, provider 자격이나 시설 QRA 승격을 의미하지
않습니다. 따라서 `NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED`는 계산상 종료
시간과 질량 장부는 있으나 provider가 운영자 제한으로 표시된 사례를 뜻합니다.
`release_duration_s`, 초기·누적 방출·잔여 질량과 잔여율도 같은 case 행에 복사해
방출부터 피해계산으로 전달되는 입력을 재현할 수 있게 했습니다.

## 현재 권위 실행

IJHE용 권위 입력은 전체 union 시설 평가입니다.

`results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_assessment.json`

재현 명령:

```powershell
python scripts/audit_release_boundary_cases.py `
  --facility-assessment results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_assessment.json `
  --facility-evidence-request results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_evidence_request.json `
  --provider-termination-evidence results/20261114/provider_termination_evidence_catalog_union_fullscope_hazop_port_bound_state_bound.json `
  --output results/20261114/release_boundary_case_audit_union_fullscope_hazop_port_bound_state_bound.json
```

전체 union 결과는 [`release_boundary_case_audit_union_fullscope_hazop_port_bound_state_bound.json`](../results/20261114/release_boundary_case_audit_union_fullscope_hazop_port_bound_state_bound.json)이며, 24개 native isolation subset 결과도 [`release_boundary_case_audit_fullscope_hazop_port_bound.json`](../results/20261114/release_boundary_case_audit_fullscope_hazop_port_bound.json)으로 보존합니다. 전체 결과는 44개 case 요청과 복합키 정렬을 독립적으로 확인하고, 요청 ID와 필수 provider 증거 수를 각 행에 복사합니다. IJHE 완료 감사도 이 정렬 결과를 재검증합니다.

- 전체 union 총 44개 case
- 개별 방출 경계 조건을 만족한 case 13개
- 방출 경계에서 보류된 case 31개
- 수치상 종료가 닫힌 case 32개(그중 운영자 검토 필요 19개)
- 수치상 종료가 열린 case 12개
- 명시적 provider 종료 증거 catalog: 29개 event row가 32개 case에 연결(27개 valid, 2개 unsupported basis)
- provider qualification, 독립 물리검증, 빈도 추론, 시설 IR/F-N 승격은 0건
- 전체 상태: `CASE_BOUNDARY_PARTIAL`

수직 handoff 5개 event와 10개 case는 별도 종료 증거 검색도 수행했습니다. 검색 결과는
[`vertical_handoff_termination_evidence_search.json`](../results/20261114/vertical_handoff_termination_evidence_search.json)이며,
다섯 area-bin packet의 `provider_result_digest`, 방출시간, 질량 적분과 handoff provenance를
읽었지만 종료 기준은 모두 `synthetic_diagnostic_horizon`이었습니다. 따라서 이 자료는
계산 결과가 없다는 뜻이 아니라, provider가 실제 차단 성공·재고소진까지 계속 계산했다는
증거가 없다는 뜻입니다. 5개 event와 10개 case를 `NOT_SUPPLIED`로 명시하고,
release-boundary catalog에는 억지로 추가하지 않았습니다.

여기서 strict 경계를 통과한 13개는 `reviewed_isolation_success` 또는
명시적 `inventory_depletion_positive_threshold`를 포함한 종료 기준, 질량 잔차, 계산
상태를 개별적으로 통과했다는 뜻입니다. 추가로 19개는 같은 수치 조건은 닫혔지만
`EXECUTED_OPERATOR_LIMITED`라서
운영자 독립 종료 증거가 필요합니다. 양단 파열 2건은 두 endpoint의 digest와 공통
질량잔차를 확인해 수치 종료로 분류되지만, `EXECUTED_OPERATOR_LIMITED` 상태는
그대로 보존합니다. 어느 쪽도 실제 현장 자료라는 뜻은 아닙니다.
현재 32개 모두 provider 원점이 `model_prediction` 또는 synthetic이고 독립 물리검증
주장이 없으므로 시설 QRA에 자동으로 들어가지 않습니다. 양의 임계값 종료는 잔여질량을
0으로 치환하지 않고 provider digest·질량·임계값·잔차가 맞는 경우에만 닫습니다.

## 보류 사유를 읽는 법

- `status_executed_operator_limited`: 수치 계산은 실행됐지만 설비 모델의 일정한 상태,
  운영자 선언 또는 관측 종료 한계가 남아 있습니다.
- `termination_basis_inventory_over_600s_is_not_allowed`: 600초 계산 한계로 끝난 행입니다.
  재고 소진이나 검토된 차단 성공으로 바꾸어 쓰지 않습니다.
- `termination_basis_emergency_relief_discharge_is_not_allowed`: 비상 방출은 계산됐지만
  현재 strict release boundary 정책의 종료 기준에 포함되지 않습니다.
- `termination_basis_two_sided_rupture_is_not_allowed`: 이전 호환 입력에서 양단 파열
  endpoint 결합 근거가 없을 때만 나타납니다. 최신 native set은 양쪽 digest·endpoint
  수·공통 질량잔차를 확인하지만 운영자 제한과 provider 자격 gate는 별도로 남습니다.
- `provider_inventory_residual_not_depleted`: 재고 소진이라고 적혔지만 provider 잔여
  질량이 허용 잔차 안으로 닫히지 않았습니다.
- `provider_termination_evidence_invalid`: 종료 증거의 event/digest/질량/임계값 중
  하나가 소비 case와 맞지 않아 증거를 사용하지 않았습니다.
- `consequence_domain_truncated`: 피해 계산 영역 밖의 가연성 여부가 완전히 입증되지
  않았습니다.

case 식별자는 `event_id` 하나가 아니라 `event_id × release_branch_id × annual_condition_id`
복합키입니다. 서로 다른 기상 조건이나 handoff branch가 같은 event ID를 공유할 수
있기 때문입니다.

`strict_release_boundary_eligible`은 방출 종료 경계의 국소 검사 결과일 뿐입니다.
이 값은 사고 빈도를 학습하거나 시설 전체 IR/F-N을 계산해도 된다는 뜻이 아닙니다.
그 다음의 provider qualification과 독립 검증이 닫힐 때까지 모든 행의
`facility_qra_promotion_eligible`은 `false`입니다.

