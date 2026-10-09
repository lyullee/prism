# Native DynamicHEMPipe 기체 packet의 시설 위험 원자 결합

이번 실행은 외부 `DynamicHEMPipe`가 계산한 **gas + compressible-plane handoff**를 PRISM 시설 캠페인의 한 사건으로 넣은 기록이다. 목적은 새 빈도를 만들거나 provider 자격을 올리는 것이 아니라, 다음 연결이 실제 코드와 결과 파일에 남는지 확인하는 것이다.

```text
설비 상태
  → DynamicHEMPipe 사고 이력
  → 0.001 m opening의 exact literature event
  → 차단 성공·0 유량 종료
  → provider compressible plane
  → SLABx-LH2/SLABx 확산
  → direct/delayed ignition
  → fire/blast/TNO harm
  → 기상·인구 조건별 risk atom
  → 조건부 시설 IR/F-N 및 빈도 민감도
```

## 재현 명령

```powershell
python scripts/run_native_dynamic_pipe_gas_facility_frequency_case.py `
  --packet results/20261026/native_dynamic_pipe_gas_isolation/resolved_release_with_handoff.json `
  --request-context results/20261026/native_dynamic_pipe_gas_isolation/chain/request.json `
  --manifest examples/native_dynamic_pipe_gas_facility_manifest.json `
  --frequency-plan examples/native_dynamic_pipe_gas_facility_frequency_plan.json `
  --annual-conditions examples/native_dynamic_pipe_gas_facility_annual_conditions.json `
  --backend-config results/20261009/equipment_campaign/backend_config.json `
  --output-dir results/20261026/native_dynamic_pipe_gas_facility_frequency
```

`frequency_plan`의 0.1 m 기준 배관과 `AREA_0.01%` 문헌 LOC는 `0.001 m` provider opening과 일치한다. 실행기는 이 한 행만 request branch로 만들고 나머지 네 개 opening bin은 `UNCOMPUTED`로 보존한다. provider packet의 사건 ID와 문헌 event ID가 다르므로 둘을 조용히 덮어쓰지 않고 `binding_provenance.json`에 매핑을 기록한다.

## 결과

| 항목 | 값 |
|---|---:|
| provider opening / catalogue opening | `0.001 / 0.001 m` exact match |
| provider termination | `reviewed_isolation_success`, `0.060000 s` |
| facility event / case | 5 events / 10 cases |
| executed cases | 2 (두 기상 조건) |
| uncomputed cases | 10 (다른 opening bins) |
| risk atoms | 8 |
| central literature frequency | `3.4e-6 year^-1` |
| p05–p95 literature range | `3.2555e-7–3.5512e-5 year^-1` |
| conditional diagnostic facility IR/F-N | 계산됨 |
| facility total IR/F-N promotion | `false` |

이 gas branch의 사고 family는 `pipe_hole`이다. strict atmospheric-gas packet을 소비한 뒤에는 `liquid_two_phase`를 자동으로 붙이지 않으므로, 액체·2상 사고와 기체 사고가 시설 원장에서 섞이지 않는다.

## 해석 경계

- 빈도는 provider packet에서 추정하지 않고 기존 문헌 `FrequencyPlan`에서 한 번 적용했다.
- IR/F-N은 선언된 합성 기상·인구와 8개 risk atom의 **조건부 진단값**이다. 이번 작은 packet에서는 수용점 harm이 0으로 기록될 수 있으며, 이는 계산 경로가 실행되지 않았다는 뜻이 아니다.
- provider packet은 `model_prediction`이고 handoff는 독립 근접장 검증이 아니므로 `provider_packet_promoted=false`, `physical_validation_claim=false`다.
- 전체 opening bin·사고군·실제 설비 범위가 닫히지 않았고, 시설 전체 IR/F-N은 계속 보류한다.
- 처리시간은 한 번의 캠페인 측정값이며 1 Hz 신규 물리계산 서비스나 실시간 성능 보증이 아니다.

주요 산출물은 [verification.json](../results/20261026/native_dynamic_pipe_gas_facility_frequency/verification.json), [campaign_result.json](../results/20261026/native_dynamic_pipe_gas_facility_frequency/campaign_result.json), [facility_assessment.json](../results/20261026/native_dynamic_pipe_gas_facility_frequency/facility_assessment.json), [binding_provenance.json](../results/20261026/native_dynamic_pipe_gas_facility_frequency/binding_provenance.json)이다.
