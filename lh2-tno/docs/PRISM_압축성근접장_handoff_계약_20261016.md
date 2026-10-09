# PRISM 압축성·저마하 근접장 handoff 계약

작성일: 2026-10-16  
대상: 고속 GH2/LH2 기체 출구를 일반 실외 LH2 시설 위험계산에 연결하는 경계

## 문제

외부 `DynamicVaporizer`의 대기 밸브 packet은 공급자 시간 이력·질량·정적 엔탈피·출구 단면을 보존한다. 그러나 출구 속도가 커서 Mach 0.3을 넘으면, PRISM의 저마하 확산 전이 모델에 바로 넣을 수 없다. 출구 압력과 속도만으로 PRISM이 충격파·팽창·혼입을 다시 계산하면 공급자 모델과 다른 방출을 만들어 버린다.

따라서 고속 사건은 다음 중 하나만 허용한다.

1. 공급자가 계산한 압축성/underexpanded 근접장 handoff를 제공한다.
2. 공급자 packet이 직접 저마하 조건을 만족한다.

고속 packet에 두 정보가 모두 없으면 사건을 `FAILED` 또는 `UNCOMPUTED`로 남긴다. 기존 저마하 진단 packet을 선택된 고속 사건에 복사하지 않는다.

## 새 계약

`prism.compressible_plane_handoff.v1` JSON은 다음 정보를 갖는다.

- `component_id`, `port_id`, `event_id`: 원래 사고 packet과 정확히 같은 식별자
- `upstream_provider_source_digest`, `upstream_provider_result_digest`: 손실 없이 연결할 원 packet의 SHA-256
- `handoff_provider_source_digest`, `handoff_provider_result_digest`: 근접장 계산기의 코드·실행 결과 해시
- `handoff_model`, `handoff_revision`, `evidence_status`, `scenario_provenance`
- `handoff`: 공급자가 선택한 downstream plane의 위치·수평 방향·온도·밀도·속도·수소 질량분율·직사각 단면
- `handoff.states`: 방출 시계에 따라 상태가 변하면 원 packet의 각 interval과 같은 시계로 제공

각 handoff state는 다음 장부를 만족해야 한다.

```text
provider H2 mass flow
  = density × velocity × (2 × half_width × depth) × H2 mass fraction
```

단면·상태 수·시간은 `ResolvedGasRelease`가 다시 검사한다. 검사가 끝나도 `provider_packet_qualified=false`, `physical_validation_claim=false`, `facility_qra_claim=false`로 남는다. 이는 연결과 보존을 확인하는 단계이며, 독립 실험 검증이나 현장 빈도를 부여하는 단계가 아니다.

## 사용법

외부 근접장 provider가 위 계약으로 `handoff.json`을 내보낸 뒤 다음 명령으로 기존 packet에 붙인다.

```powershell
python scripts/attach_compressible_plane_handoff.py `
  --packet results/20261014/vaporizer_worklist_g1/resolved_release.json `
  --handoff results/20261016/vaporizer_g1_compressible_handoff.json `
  --output-packet results/20261016/vaporizer_g1_with_handoff/resolved_release.json `
  --output-audit results/20261016/vaporizer_g1_with_handoff/audit.json
```

성공 상태는 `COMPRESSIBLE_PLANE_HANDOFF_ATTACHED_AND_VALIDATED`다. 원 packet의 식별자나 digest가 다르면, 단면 질량 장부가 닫히지 않으면, interval 수가 다르면 명령은 `COMPRESSIBLE_PLANE_HANDOFF_ATTACH_BLOCKED`로 종료한다.

`scripts/validate_compressible_plane_handoff.py`로 최종 packet의 PH·연속성·handoff 소비 여부를 다시 확인한다. `src/lh2_tno/chain_worker.py`는 handoff가 선언한 plane에서만 SLABx를 시작하며 plane을 회전·팽창·추정하지 않는다.

## 현재 실제 상태

선택된 `ambient-vaporizer/G1` packet은 고속이지만 provider handoff가 없어서 `COMPRESSIBLE_PLANE_HANDOFF_BLOCKED`다. 별도로 보관된 저마하 packet은 최대 Mach `0.243589`로 계약을 통과하지만, 선택된 G1에 대체하지 않는다. 합성 handoff smoke는 연결 코드와 19개 시계 상태 소비만 확인했으며 실제 provider 증거 또는 독립 물리검증으로 승격하지 않는다.

다음에 필요한 자료는 근접장 provider가 고정된 plane에서 내보낸 상태 이력, 그 계산의 원본·결과 digest, plane 선택 근거, 그리고 독립 실험의 동일 관측량이다. 이 자료가 없으면 시설 전체 IR/F-N은 계속 보류한다.

## source-state adapter 보완

`src/lh2_tno/compressible_source_adapter.py`와 `scripts/build_compressible_plane_handoff.py`는 provider가 위의 상류·throat 상태를 아직 별도 근접장 결과로 내보내지 못할 때 사용할 수 있는 선택형 진단 경로다. 각 구간에 `ResolvedGasStep.provider_source_state`가 있어야 하고, 원 provider 결과 digest와 정확히 일치해야 한다. 기본 `birch_momentum_energy` 구성은 질량·운동량으로 등가 평면 속도를 만들고 provider property backend에서 에너지를 닫는다. 이 출력은 `synthetic_diagnostic`으로만 기록하며, 실제 provider-owned 근접장 또는 독립 검증을 대신하지 않는다.

기존 `vaporizer_worklist_g1`은 해당 source-state가 없어 `COMPRESSIBLE_PLANE_HANDOFF_SOURCE_STATE_BLOCKED`로 남는다. source-state가 포함된 합성 1 MPa smoke는 `results/20261016/dynamic_high_pressure_source_state_smoke`에 보관되어 있으며, handoff 최대 Mach `3.9982`와 에너지 잔차 `0 J/kg`를 확인했지만 provider 승격 및 시설 위험도 계산에는 사용하지 않았다.
