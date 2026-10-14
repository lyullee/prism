# PRISM native LH2 event reconciliation 및 사고군 승격 경계 (2026-11-14)

이 문서는 현재 PRISM v0.6.0의 일반 옥외 액화수소시설 진단 결과를 검토하기 위한 보조 문서다. `conditional_status=EXECUTED`는 상태→방출→SLABx-LH2→피해 영향 계산이 실행되었다는 뜻이다. `status=PARTIAL` 또는 `QUALIFICATION_EVIDENCE_WITHHELD`는 provider 자격·독립 물리검증이 부족하다는 뜻이며, 두 상태를 서로 바꾸지 않는다.

## 현재 scope matrix

| 사고군 | 조건부 계산 | case | 수치 실행 | qualified/완전 | operator 제한 | strict 미계산 | 판정 |
|---|---:|---:|---:|---:|---:|---:|---|
| vessel_hole | EXECUTED | 5 | 5 | 0 | 5 | 5 | QUALIFICATION_EVIDENCE_WITHHELD |
| pipe_hole | EXECUTED | 25 | 25 | 10 | 15 | 15 | QUALIFICATION_EVIDENCE_WITHHELD |
| valve_hole | EXECUTED | 5 | 5 | 0 | 5 | 5 | QUALIFICATION_EVIDENCE_WITHHELD |
| vent_hole | EXECUTED | 1 | 1 | 1 | 0 | 0 | COMPLETE |
| pump_hole | EXECUTED | 2 | 2 | 0 | 2 | 2 | QUALIFICATION_EVIDENCE_WITHHELD |
| vaporizer_hole | EXECUTED | 1 | 1 | 1 | 0 | 0 | COMPLETE |
| reliquefier_hole | EXECUTED | 1 | 1 | 1 | 0 | 0 | COMPLETE |
| liquid_two_phase | EXECUTED | 17 | 17 | 0 | 17 | 17 | QUALIFICATION_EVIDENCE_WITHHELD |
| inventory_depletion | EXECUTED | 28 | 28 | 11 | 17 | 17 | QUALIFICATION_EVIDENCE_WITHHELD |
| inventory_over_600s | EXECUTED | 1 | 1 | 1 | 0 | 0 | COMPLETE |
| two_sided_rupture | EXECUTED | 2 | 2 | 0 | 2 | 2 | QUALIFICATION_EVIDENCE_WITHHELD |
| vertical_handoff | EXECUTED | 10 | 10 | 0 | 10 | 10 | QUALIFICATION_EVIDENCE_WITHHELD |

전체는 34개 event, 44개 case이며, 조건부 계산은 44개 case에서 실행되고 조건부 미계산은 0개다. `matrix_complete=False`인 이유는 수치 계산 실패가 아니라 qualified evidence가 보류된 사고군이 있기 때문이다.

## native isolation catalog 대조

`results/20261114/native_isolation_event_reconciliation.json`은 `results/20261111/native_generic_scope_packets_isolation/verification.json`의 24개 event row를 각 event의 `resolved_release(.json|_set.json)` 및 `verification.json`과 대조한다.

- event row: 24개
- exact native packet: 24개
- resolved release/verification 일치: 24/24, mismatch 0
- 명시적 격리 성공: 14개
- provider 승격, 빈도 추론, 물리검증, 시설 IR/F-N 승격: 모두 false

이 결과는 방출 경로가 코드에서 끊기지 않았음을 보여준다. 현장 provider 자격이나 독립 실험 검증을 대신하지 않으므로 시설 전체 IR/F-N 승격 조건을 열지 않는다.

## 명시적 provider 종료 증거의 추가 대조

`results/20261114/provider_termination_evidence_catalog_union_fullscope_hazop_port_bound_state_bound.json`은 이미 저장된 provider 산출물에서 양의 재고 임계값 종료 증거를 추출한다.

- 저장탱크 5개 packet sidecar와 inventory-depletion 5개 provider 응답을 대조해 총 10개 event row를 만들었다.
- 10개 row 모두 packet result digest, 초기 재고, 누적 방출량, 임계값, 종료 시 잔여량, 질량 잔차가 일치한다.
- 양의 임계값은 잔여질량을 0으로 바꾸지 않는다. `remaining_mass_kg <= threshold_mass_kg`와 provider 질량 잔차만 방출 경계 판단에 사용한다.
- annual condition이 두 개인 inventory-depletion extension은 같은 provider event 증거를 두 case에 재사용하되, case key와 digest는 각 행에서 다시 확인한다.
- 이 증거를 release-boundary audit에 연결한 결과 15개 case가 추가로 수치 종료되었다. 전체 수치 종료는 30/44 case(그중 17개는 `NUMERICALLY_CLOSED_OPERATOR_REVIEW_REQUIRED`), strict boundary는 13/44 통과다.
- native catalog의 나머지 19개 event는 provider termination sidecar가 없어 카탈로그에 `errors`로 남겼다. 이 행들에는 종료 증거를 추정하지 않는다.

이 카탈로그는 provider qualification, 독립 물리검증, 빈도 추론, 시설 IR/F-N 승격을 주장하지 않는 진단 장부다.

## 남은 승격 조건

1. 남은 `EXECUTED_OPERATOR_LIMITED`, synthetic horizon, emergency relief, two-sided rupture, inventory-over-600s 행에 provider 소유의 종료·차단·재고 경계 기록을 붙인다. 현재 strict boundary 보류는 31개다.
2. 각 provider packet의 source/result digest와 qualification sidecar를 제출한다.
3. 액화수소 방출·pool/확산·점화/피해 영향에 대한 독립 물리검증을 사고군별로 연결한다.
4. 위 증거가 충족된 뒤에만 시설 전체 IR/F-N을 promotion 대상으로 재평가한다.

## 재현

```powershell
python scripts/build_native_isolation_event_reconciliation.py `
  --catalog-dir results/20261111/native_generic_scope_packets_isolation `
  --output results/20261114/native_isolation_event_reconciliation.json
```

전체 IJHE 감사에는 `--native-isolation-event-reconciliation`과 provider 종료 evidence catalog가 입력으로 연결되며, 최신 감사는 44개 검사 중 40개 PASS·4개 BLOCKED 상태를 유지한다.
