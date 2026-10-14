# PRISM 네이티브 일반 LH2 전체범위 재검증 기록 (2026-11-10)

이번 재검증은 일반 옥외 액화수소 시설의 7개 사고 대상 설비를 외부 `lh2dt_models`의 네이티브 사고 export와 다시 연결하고, 그 결과를 PRISM 시설 캠페인에 결합한 것이다. 입력은 합성 일반 시설과 문헌 빈도이므로 이 기록은 구조·계산 연결 진단이며, 현장 시설의 적격 QRA 결과가 아니다.

## 이번에 고친 연결 결함

1. 사고 요청에는 `failure_opening_diameter_m`가 있었지만 공통 사고 어댑터가 이를 `None`으로 바꾸고 있었다. 그 결과 배관·밸브·펌프처럼 유한한 실패 구경을 가진 방출도 구경 없는 재고 방출로 잘못 판정됐다. 사고 요청의 선언 구경을 gas/liquid strict adapter까지 보존하도록 수정했다.
2. 밸브 provider가 격리 기능을 사용하지 않을 때 `provider_meta`에 `isolation_time_s=null`을 기록했다. 선택적 제어값은 생략해야 하므로 `null` 항목을 제거하고, 실제 격리 제어를 요청했을 때만 숫자와 성공 여부를 기록하도록 수정했다.

관련 검증은 다음과 같다.

```powershell
python -m pytest tests/test_equipment_accident_export.py tests/test_equipment_release_adapter.py -q
# 36 passed
```

## 1. 네이티브 설비 사고 패킷 카탈로그

재현 명령:

```powershell
python scripts/build_native_generic_scope_packet_catalog.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --output-dir results/20261110/native_generic_scope_packets_latest2
```

결과:

| 항목 | 결과 |
|---|---:|
| 문헌 빈도 사건 | 24 |
| 네이티브 strict packet | 24/24 |
| 미계산 export | 0 |
| 상태 snapshot 바인딩·provider echo | 24/24 |
| accidental release | 21 |
| emergency relief | 1 |
| two-sided rupture | 2 |
| qualified provider packet | 0 |
| 물리검증 주장 | false |

24개 사건은 저장탱크 5개 hole 크기, 이송배관 5개, 밸브 5개, 압력방출 벤트 1개, 펌프 2개, 기화기 3개, 재액화기 3개를 포함한다. 재액화기 G4/G5는 두 개의 명시적 출구를 가진 하나의 `ResolvedGasReleaseSet`으로 기록된다. packet은 방출 지속시간, 질량 장부, 종료 basis, port identity와 source/result digest를 보존한다.

카탈로그 결과는 `results/20261110/native_generic_scope_packets_latest2/verification.json`과 `state_snapshot_binding_audit.json`에 저장된다. 별도 packet evidence 감사도 다음 명령으로 재현할 수 있다.

```powershell
python scripts/build_native_scope_packet_evidence.py `
  --catalog results/20261110/native_generic_scope_packets_latest2/verification.json `
  --state-snapshot-audit results/20261110/native_generic_scope_packets_latest2/state_snapshot_binding_audit.json `
  --output results/20261110/native_generic_scope_packets_latest2/native_scope_packet_evidence.json
# EXACT_NATIVE_SCOPE_PACKET_EVIDENCE, 24/24
```

여기서 `EXACT_NATIVE_PACKET`은 모델 호출·packet identity·상태 snapshot echo가 닫혔다는 뜻이다. 합성 초기조건, 현장 차단 신뢰도, 현장 사고빈도, 독립 물리검증을 자동으로 만들어 주지는 않는다.

## 2. 문헌 빈도와 PRISM 캠페인 결합

카탈로그 packet을 문헌 빈도에 붙이는 캠페인을 다음과 같이 생성했다.

```powershell
python scripts/build_lh2_mixed_provider_campaign.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --accidental-catalog results/20261110/native_generic_scope_packets_latest2/accidental_catalog.json `
  --emergency-relief-catalog results/20261110/native_generic_scope_packets_latest2/emergency_relief_catalog.json `
  --two-sided-catalog results/20261110/native_generic_scope_packets_latest2/two_sided_catalog.json `
  --request-defaults results/20261024/provider_request_defaults_domain_recovery_v1.json `
  --annual-conditions examples/generic_lh2_full_scope_annual_conditions.json `
  --scope-provenance "native external lh2dt generic outdoor scope catalog; synthetic diagnostic only; 2026-11-10 recheck" `
  --rebase-positions `
  --pool-radius-m 0.2 `
  --output results/20261110/native_generic_scope_campaign_latest2.json
```

캠페인 컴파일 결과는 24/24 event route가 provider packet과 결합되었고, 빈도는 packet에서 추출하지 않았다. `FrequencyPlan`이 문헌 빈도를 제공하고, packet은 방출 이력만 제공한다.

## 3. 방출부터 시설 위험 원장까지의 실행

```powershell
python scripts/run_native_full_scope_frequency_assessment.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign results/20261110/native_generic_scope_campaign_latest2.json `
  --backend-config results/20261009/backend_config_current.json `
  --output-dir results/20261110/native_full_scope_frequency_assessment_latest2
