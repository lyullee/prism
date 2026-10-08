# PRISM provider 방출 packet 요청 사양

2026-10-09. PRISM이 일반 옥외 액화수소시설의 설비 모델과 연결될 때, 설비 모델은 정상 유량이나 센서값이 아니라 `prism.resolved_release.v1` 사고 방출 packet을 제공해야 한다. 이 문서는 검사센터 전용 입력이 아니라 모든 LH2 설비 모델에 적용되는 요청 사양이다.

## 반드시 선언할 것

- `provider_export_schema`: `prism.resolved_release.v1`
- `event_kind`: `accidental_leak` 또는 `emergency_relief`
- 설비·포트·사고 ID, 상류 서비스, 물성 기준, 출구 위치·방향
- provider가 계산한 시간별 방출 장부와 `duration_s`
- 사용 가능한 재고, 누적 질량, 정적 또는 전체 출구 엔탈피 장부
- 종료 근거와 source/discharge owner
- `accidental_leak`인 경우 문헌 빈도와 exact-match할 `failure_opening_diameter_m`

`accidental_leak`는 각 사고 개구를 명시해야 한다. `emergency_relief`는 임의 누출 개구를 넣지 않고, PSV/벤트의 provider 방출 이력과 `emergency_relief_discharge` 종료 근거를 제공한다. 정상 벤트나 스크리닝 유량 JSON은 사고 packet으로 승격되지 않는다.

## 시간·보존식 규칙

`steps`는 0초에서 시작하는 좌측 보유 구간이어야 하며 시간이 엄격히 증가해야 한다. `duration_s`는 실제 provider 종료시각이어야 한다. PRISM은 마지막 유량을 요청시간까지 복사하거나 압력·직경만으로 새 유량을 계산하지 않는다. 질량과 정적/전체 엔탈피 장부가 닫히지 않으면 packet은 미계산으로 남는다.

액체·2상 출구는 `gas_mass_flow_kg_s`, `ground_liquid_mass_flow_kg_s`, `airborne_liquid_mass_flow_kg_s`가 매 구간에서 닫혀야 한다. airborne liquid은 별도 검증 adapter가 없으면 거절된다. 수직 출구는 provider가 수평 handoff 위치·방향·상태를 함께 제공해야 한다.

## PRISM에서의 결합 순서

1. provider packet의 연속성·질량·엔탈피·시계를 strict validator로 검사한다.
2. 검토된 consequence context(기상, 점화, 계산영역, 종료근거)와 결합한다.
3. 설비 ID와 실제 사고 개구를 `FrequencyPlan`의 문헌 LOC와 exact-match한다.
4. 일치한 사건만 방출→SLABx-LH2/풀→점화→피해→IR/F-N으로 보낸다.
5. 일치하지 않는 LOC와 누락된 packet은 `UNCOMPUTED`로 기록한다.

공급자는 차단 성공·실패를 별도 방출 history와 검토된 branch 확률로 제공해야 한다. 한 packet을 복사해 다른 설비나 다른 개구에 재사용하지 않는다. 사고 빈도는 packet에 넣지 않고 PRISM 문헌 빈도 계층에서 한 번만 부여한다.

## 현재 외부 자료의 판정

검사센터 provider 폴더 556개 JSON을 읽기 전용으로 감사한 결과, 정상·스크리닝 유량 파일 24개는 확인됐지만 적격 사고 packet과 비상 릴리프 packet은 각각 0건이었다. 따라서 현재 자료로는 실제 시설 위험을 계산하지 않는다. 감사기는 필요한 필드와 소유권·시계 규칙을 `release_evidence.provider_export_request`로 함께 출력한다.

재현 명령:

```powershell
python lh2-tno/scripts/audit_external_provider.py `
  --provider-root "<provider-root>" `
  --output lh2-tno/results/20261009/provider_evidence/center_provider_audit_with_release_inventory.json
```

현재 결과는 `NO_ACCIDENT_RELEASE_EXPORT`이며, 이 판정은 위험도가 0이라는 뜻이 아니라 방출 경계가 제공되지 않아 계산을 시작할 수 없다는 뜻이다.
