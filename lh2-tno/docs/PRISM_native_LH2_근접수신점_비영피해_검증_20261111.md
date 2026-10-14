# Native LH2 근접 수신점 비영 피해 연결 검증

## 목적

일반 시설용 수신점(예: 20 m)에서는 작은 합성 방출이 수신점에 도달하지 않아 IR/F-N 값이 0으로 보일 수 있다. 이 값을 시설 위험이 0이라는 뜻으로 해석하지 않도록, 같은 24개 native 격리 packet을 수신점이 방출원 가까이에 있는 별도 진단 geometry로 다시 실행했다.

이 검증은 수신점 geometry를 바꾸어 위험을 부풀리는 작업이 아니다. 일반 시설 결과와 근접 수신점 결과를 분리해 보존하고, 방출→SLABx-LH2→점화·피해→수신점→조건부 IR/F-N 계산이 실제로 비영 값을 낼 수 있는지 확인하는 계산 경로 검증이다. 수신점·설비 형상은 합성 진단 입력이며 현장 조사값이 아니다.

## 재현 명령

```powershell
python scripts/run_native_isolation_catalog_facility_chain.py `
  --manifest examples/generic_lh2_near_receptor_manifest.json `
  --campaign results/20261030/native_near_receptor_scope_packets_state_bound/campaign.json `
  --catalog-dir results/20261111/native_generic_scope_packets_isolation `
  --backend-config results/20261009/backend_config_current.json `
  --output-dir results/20261111/native_isolation_catalog_facility_chain_near_receptor_v3
```

여기서 campaign은 근접 수신점용 풀 반경 0.2 m·계산영역 반경 2 m를 유지하고, 방출 packet은 2026-11-11 native isolation catalog에서 event/component/port 및 상태 snapshot 기준으로 재결합한다. packet에서 빈도를 학습하지 않으며, 문헌 빈도는 기존 FrequencyPlan 입력을 그대로 사용한다.

## 확인된 결과

권위 원장은 [`verification.json`](../results/20261111/native_isolation_catalog_facility_chain_near_receptor_v3/verification.json), 시설 원장은 [`facility_assessment.json`](../results/20261111/native_isolation_catalog_facility_chain_near_receptor_v3/facility_assessment.json)이다.

| 항목 | 결과 |
| --- | ---: |
| 문헌 event / exact native packet | 24 / 24 |
| 시설 campaign case / risk atom | 24 / 96 |
| 비영 receptor-harm risk atom | 1 |
| 수신점 | worker-01, (0.5, 0, 1.0) m |
| 조건부 IR (저·고 빈도 끝점) | 4.68×10⁻⁵ /년 |
| F/N | N=1 endpoint, 4.68×10⁻⁵ /년 |
| 시설 전체 QRA 승격 | `false` |
| provider packet 승격·물리검증 주장 | `false` / `false` |

비영 값을 낸 atom은 저장탱크 `AREA_0.01%`의 `delayed_explosion` branch다. 나머지 95개 atom의 수신점 harm 값이 0인 것은 계산 누락으로 숨기지 않고 원장에 남겼다. 실행 중 2개 case는 계산영역 경계 제한을 기록했고, 20개 case는 ignition 시점의 flammability 판정이 계산되었다.

## 0값 해석 규칙

실행 원장의 `harm_diagnostic.zero_is_not_zero_facility_risk=true`는 다음을 강제한다.

1. 수신점에서 harm이 0이면 해당 조건·geometry에서의 모델 출력으로만 해석한다.
2. 계산영역 truncation, 수신점 거리, 방출량·지속시간 부족으로 인한 0과 실제 위험 부재를 구분한다.
3. 모든 선언 사건의 packet 자격·물리검증·사고범위가 닫히기 전에는 시설 전체 IR/F-N으로 승격하지 않는다.

## IJHE 완료 감사 연결

```powershell
python scripts/build_ijhe_completion_audit.py `
  --current-status CURRENT_STATUS.json `
  --scope-matrix results/20261111/native_isolation_catalog_facility_chain_full/scope_matrix.json `
  --campaign-result results/20261111/native_isolation_catalog_facility_chain_full/campaign_result.json `
  --facility-assessment results/20261111/native_isolation_catalog_facility_chain_full/facility_assessment.json `
  --native-scope-packet-catalog-verification results/20261111/native_generic_scope_packets_isolation/verification.json `
  --native-scope-isolation-branch-catalog-audit results/20261111/native_generic_scope_packets_isolation/isolation_branch_audit.json `
  --native-isolation-catalog-facility-chain-verification results/20261111/native_isolation_catalog_facility_chain_full/verification.json `
  --native-isolation-catalog-near-receptor-verification results/20261111/native_isolation_catalog_facility_chain_near_receptor_v3/verification.json `
  --output results/20261111/ijhe_completion_audit_with_native_isolation_catalog_near_receptor_check.json
```

새 `diagnostic_native_isolation_catalog_near_receptor_harm` 검사는 PASS다. 전체 감사는 `INCOMPLETE_EVIDENCE`로 유지되며, qualified provider packet·독립 물리검증·완전 사고범위·시설 전체 QRA 승격 gate는 계속 차단된다.
