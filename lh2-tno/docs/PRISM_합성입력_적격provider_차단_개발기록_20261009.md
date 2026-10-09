# PRISM 합성 입력의 적격 provider 승격 차단

## 목적

PRISM은 합성 시나리오를 이용해 연결 구조와 수치 계약을 시험할 수 있다. 그러나 합성 시나리오의 방출 결과는 실제 시설의 사고 증거가 아니다. 따라서 `input_origin=synthetic`인 요청은 provider가 `qualified_actual` 자격 기록을 함께 반환하더라도 적격 provider packet으로 승격할 수 없어야 한다.

## 보완 내용

`src/lh2_tno/equipment_accident_export.py`의 세 사고 방출 요청에 공통 검사를 추가했다.

- 일반 사고 누출(`AccidentReleaseExportRequest`)
- 비상 릴리프 방출(`EmergencyReliefExportRequest`)
- 재고 기반 방출(`InventoryReleaseExportRequest`)

세 요청 모두 다음 조합을 요청 생성 단계에서 즉시 거부한다.

```text
input_origin = synthetic
evidence_status = qualified_actual
```

이 검사는 provider를 호출하기 전에 실행된다. 그러므로 provider 응답의 자격 sidecar만으로 합성 요청을 적격 실제 packet처럼 표시하는 경로가 없다. 합성 요청은 `synthetic_diagnostic` 또는 `screening_only`로 실행해야 한다.

## 의미와 한계

이 변경은 실제 provider 자료를 새로 만들지 않는다. 현재 PRISM의 외부 `lh2dt` 연결 결과는 여전히 합성·operator-limited 진단으로 남고, 시설 IR/F-N과 적격 provider 수는 증가하지 않는다. 변경의 목적은 자료가 부족한 상태에서 잘못된 승격을 사전에 막고, 실제 provider 자료가 들어왔을 때만 다음 단계의 digest·event·component·port 일치 검사가 수행되도록 하는 것이다.

## 검증

```text
tests/test_equipment_accident_export.py
tests/test_provider_packet_promotion.py
22 passed
```

회귀 테스트는 자격 실제 요청이 비합성 입력에서만 실행되는지, 합성 자격 요청이 provider 호출 전에 거부되는지를 확인한다.
