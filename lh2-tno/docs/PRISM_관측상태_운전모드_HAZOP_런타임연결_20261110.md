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

이 원장을 최신 native 시설 원장과 문헌 빈도 민감도 장부에 함께 넣은 완료 감사는
`results/20261110/ijhe_completion_audit_with_observed_hazop_runtime_frequency.json`이다.
27개 검사 중 운전 모드 런타임 선택, 문헌 빈도 시나리오 5개와 재합산 일치는 PASS이며,
qualified provider packet·방출경계·독립 물리검증·완전 사고범위·시설 IR/F-N은 여전히
차단된다.

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

## HAZOP 시나리오와 문헌 provider event의 명시적 연결

HAZOP가 고른 시나리오를 정량 계산으로 넘길 때는 시나리오 이름만으로 설비나 누출구를 추측하지 않는다. 다음 매핑 파일에서 각 `scenario_id`를 문헌 기반 `provider_event_id`, provider `component_id`, `accident_port_id`에 하나씩 명시한다.

`examples/inspection_center_hazop_provider_event_bindings.json`은 진단용 세 연결을 담고 있다.

| HAZOP 시나리오 | 문헌 event | 방출 port | 현재 packet 상태 |
| --- | --- | --- | --- |
| 인수 고압 → `vessel_hole` | storage-shell `AREA_0.01%` | `tank-accident-out` | `UNCOMPUTED_PROVIDER_PACKET` |
| 대기 벤트 압력 → `vent_hole` | pressure-relief-vent `G1` | `vent-accident-out` | `UNCOMPUTED_PROVIDER_PACKET` |
| 공급 기화기 고압 → `vaporizer_hole` | ambient-vaporizer `G3` | `vaporizer-accident-out` | `UNCOMPUTED_PROVIDER_PACKET` |

아래 명령은 event family, release mode, port, 양의 문헌 빈도 필드가 서로 맞는지 검사한다.

```powershell
python scripts/audit_observed_hazop_provider_binding.py `
  --observed-hazop-runtime-audit results/20261110/inspection_center_observed_hazop_runtime_audit.json `
  --provider-worklist results/20261110/native_full_scope_frequency_assessment_latest2/provider_worklist.json `
  --binding-map examples/inspection_center_hazop_provider_event_bindings.json `
  --output results/20261110/inspection_center_observed_hazop_provider_event_binding.json
```

현재 결과는 3/3 시나리오가 명시적 event identity에 연결된 `OBSERVED_HAZOP_PROVIDER_EVENT_BINDINGS_DIAGNOSTIC`이다. 이는 빈도 값을 센서에 할당하거나 누출 packet을 만드는 단계가 아니다. provider packet·방출 종료·차단·재고 폐합·SLABx-LH2 검증이 없는 동안에는 시설 IR/F-N에 자동 포함되지 않는다. 이를 최신 IJHE 감사에 넣으면 `diagnostic_observed_hazop_provider_event_binding=PASS`가 추가되지만 전체 상태는 `INCOMPLETE_EVIDENCE`로 남는다.

## 실제 packet 계약을 적용한 결과

identity 매핑만으로는 packet을 실행하지 않는다. `scripts/run_observed_hazop_provider_consequence_chain.py`는 실제 native packet의 event·component·port·event kind·종료 basis·지속시간·질량 장부를 다시 확인한 뒤, 사고군 계약을 만족하는 행만 기존 HAZOP runtime gate와 SLABx-LH2 consequence service에 넘긴다.

2026-11-10 실행 결과는 다음과 같다.

| 시나리오 | 결과 | 이유 |
| --- | --- | --- |
| 인수 탱크 `vessel_hole` | 보류 | packet 종료 basis가 `inventory_depletion`이라 vessel-hole 계약과 불일치 |
| 저장 벤트 `vent_hole` | 실행 | `emergency_relief_discharge`와 event/port가 일치하고 SLABx-LH2까지 실행 |
| 공급 기화기 `vaporizer_hole` | 보류 | packet 종료 basis가 `synthetic_diagnostic_horizon`이라 허용된 사고군 종료 basis가 아님 |

