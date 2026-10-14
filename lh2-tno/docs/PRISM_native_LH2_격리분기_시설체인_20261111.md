# Native LH2 격리 분기 → 시설 위험 체인

## 목적

`native_generic_scope_packets_isolation`에서 만든 설비별 방출 packet을 단순히 파일로 보관하는 데서 끝내지 않고, PRISM의 기존 옥외 시설 chain에 다시 넣는 재현 경로다.

```text
설비 상태·격리 명령
  → native provider release packet
  → packet identity/state snapshot 재바인딩
  → SLABx-LH2/SLABx 누출·확산
  → 점화·화재/폭발 피해
  → 인구·기상 조건
  → risk atom
  → 조건부 시설 IR/F-N
```

이 경로는 기존 `facility_total_risk_available` 승격 조건을 우회하지 않는다. 합성 packet, operator-limited 경계, 적격 provider 근거 부재와 독립 물리검증 부재를 그대로 시설 원장에 보존한다.

## 재현 명령

```powershell
python scripts/run_native_isolation_catalog_facility_chain.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign results/20261019/generic_native_packet_rebound_campaign.json `
  --catalog-dir results/20261111/native_generic_scope_packets_isolation `
  --backend-config results/20261009/backend_config_current.json `
  --output-dir results/20261111/native_isolation_catalog_facility_chain_full
```

이 명령은 다음을 자동으로 수행한다.

1. catalog의 exact packet evidence를 기존 24개 event route에 event/component/port 기준으로 재바인딩한다.
2. packet 옆의 상태 snapshot과 provider echo를 campaign request에 전달한다.
3. 외부 packet의 방출 지속시간·종료근거·재고 장부를 사용해 PRISM consequence chain을 실행한다.
4. 문헌 빈도는 campaign `FrequencyPlan`에서 가져오고, packet에서 빈도를 만들지 않는다.
5. 설비별 risk atom을 시설 조건·인구·기상·점화 계산으로 집계한다.
6. 조건부 IR/F-N과 strict QRA gate를 별도로 기록한다.

## 결과

[`verification.json`](../results/20261111/native_isolation_catalog_facility_chain_full/verification.json)은 다음을 기록한다.

| 항목 | 결과 |
| --- | ---: |
| 문헌 event / exact packet | 24 / 24 |
| packet 미계산 | 0 |
| 명시적 격리 성공 branch | 14 |
| 상태 snapshot bound·echo | 24/24 |
| 시설 campaign case | 24 |
| risk atom | 96 |
| 조건부 시설 위험 경로 | `true` |
| 적격 provider packet 승격 | `false` |
| 시설 전체 IR/F-N 승격 | `false` |

최신 실행은 5개 `EXECUTED`, 19개 `EXECUTED_OPERATOR_LIMITED`로 남았다. 따라서 모든 사건이 숫자로 실행되었다는 사실과 엄격한 시설 QRA 증거를 분리한다. `facility_assessment.json`의 `conditional_diagnostic_facility_risk_available=true`는 현재 합성 조건에서 risk atom을 집계할 수 있다는 뜻이고, `facility_total_risk_available=false`는 현장 적용 가능한 완결 QRA가 아직 아니라는 뜻이다.

## 현재 한계

- 입력 설비 형상·상태·수신점은 일반 LH2 합성 manifest다.
- 14개 `reviewed_isolation_success`는 외부 모델의 actuator close와 zero-flow 관찰이며, 현장 차단 신뢰도나 사고빈도가 아니다.
- 19개 operator-limited case와 1개 domain-incomplete case는 숫자 결과가 있어도 strict 시설 경계에서 보류한다.
- 문헌 빈도 불확실성은 p05/published/p95를 조건부로 계산하지만, 현장 사고빈도나 센서 신호에서 빈도를 학습하지 않는다.
- 실제 시설 IR/F-N 승격에는 설비별 적격 provider packet, 현장 형상·수신점·인구 검토, 독립 물리검증, 전체 사고범위 폐합이 추가로 필요하다.
