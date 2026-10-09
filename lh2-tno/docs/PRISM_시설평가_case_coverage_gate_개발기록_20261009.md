# PRISM 시설 평가 원장 case coverage gate 개발기록

## 무엇을 보완했나

기존에는 시설 case와 적격 provider packet의 정확한 일치 여부를 별도 감사와 IJHE 완료 감사에서만 확인했다. 이제 같은 결과를 시설 평가 원장에도 직접 넣는다. 시설 평가 결과의 `facility_case_packet_coverage`와 `facility_case_packet_coverage_complete`를 보면, 그 평가가 모든 요청 case에 실제 provider 증거를 갖추었는지 바로 확인할 수 있다.

## 승격 규칙

`build_facility_assessment.py`에 `--facility-case-packet-coverage`를 추가했다. 입력 보고서가 다음 조건을 모두 만족해야 case gate가 열린다.

병합 원장에 provider case가 하나라도 있으면 이 보고서를 생략할 수 없다. 보고서가 없을 때도 `MISSING_REPORT` gate를 원장에 남기고 시설 QRA를 닫는다.

- schema가 `prism.facility_case_provider_coverage.v1`이다.
- status가 `QUALIFIED_FULL_CASE_COVERAGE`이다.
- 요청 case 수가 양수이고, qualified provider case 수가 그 수와 같다.
- qualified provider event 수가 양수이다.
- 병합 시설 원장의 `provider_packet_case_count`와 요청 case 수가 같다.
- `frequency_is_not_assigned=true`, `physical_validation_claim=false`이다.
- `facility_ir_fn_promotion`이 독립 범위·검증 관문을 요구한다.

하나라도 빠지면 `complete=false`와 구체적인 `blocking_reasons`를 저장한다. 이 gate는 빈도를 만들거나 센서 신호를 학습하지 않으며, provider 물리를 검증했다고 표시하지도 않는다. 모든 case가 qualified여도 사고범위 완성, 독립 물리검증, IR/F-N 승격 조건은 별도로 통과해야 한다.

## 현재 재생 결과

```powershell
python scripts/build_facility_assessment.py `
  --campaign-result results/20261024/native_generic_scope_vertical_merged_facility_ledger_population_v3.json `
  --facility-case-packet-coverage results/20261024/native_generic_scope_vertical_case_packet_coverage_v1.json `
  --output results/20261024/native_generic_scope_vertical_merged_facility_assessment_population_v6.json
```

현재 원장은 34개 facility case를 요구하지만 qualified provider case는 0개다. 따라서 v6 결과는 `PARTIAL_FACILITY_SCOPE`, `facility_case_packet_coverage_complete=false`, `qualified_facility_qra_available=false`, `facility_total_risk_available=false`이다. 기존 136개 조건부 risk atom은 보존되며, case 증거가 없다는 이유로 0으로 바꾸거나 빈도를 재분배하지 않는다.

## 검증

시설 원장·완료 감사·case coverage 단위검사를 함께 실행했다. 새 gate를 포함한 대상 검사는 70개가 통과했다. GitHub Actions 실행 #378은 전체 portable suite 560개 통과를 확인했고, 이 문서의 필수 case coverage gate 보강은 다음 실행에서 재검증한다.