권위 결과는 `results/20261110/inspection_center_observed_hazop_provider_consequence_chain.json`이다. 3개 중 1개가 실행되고 2개가 보류된 `OBSERVED_HAZOP_PROVIDER_CHAIN_EXECUTED_PARTIAL` 상태이며, 실행된 진단 risk atom의 문헌 빈도는 별도로 적용했지만 provider 자격·독립 물리검증·시설 전체 IR/F-N은 열지 않았다. 이 결과는 지원되지 않는 사고를 다른 사고군으로 바꾸지 않는다는 점과 신규 계산 처리시간(실행 branch 약 3.66초, 전체 약 3.69초)을 함께 기록한다.

재현 명령은 다음과 같다.

```powershell
python scripts/run_observed_hazop_provider_consequence_chain.py `
  --observed-hazop-runtime-audit results/20261110/inspection_center_observed_hazop_runtime_audit.json `
  --observed-hazop-provider-binding results/20261110/inspection_center_observed_hazop_provider_event_binding.json `
  --runtime-frames results/20261110/inspection_center_observed_state_runtime_frames_with_modes.json `
  --provider-worklist results/20261110/native_full_scope_frequency_assessment_latest2/provider_worklist.json `
  --packet-evidence results/20261110/native_generic_scope_packets_latest2/native_scope_packet_evidence.json `
  --packet-root results/20261110/native_generic_scope_packets_latest2 `
  --manifest examples/generic_lh2_near_receptor_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --provider-defaults-liquid examples/provider_request_defaults_liquid_provider_duration.json `
  --provider-defaults-relief examples/provider_emergency_relief_defaults.json `
  --template examples/equipment_consequence_template.json `
  --backend-config results/20261008/full_chain/backend_config.json `
  --output results/20261110/inspection_center_observed_hazop_provider_consequence_chain.json
```

완료 감사에는 `--observed-hazop-provider-consequence-chain`을 추가한다. 이 검사는 부분 실행과 보류 사유가 보존되었는지만 확인하며, 부분 실행을 시설 위험평가 완료로 해석하지 않는다.

저장탱크에 대해서는 외부 `LayeredTankNetworkSimulator`가 명령 밸브를 닫고 zero-flow를 확인한 성공 branch도 별도로 연결했다. 성공 branch는 `reviewed_isolation_success`, 0.15 s, branch probability 0.99로 기록되고 저장탱크 HAZOP→provider→SLABx-LH2가 실행된다. 실패 branch는 0.01의 명시적 probability와 `synthetic_diagnostic_horizon`을 보존하지만 vessel-hole chain에는 포함하지 않는다. 성공 branch와 저장 벤트를 함께 실행한 결과는 `results/20261110/inspection_center_observed_hazop_provider_consequence_chain_with_storage_isolation_success.json`이며, 3개 시나리오 중 2개 실행·1개 보류 상태이다. branch 근거와 질량·차단 요약은 `results/20261110/observed_hazop_storage_isolation_branch_evidence.json`에서 확인한다. 이는 isolation 계약을 실행 가능한 진단 경로로 만든 것이며 현장 차단 신뢰도나 시설 전체 QRA를 의미하지 않는다.

## 다음 승격 조건

이 진단 결과를 실제 시설 위험평가 입력으로 승격하려면 설비별 검토된 P&ID/HAZOP asset identity, 단위·교정 확인, provider가 계산한 사고 방출 이력과 종료·차단·재고 폐합, 해당 사고의 문헌 빈도, SLABx-LH2 독립 검증이 필요하다. 하나라도 없으면 해당 사고는 조건부 결과로만 남기고 시설 전체 IR/F-N에 포함하지 않는다.
