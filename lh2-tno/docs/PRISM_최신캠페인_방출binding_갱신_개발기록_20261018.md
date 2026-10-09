# 최신 캠페인 방출 binding 갱신 기록

## 무엇을 갱신했는가

이전 진단 기록이 2026-10-15의 rebound 캠페인을 가리키고 있어, 현재 정제 캠페인과 event/risk atom 수가 일치하지 않았다. 다음 세 장부를 같은 실행으로 다시 비교했다.

- 현재 provider worklist: `results/20261017/provider_worklist_with_scenario_families.json`
- 현재 방출 packet evidence: `results/20261014/generic_lh2_provider_worklist_packet_evidence.json`
- 현재 정제 캠페인: `results/20261018/generic_mixed_provider_campaign_refined_pool_current.json`

명령:

```powershell
.venv\Scripts\python.exe scripts/audit_diagnostic_campaign_binding.py `
  --packet-evidence results/20261014/generic_lh2_provider_worklist_packet_evidence.json `
  --campaign-result results/20261018/generic_mixed_provider_campaign_refined_pool_current.json `
  --provider-worklist results/20261017/provider_worklist_with_scenario_families.json `
  --packet-root . `
  --output results/20261018/generic_lh2_diagnostic_campaign_binding_current.json
```

## 확인 결과

- provider event: 24
- campaign event: 24
- campaign case: 24
- campaign risk atom: 96
- event·case·risk atom 일치: 24/24
- component 일치: 24/24
- 개구 geometry 일치: 21/21 (재고 소진·릴리프처럼 개구가 없는 3개는 명시적 경계로 기록)
- packet digest 확인: 24개
- 저장 packet digest 일치: 18개
- `structural_binding_complete`: `true`
- `packet_identity_consumed`: `false`
- 빈도 생성: `false`
- 적격 provider packet: 0
- 시설 QRA 주장: `false`

따라서 현재 기록은 **구조적 event→case→risk atom 연결이 완성된 진단 증거**이다. 6개 event는 현재 캠페인의 provider digest가 기존 저장 packet 파일과 같다는 것을 증명하지 못했으므로 packet 시간 이력을 소비했다고 표시하지 않는다. 이 불일치는 방출 packet을 새로 만들거나 빈도를 추정해서 메우지 않고, 일치하는 18개와 미확인 6개를 그대로 남긴다.

## IJHE 감사 해석

`external_native_model_contract_audit`, `actual_provider_release_packet`, 사고 범위 완전성, 전체 시설 IR/F-N 차단 사유는 변하지 않는다. 이번 갱신은 stale binding 장부를 제거하고 현재 캠페인의 구조 연결을 정확히 기록한 것이다. `PARTIAL_DIAGNOSTIC_CAMPAIGN_BINDING`은 설비 사고방출 packet의 적격성이나 현장 물리검증을 의미하지 않는다.
