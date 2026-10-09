# PRISM 조건부 case 회계 보정 기록

## 왜 보정했는가

시설 원장은 하나의 initiating event가 여러 기상 조건이나 방출 branch를 가질 수 있다. 예를 들어 같은 배관 개구가 `D-3ms-west`와 `D-4ms-west`에서 각각 계산되거나, 한 사건이 isolation-success와 isolation-failure로 갈라질 수 있다.

기존 시설 coverage 요약은 `event_id`만 사용했다. 그러면 서로 다른 계산을 하나의 사건으로 합쳐서, 실제로는 80개 case가 있는데 41개 사건 상태만 보이는 문제가 생겼다. 위험 원자 합계 자체는 중복 계산되지 않았지만, “몇 개 case가 숫자로 계산됐는가”라는 설명이 부정확했다.

## 바뀐 계산

이제 case 식별자는 다음 네 가지를 함께 사용한다.

- event ID
- 연간 조건 또는 기상 ID
- release branch ID
- ignition branch ID

이 정보가 없는 오래된 JSON은 event ID만 사용해 하위 호환한다. `cases`와 `uncomputed_cases`에 같은 case가 함께 있으면, 계산된 case 상태를 우선하고 보류 복사본은 엄격한 증거 회계로 보존한다.

시설 coverage에는 다음 필드가 추가됐다.

- `conditional_case_count`: 고유 case 수
- `conditional_executed_case_count`: `EXECUTED*` 숫자 결과가 있는 고유 case 수
- `conditional_uncomputed_case_count`: 숫자 결과 자체가 없는 고유 case 수
- `strict_uncomputed_case_count`: 운영자 제한·domain incomplete 설명을 위해 보존한 엄격 보류 복사본 수

`uncomputed_case_count`는 기존 호환성을 위해 그대로 유지한다. 따라서 이 값은 “엄격한 시설 승격에 사용할 수 없는 행 수”이고, 숫자 chain이 전혀 실행되지 않은 case 수는 `conditional_uncomputed_case_count`로 읽어야 한다.

## 최신 시설 결과

2026-10-22 보정 후 공식 시설 원장은 41개 event, 80개 case, 312개 risk atom을 보존한다. 고유 case 기준으로 78개는 방출부터 피해까지 숫자 결과가 있고, 2개는 `UNCOMPUTED`로 남아 있다. 엄격한 보류 복사본은 37개이며, 그 안에는 `EXECUTED_OPERATOR_LIMITED` 34개와 domain/미계산 설명이 포함된다.

이 보정은 실제 provider 자격이나 물리 검증을 추가하지 않는다. 따라서 `facility_total_risk_available=false`와 9개 사고 family의 strict `PARTIAL` 상태는 그대로다. 조건부 진단 IR/F-N은 계산된 risk atom의 연결을 보여주는 용도로만 사용한다.

검증:

```powershell
..\output\prism-export-v060-1febujhk\venv\Scripts\python.exe -m pytest -q
```

현재 portable suite 결과는 497개 통과다.

증거 요청서도 이 회계를 사용한다. 가족별 요청 행은 조건부 실행 수, 조건부 미계산 수, 엄격 보류 수와 엄격 차단 이유를 함께 보여주므로, 다음 실제 provider 자료의 우선순위를 바로 정할 수 있다.
