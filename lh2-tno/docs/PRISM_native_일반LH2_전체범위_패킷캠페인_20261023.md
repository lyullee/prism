# PRISM native 일반 LH2 전체범위 패킷·캠페인 기록 (2026-10-23)

## 목적

이 기록은 특정 액화수소검사지원센터의 태그나 운전값이 아닌, 일반적인 옥외 액화수소시설 예제를 대상으로 한다. 합성 `manifest`와 문헌 기반 `FrequencyPlan`의 24개 사건을 설비별 외부 `lh2dt_models` 사고 exporter에 전달하고, 사고 방출 packet을 PRISM의 피해 chain에 연결한 실행을 보존한다.

이번 기록의 연결은 다음과 같다.

```text
문헌 FrequencyPlan
  → 설비별 event ID·개구·사고 port
  → native lh2dt export_accident_history(request)
  → ResolvedGasRelease / ResolvedLiquidRelease / ResolvedGasReleaseSet
  → SLABx-LH2·SLABx 확산·풀·점화·화재/폭발 피해
  → 시설 campaign 회계와 미완료 사유
```

빈도는 packet에 복사하지 않는다. packet이 만들어졌다는 사실만으로 현장 빈도, provider 자격, 물리검증 또는 시설 IR/F-N 결과를 만들지 않는다.

## 최신 재실행 명령

외부 모델 소스는 다음 digest로 고정했다.

`1b9503c459470b899f684b8883ed3fe155a0900d0eb335011a74de770ae5ce52`

```powershell
$py = "C:\Users\lyul\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$lh2dt = "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models"

& $py scripts/build_native_generic_scope_packet_catalog.py `
  --lh2dt-root $lh2dt `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --output-dir results/20261023/native_generic_scope_packets_v10

& $py scripts/build_lh2_mixed_provider_campaign.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --accidental-catalog results/20261023/native_generic_scope_packets_v10/accidental_catalog.json `
  --emergency-relief-catalog results/20261023/native_generic_scope_packets_v10/emergency_relief_catalog.json `
  --two-sided-catalog results/20261023/native_generic_scope_packets_v10/two_sided_catalog.json `
  --request-defaults examples/provider_request_defaults.json `
  --annual-conditions examples/generic_lh2_full_scope_annual_conditions.json `
  --scope-provenance "current-source native generic scope; synthetic diagnostic only" `
  --rebase-positions --pool-radius-m 0.2 `
  --output results/20261023/native_generic_scope_campaign_v11.json

& $py scripts/run_lh2_mixed_provider_campaign.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign results/20261023/native_generic_scope_campaign_v11.json `
  --backend-config results/20261009/backend_config_current.json `
  --output results/20261023/native_generic_scope_campaign_result_v11.json
