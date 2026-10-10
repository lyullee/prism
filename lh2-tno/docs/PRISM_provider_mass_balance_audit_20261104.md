# PRISM 공급자 질량수지 연결 점검 (2026-11-04)

## 왜 추가했나

방출량만 보면 “얼마나 밖으로 나왔는가”는 알 수 있습니다. 설비 모델은 여기에 “설비 안에 얼마가 남았는가”를 별도로 보고할 수 있습니다. 두 정보를 섞으면 차단 뒤 남은 배관 재고를 전량 방출 또는 재고 고갈로 잘못 읽을 수 있습니다.

이번 보완은 외부 액화수소 설비 모델의 `data.provider_meta` 질량수지를 `prism.provider_mass_balance.v1`로 보존합니다. PRISM은 이 값을 다시 계산해 고치지 않습니다. 다음 식의 결과를 그대로 표시합니다.

```text
설비 질량수지 잔차 = 최종 질량 + 누적 유입 질량 - 초기 질량 - 누적 유출 질량
```

잔차가 0에 가까우면 공급자 질량수지가 닫힌 것입니다. 잔차가 남거나 필요한 값이 없으면 진단 결과로만 남고, 엄격한 방출 경계 승인에는 사용할 수 없습니다.

## 현재 외부 LH2 모델 결과

정본 결과는 [`provider_mass_balance_audit_current.json`](../results/20261104/provider_mass_balance_audit_current.json)입니다. 외부 모델의 7개 사고방출 결과를 읽은 결과는 다음과 같습니다.

| 상태 | 개수 | 의미 |
|---|---:|---|
| `CLOSED` | 3 | 초기·최종·유출 질량의 공급자 수지가 허용오차 안에서 닫힘 |
| `PARTIAL` | 3 | 잔류 질량은 있으나 초기 또는 최종 질량이 없어 전체 수지를 확인할 수 없음 |
| `UNBALANCED` | 1 | 공급자가 보고한 초기·최종·유출 질량이 서로 맞지 않음 |

`DynamicHEMPipe` 결과가 `UNBALANCED`입니다. 초기 질량은 약 2.5156 kg, 누적 유출량도 약 2.5156 kg인데 최종 질량 1.0939 kg이 남아 있어, 현재 출력만으로는 이 잔류량의 유입·저장 범위를 닫을 수 없습니다. 따라서 PRISM은 이를 “차단 성공 및 재고 고갈”로 승격하지 않습니다.

`LayeredTank`는 공급자 자체 질량수지는 닫히지만, 방출 packet의 가용 재고와 누적 방출량 관점에서는 큰 잔여 재고가 남습니다. 이것은 “공급자 내부 수지의 닫힘”과 “사고 방출이 탱크 재고를 모두 소진했는가”가 서로 다른 질문임을 보여줍니다.

## 코드 연결

- `src/lh2_tno/equipment_boundary.py`: `ProviderMassBalance` 계약
- `src/lh2_tno/equipment_release_adapter.py`: `provider_meta` 추출 및 수지 잔차 계산
- `src/lh2_tno/campaign.py`: 사건·case provider identity에 질량수지 보존
- `src/lh2_tno/service.py`, `src/lh2_tno/realtime_campaign.py`: 실시간 방출 경로에도 동일 정보 전달
- `src/lh2_tno/release_ledger.py`: `CLOSED`, `PARTIAL`, `UNBALANCED` 상태와 엄격한 경계 gate 연결
- `src/lh2_tno/provider_mass_balance_audit.py`: 외부 결과 일괄 감사
- `scripts/audit_external_provider_mass_balance.py`: 외부 결과 폴더를 읽는 재현용 CLI

## 현재 의미

이번 개발로 **방출량 → 설비 잔류재고 → 차단/고갈 판정**의 정보 연결은 구현됐습니다. 그러나 외부 결과의 `UNBALANCED`와 `PARTIAL` 상태가 남아 있으므로, 이 기능은 현재 진단·검증 단계입니다. 공급자 질량수지와 독립 물리검증이 확보되기 전까지 시설 전체 IR/F-N을 정식 위험도 결과로 승격하지 않습니다.
