# PRISM 설비별 빈도와 사고 방출 포트 연결

## 왜 필요한가

문헌 빈도는 탱크·배관·밸브 같은 **설비 항목**에 붙어 있지만, 실제 피해 계산은 특정한 **방출 포트**에서 시작한다. 한 설비에 출구가 여러 개이면 설비 이름만 맞춰서는 빈도가 어느 출구의 사고인지 알 수 없다. PRISM은 이 연결을 명시적으로 기록하고, 확인하지 못한 연결을 자동으로 만들지 않는다.

## 입력 방법

`FrequencyAsset`에 `port_ids`를 넣는다.

```json
{
  "id": "tank-shell",
  "model_component_id": "storage-tank-01",
  "profile": "LH2_VESSEL",
  "physical_scope_ids": ["tank-shell-01"],
  "port_ids": ["tank-accident-out"],
  "classification_basis": "reviewed equipment and accident-port allocation"
}
```

한 자산의 LOC가 한쪽 구멍과 양단 파열을 함께 만들면 `port_ids_by_loc`로 LOC별 포트를 지정한다. 예를 들어 `G1` 양단 파열에는 두 포트를, `G2` 구멍에는 한 포트를 넣는다.

```json
{
  "port_ids_by_loc": {
    "G1": ["pipe-accident-a", "pipe-accident-b"],
    "G2": ["pipe-accident-a"]
  }
}
```

이 값은 `physical_scope_ids`와 다른 정보다. `physical_scope_ids`는 문헌 빈도를 적용한 물리적 설비·배관 구간을 세고, `port_ids` 또는 `port_ids_by_loc`는 그 빈도가 어느 사고 출구로 배분됐는지 기록한다.

PRISM은 이벤트를 만들 때 다음을 확인한다.

1. 포트가 시설에 실제로 존재하는가.
2. 포트가 빈도 자산의 동일한 `model_component_id`에 속하는가.
3. 포트가 입구가 아닌 외부 방출 방향인가.
4. 단일 방출은 포트 하나, 양단 파열은 포트 두 개를 지정했는가.

## 계산 중 확인

생성된 `FrequencyEvent`에도 같은 `port_ids`가 보존된다. `bind_event()`가 provider 방출 패킷을 빈도와 결합할 때는 다음 조건을 모두 확인한다.

- component ID가 일치한다.
- provider가 반환한 방출 포트 목록이 이벤트의 `port_ids`와 순서까지 일치한다.
- 양단 파열은 두 endpoint 포트가 모두 일치한다.

포트가 다르면 빈도를 억지로 붙이지 않고 오류를 낸다. 이 오류는 해당 사고 케이스가 **미계산**이라는 뜻이며, 빈도를 0으로 바꾸거나 다른 포트로 옮기지 않는다.

## 포트가 아직 없는 기존 계획

기존 문헌 계획은 하위 호환을 위해 `port_ids` 없이도 읽을 수 있다. 이런 이벤트는 component-level 빈도로만 표시되며, provider가 반환한 특정 방출 포트의 근거가 자동으로 생기지 않는다. 따라서 보고서의 `frequency_port_binding`에 `port_unbound_event_count`로 남는다.

이 상태는 계산을 중단시키지 않지만, 설비에 출구가 여러 개일 때는 설계 검토자가 사고 포트 배분을 추가해야 한다. 포트가 없다는 이유로 현장 빈도를 학습하거나 압력·센서값으로 빈도를 추정하지 않는다.

## 보고서 필드

- `frequency_port_binding.port_scoped_event_count`: reviewed accident port가 지정된 이벤트 수
- `frequency_port_binding.port_unbound_event_count`: component-level로만 남은 이벤트 수
- `frequency_port_binding.all_events_port_scoped`: 모든 생성 이벤트에 포트가 있는지
- `coverage.by_component[*].reviewed_accident_port_ids`: 설비별 검토된 사고 포트 목록
- `coverage.by_component[*].generated_port_unbound_event_count`: 설비별 포트 미지정 이벤트 수

`strict_facility_qra_gate`는 현재 `false`로 유지한다. 즉, 이 기능은 잘못된 포트 결합을 막고 심사 가능한 누락을 드러내는 연결부이며, 독립 물리 검증·provider 자격 증명·시설 전체 범위 충족을 대신하지 않는다.

## 빈도에 관한 경계

빈도는 계속 검토된 Purple Book/LH2 문헌 카탈로그에서만 온다. 디지털 트윈의 정상 상태, 알람, 압력, 온도 또는 누출 감지 신호는 빈도를 만들지 않는다. 신호는 상태 스냅샷과 provider 방출 계산의 입력으로만 사용되며, 문헌 빈도와 포트 배분은 별도로 감사한다.
