# 압축성 방출 handoff부터 피해영향까지 재현하는 실행 경로

이 문서는 고압 기화기 또는 기체 방출 포트에서 **provider가 계산한 소스 상태**를 PRISM의 피해영향 계산까지 전달하는 진단 경로를 설명한다. 대상은 선언된 옥외 액화수소시설 범위이며, 이 경로는 사고빈도를 만들거나 provider를 자격화하지 않는다.

## 연결되는 단계

1. 설비 provider가 `prism.resolved_release.v1` packet을 만든다. packet에는 시간별 질량유량, 출구 상태, 방출 지속시간, 재고, 설비·포트 ID가 들어간다.
2. provider가 각 시간 구간의 `provider_source_state`를 별도 결과에 넣는다. PRISM은 대기 출구 속도만으로 고압 원천 상태를 역산하지 않는다.
3. `build_compressible_plane_handoff.py`가 provider source/throat 상태를 사용해 압축성 평면 handoff를 만든다. 질량·운동량·에너지 잔차와 원본 digest를 기록한다.
4. `run_compressible_plane_chain.py`가 handoff를 정확한 packet에 다시 붙이고, 시설 manifest의 설비·포트·좌표·물성 기준을 확인한다.
5. 동일한 provider 방출 이력과 지속시간을 `ConsequenceRequest`에 넣어, 압축성 근접장 → SLABx-LH2 확산 → 점화 분기 → 복사/폭압 → 인체 피해 → 조건부 위험 계산을 실행한다.

시설 manifest의 좌표가 provider packet과 다르면 실행을 중단한다. 좌표를 코드가 임의로 이동시키거나, 누출구를 정상 운전 모델에서 추정하지 않는다.

## 재현 명령

다음 명령은 저장된 진단 packet과 handoff를 사용한다. `--refresh-pins`는 현재 작업공간의 외부 모델 digest를 명시적으로 다시 기록하는 선택이며, 실행 결과에 변경된 pin을 남긴다.

```powershell
python scripts/run_compressible_plane_chain.py `
  --packet results/20261016/vaporizer_g1_attached_smoke/resolved_release.json `
  --handoff results/20261016/vaporizer_g1_synthetic_handoff.json `
  --facility examples/compressible_plane_chain_facility.json `
  --context examples/compressible_plane_chain_context.json `
  --backend-config results/20261008/full_chain/backend_config.json `
  --output-dir results/diagnostic/compressible_plane_chain `
  --refresh-pins
```

실제 provider export 파일명을 사용하는 경우에도 입력 네 개(packet, handoff, facility, context)만 같은 계약으로 준비하면 된다. provider packet을 만들고 handoff를 생성하는 기존 명령은 다음과 같다.

```powershell
python scripts/build_compressible_plane_handoff.py `
  --packet <resolved_release.json> `
  --provider-response <provider_response.json> `
  --lh2dt-root <lh2dt_models> `
  --output-handoff <compressible_handoff.json> `
  --output-audit <compressible_handoff_audit.json>
```

## 결과 해석

실행 성공 시 `verification.json`에는 다음이 기록된다. 저장된 진단용 요약은 [`examples/compressible_plane_chain_smoke_result.json`](../examples/compressible_plane_chain_smoke_result.json)에서 확인할 수 있다.

- `chain_status=END_TO_END_DIAGNOSTIC_EXECUTED`
- `provider_handoff_consumed=true`
- provider 방출 지속시간과 질량 잔차
- handoff가 downstream에 전달된 구간 수와 최대 상대 질량잔차
- 계산된 진단용 Mach 수
- 실제 source operator와 backend pin 갱신 내역

현재 결과의 상태는 `SYNTHETIC_COMPRESSIBLE_PLANE_CHAIN_EXECUTED`이다. 이는 방출 이력과 압축성 handoff가 같은 계산 경로를 통과했다는 뜻이다. 다음 항목은 별도 증거가 없으므로 자동으로 승격하지 않는다.

- 현장 사고빈도 또는 빈도 불확실성
- provider의 자격화 및 현장 보정
- 압축성 근접장 모델의 독립 실험 검증
- 시설 전체 IR/F-N
- 1 Hz 신규 물리 계산 성능

