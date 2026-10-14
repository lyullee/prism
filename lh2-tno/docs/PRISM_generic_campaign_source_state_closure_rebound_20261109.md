# PRISM 일반 LH2 24개 사건 source-state/재고종료 재연결 캠페인 (2026-11-09)

## 목적

최신 `lh2dt.DynamicVaporizer` source-state 패킷을 기존 일반 액화수소시설 24개 사건 장부의 `ambient-vaporizer/G1`에 다시 연결했다. 동시에 이미 확인된 재고 종료(`inventory_depletion`) 패킷을 `ambient-vaporizer/G3`와 `reliquefier/G6`에 다시 연결했다. 목적은 오래된 G1 고속출구 실패가 현재 소스 경계에서도 그대로 남는지, 그리고 방출→피해 체인이 사건 장부 전체에서 중단 없이 돌아가는지 확인하는 것이다.

이 기록은 **진단용 연결 검증**이다. 공급자 적격성, 독립 물리검증, 현장 사고빈도 추정, 시설 전체 IR/F-N 승격은 하지 않는다.

## 실행 결과

| 항목 | 결과 |
|---|---:|
| 대상 사건 | 24개 fresh physics cases |
| 상태 | `PARTIAL_DECLARED_SCOPE` |
| 완전 실행(`EXECUTED`) | 4 |
| 수치 실행 후 운영자 제한(`EXECUTED_OPERATOR_LIMITED`) | 20 |
| 별도 실패 | 0 |
| 수치 미실행 | 0 |
| 공급자 적격 증거로 인정된 사건 | 0 / 24 |
| 시설 IR/F-N | 계산 보류 |
| 캠페인 총 시간 | 171188.6 ms (171.2 s) |
| 사건별 중앙 시간 | 4481.3 ms |
| 사건별 p95 시간 | 20698.1 ms |

`EXECUTED_OPERATOR_LIMITED`는 계산 코드가 결과를 냈다는 뜻이지만, 공급자 모델이 상수상태 또는 열린 물리종료를 선언하여 IJHE용 확정 위험증거로는 세지 않는다는 뜻이다. 따라서 “24개가 모두 완전히 검증되었다”고 해석하면 안 된다.

## 주요 사건 재연결

| 사건 | 새로 연결한 근거 | 결과 | 해석 |
|---|---|---|---|
| `ambient-vaporizer/G1` | 최신 source-state 패킷 + 압축성 handoff | `EXECUTED_OPERATOR_LIMITED` | 기존 고속출구 예외는 사라졌고 source/throat 상태를 사용해 전 체인을 통과했다. 다만 공급자 종료·상수상태 제한 때문에 적격 증거로 승격하지 않았다. |
| `ambient-vaporizer/G2` | `inventory_over_600s` | `EXECUTED` | 600초 계산은 되었지만, 완전한 격리 성공/후관찰 근거가 없어 장기 방출 종료로 선언하지 않는다. |
| `ambient-vaporizer/G3` | strict `inventory_depletion` 패킷 | `EXECUTED` | 공급자 재고 장부가 0까지 닫힌 진단 경로를 사용했다. 적격성·독립검증은 별도 게이트다. |
| `reliquefier/G6` | strict `inventory_depletion` 패킷 | `EXECUTED` | 재액화기 재고 종료 경로를 사용했다. 적격성·독립검증은 별도 게이트다. |

## 연결된 전체 체인

`운전/사건 장부` → `설비별 공급자 방출 패킷` → `압축성 경계(source/throat가 있는 경우)` → `풀·rainout` → `SLABx-LH2/SLABx 누출·확산` → `수소운 cloud` → `점화` → `화재·폭발 피해` → `TNO 인체피해` → `조건부 risk atom`.

이번 캠페인에서 G1의 최신 패킷은 다음 식별자로 추적된다.

- source digest: `b5663098ec6e2e7b4635dfcf44e1523a4114e84ce9b9258b862ec51c98c47f07`
- provider result digest: `83ffcc0aa63a9ed3fe2bdd44124cba70493664ab422706be9d3d8293b78c5b28`
- provider 종료: `inventory_depletion`
- 방출시간: `1.0999999999999999 s`
- 방출 질량: `0.00358694709072 kg`
- 질량 잔차: `0 kg`
- facility 위치: 캠페인 장부 위치로 재바인딩하여 평가

## 파일

- 캠페인 결과: `results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff_result.json`
- G1 handoff 재연결 캠페인: `results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff.json`
- G1 handoff 재연결 provenance: `results/20261109/generic_scope_campaign_source_state_closure_rebound_g1_handoff.provenance.json`
- 사건별 source-state/재고종료 evidence: `results/20261109/generic_scope_packet_evidence_source_state_closure_rebound.json`
- 최신 G1 공급자 방출 패킷: `results/20261109/g1_source_state_native_export/resolved_release.json`
- 최신 G1 압축성 handoff 포함 패킷: `results/20261109/g1_source_state_native_export/resolved_release_with_handoff.json`

## 남은 개발 게이트

1. 실제 또는 적격 공급자 모델의 source/throat 및 종료조건 증거를 확보한다.
2. G1 고속 근접장에 대한 독립 실험/검증 자료를 연결한다.
3. G2의 600초 제한을 실제 차단·후관찰 증거로 대체한다.
4. 저장탱크·배관·밸브·펌프·재액화기 전체 사고군에 대해 시설 위치와 사고 포트가 모두 명시된 방출 경계를 닫는다.
5. 위 증거가 모인 뒤에만 시설 IR/F-N을 승격한다.

따라서 현재 결과는 **방출부터 최종 피해까지 24개 사건을 실행하는 연결 진단은 완료했지만, 일반 액화수소시설의 완전한 정량위험평가가 완료된 상태는 아니다**.
