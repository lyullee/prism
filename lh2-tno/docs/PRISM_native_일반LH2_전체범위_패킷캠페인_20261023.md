# PRISM native 일반 LH2 전체범위 패킷·캠페인 기록 (2026-10-23)

## 목적

일반 옥외 액화수소시설 예제의 24개 문헌 빈도 사건을 외부 `lh2dt_models`의 사고 전용 `export_accident_history(request)` 경계로 하나씩 실행했다. 이 기록은 특정 액화수소검사지원센터의 태그나 운전값을 사용하지 않는다. `generic_lh2_full_scope_manifest.json`과 `generic_lh2_full_scope_frequency_plan.json`은 구조·빈도 연결을 확인하기 위한 합성 예제다.

이번 작업은 다음 연결을 확인한다.

```text
문헌 FrequencyPlan
  → 설비별 사고 event ID·개구·포트
  → native lh2dt 사고 export
  → ResolvedGasRelease / ResolvedLiquidRelease / ResolvedGasReleaseSet
  → SLABx-LH2·SLABx 피해 chain
  → 시설 campaign 회계
```

빈도는 packet에 복사하지 않는다. packet이 정확히 생성돼도 현장 빈도·자격 provider·시설 IR/F-N으로 승격되지 않는다.

## 실행 명령

외부 모델 소스는 현재 digest `1b9503c459470b899f684b8883ed3fe155a0900d0eb335011a74de770ae5ce52`로 고정해 실행했다.

```powershell
$py = "C:\Users\lyul\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$lh2dt = "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models"

& $py scripts/build_native_generic_scope_packet_catalog.py `
  --lh2dt-root $lh2dt `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --output-dir results/20261023/native_generic_scope_packets_v4

& $py scripts/build_lh2_mixed_provider_campaign.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --accidental-catalog results/20261023/native_generic_scope_packets_v4/accidental_catalog.json `
  --emergency-relief-catalog results/20261023/native_generic_scope_packets_v4/emergency_relief_catalog.json `
  --two-sided-catalog results/20261023/native_generic_scope_packets_v4/two_sided_catalog.json `
  --request-defaults examples/provider_request_defaults.json `
  --annual-conditions examples/generic_lh2_full_scope_annual_conditions.json `
  --scope-provenance "current-source native generic scope; synthetic diagnostic only" `
  --rebase-positions --pool-radius-m 0.2 `
  --output results/20261023/native_generic_scope_campaign.json

& $py scripts/run_lh2_mixed_provider_campaign.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign results/20261023/native_generic_scope_campaign.json `
  --backend-config results/20261009/backend_config_current.json `
  --output results/20261023/native_generic_scope_campaign_result.json
```

## 결과

| 항목 | 결과 |
|---|---:|
| 문헌 빈도 이벤트 | 24 |
| exact native packet | 17 |
| export 미계산 | 7 |
| 우발 방출 catalog | 14 |
| 비상 릴리프 catalog | 1 |
| 양단 파열 release-set catalog | 2 |
| campaign에 연결된 요청 branch | 13 |
| campaign 미계산 branch | 11 |
| `EXECUTED` | 4 |
| `EXECUTED_OPERATOR_LIMITED` | 8 |
| `FAILED` | 1 |
| fresh physics case | 13 |
| campaign 시간 | 약 94.5 s |
| 시설 전체 IR/F-N | 보류 |

packet coverage ledger는 17개 native packet 디렉터리의 event/component/port identity와 종료·질량 장부를 확인했다. `provider_packet_promoted=false`, `frequency_inference_performed=false`, `physical_validation_claim=false`, `facility_qra_claim=false`를 모든 행에서 유지한다.

600초 기체 재고 사건은 외부 모델 내부 0.1초 계산 이력(6,000구간)을 PRISM packet의 최대 100구간 계약에 맞춰 96개 구간으로 질량·정적 엔탈피 보존형 압축했다. packet 결과는 duration `600.0 s`, mass residual `0 kg`, energy residual `0 J`이다. 압축은 provider 내부 상태 계산을 바꾸지 않고 PRISM 경계 trace만 줄인다.

## 미계산을 숨기지 않은 이유

다음 일곱 사건은 모델이나 입력 계약의 제한을 그대로 남겼다.

- 저장탱크 `AREA_0.1%`, `1%`, `10%`, `100%`: 현재 LayeredTank native solver가 대형 개구에서 양의 질량·압력 상태를 유지하지 못했다.
- 이송배관 `AREA_100%`: DynamicHEMPipe가 세 번째 interval에서 유효하지 않은 outward flow를 반환했다.
- 이송펌프 `G1`, `G2`: MappedPump 운전점과 대기 밸브 방출 유량이 각각 상대오차 `2163.85`, `20.6485`로 일치하지 않았다.

추가로 배관의 문헌 길이 빈도는 `location_weight`가 없는 5개 사건을 하나의 방출점에 몰아넣지 않도록 campaign branch에서 계속 `UNCOMPUTED`로 둔다. 이 미계산은 위험 0이나 빈도 재배분으로 해석하지 않는다.

## IJHE 준비도 판정

`results/20261023/ijhe_completion_audit_native_generic_scope_v4.json`의 감사는 19개 검사를 수행하고 `INCOMPLETE_EVIDENCE`를 반환했다. native 소스 계약, native 바인딩 정합성, 구조 packet coverage, 빈도 불확실성, 처리시간, 실시간 모니터 계약, 범위·원장 일관성은 PASS다. 다음 네 gate는 계속 차단된다.

1. qualified 또는 실제 시설 provider packet이 없다.
2. 24개 worklist 전체를 exact native packet으로 닫지 못했다.
3. 선언한 주요 사고군에 미계산·실패 사건이 있다.
4. 합성·부분 범위이므로 시설 전체 IR/F-N을 제공할 수 없다.

이 판정은 방출→피해 연결 코드가 없다는 뜻이 아니다. 13개 요청 branch는 실제 campaign chain까지 들어갔고, 남은 범위는 모델 수치 안정화, 펌프 경계 계약, 배관 위치 빈도 배분, 현장 provider packet과 물리 검증이다.

## 다음 개발 항목

1. LayeredTank 대형 개구의 안정적인 압력·질량 종료 조건을 외부 모델에서 검증한다.
2. MappedPump 사고 모드에서 펌프 유량과 대기 방출 경계의 단일 provider 소유 계약을 정한다.
3. 배관 segment별 reviewed `location_weight`를 입력받아 길이 빈도를 물리 위치에 배분한다.
4. 실제 시설 provider가 반환한 종료시계·재고·flash/ground partition을 같은 catalog 계약으로 교체한다.
5. 독립 실험 자료와 source digest를 연결한 사고 방출 검증을 추가한 뒤에만 시설 IR/F-N gate를 다시 검토한다.

## 결과 파일

- `results/20261023/native_generic_scope_packets_v4/verification.json`
- `results/20261023/native_generic_scope_packets_v4/accidental_catalog.json`
- `results/20261023/native_generic_scope_packets_v4/emergency_relief_catalog.json`
- `results/20261023/native_generic_scope_packets_v4/two_sided_catalog.json`
- `results/20261023/native_generic_scope_packet_coverage.json`
- `results/20261023/native_generic_scope_campaign.json`
- `results/20261023/native_generic_scope_campaign_result.json`
- `results/20261023/native_generic_scope_matrix_v2.json`
- `results/20261023/native_generic_scope_ledger_consistency_v2.json`
- `results/20261023/ijhe_completion_audit_native_generic_scope_v4.json`
