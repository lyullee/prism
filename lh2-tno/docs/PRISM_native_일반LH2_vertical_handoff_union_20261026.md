# native 일반 LH2 + vertical handoff union (2026-10-26)

기존 native 일반 LH2 캠페인은 저장탱크·배관·밸브·벤트·펌프·기화기·재액화기의 24개 사건을 계산했지만 `vertical_handoff` 사건을 생성하지 않았다. 이번 union 실행은 이미 계산된 수직 handoff all-bin 결과를 새로 물리 계산한 것으로 가장하지 않고, 현재 near-receptor 시설 namespace로 명시적으로 rebind한 뒤 두 장부를 병합했다.

## 재현

```powershell
python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261026/native_full_scope_frequency_assessment `
  --vertical-result results/20261020/vertical_handoff_rebound_facility_result_all_bins.json `
  --vertical-scope-matrix results/20261020/vertical_handoff_scope_matrix_all_bins.json `
  --output-dir results/20261026/native_full_scope_union_assessment
```

## 연결 결과

| 항목 | 결과 |
|---|---:|
| 기존 native 사건 | 24개 |
| vertical handoff 사건 | 5개 |
| 병합 사건 | 29개 |
| 병합 case | 34개 |
| 병합 risk atom | 136개 |
| vertical strict 상태 | `PARTIAL` |
| vertical 조건부 수치 상태 | `EXECUTED` |
| vertical 조건부 실행 case | 10개 |
| vertical operator-limited case | 10개 |
| qualified provider packet | 0개 |
| 시설 전체 IR/F-N | 보류 |
| 자동 증거 요청 | 12개 사고군·34개 case |

수직 결과의 event ID, provider packet identity, 설비 ID와 수용점 ID를 `generic-lh2-near-receptor-diagnostic/vertical-handoff/...` namespace로 함께 바꿨다. 사고범위 표에서도 `vertical_handoff`가 `NO_EVENT_GENERATED`에서 `PARTIAL`로 바뀌고, 조건부 chain은 10개 case 모두 숫자를 갖는다. 그러나 source history가 synthetic/operator-limited이고 전체 시설의 다른 사고군도 partial이므로 시설 전체 IR/F-N과 QRA gate는 계속 닫혀 있다.

빈도는 수직 결과에서 역산하지 않았다. 기존 문헌 시나리오에 `vertical-handoff-vent` 자산을 `published`로 명시해 저장된 risk atom만 재가중했다. 따라서 이 union은 사고군 누락을 줄인 범위 회계와 조건부 진단이며 현장 빈도, qualified packet, 독립 물리검증, 1 Hz 신규 물리 계산을 주장하지 않는다.

산출물은 `results/20261026/native_full_scope_union_assessment/` 아래에 있다.

- `campaign_result.json`: 29개 사건·34개 case·136개 risk atom 병합 원장
- `vertical_handoff_rebound_result.json`: namespace rebind provenance가 포함된 5개 vertical 사건 원장
- `scope_matrix.json`: 12개 주요 사고군의 병합 상태
- `facility_assessment.json`: 조건부 IR/F-N과 시설 QRA gate
- `facility_evidence_request.json`: 각 사고군·case의 provider packet·물리검증·종료/재고 증거 요구
- `verification.json`: 병합 수·상태·제한 자동 검사
- `ijhe_completion_audit.json`: 17개 검사 중 13개 PASS·4개 BLOCKED