따라서 이 경로의 결과는 IJHE 원고에서 “provider-resolved source history를 피해영향 체인으로 전달하는 diagnostic integration”을 보여주는 데 사용할 수 있지만, qualified facility QRA나 독립 물리검증 결과로 인용하면 안 된다.

## 시설 campaign까지 연결한 확인

단일 사건 chain을 시설 campaign에 넣을 때는 `scripts/run_compressible_plane_facility_campaign.py`를 사용한다. 이 명령은 한 event만 handoff packet으로 재결합하고, campaign이 소유한 문헌/조건부 빈도를 그대로 둔 채 24개 사건을 시설 위험엔진에 전달한다.

```powershell
python scripts/run_compressible_plane_facility_campaign.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign <compiled_campaign.json> `
  --handoff-packet <resolved_release_with_handoff.json> `
  --event-id generic-lh2-full-scope-frequency-example/ambient-vaporizer/G1 `
  --backend-config results/20261008/full_chain/backend_config.json `
  --output results/diagnostic/compressible_facility_result.json `
  --provenance-output results/diagnostic/compressible_facility_provenance.json `
  --ledger-output results/diagnostic/compressible_facility_ledger.json `
  --refresh-pins
```

실행 스냅샷은 [`examples/compressible_plane_facility_campaign_smoke_result.json`](../examples/compressible_plane_facility_campaign_smoke_result.json)이다. 24개 event와 24개 case가 원장에 기록되고, 24개 chain이 실행되며, G1 handoff의 원본·재결합 provider digest가 서로 다른 값으로 보존된다. 결과는 `PARTIAL_DECLARED_SCOPE`이고 20개 case는 `EXECUTED_OPERATOR_LIMITED`, 4개는 `EXECUTED`로 기록되었다. `total_facility_annual_ir_low_high`와 F/N은 `null`로 남으며, 이는 provider qualification·독립 물리검증·엄격한 시설범위 gate가 열려 있기 때문이다. `uncomputed_case_count=23`은 해당 case의 진단 chain 실행 여부와 별개로 qualified evidence가 없어 승격할 수 없는 case 수를 뜻한다.

같은 campaign의 위험 원자에 문헌 빈도 불확실성을 재현 가능하게 적용하려면 campaign 범위에 맞춘 시나리오 catalog를 함께 전달한다.

```powershell
python scripts/run_compressible_plane_facility_campaign.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --campaign <compiled_campaign.json> `
  --handoff-packet <resolved_release_with_handoff.json> `
  --event-id generic-lh2-full-scope-frequency-example/ambient-vaporizer/G1 `
  --backend-config results/20261008/full_chain/backend_config.json `
  --output results/diagnostic/compressible_facility_result.json `
  --provenance-output results/diagnostic/compressible_facility_provenance.json `
  --ledger-output results/diagnostic/compressible_facility_ledger.json `
  --frequency-scenarios examples/compressible_plane_facility_frequency_scenarios.json `
  --frequency-uncertainty-output results/diagnostic/compressible_facility_frequency_uncertainty.json `
  --refresh-pins
```

이 catalog는 현재 24개 사건 campaign에 정확히 맞춘 5개 시나리오(자산별 shared central/low/high와 event별 independent low/high)를 사용한다. 계산은 저장된 risk atom의 빈도 가중치만 바꾸고 방출·확산 물리를 다시 실행하지 않는다. 따라서 `fresh_physics_executed=false`, `facility_credible_interval=false`, `frequency_inference_performed=false`가 정상이며, 이는 시설 전체의 통계적 신뢰구간이나 센서 기반 빈도 추정을 뜻하지 않는다. qualified provider·독립 물리검증·엄격한 시설범위 gate가 닫히기 전까지 결과는 조건부 진단으로만 사용한다.

실제 24개 campaign에 이 옵션까지 붙인 실행 요약은 [`examples/compressible_plane_facility_frequency_execution.json`](../examples/compressible_plane_facility_frequency_execution.json)이다. 24/24 chain이 실행되었고, 5개 빈도 시나리오가 저장된 risk atom에 적용되었으며, 물리 재실행 없이 correlation comparison이 기록되었다. 실행시간은 새 물리 계산 24건, 중앙값 약 7.07초/case, p95 약 13.91초/case, 전체 약 176.9초였고, 이는 단일 campaign 관측값이지 1 Hz 서비스 보장이 아니다.
