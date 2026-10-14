# Native LH2 설비별 격리 분기 catalog

## 목적

기존 일반 LH2 catalog의 고정 진단시계를 그대로 두지 않고, 배관·밸브·펌프·기화기·재액화기 사고에서 격리 명령 시각과 격리 후 zero-flow 관찰을 provider packet에 넣는 선택형 경로를 만들었다. 이 경로는 시설별 실제 차단 신뢰도나 사고빈도를 추정하지 않는다. 외부 `lh2dt` 모델이 계산한 actuator 동작과 packet 경계를 PRISM의 방출→피해 연결에 전달할 수 있는지 확인하는 진단 catalog다.

## 재현

```powershell
python scripts/build_native_generic_scope_packet_catalog.py `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --output-dir results/20261111/native_generic_scope_packets_isolation `
  --isolation-time-s 0.1 `
  --post-isolation-observation-s 0.2

python scripts/build_native_scope_packet_evidence.py `
  --catalog results/20261111/native_generic_scope_packets_isolation/verification.json `
  --state-snapshot-audit results/20261111/native_generic_scope_packets_isolation/state_snapshot_binding_audit.json `
  --output results/20261111/native_generic_scope_packets_isolation/native_scope_packet_evidence.json
```

## 결과

[`isolation_branch_audit.json`](../results/20261111/native_generic_scope_packets_isolation/isolation_branch_audit.json)은 다음을 기록한다.

| 항목 | 결과 |
| --- | ---: |
| 문헌 사건 수 | 24 |
| exact native packet | 24 |
| 미계산 사건 | 0 |
| 상태 snapshot bound·echo | 24/24 |
| 명시적 격리 성공 branch | 14 |
| exporter 총 wall-clock | 약 81.1초 |

격리 성공 branch는 이송배관 5개, 이송밸브 5개, 이송펌프 2개, 기화기 1개, 재액화기 1개다. 나머지 사건은 inventory depletion 6개, emergency relief discharge 1개, inventory-over-600 s 1개, two-sided rupture 2개로 분리되어 termination basis를 보존한다.

각 성공 branch는 `isolation_time_s=0.1 s`, provider별 stroke, `post_isolation_observation_s=0.2 s`를 사용하고, 외부 모델이 actuator opening 0과 zero-flow를 확인한 경우에만 `reviewed_isolation_success`를 기록한다. 이 명칭은 현장 차단 성공확률을 뜻하지 않는다.

## 현재 시설 QRA와의 관계

이 catalog는 packet·상태·종료근거를 닫은 구조 진단이다. `provider_packet_promoted=false`, `physical_validation_claim=false`, `facility_qra_claim=false`를 유지한다. 문헌 빈도는 packet 생성 단계에서 부여하지 않으며, 현장 사고빈도 수집이나 센서 기반 빈도 학습도 수행하지 않는다. 실제 시설 IR/F-N에 포함하려면 설비별 검토 packet, 차단·재고·질량/에너지 장부, provider qualification sidecar, 독립 물리검증과 시설 조건 검토가 추가로 필요하다.

## IJHE 준비도 감사 연결

`build_ijhe_completion_audit.py --native-scope-isolation-branch-catalog-audit results/20261111/native_generic_scope_packets_isolation/isolation_branch_audit.json`로 이 기록을 준비도 감사에 연결할 수 있다. 최신 결과([`ijhe_completion_audit_with_observed_hazop_runtime_frequency_provider_binding_storage_vaporizer_isolation_catalog_isolation_branch_checks.json`](../results/20261111/ijhe_completion_audit_with_observed_hazop_runtime_frequency_provider_binding_storage_vaporizer_isolation_catalog_isolation_branch_checks.json))는 전체 33개 검사 중 28개를 통과시키고 5개 strict blocker를 남긴다. 새 검사는 24개 exact packet, 24/24 상태 snapshot echo, 14개 격리 성공 branch, 이벤트별 wall-clock과 총 약 81.1초를 확인한다. 이 검사는 `diagnostic_only`이며, catalog가 합성 입력이라는 사실과 qualified provider·독립 검증·시설 전체 IR/F-N 보류를 그대로 보존한다.
