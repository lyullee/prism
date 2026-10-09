# 시설 case provider packet branch coverage 개발기록

## 목적

하나의 initiating event가 차단 성공·실패, 양단 출구, 수직 handoff처럼 여러 방출 경로를 가질 때, provider packet의 `event_id`가 같다는 이유만으로 한 packet이 다른 case를 덮어쓰지 않게 한다.

시설 증거 요청은 event·설비·port·provider source digest·provider result digest의 정확한 조합을 요구한다. 따라서 case 감사기는 event ID별로 모든 증거 후보를 보존하고, 요청된 전체 identity와 일치하는 후보를 선택한다.

## 변경 내용

- `load_provider_packet_evidence_catalog()`은 같은 event ID라도 exact packet identity가 다르면 여러 행을 보존한다.
- event·component·port·source digest·result digest가 모두 같은 중복 행은 계속 거부한다.
- `audit_facility_case_packet_coverage()`는 event ID 하나에 대한 후보 목록을 만든 뒤 exact identity를 비교한다.
- exact match가 없으면 첫 후보의 불일치 항목을 blocking reason으로 남겨 잘못된 packet을 승격하지 않는다.
- 같은 event의 서로 다른 release branch가 각기 다른 provider result digest를 가질 수 있다.
- weather case 재사용은 같은 exact packet을 여러 annual condition에 적용할 때만 허용한다.

## 검증

같은 `event-01`에 result digest가 다른 두 provider evidence를 만들고, 두 release branch case가 각각 올바른 packet을 선택하는지 확인했다.

```powershell
python -m pytest -q tests/test_facility_case_packet_coverage.py tests/test_provider_packet_promotion.py
```

결과는 8 passed이다. 전체 portable suite는 673 passed, 1 skipped이다.

## 해석 경계

이 변경은 provider packet과 시설 case의 identity를 정확히 대조하는 구조 개선이다. provider packet을 실제 적격 근거로 만들거나, 빈도를 추정하거나, 독립 물리검증을 대신하지 않는다. 현재 union의 `qualified_provider_packet_count=0`, 시설 전체 IR/F-N 보류 상태는 그대로 유지된다.
