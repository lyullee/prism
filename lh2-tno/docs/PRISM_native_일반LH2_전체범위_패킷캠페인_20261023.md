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
  --output results/20261023/native_generic_scope_campaign_result_v12.json
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

컴파일 결과 `results/20261023/native_generic_scope_campaign_v11.json`은 24개 요청을 모두 packet과 연결했다. 실제 실행 `results/20261023/native_generic_scope_campaign_result_v12.json`은 다음과 같다.

| 상태 | 건수 | 의미 |
|---|---:|---|
| `EXECUTED` | 5 | chain을 통과했고 해당 상태의 제한 표시가 없는 실행 |
| `EXECUTED_OPERATOR_LIMITED` | 19 | provider가 합성 상태, 종료시계, 경계 또는 미검증 가정을 소유하는 실행 |
| `FAILED` | 0 | 계산 중 질량 장부 검사로 중단된 실행 없음 |
| fresh physics case | 24 | 캐시가 아닌 새 피해 계산 |

이전 실행에서 `storage-shell/AREA_1%`가 `end-to-end hydrogen mass ledger failed`로 중단된 원인은 후속 시점에 이미 wet area가 보고되는 작은 초기 pool에서 불필요한 미세시계 재정제가 source 보간을 흔들었기 때문이다. 현재 worker는 전체 실행에 wet area가 전혀 없을 때만 재정제하고, wet area가 있으면 native solver가 닫은 질량 장부를 그대로 사용한다. 허용오차 확대나 질량 보정은 하지 않았다. 최신 실행은 24개 case 모두 chain에 도달했고, 6개 case에는 액체/2상 flash·airborne liquid·재고 종료 경계처럼 선언된 범위 중 아직 완전히 닫히지 않은 `domain-incomplete` 표지가 남는다.

한 실행의 시간은 약 260.4초였다. case 시간의 p95는 약 50.7초, p99는 약 61.7초다. 이 값은 1 Hz 또는 실시간 서비스 수준을 보증하지 않으며, 동일 PC에서 새 물리 계산을 수행한 한 번의 campaign 분포다.

실시간 monitor의 동일 요청 cache 경로는 별도 benchmark로 측정했다. [`native_lh2_realtime_cache_benchmark_v1.json`](../examples/native_lh2_realtime_cache_benchmark_v1.json)은 native LH2 `AREA_0.01%` request에 대해 fresh physics 약 `2685.50 ms`, exact-cache 20/20 hit, cache median `31.47 ms`, p95 `33.23 ms`를 기록했다. 이 값은 cache lookup이 1 Hz deadline을 만족한 진단 증거이며, fresh physics 1 Hz 처리나 운영 SLA를 의미하지 않는다. 상태·방출 경계가 바뀌면 monitor는 새 계산을 수행하고 deadline 결과를 별도로 기록한다.

`total_facility_annual_ir_low_high`와 `total_facility_expected_death_fn_low_high`는 `null`이다. 실제로 계산된 risk atom이 없다는 뜻이 아니라, 일부 사건과 provider 증거가 합성·부분 상태이므로 시설 전체 위험도로 승격하지 않았다는 뜻이다.

## 범위와 빈도 판정

`results/20261023/native_generic_scope_matrix_v6.json`은 generic native campaign의 12개 사고 family를 감사한다. generic campaign만 보면 수직 handoff는 `NO_EVENT_GENERATED`였지만, 별도 all-bin 수직 handoff 진단을 공통 시설 namespace로 결합한 최신 병합 범위표에서는 `vertical_handoff: PARTIAL`로 기록된다. 병합 결과 `results/20261023/native_generic_scope_vertical_merged_scope_matrix_v1.json`은 29개 event·34개 case를 보존하며, 저장탱크·액체/2상·재고소진·양단 파열과 수직 handoff의 strict 상태를 승격하지 않는다. `results/20261023/native_generic_scope_vertical_merged_ledger_consistency_v1.json`은 병합 범위표와 시설 원장의 29개 event ID를 비교해 `CONSISTENT_SCOPE_LEDGER`를 반환했다.

`results/20261023/native_generic_scope_frequency_uncertainty_v8.json`은 문헌 빈도만 다시 가중하는 5개 시나리오를 계산했다. 새 물리 계산을 다시 하지 않았고, facility credible interval도 만들지 않았다. 이는 빈도 문헌의 불확실성을 표시하는 기능이며 현장 빈도 학습이 아니다.

병합 시설 원장의 수직 handoff까지 같은 빈도 시나리오에 포함하려면 다음 순서로 입력을 만든다.