```

실행 결과:

| 단계 | 결과 |
|---|---:|
| 시설 case | 24 |
| 수치 실행 case | 24 |
| risk atom | 96 |
| 완전 `EXECUTED` | 5 |
| `EXECUTED_OPERATOR_LIMITED` | 19 |
| 문헌 빈도 시나리오 | central / p05 / p95 |
| provider worklist 정합 | 24/24 `ALIGNED` |
| 조건부 진단 IR/F-N | 계산 경로 생성 |
| 적격 시설 전체 QRA | 보류 |

각 case는 provider release packet을 소비한 뒤 다음 공통 경로를 실행한다.

```text
설비 상태 snapshot
  → provider 방출 지속시간·차단·재고 장부
  → SLABx-LH2/SLABx 누출·확산 및 cloud observation
  → 기상·점화 branch·화재/폭발 피해
  → 인구 receptor·IR/F-N 원장
  → 설비·사고군·빈도 시나리오별 집계
```

이번 실행은 일반 full-scope manifest에서 worker receptor가 방출원에서 멀어 조건부 IR/F-N 값이 0으로 나타났다. 이것은 위험이 없다는 결론이 아니라, 선언한 합성 receptor에서 사망 threshold가 관측되지 않았다는 진단 결과다. near-receptor manifest로 동일 packet을 재실행해도 계산 경로와 게이트 상태는 동일하게 유지된다.

## 4. 처리시간과 실시간 해석

최신 24-case fresh-physics 실행은 약 149.4초였다. case별 중앙값은 약 4.01초, p95는 약 16.18초, 최대는 약 20.96초였다. 이 수치는 한 번의 캠페인 실행에서 얻은 처리시간이며 1 Hz fresh-physics 보장이나 서비스 수준 인증이 아니다. 실시간 모니터링에서는 exact cache, 위험조건 도달 case 선택, warm worker와 별도 지연시간 검증이 필요하다.

캠페인 결과를 별도 chain-closure 감사로 재합산했을 때 24/24 event가 packet identity를 소비했고, packet이 없는 event는 0건, IR aggregate closure와 F/N aggregate closure는 모두 `true`였다. 이 감사가 의미하는 것은 계산 원장의 합산 일관성이다. qualified provider, 독립 물리검증, 시설 전체 QRA 승격을 의미하지 않는다.

```powershell
python scripts/audit_native_packet_campaign_execution.py `
  --campaign results/20261110/native_generic_scope_campaign_latest2.json `
  --result results/20261110/native_full_scope_frequency_assessment_latest2/campaign_result.json `
  --provenance results/20261110/native_full_scope_frequency_assessment_latest2/binding_provenance.json `
  --state-snapshot-audit results/20261110/native_generic_scope_packets_latest2/state_snapshot_binding_audit.json `
  --output results/20261110/native_full_scope_frequency_assessment_latest2/native_packet_campaign_execution_ledger.json

python scripts/audit_facility_chain_closure.py `
  --campaign-result results/20261110/native_full_scope_frequency_assessment_latest2/campaign_result.json `
  --packet-evidence results/20261110/native_generic_scope_packets_latest2/native_scope_packet_evidence.json `
  --packet-root results/20261110/native_generic_scope_packets_latest2 `
  --output results/20261110/native_full_scope_frequency_assessment_latest2/facility_chain_closure_audit.json
```

## 남은 차단 항목

- 24개 packet은 모두 synthetic diagnostic이며 qualified actual provider packet은 0개다.
- 19개 case는 provider가 일정 상태·열린 물리 경계·운전자 제한 조건을 남겨 `EXECUTED_OPERATOR_LIMITED`로 기록된다.
- 시설별 실제 재고, 차단시간·실패확률, 포트 위치, 기상·인구 자료가 필요하다.
- `vertical_handoff` 사고군은 별도 provider 사건으로 생성되지 않았다.
- SLABx-LH2의 독립 실험·실증 검증 자료와 시설별 물리검증 evidence가 아직 연결되지 않았다.
- 따라서 `facility_total_risk_available=false`, `provider_packet_promoted=false`, `physical_validation_claim=false`, `facility_qra_claim=false`를 유지한다.

최신 입력을 반영한 IJHE completion audit는 21개 검사 중 14개를 통과하고 7개를 차단했다. 새로 확인된 diagnostic packet·상태 snapshot·campaign chain·문헌 빈도 불확실성·처리시간 검사는 통과했으며, 남은 차단은 시설 release boundary, qualified provider packet, major accident scope, 적격 시설 IR/F-N, 독립 물리검증, 실시간 monitor contract와 설비 모델 binding gate다. 감사 원장은 `results/20261110/native_full_scope_frequency_assessment_latest2/ijhe_completion_audit_latest2.json`이다.

이번 재검증으로 “설비별 native 상태·방출 → SLABx-LH2/피해 → 점화·노출 → 문헌 빈도 기반 시설 원장”이라는 계산 연결은 24개 선언 사건에 대해 실행 가능한 상태가 됐다. 위 차단 항목을 해소하기 전까지는 일반 시설의 인증된 전체 위험도라고 표시하지 않는다.
