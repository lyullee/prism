# PRISM provider 종료 증거 카탈로그 (2026-11-14)

이 문서는 저장된 provider 출력에 이미 들어 있는 **방출 종료·격리·양단 endpoint 결합 근거**를 시설 case별 방출 경계 감사로 전달하는 방법을 기록한다. 대상은 일반 옥외 액화수소시설 union scope이며, 이 장부는 provider 자격·현장 빈도·독립 물리검증·시설 IR/F-N을 승인하지 않는다.

## 왜 별도 카탈로그가 필요한가

일부 provider는 액화수소 재고를 수학적으로 0 kg까지 계산하지 않고, 양의 임계값·releasable inventory·명시적 격리 관찰에서 계산을 멈춘다. 또 양단 파열은 두 endpoint를 하나의 공유 inventory 사건으로 계산한다. 기존 release ledger의 `available_mass - cumulative_mass_out`만 보면 이런 종료 경계와 endpoint 결합이 드러나지 않는다. 이를 해결하기 위해 provider가 직접 기록한 다음 항목을 그대로 보존한다.

- provider result digest
- 초기 가용 재고와 누적 방출량
- 양의 재고 임계값 또는 releasable-inventory 정의
- 종료 시 잔여량
- provider 질량 잔차
- 격리 성공 시각·관찰 시각·zero-flow 상태
- 양단 사건의 endpoint 수·endpoint result digest·공통 inventory provenance

임계값을 넘은 잔여량을 0으로 치환하지 않는다. 모든 값과 digest가 소비 case와 일치할 때에만 `numerical_release_closed=true`로 표시한다.

## 현재 산출물

권위 카탈로그는 [`provider_termination_evidence_catalog_union_fullscope_hazop_port_bound_state_bound.json`](../results/20261114/provider_termination_evidence_catalog_union_fullscope_hazop_port_bound_state_bound.json)이다. 생성기는 [`build_provider_termination_evidence_catalog.py`](../scripts/build_provider_termination_evidence_catalog.py)이며 native event의 `resolved_release(.json|_set.json)`, `verification.json`, `provider_response(.json|_endpoints.json)`와 inventory-depletion provider 파일을 입력으로 받는다.

| 출처 | event row | 상태 |
|---|---:|---|
| LayeredTank 저장탱크 sidecar | 5 | digest·질량·양의 임계값·잔차 일치 |
| native 격리·releasable inventory·양단 endpoint 응답 | 24 | digest·질량·종료/endpoint 결합 일치 |
| inventory-depletion provider 응답 | 5 | digest·질량·양의 임계값·잔차 일치 |
| 합계 | 29 | 진단용 종료 증거 |

카탈로그는 29개 event row를 모두 구조적으로 읽는다. 그중 27개는 현재 종료 evidence basis를 통과하고, 2개(`emergency_relief_discharge`, `inventory_over_600s`)는 명시적 provider 결과를 보존하지만 현재 release-boundary basis로는 `INVALID`로 남긴다. vertical handoff synthetic horizon 등 별도 event는 `NOT_SUPPLIED`로 남겨 종료 시간을 0 또는 재고 소진으로 추정하지 않는다.

## 방출 경계 감사에 반영한 결과

44개 facility case 중 32개 case가 이 카탈로그와 digest·질량·종료/endpoint 조건을 일치시킨다. annual condition이 두 개인 inventory-depletion event는 동일 provider packet을 사용하지만 case key가 다른 두 행으로 각각 대조한다.

- 수치상 종료: 32/44 case
- 그중 운영자 검토 필요: 19/44 case
- 수치상 미종료: 12/44 case
- strict release boundary 통과: 13/44 case
- strict release boundary 보류: 31/44 case
- provider qualification: 0건
- 독립 물리검증: 미주장
- 시설 IR/F-N 승격: 차단

저장탱크·격리 성공·양단 endpoint case는 종료 증거가 닫혔어도 `EXECUTED_OPERATOR_LIMITED`, synthetic provider 원점 또는 consequence-domain 제한이 남아 있다. inventory-depletion 10개는 방출 경계는 닫혔지만 synthetic provider 원점과 독립 검증 부재가 남아 있으므로 시설 QRA로 승격하지 않는다. 양단 파열 2개도 endpoint 결합을 수치상 닫았지만 operator-limited로 유지한다.

## 재현 명령

```powershell
python scripts/build_provider_termination_evidence_catalog.py `
  --storage-catalog-dir results/20261111/native_generic_scope_packets_isolation `
  --inventory-provider-responses results/20261009/equipment_inventory_campaign/provider_responses.json `
  --inventory-resolved-releases results/20261009/equipment_inventory_campaign/resolved_releases.json `
  --output results/20261114/provider_termination_evidence_catalog_union_fullscope_hazop_port_bound_state_bound.json

python scripts/audit_release_boundary_cases.py `
  --facility-assessment results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_assessment.json `
  --facility-evidence-request results/20261114/native_full_scope_union_assessment_fullscope_hazop_port_bound_state_bound/facility_evidence_request.json `
  --provider-termination-evidence results/20261114/provider_termination_evidence_catalog_union_fullscope_hazop_port_bound_state_bound.json `
  --output results/20261114/release_boundary_case_audit_union_fullscope_hazop_port_bound_state_bound.json
```

이 재현 경로는 release ledger의 잔여질량을 수정하지 않고, 명시적 provider 종료 증거가 있는 case에만 경계 근거를 추가한다.
