# 조건부 provider packet identity 분기 연결 개발기록

## 변경 이유

하나의 initiating event는 차단 성공·실패, 양단 방출처럼 여러 조건부 방출 branch를 가질 수
있다. 이전 campaign 실행기는 `event_id`만으로 provider qualification evidence를 찾았다.
그 결과 같은 event의 여러 packet을 다룰 때 마지막 행이 앞선 행을 덮어쓸 수 있고, 한 branch의
증거가 다른 branch에 잘못 적용될 위험이 있었다.

## 이번 변경

`RiskCampaign.provider_packet_evidence`는 이제 다음 다섯 값을 묶은 **exact packet identity**가
다를 때 같은 event의 여러 증거 행을 보존한다.

- `event_id`
- `component_id`
- `port_ids`
- `provider_source_digests`
- `provider_result_digests`

실행 시에는 소비한 `provider_packet_identity`와 위 다섯 값을 모두 대조한다. 따라서 첫 번째
branch의 source/result digest가 두 번째 branch와 다르면 각각 별도 evidence를 선택하고,
어느 digest도 일치하지 않으면 그 case는 `provider_packet_missing_evidence_cases`에 남는다.
정확히 같은 identity를 두 번 넣는 것은 계속 거부한다.

기존 단일 event catalog는 그대로 사용할 수 있다. 조건부 branch 증거 JSON에 같은 event의
서로 다른 packet을 함께 넣을 때는 다음 컴파일 옵션을 사용한다.

```powershell
python scripts/build_equipment_campaign.py `
  --manifest examples/equipment_manifest.json `
  --frequency-plan examples/equipment_frequency_plan.json `
  --provider-release-branch-catalog <provider-branches.json> `
  --request-defaults examples/equipment_consequence_template.json `
  --provider-evidence-catalog <branch-evidence.json> `
  --allow-distinct-event-evidence `
  --annual-conditions examples/equipment_annual_conditions.json `
  --scope-provenance reviewed-conditional-provider-branches `
  --output <campaign.json>
```

`--allow-distinct-event-evidence`는 같은 event의 exact identity가 다른 증거를 읽도록 허용하는
입력 옵션이다. 자격 상태는 여전히 `qualified_actual`, source/result SHA-256 일치, 실제
provider 원본과 별도 물리검증 조건을 모두 요구한다. 옵션을 켜도 합성 packet·센서 빈도·시설
전체 QRA를 자동으로 만들지 않는다.

## 검증

다음 회귀 검사는 조건부 branch 두 개가 서로의 evidence를 교차 사용하지 않는지, 같은 exact
identity 중복은 차단되는지 확인한다.

```powershell
python -m pytest -q tests/test_campaign.py tests/test_provider_packet_promotion.py
```

이 변경은 방출→피해 계산을 새로 실행하거나 현장 빈도를 추정하는 기능이 아니다. provider가
실제 packet과 qualification sidecar를 제공하면 해당 branch의 자격을 정확히 선택할 수 있게
한 증거 연결 보완이다. 다른 사고군·다른 설비의 누락과 독립 물리검증 gate는 계속 별도로
보류한다.
