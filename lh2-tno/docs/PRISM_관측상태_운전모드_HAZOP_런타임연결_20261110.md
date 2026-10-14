# PRISM 관측 상태·운전 모드·HAZOP 런타임 연결

## 이번 단계의 목적

검사지원센터 데이터에서 읽은 압력·온도·차압을 정상 공정상태 프레임으로 만들고, 운전 모드를 별도 입력으로 함께 전달하여 HAZOP 표가 운전 모드에 맞는 이탈과 위험 시나리오를 선택하는 경계를 고정했다.

운전 모드는 센서값으로 추정하지 않는다. 인수·공급·대기 같은 모드는 운전 시퀀스 또는 SCADA 상위 입력이 `source_id → operating_mode` 맵으로 제공해야 한다. 이 단계는 누출 방출량, 지속시간, 차단, 재고 소진, 빈도를 생성하지 않는다.

## 실행 흐름

```text
관측 신호
  → SI 정상 상태 프레임
  + 명시적 운전 모드 입력
  → 운전 모드별 HAZOP 표 비교
  → 이탈·사고 family 선택
  → 설비 provider 방출 packet 요청
  → SLABx-LH2/TNO 피해계산
  → 문헌 빈도 결합 후 시설 IR/F-N
```

마지막 네 단계는 이번 진단 원장에 자동으로 만들어지지 않는다. HAZOP 선택 결과의 `provider_release_required=true`와 `frequency_assignment=not_performed`로 다음 경계를 명시한다.

## 검사지원센터 진단 입력

`examples/inspection_center_runtime_operating_modes.json`은 세 관측 source에 모드를 명시한다.

| source | mode |
| --- | --- |
| `inspection-center-intake-10-runs` | `receiving` |
| `inspection-center-storage-vent-10-runs` | `standby` |
| `inspection-center-supply-10-runs` | `supply` |

`examples/inspection_center_hazop_runtime_tables.json`에는 세 설비의 진단용 HAZOP 행이 있다. 임계값은 현장 설계 한계로 승격하지 않았으며, 각 행의 provenance에 검토 필요 상태를 남겼다.

실행 결과는 다음과 같다.

- runtime frame 3개가 모두 `EXPLICIT_MODE_INPUT_BOUND`
- 인수·대기·공급 모드가 각각 1개씩 보존
- HAZOP 시나리오 3개 선택: `vessel_hole`, `vent_hole`, `vaporizer_hole`
- 방출 packet 0개, 빈도 결합 0건, 피해계산 0건
- 결과 상태: `OBSERVED_HAZOP_MODE_SCENARIOS_SELECTED`

권위 결과는 `results/20261110/inspection_center_observed_state_runtime_frames_with_modes.json`와 `results/20261110/inspection_center_observed_hazop_runtime_audit.json`이다.

## 재현 명령

```powershell
python scripts/build_observed_state_runtime_frames.py `
  --manifest examples/inspection_center_observed_state_manifest.json `
  --source-root "C:\Users\lyul\Desktop\DocuData\액화수소검사지원센터 데이터" `
  --operating-mode-map examples/inspection_center_runtime_operating_modes.json `
  --output results/20261110/inspection_center_observed_state_runtime_frames_with_modes.json

python scripts/audit_observed_hazop_runtime.py `
  --runtime-frames results/20261110/inspection_center_observed_state_runtime_frames_with_modes.json `
  --hazop-table-set examples/inspection_center_hazop_runtime_tables.json `
  --now-s 10081 `
  --output results/20261110/inspection_center_observed_hazop_runtime_audit.json
```

IJHE 완료 감사에는 `--observed-hazop-runtime-audit` 옵션으로 이 원장을 넣을 수 있다. 감사는 정성적 모드·시나리오 연결만 PASS로 기록하고, 시설 QRA·빈도·물리검증 차단 항목을 해제하지 않는다.

## 다음 승격 조건

이 진단 결과를 실제 시설 위험평가 입력으로 승격하려면 설비별 검토된 P&ID/HAZOP asset identity, 단위·교정 확인, provider가 계산한 사고 방출 이력과 종료·차단·재고 폐합, 해당 사고의 문헌 빈도, SLABx-LH2 독립 검증이 필요하다. 하나라도 없으면 해당 사고는 조건부 결과로만 남기고 시설 전체 IR/F-N에 포함하지 않는다.