```

## 패킷 카탈로그 결과

| 항목 | 최신 결과 |
|---|---:|
| 문헌 initiating event | 24 |
| exact native packet | 24 |
| export 미계산 | 0 |
| 우발 방출 catalog | 21 |
| 비상 릴리프 catalog | 1 |
| 양단 파열 release-set catalog | 2 |
| 수치 안정화 재시도 | 5 |
| provider packet 승격 | 아니오 |
| 시설 QRA 주장 | 아니오 |

결과는 `results/20261023/native_generic_scope_packets_v10/verification.json`에 있다. 재시도는 저장탱크와 대형 배관의 적분 시계를 세분화하고, 저장탱크의 극초단 양의 재고 이력을 후단 장부가 읽을 수 있도록 조금 더 길게 유지한다. 사고 개구면적과 문헌 빈도는 바꾸지 않는다. 이는 합성 진단 입력의 수치 안정화이며 현장 사고 방출을 대신하지 않는다.

기화기 `inventory_over_600s`는 외부 모델의 6,000개 0.1초 시점을 packet 계약의 96개 구간으로 줄인다. 이때 질량과 정적 엔탈피 적분은 보존하고, 압력과 엔탈피를 평균한 뒤 CoolProp EOS로 온도와 밀도를 다시 계산한다. 따라서 평균화된 `P-H-T-rho`가 서로 모순되는 상태를 strict gas worker에 넘기지 않는다.

## 방출부터 피해까지 실행 결과

컴파일 결과 `results/20261023/native_generic_scope_campaign_v11.json`은 24개 요청을 모두 packet과 연결했다. 실제 실행 `results/20261023/native_generic_scope_campaign_result_v11.json`은 다음과 같다.

| 상태 | 건수 | 의미 |
|---|---:|---|
| `EXECUTED` | 5 | chain을 통과했고 해당 상태의 제한 표시가 없는 실행 |
| `EXECUTED_OPERATOR_LIMITED` | 18 | provider가 합성 상태, 종료시계, 경계 또는 미검증 가정을 소유하는 실행 |
| `FAILED` | 1 | 계산 중 질량 장부 검사에서 중단된 실행 |
| fresh physics case | 24 | 캐시가 아닌 새 피해 계산 |

실패 사건은 `storage-shell/AREA_1%`이며 사유는 `end-to-end hydrogen mass ledger failed`이다. 이 오류를 허용오차 확대나 질량 보정으로 숨기지 않고 실패 원장에 남겼다. 다섯 사례는 `EXECUTED_DOMAIN_INCOMPLETE` 표지를 함께 갖는다. 여기에는 액체/2상 flash·airborne liquid, 재고 종료, 수직 handoff처럼 선언된 범위 중 아직 완전히 닫히지 않은 경계가 반영된다.

한 실행의 시간은 약 275.6초였다. case 시간의 p95는 약 51.3초, p99는 약 61.7초다. 이 값은 1 Hz 또는 실시간 서비스 수준을 보증하지 않으며, 동일 PC에서 새 물리 계산을 수행한 한 번의 campaign 분포다.

`total_facility_annual_ir_low_high`와 `total_facility_expected_death_fn_low_high`는 `null`이다. 실제로 계산된 risk atom이 없다는 뜻이 아니라, 일부 사건과 provider 증거가 합성·부분 상태이므로 시설 전체 위험도로 승격하지 않았다는 뜻이다.

## 범위와 빈도 판정

`results/20261023/native_generic_scope_matrix_v5.json`은 12개 사고 family를 감사한다. 저장탱크·액체/2상·재고소진은 `PARTIAL`, 수직 handoff는 `NO_EVENT_GENERATED`, 시설 전체 IR/F-N은 보류다. `results/20261023/native_generic_scope_ledger_consistency_v5.json`은 24개 event ID와 실제 원장을 비교해 `CONSISTENT_SCOPE_LEDGER`를 반환했다.

`results/20261023/native_generic_scope_frequency_uncertainty_v7.json`은 문헌 빈도만 다시 가중하는 5개 시나리오를 계산했다. 새 물리 계산을 다시 하지 않았고, facility credible interval도 만들지 않았다. 이는 빈도 문헌의 불확실성을 표시하는 기능이며 현장 빈도 학습이 아니다.

## packet 소비 감사와 IJHE 준비도

- `native_generic_scope_packet_coverage_v7.json`: 24개 packet identity와 24개 consequence-chain event identity를 확인했지만, 빈도를 packet에 자동 결합하지 않는다.
- `native_generic_scope_packet_campaign_ledger_v9.json`: 24개 event/case, 23개 chain 실행, 1개 실패, 24개 packet identity/digest 소비를 기록한다.
- `native_generic_scope_worklist_packet_evidence_v7.json`: worklist 24개, candidate 24개, exact/strict 24개, consequence-chain 24개를 확인한다. 모두 synthetic diagnostic evidence다.
- `ijhe_completion_audit_native_generic_scope_v11.json`: 19개 검사 중 16개 PASS, 3개 BLOCKED인 `INCOMPLETE_EVIDENCE`다.

남은 세 가지 차단 이유는 다음과 같다.

1. qualified 또는 실제 시설 provider release packet이 없다.
2. 선언한 주요 사고 범위에 partial·미계산 family가 있다.
3. 위 두 이유 때문에 시설 IR/F-N을 제공할 수 없다.

따라서 현재 결과는 “설비 상태에서 방출을 만들고, 방출을 SLABx-LH2/SLABx와 피해 계산까지 연결하는 진단 체인”의 증거다. 일반 액화수소시설의 완전한 QRA나 IJHE용 검증 완료 결과가 아니다. IJHE 원고에는 이 경계를 그대로 쓰고, 다음 단계는 현장 설비 provider packet·수직 handoff·액체 flash/재고 종료 검증·독립 실험 비교로 제한하는 것이 맞다.
