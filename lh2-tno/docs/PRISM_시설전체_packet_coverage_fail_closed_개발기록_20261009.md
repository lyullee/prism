# 시설 전체 packet coverage fail-closed 보완

## 확인된 문제

2026-10-24 최신 merged facility ledger에는 29개 event가 있습니다. 이 중 24개는
`results/20261023/native_generic_scope_packets_v10`에서 다시 스캔한 native packet과
source/result digest가 모두 일치했습니다. 나머지 5개는 수직 handoff 영역 사건으로,
아직 packet evidence 파일이 없습니다.

이전 감사 함수는 packet evidence에 포함된 event만 비교한 뒤, campaign case에
provider identity가 기록되어 있으면 `packet_identity_consumed=true`로 표시할 수
있었습니다. 그러면 “24개 packet subset의 digest가 맞다”와 “29개 시설 event가 모두
packet을 소비했다”가 같은 값처럼 읽힐 수 있었습니다.

## 보완 내용

`src/lh2_tno/diagnostic_campaign_binding.py`가 다음 값을 분리해 기록합니다.

- `packet_subset_identity_consumed`: 선택된 packet subset의 source/result digest가
  packet 파일과 모두 일치하는지
- `packet_identity_consumed`: 시설 campaign의 모든 event가 packet evidence를 갖고
  digest까지 일치하는지
- `packet_scope_subset_complete`: packet subset이 campaign event/case/risk atom,
  component, opening geometry에 도달했는지
- `campaign_scope_packet_coverage_complete`: 시설 campaign event 전체가 packet
  evidence에 포함되는지
- `unbound_campaign_event_ids`와 세 가지 coverage ratio

따라서 현재 결과는 다음처럼 해석됩니다.

```text
24/24 packet digest match
packet subset consumption = true
29 facility events 중 5개 packet 미결합
full campaign packet consumption = false
facility QRA qualification = false
```

이는 새로운 빈도나 피해값을 만들지 않습니다. 수직 handoff 5개 사건은 계속
미결합 상태로 남고, 적격 provider·독립 물리검증·시설 IR/F-N gate도 그대로
차단됩니다.

## 재현 기록

```powershell
python scripts/audit_provider_worklist_packet_evidence.py `
  --provider-worklist results/20261024/native_generic_scope_worklist_with_native_binding_v1.json `
  --results-root results/20261023 `
  --output results/20261024/native_generic_scope_packet_evidence_v10.json

python scripts/audit_diagnostic_campaign_binding.py `
  --packet-evidence results/20261024/native_generic_scope_packet_evidence_v10.json `
  --campaign-result results/20261024/native_generic_scope_vertical_merged_facility_ledger_population_v3.json `
  --provider-worklist results/20261024/native_generic_scope_worklist_with_native_binding_v1.json `
  --packet-root . `
  --output results/20261024/native_generic_scope_vertical_diagnostic_campaign_binding_v4.json
```

결과는 `PARTIAL_DIAGNOSTIC_CAMPAIGN_BINDING`, packet subset 24/24, 전체 facility
coverage 24/29, `packet_identity_consumed=false`입니다. 이는 시설 전체 chain이
완료되었다는 주장이 아니라, 현재 연결된 범위를 정확하게 표시하는 감사 증거입니다.
