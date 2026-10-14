# HAZOP 사고범위·provider worklist 연결

## 목적

다중 설비 HAZOP 실행 결과는 대표 행을 실제 계산했는지를 보여주고, provider worklist는 문헌 빈도 계획에 선언된 모든 정확한 사건 ID와 필요한 방출 packet을 보여준다. 두 결과를 한 장부로 합치지 않으면 “7개 설비가 계산되었다”는 사실이 “전체 사고군과 24개 빈도 사건이 계산되었다”는 말로 잘못 읽힐 수 있다.

`src/lh2_tno/hazop_scope_worklist.py`의 `build_hazop_scope_worklist()`는 다음 두 층을 분리해서 기록한다.

1. **가족·설비 층**: `DISPATCHED_DIAGNOSTIC`, `APPLICABLE_NOT_DISPATCHED`, `NO_FREQUENCY_EVENT_BINDING`을 설비별로 기록한다.
2. **빈도 사건 층**: provider worklist의 정확한 event ID, 사고 크기, 연간 빈도, 방출 모드, 필요한 provider schema와 종료근거를 그대로 보존한다. provider packet이 없으면 `UNCOMPUTED_PROVIDER_PACKET` 또는 `UNCOMPUTED_NO_ACCIDENT_PORT`로 남는다.

진단 행이 계산되었다는 이유만으로 provider packet을 만들거나 빈도를 재배분하지 않는다. `frequency_inference_performed=false`, `packet_substitution_performed=false`가 항상 함께 기록된다.

## 재현 명령

기존 다중 설비 진단과 전체 빈도 계획을 연결한다.

```powershell
python scripts/build_hazop_scope_worklist.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --diagnostic-result examples/hazop_multiequipment_provider_isolation_execution_20261014.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --model-binding examples/generic_lh2_model_binding.json `
  --output examples/hazop_scope_worklist_execution_20261014.json
```

`--strict`를 붙이면 남은 scope 또는 provider gap이 있을 때 종료 코드 2를 반환한다. 기본 실행은 gap을 장부로 저장하고 정상 종료하므로 후속 검토·증거 요청 단계에서 사용할 수 있다.

IJHE 완료 감사에 연결할 때는 `scripts/build_ijhe_completion_audit.py`에
`--hazop-scope-worklist examples/hazop_scope_worklist_execution_20261014.json`을
추가한다. 감사의 `diagnostic_hazop_scope_worklist` 검사는 장부의 구조와
fail-closed 정책이 맞는지를 확인하며, `SCOPE_GAPS_EXPLICIT` 자체를 완료로
승격하지 않는다.

## 현재 진단 snapshot의 의미

현재 snapshot은 12개 사고군, 8개 manifest component, 24개 문헌 frequency event를 기준으로 다음을 기록한다.

| 항목 | 현재 값 | 해석 |
| --- | ---: | --- |
| 가족·설비 조합 | 31 | 선언된 옥외 사고군과 적용 설비 조합 |
| HAZOP diagnostic dispatch | 7 | 7개 설비·사고군 조합이 대표 runtime까지 도달 |
| 적용 가능하지만 미 dispatch | 9 | provider/HAZOP 실행 요청이 아직 필요 |
| 정확한 빈도 event가 없는 조합 | 15 | 현재 frequency plan에 해당 방출 사건이 선언되지 않음 |
| provider frequency event | 24 | 빈도 계획에 있는 정확한 사건 수 |
| provider packet 미계산 | 24 | 방출·지속시간·차단·재고 장부 packet이 필요 |

따라서 이 결과는 누락 사고를 드러내는 작업목록이지, 전체 시설 QRA 완료 선언이 아니다. 예를 들어 `pipe_hole/liquid-transfer-line-01`은 대표 HAZOP 진단이 있었지만 5개 면적별 provider event는 모두 별도로 packet을 요구한다. `vertical_handoff`는 적용 가능한 설비가 있으나 현재 frequency event가 없어 `NO_FREQUENCY_EVENT_BINDING`으로 남는다. 이 경우 다른 사고의 빈도나 방출 결과를 대신 사용하지 않는다.

## 설비 모델과의 결합 규칙

각 provider event row에는 설비 ID, profile, location bin, release mode, annual frequency, scenario families, required termination basis, provider schema와 기존 model-binding 차단사유를 함께 담는다. 정상상태 model binding 또는 합성 diagnostic adapter가 있어도 `provider_packet_created=false`이며, provider가 제공해야 할 실제 사고 방출 이력은 별도 요청으로 남는다.

이 구조는 다음 작업을 바로 생성한다.

- `APPLICABLE_NOT_DISPATCHED`: 해당 설비·사고군 HAZOP 행을 추가 실행
- `NO_FREQUENCY_EVENT_BINDING`: 문헌 빈도 event와 물리적 범위를 검토해 frequency plan을 명시적으로 보완
- `UNCOMPUTED_PROVIDER_PACKET`: 설비 모델에서 방출량·지속시간·차단·재고 소진·출구 상태를 provider packet으로 내보내기
- `DISPATCHED_DIAGNOSTIC` + 미계산 provider event: diagnostic 결과와 qualified provider evidence를 별도로 대조

이 장부가 닫힌 뒤에야 해당 사고군과 사건을 시설 기상·점화·인구·IR/F-N 원장에 포함할 수 있다. 현재 snapshot의 조건부 위험 결과와 `facility_qra_promotion=false` 정책은 그대로 유지한다.