```powershell
$py = "C:\Users\lyul\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $py scripts/build_merged_frequency_scenarios.py `
  --source examples/generic_lh2_mixed_frequency_scenarios.json `
  --output examples/native_lh2_generic_vertical_frequency_scenarios.json

& $py scripts/compute_frequency_uncertainty.py `
  --ledger results/20261023/native_generic_scope_vertical_merged_facility_ledger_repaired_v1.json `
  --scenarios examples/native_lh2_generic_vertical_frequency_scenarios.json `
  --output results/20261023/native_generic_scope_vertical_merged_frequency_uncertainty_v1.json
```

생성기는 generic asset 시나리오에 `vertical-handoff-vent: published`를 추가하고, event 시나리오에는 다섯 수직 handoff event를 `published`로 추가한다. 여기서 `published`는 현장 사고빈도를 새로 추정했다는 뜻이 아니라, 기존 수직 handoff 진단에 선언된 값을 빈도 재가중 입력으로 고정했다는 뜻이다. 따라서 결과는 29개 event를 다루는 5개 문헌 시나리오이지만, fresh physics·현장 빈도 학습·시설 credible interval을 만들지 않는다.

## packet 소비 감사와 IJHE 준비도

- `native_generic_scope_packet_coverage_v7.json`: 24개 packet identity와 24개 consequence-chain event identity를 확인했지만, 빈도를 packet에 자동 결합하지 않는다.
- `native_generic_scope_packet_campaign_ledger_v10.json`: 24개 event/case, 24개 chain 실행, 실패 0개, 24개 packet identity/digest 소비를 기록한다.
- `native_generic_scope_worklist_packet_evidence_v7.json`: worklist 24개, candidate 24개, exact/strict 24개, consequence-chain 24개를 확인한다. 모두 synthetic diagnostic evidence다.
- `ijhe_completion_audit_native_generic_scope_v12.json`: generic native campaign 기준 19개 검사 중 16개 PASS, 3개 BLOCKED인 `INCOMPLETE_EVIDENCE`다.
- `ijhe_completion_audit_native_generic_scope_vertical_v4.json`: generic v12와 all-bin vertical handoff를 병합한 2026-10-23 감사 스냅샷이다. 19개 검사 중 16개 PASS, 3개 BLOCKED이며, vertical handoff가 병합 범위표에 `PARTIAL`로 들어갔음을 확인한다. 최신 입력과 native binding 보정은 [`ijhe_completion_audit_native_generic_scope_vertical_v8.json`](../results/20261024/ijhe_completion_audit_native_generic_scope_vertical_v8.json)에서 22개 검사 중 19개 PASS, 3개 BLOCKED로 다시 기록했다. v8에는 시설 F/N 빈 배열의 원인을 설명하는 `conditional_diagnostic_facility_expected_death_fn_diagnostics`와 annual-condition population accounting도 포함된다.

남은 세 가지 차단 이유는 다음과 같다.

1. qualified 또는 실제 시설 provider release packet이 없다.
2. 선언한 주요 사고 범위에 partial·미계산 family가 있다.
3. 위 두 이유 때문에 시설 IR/F-N을 제공할 수 없다.

따라서 현재 결과는 “설비 상태에서 방출을 만들고, 방출을 SLABx-LH2/SLABx와 피해 계산까지 연결하며, 수직 handoff를 시설 event ledger에 결합하는 진단 체인”의 증거다. 일반 액화수소시설의 완전한 QRA나 IJHE용 검증 완료 결과가 아니다. IJHE 원고에는 이 경계를 그대로 쓰고, 다음 단계는 현장 설비 provider packet·수직 handoff의 독립 검증·액체 flash/재고 종료 검증·독립 실험 비교로 제한하는 것이 맞다.

## 수직 handoff를 generic 시설 원장에 결합한 최신 진단

generic v12 campaign에는 수직 handoff 사건이 생성되지 않았기 때문에, 기존 `results/20261020/vertical_vent_all_bins/verification.json`의 all-bin 진단을 별도 namespace로 보존한 뒤 `scripts/merge_facility_campaigns.py`로 generic campaign과 병합했다. 이 단계는 새 사고빈도를 만들지 않고, 수직 벤트의 `AREA_0.01%`, `AREA_0.1%`, `AREA_1%`, `AREA_10%`, `AREA_100%` 다섯 event와 두 기상 조건의 10개 case를 기존 시설 ID 아래에 기록하는 회계 결합이다.

최신 병합 원장은 [`native_generic_scope_vertical_merged_facility_ledger_repaired_v1.json`](../results/20261023/native_generic_scope_vertical_merged_facility_ledger_repaired_v1.json)이며 29개 event, 34개 case, 136개 risk atom을 보유한다. 병합 범위표 [`native_generic_scope_vertical_merged_scope_matrix_v1.json`](../results/20261023/native_generic_scope_vertical_merged_scope_matrix_v1.json)는 12개 family를 다시 확인하고 `vertical_handoff: PARTIAL`을 유지한다. 조건부 chain은 모두 도달했지만 strict 상태에는 operator-limited와 domain-incomplete가 남는다.

`audit_scope_ledger_consistency.py`의 결과 [`native_generic_scope_vertical_merged_ledger_consistency_v1.json`](../results/20261023/native_generic_scope_vertical_merged_ledger_consistency_v1.json)는 scope event 29개와 ledger event 29개가 일치하는 `CONSISTENT_SCOPE_LEDGER`다. 이 결과는 event·case 회계가 맞다는 뜻이며, provider 자격·독립 물리검증·시설 IR/F-N을 의미하지 않는다. 최신 IJHE 감사 [`ijhe_completion_audit_native_generic_scope_vertical_v8.json`](../results/20261024/ijhe_completion_audit_native_generic_scope_vertical_v8.json)는 이 병합을 읽어도 `INCOMPLETE_EVIDENCE`를 유지하고, 실제 provider packet 부재·partial 사고군·시설 IR/F-N 보류 세 가지 차단 이유를 남긴다.

병합 원장을 시설 assessment wrapper로 다시 읽은 결과는 `results/20261023/native_generic_scope_vertical_merged_facility_assessment_v1.json`이다. 이 결과는 5개 빈도 시나리오와 원장 risk atom을 다시 연결해 조건부 IR/F-N 필드를 노출하지만, `facility_total_risk_available=false`, `qualified_facility_qra_available=false`, `complete_facility_qra_claim=false`를 유지한다. 따라서 assessment wrapper는 시설 계산 경로가 실제로 호출됐다는 진단 증거이며, 부분·합성 입력을 완전한 시설 QRA로 바꾸는 승격 단계가 아니다.

이번 보완으로 assessment와 ledger에 `conditional_diagnostic_facility_expected_death_fn_diagnostics`를 추가했다. F/N은 N≥1 임계값으로 작성되므로, 현재 20 m 수용점 원장의 빈 배열은 `ZERO_EXPECTED_DEATH_AT_DECLARED_RECEPTORS`라는 명시적 상태를 갖는다. risk atom이 없어서 빈 배열인 경우(`NO_RISK_ATOMS`)와 구분되며, 0보다 작지 않은 기대 사망자가 N=1 아래에만 있는 경우도 `SUB_ONE_EXPECTED_DEATH_LEVEL_ONLY`로 구분한다.

## 비영 조건부 IR/F-N 연결 확인

병합 시설 원장의 일반 수용점은 source에서 20 m 떨어져 있어 현재 합성 방출량에서는 harm이 0으로 보인다. 계산 경로가 0값에만 의존하지 않는지 확인하기 위해 별도 [near-receptor 검증 요약](../examples/native_lh2_near_receptor_ir_fn_chain_verification.json)을 만들었다. `generic_lh2_near_receptor_manifest.json`의 합성 수용점을 source에서 0.5 m로 두고 저장탱크 `AREA_0.01%` 한 사건을 fresh physics로 실행한 결과, 한 `EXECUTED_OPERATOR_LIMITED` case에서 risk atom 4개와 조건부 IR `4.68×10^-5`가 생성됐다. 방출 질량잔차는 `7.92×10^-19 kg`, 새 물리 계산시간은 약 `2.694 s`였다.

같은 저장 결과를 `scripts/build_near_receptor_facility_assessment_summary.py`로 시설 원장에 통과시킨 요약도 [near-receptor facility assessment summary](../examples/native_lh2_near_receptor_facility_assessment_summary.json)에 기록했다. 여기서는 `CURVE_AVAILABLE` 상태와 N=1 누적빈도 `4.68×10^-5/year`가 확인되며, `facility_total_risk_available=false`와 `complete_facility_qra_claim=false`는 그대로 유지된다. 즉 20 m 원장의 명시적 0 피해와 0.5 m 연결 검증을 각각 보존하면서, F/N 계산 자체가 빈 배열 때문에 누락된 것으로 오해되지 않게 했다.

이번 재집계에서는 annual condition population도 함께 확인했다. generic 조건과 vertical 조건을 모두 보존한 결과는 [population binding summary](../examples/native_generic_scope_vertical_population_binding_summary.json)에서 보며, vertical의 네 수용점을 `worker-01`로 접은 부분은 `RECEPTOR_POPULATION_REBOUND_DIAGNOSTIC`으로 남는다. 이는 수용점·인구가 원장에 도달했다는 구조 증거이지만, 서로 다른 수용점 집단을 실제 시설 인구로 합산했다는 뜻이 아니다.

이 진단 campaign은 24개 생성 LOC 중 한 개만 실행하고 나머지 23개를 명시적 `UNCOMPUTED`로 남긴다. 따라서 nonzero IR은 수용점·기상·점화·피해 계산이 연결됐다는 증거이고, 실제 시설 인구·provider 적격성·물리검증·시설 전체 IR/F-N을 뜻하지 않는다. 원래 20 m generic geometry와도 합산하지 않는다.
