# PRISM 일반 LH2 전체범위 상태 snapshot·방출경계 감사 (2026-10-27)

이번 보완의 목적은 설비별 공정 상태가 사고 방출 계산으로 넘어갈 때 원문이
사라지지 않도록 하는 것이다. 방출 packet에 압력·온도·상·위치 같은 상태값을
방출량에서 거꾸로 만들어 넣지 않고, 각 exporter가 명시한 상태 snapshot을
그대로 요청에 넣는다.

## 구현한 경계

각 adapter는 다음 순서로 동작한다.

1. 외부 모델의 명시한 초기 압력·온도·상태·위치를
   `prism.equipment_state_snapshot.v1`로 만든다.
2. snapshot의 canonical SHA-256 digest를 사고 export 요청에 넣는다.
3. provider는 같은 digest를 `provider_state_snapshot_digest`로 echo한다.
4. PRISM은 snapshot의 설비 ID와 digest를 다시 검사한 뒤에만 strict
   `ResolvedGasRelease`, `ResolvedLiquidRelease` 또는 양단 release set을 만든다.
5. 검증 파일에는 요청 snapshot, provider echo, digest 일치 여부를 함께 보존한다.

대상 adapter는 저장탱크, DynamicHEMPipe, Valve, VentStack, MappedPump,
DynamicVaporizer/DynamicReliquefier inventory, DynamicReliquefier two-sided rupture다.
상태 snapshot에는 누출구경·방출시간·빈도·종료근거·방출 이력을 넣지 않는다.

## 재현 명령

```powershell
python scripts/build_native_generic_scope_packet_catalog.py `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --output-dir results/20261027/native_generic_scope_packets_state_bound
```

이 명령은 24개 사건을 실행하고 `verification.json`,
`state_snapshot_binding_audit.json`, 사건별 `events/*/verification.json`을
보존한다.

카탈로그를 campaign에 재결합할 packet evidence는 다음처럼 만든다.

```powershell
python scripts/build_native_scope_packet_evidence.py `
  --catalog results/20261027/native_generic_scope_packets_state_bound/verification.json `
  --state-snapshot-audit results/20261027/native_generic_scope_packets_state_bound/state_snapshot_binding_audit.json `
  --output results/20261027/native_generic_scope_packets_state_bound/packet_evidence.json
```

그 다음 `rebind_campaign_to_worklist_packets.py`로 strict packet을 campaign에
넣고 `run_native_full_scope_frequency_assessment.py`를 실행한다. 마지막으로
`audit_native_packet_campaign_execution.py --state-snapshot-audit ...`를 호출하면
packet identity 소비와 snapshot event/component 대조가 별도 장부에 남는다.
현재 union 재현에서는 `run_native_full_scope_union_assessment.py`에 이 catalog의
campaign과 result를 함께 넘겨 `native_state_snapshot_campaign_ledger.json`을 만들고,
provider result digest까지 같은 사건별로 대조한다.

| 항목 | 결과 |
|---|---:|
| 문헌 사건 | 24 |
| exact native packet | 24 |
| 미계산 exporter | 0 |
| snapshot 감사 행 | 24 |
| `BOUND_AND_ECHOED` | 24 |
| digest 불일치 | 0 |
| provider packet 승격 | 0 |
| 물리검증 claim | 0 |
| 시설 QRA claim | 0 |

양단 파열은 두 endpoint가 같은 snapshot digest를 각각 echo한다. 감사기는 provider
echo가 배열인 경우에도 모든 endpoint가 같은 canonical digest를 보냈을 때만 해당
사건을 bound로 센다.

## 해석 범위

이 결과는 상태 snapshot이 사고 export 경계까지 보존된다는 통합 시험이다. 각
상태와 형상은 일반 설비를 위한 합성 진단 입력이며, 현장 계측값·현장 재고·밸브
신뢰도·실제 사고빈도를 뜻하지 않는다. 문헌 빈도는 별도 `FrequencyPlan`에서만
들어오고 snapshot으로부터 학습하지 않는다. provider의 방출 이력이
`EXECUTED_OPERATOR_LIMITED`이면 그 제한은 그대로 campaign과 시설 ledger에
남는다. 따라서 24/24 snapshot binding은 qualified provider packet이나 시설
연간 IR/F/N을 열지 않는다.

기존 2026-10-26 union 감사의 26행(대표 진단 2행 + campaign 24행)은 이전
campaign JSON에 상태 payload가 없었기 때문에 24행이 `UNBOUND`였다. 이번
카탈로그는 새로 실행한 24개 native verification 원문을 보존하고, union은 이
동일한 새 campaign result를 사용해 packet 결과 digest까지 재결합한다.

이후 `rebind_campaign_to_worklist_packets.py`로 24개 campaign request를 이
카탈로그의 strict packet에 다시 결합하고, `run_native_full_scope_frequency_assessment.py`를
재실행했다. 결과는 24/24 event, 24/24 case, 24/24 consequence-chain 실행,
96개 risk atom, 19개 `EXECUTED_OPERATOR_LIMITED`였고 시설 전체 QRA는 계속
보류됐다. `native_state_snapshot_campaign_ledger.json`의
`state_snapshot_campaign_reconciliation`은 campaign event ID 24개와 snapshot
감사 event 24개, component ID, provider result digest가 모두 일치함을 기록한다.
이 대조는 상태 snapshot이 campaign에 사용된 native packet과 같은 사건에 붙었음을
보여주는 진단 연결이며, 수직 handoff·inventory depletion까지 자동으로 bound했다고
가정하지 않는다. provider 자격이나 현장 위험도 승격도 아니다.
