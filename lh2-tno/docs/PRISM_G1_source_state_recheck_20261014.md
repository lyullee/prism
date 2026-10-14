# PRISM G1 source-state handoff 재검증 기록 (2026-10-14)

## 목적

기존 `ambient-vaporizer/G1` 패킷은 대기 출구의 질량연속 속도만 포함해 고속 기체 경계에서 중단되었다. 이번 재검증은 외부 `lh2dt.DynamicVaporizer`가 제공한 상류·throat 상태를 포함한 source-state 패킷을 시설 포트 위치에 배치하고, 같은 사건 ID를 전체 피해 체인에 통과시키는지 확인한다.

이 결과는 합성 진단용이다. 공급자 적격성, 독립 물리검증, 현장 빈도 추정, 시설 전체 IR/F-N 승격은 수행하지 않는다.

## 검증 증거

- 패킷: `results/20261017/vaporizer_g1_source_state_rebased/resolved_release_with_handoff.json`
- 압축성 handoff: `results/20261017/vaporizer_g1_source_state_rebased/compressible_handoff.json`
- handoff 감사: `results/20261017/vaporizer_g1_source_state_rebased/handoff_validation.json`
- 전체 체인 재검증: `results/20261014/vaporizer_g1_source_state_rebased_chain_recheck/verification.json`
- 전체 체인 결과: `results/20261014/vaporizer_g1_source_state_rebased_chain_recheck/consequence_result.json`

| 확인 항목 | 결과 |
|---|---:|
| 사건·설비·포트 식별자 | exact match |
| source/throat 상태 구간 | 11/11 |
| handoff 최대 Mach | 3.9982 |
| handoff 에너지 잔차 | 0 J/kg |
| provider 질량 잔차 | 0 kg |
| provider 방출시간 | 1.1 s |
| 시설 위치 | [10, 0, 1] m |
| 최종 체인 처리시간 | 8,143.1 ms |
| 체인 상태 | `END_TO_END_DIAGNOSTIC_EXECUTED` |

## 연결된 단계

`lh2dt.DynamicVaporizer source/throat state` → `compressible_plane_handoff` → 설비 경계 → `SLABx-LH2/SLABx` 누출·확산 → 풀·기상 → 점화 → 화재·폭발 → TNO 인체피해 → 조건부 risk atom.

전체 체인 명령은 initiating frequency를 적용하지 않으므로 이 재검증은 빈도나 시설 전체 위험을 계산하지 않는다. 시설 캠페인에서 문헌 빈도를 적용할 때에는 동일 사건 ID와 별도 frequency-port 근거가 필요하다.

## 남은 제한

1. source state와 notional plane은 외부 모델의 합성 진단 입력이며 독립 근접장 검증이 없다.
2. 실제 설비의 압력·재고·차단 신뢰도와 사고빈도는 아직 연결하지 않았다.
3. 따라서 기존 공식 24개 캠페인의 원래 G1 실패 기록을 삭제하지 않고, source-state rebind를 별도 진단으로 보존한다.
