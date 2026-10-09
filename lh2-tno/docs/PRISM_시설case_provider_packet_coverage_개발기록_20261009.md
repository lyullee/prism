# PRISM 시설 case provider packet coverage 개발기록

## 목적

시설 case 요청서와 공급자가 제출한 `prism.provider_packet_evidence.v1`를
정확히 대조하는 fail-closed 검증 단계를 추가했다. 이 단계는 packet을 위험도에
합산하지 않고, 사건을 잘못 연결하지 않았는지 확인하는 장부 역할만 한다.

## 대조 항목

각 case마다 다음 다섯 값이 모두 같아야 한다.

- `event_id`
- `component_id`
- `port_ids`
- provider source SHA-256 digest
- provider result SHA-256 digest

같은 사건이 D-3 m/s와 D-4 m/s처럼 여러 기상 조건을 가지면 공급자 packet 하나를
여러 case가 참조할 수 있다. 따라서 보고서는 고유 provider event 수와 전체 case 수를
따로 기록한다.

## 현재 결과

```powershell
$py = 'C:\Users\lyul\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py scripts/audit_facility_case_packet_coverage.py `
  --requests results/20261024/native_generic_scope_vertical_facility_evidence_request_v2.json `
  --output results/20261024/native_generic_scope_vertical_case_packet_coverage_v1.json
```

현재 34개 case에 대해 qualified evidence는 0개이며 결과는
`NO_CASE_MATCH`이다. 이는 실패한 계산을 뜻하는 것이 아니라 실제 provider packet이
아직 들어오지 않았다는 뜻이다. 결과를 `QUALIFIED_FULL_CASE_COVERAGE`로 바꾸려면
각 사건의 실제 방출 packet과 qualification evidence를 제출해야 한다.

검증기는 빈도, 센서 신호, 누출 면적, 차단확률을 추정하지 않는다. 전체 case가
정확히 연결되어도 독립 물리검증, 사고범위 완성, 시설 IR/F-N gate가 별도로 통과되어야
시설 위험도를 공개할 수 있다.
