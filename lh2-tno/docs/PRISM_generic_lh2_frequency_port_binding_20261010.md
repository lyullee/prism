# 일반 액화수소 설비 빈도 포트 연결 검증

## 이번 개발에서 확인한 것

일반 옥외 액화수소 설비 예제의 문헌 빈도 24개를 설비별 사고 방출 포트에 명시적으로 연결했다. 이 연결은 실제 현장 설비의 P&ID를 대신하지 않는 시설 중립 진단 예제다. 실제 시설을 계산할 때는 같은 형식의 crosswalk를 현장 자산 ID와 검토된 사고 포트로 교체해야 한다.

연결된 예제 설비는 저장탱크, 액체 이송 배관, 밸브, 압력 릴리프 벤트, 이송 펌프, 앰비언트 기화기와 재액화기다. 단일 개구면적 사건은 한 포트를 사용하고, 재액화기 양단 파열 LOC는 두 포트를 사용한다.

## 재현 명령

```powershell
python scripts/build_frequency_provenance_report.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --output results/20261018/generic_lh2_frequency_provenance_current.json

python scripts/build_equipment_scenario_coverage_audit.py `
  --equipment-audit examples/generic_lh2_full_scope_equipment_model_audit.json `
  --kind-crosswalk examples/generic_lh2_full_scope_equipment_kind_crosswalk.json `
  --output results/20261105/generic_lh2_full_scope_equipment_scenario_coverage.json

python scripts/build_equipment_frequency_binding_audit.py `
  --equipment-scenario-coverage results/20261105/generic_lh2_full_scope_equipment_scenario_coverage.json `
  --frequency-provenance results/20261018/generic_lh2_frequency_provenance_current.json `
  --output results/20261105/generic_lh2_full_scope_equipment_frequency_binding.json
```

## 결과

`generic_lh2_full_scope_equipment_frequency_binding.json`에서 다음을 확인한다.

- 문헌 빈도 사건: 24개
- 검토된 포트에 결합된 사건: 24개
- 포트 미지정 사건: 0개
- 포트 crosswalk 불일치: 0개
- 빈도 결합 상태: `LITERATURE_FREQUENCY_BOUND_RELEASE_UNVERIFIED`
- 미계산 사고군: `vertical_handoff` 1개

따라서 이 결과는 “문헌 빈도가 어느 예제 방출 포트에 배분되는가”를 명확히 한다. 방출 지속시간, 차단, 재고 소진, 질량 폐합을 가진 provider packet은 아직 제출되지 않았으므로 사고 방출 계산과 SLABx-LH2 피해 계산을 자격 있는 시설 QRA로 승격하지 않는다.

## 시설 적용 시 규칙

현장 crosswalk에는 `asset_id`, `component_kind`, `identity_status`, `identity_basis`, `accident_port_ids`를 직접 검토해 넣는다. 정상 운전 포트, provider가 임의로 반환한 포트, 센서 태그만으로 사고 포트를 채우지 않는다. 빈도 계획의 `port_ids` 또는 `port_ids_by_loc`와 crosswalk의 `accident_port_ids`가 다르면 해당 사건은 `PORT_BINDING_WITHHELD`로 남기고 빈도를 0으로 바꾸지 않는다.

포트 결합이 모두 끝나도 다음 strict gate는 별도다.

1. 설비별 provider 방출 packet과 종료 근거
2. SLABx-LH2 입력 및 독립 holdout 물리 검증
3. 선언한 전체 액화수소 설비·사고군 범위
4. 시설 IR/F-N과 qualified QRA 자격

현재 generic 예제의 `facility_qra_allowed`는 의도적으로 `false`다. 이 값은 실패가 아니라, 빈도 포트 연결 완료와 시설 전체 QRA 승격을 분리해 표시하는 계약이다.
