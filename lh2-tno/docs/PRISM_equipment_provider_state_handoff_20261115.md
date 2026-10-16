# PRISM 설비 provider 상태 보존·방출 경계 연결 (2026-11-15)

## 목적

액화수소 설비 디지털트윈은 방출 유량만 보내는 것이 아니라, 각 방출 구간의 설비 포트 상태도 함께 보낼 수 있다. PRISM은 이 상태를 이용해 누출을 다시 계산하지 않지만, 어떤 설비 상태에서 만들어진 방출인지 추적할 수 있어야 한다.

이번 보완에서는 `equipment_release_adapter`가 provider JSON의 다음 선택 필드를 strict packet에 보존하도록 했다.

- `provider_port_state`: 설비·포트 ID, 시간, 유체, 액/기상, 압력, 온도, 밀도, 엔탈피, 질량유량, 위치·방향, 원본 digest
- `provider_source_state`: 상류·throat 압력, 온도, 밀도, 엔탈피, 엔트로피, 질량플럭스, choking 상태

가스 방출은 두 상태를 모두 보존할 수 있고, 액체/2상 방출은 `provider_port_state`를 보존한다. JSON 배열 좌표는 JSON 경계에서 PRISM의 tuple 계약으로 변환한 뒤 검증한다.

## 엄격한 검증 규칙

1. 포트 상태의 `component_id`, `port_id`, `time_s`, 유체, 상, 질량유량은 최종 `ResolvedGasRelease` 또는 `ResolvedLiquidRelease`의 해당 구간과 일치해야 한다.
2. 기체 방출 포트 상태는 `vapour` 또는 `two_phase`, 액체 방출 포트 상태는 `liquid` 또는 `two_phase`여야 한다.
3. 압력·엔탈피 상태만으로 누출 크기, 방출 지속시간, 빈도 또는 종료시각을 추정하지 않는다.
4. 상태가 없으면 방출 경계 자체는 계속 strict 검증하지만, 상태 추적 coverage는 partial/absent로 기록한다.
5. provider packet의 종료 근거·재고 장부·물리검증 자격은 별도 gate이며, 이번 보완만으로 qualified facility QRA가 되지 않는다.

## 검증 결과

- `tests/test_equipment_release_adapter.py`에 가스 구간별 port/source state 보존 및 malformed state 거부 검사를 추가했다.
- 관련 adapter·boundary·consequence 테스트: **119 passed**
- 전체 PRISM 테스트: **1319 passed, 1 warning**

이 기능은 설비 모델과 PRISM 사이의 상태 손실을 줄이는 연결 보완이다. 실제 시설 QRA 승격에는 여전히 실제 설비의 qualified release packet, 종료·재고 evidence, 사고군 독립 물리검증과 완전한 시설 범위가 필요하다.
