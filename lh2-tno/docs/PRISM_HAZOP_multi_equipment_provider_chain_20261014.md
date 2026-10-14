# PRISM HAZOP 다중 설비 연결 진단

## 목적

이 진단은 한 개 탱크만 통과시키던 HAZOP 연결을 일반적인 옥외 액화수소 설비 구성으로 확장한다. 같은 시설 테이블 안에 저장탱크, 이송배관, 밸브, 릴리프 벤트, 펌프, 기화기, 재액화기를 넣고, 각 설비의 상태값과 운전 모드를 HAZOP 판단에 전달한다.

운전 모드는 압력값으로 추정하지 않는다. 상태 프레임에 `receiving`, `supply`, `standby`를 명시하고, HAZOP 행의 운전 모드와 일치할 때만 시나리오를 선택한다.

전체 데이터 흐름을 한 장으로 보려면 최신 [통합 흐름도 PNG](figures/lh2_hazop_multiequipment_integrated_flow_v10.png) 또는 [편집 가능한 SVG](figures/lh2_hazop_multiequipment_integrated_flow_v10.svg)를 사용한다. 현장 입력값에는 설비 상태와 운전 모드가 함께 들어가며, HAZOP 판단 이후 정량분석 계층은 설비·공정 모델, 사고빈도, SLABx-LH2, 점화·기상·인구, 통합 실행 계층을 동등한 구성요소로 결합한다. PRISM은 이 계층을 구현하는 실행·연계 요소로 표시되며, 단일 모델이 전체 분석을 대표하지 않는다.

## 실행 경로

```text
상태 프레임(설비값 + 운전 모드)
    → HAZOP 행 선택
    → 설비별 provider packet resolver
    → 방출 종료·재고·출구 포트 계약 확인
    → SLABx-LH2/TNO 피해영향 계산
    → 문헌 빈도 결합 current-weather IR 원자
    → 연결 가능한 설비만 시설 조건부 진단 ledger로 전달
```

실행 명령은 다음과 같다.

```powershell
python scripts/run_hazop_lh2_multiequipment_provider_diagnostic.py `
  --backend-config results/20261009/backend_config_current.json `
  --output results/20261014/hazop_multiequipment_provider_diagnostic.json
```

현장별 옥외 기상·인구 조건을 연결할 때는 `--annual-conditions`로 JSON 파일을
추가한다.

```powershell
python scripts/run_hazop_lh2_multiequipment_provider_diagnostic.py `
  --backend-config results/20261009/backend_config_current.json `
  --annual-conditions examples/generic_lh2_near_receptor_annual_conditions.json `
  --output results/20261014/hazop_multiequipment_provider_site_condition_diagnostic.json
```

파일은 `id`, `annual_probability`, `weather`, `population`, `provenance`를 가진
조건 목록이며, 확률 합은 1이어야 하고 모든 조건의 수용점 집합은 같아야 한다.
첫 번째 조건의 기상은 현재 provider consequence를 실행한 기상과 일치해야 하며,
다르면 입력 경계에서 보류한다. 첫 번째 조건만 현재 HAZOP runtime의 관측 피해 결과를 사용할 수 있다. 두 번째
조건부터는 현재 날씨 결과를 재사용하지 않도록 각 조건에
`reviewed_consequence`를 넣어 `observed_harm_low_high`,
`branch_harm_low_high`, `provenance`를 별도로 제공해야 한다. 이 자료가 없으면
다중 기상 조건은 즉시 보류된다. 입력 파일을 받았다는 사실만으로 현장 기상·인구
검증이나 시설 QRA 승격을 하지 않으며, 결과의 `policy.annual_condition_source`에
입력 출처와 조건 수를 남긴다.

스크립트는 외부 provider 출력의 좌표 원점과 예시 시설 manifest의 좌표가 다를 때, 명시된 provider 출구 위치에 맞춘 **진단용 geometry rebase**를 결과에 남긴다. 이 재배치는 실제 플랜트 배치 검증이나 물리 검증을 뜻하지 않는다.

## 현재 실행 결과

현재 로컬 실행에서는 7개 설비 중 5개가 HAZOP → provider → consequence → current-weather IR 원자까지 도달했다.

| 설비 | 대표 사고 경로 | 결과 |
| --- | --- | --- |
| 저장탱크 | 액체 2상 hole, inventory depletion | 연결됨 |
| 이송배관 | pipe hole, model pressure equalization | 연결됨 |
| 이송밸브 | 액체 2상 hole | `synthetic_diagnostic_horizon` 때문에 보류 |
| 릴리프 벤트 | maximum relief discharge | 연결됨 |
| 이송펌프 | 액체 2상 hole | `synthetic_diagnostic_horizon` 때문에 보류 |
| 기화기 | instantaneous inventory depletion | 연결됨 |
| 재액화기 | two-sided rupture | 연결됨 |

보류된 밸브와 펌프는 provider packet 자체가 없어서가 아니라, 현재 패킷의 종료근거가 `synthetic_diagnostic_horizon`이기 때문이다. HAZOP 시나리오 카탈로그는 이 종료근거를 실제 차단 성공이나 재고 소진으로 바꿔 읽지 않는다. 따라서 이 두 설비는 결과에 `CONSEQUENCE_REJECTED`로 남고, 연결된 5개 설비의 조건부 진단 결과에도 자동으로 시설 완성 주장을 붙이지 않는다.

## 시설 위험 ledger의 의미

연결된 5개 설비에 대해서는 동일한 synthetic weather·receptor 조건 아래에서 current-weather IR을 계산하고, 문헌 빈도는 `FrequencyEvent`에서 별도로 가져온다. 결과에는 다음이 함께 기록된다.

- 설비별 HAZOP scenario ID, 운전 모드, provider event ID, port ID
- 방출 지속시간과 종료근거
- SLABx-LH2 피해영향 결과와 점화 branch
- 설비별 IR 원자와 조건부 시설 IR/F-N 진단
- 보류 설비 목록과 보류 사유
- 전체 runtime wall-clock과 설비별 monitor timing

조건부 시설 ledger의 `facility_total_risk_available`와 `qualified_facility_qra_available`는 계속 `false`다. 현재 패킷은 synthetic/model-prediction 자료이고, 모든 사고 family의 qualified provider packet, 독립 물리검증, 현장 geometry·인구·기상 자료가 닫히지 않았기 때문이다. 이 결과는 **다중 설비 연결이 실제 코드 경로를 통과한다는 증거**이며, IJHE용 완성 QRA 결과가 아니다.

처리시간도 결과 원장에 설비별로 남긴다. 이번 실행에서 연결된 5개 설비 중 4개는 monitor deadline 30초 이내였고, 이송배관은 46.3초로 deadline을 넘겼다. 전체 실행은 약 76.8초였다. 따라서 현재 결과는 “상태 입력이 들어오면 같은 경로로 자동 계산된다”는 진단 증거이지, 모든 설비에 대한 1 Hz 신선 물리계산 보장이 아니다. deadline을 넘긴 경우에도 stale 결과를 대신 사용하지 않고 `deadline_missed`를 기록한다.

## IJHE 목표와 다음 닫을 항목

이 진단으로 설비 단위 연결과 실패 이유를 한 기록에 모을 수 있게 되었다. 다음 단계는 보류된 밸브·펌프의 reviewed isolation/pressure-equalization provider packet을 정확한 포트·좌표·종료근거와 함께 재생성하고, 7개 설비의 모든 사고 family와 모든 frequency event를 같은 방식으로 묶는 것이다. 그 뒤에야 시설 전체 IR/F-N을 완전한 scope로 재계산하고, 외부 실험 또는 독립 계산으로 SLABx-LH2 입력과 결과를 검증할 수 있다.

관련 코드:

- `scripts/run_hazop_lh2_multiequipment_provider_diagnostic.py`
- `src/lh2_tno/hazop.py`의 `run_hazop_facility_runtime`
- `src/lh2_tno/hazop_campaign.py`의 `build_hazop_facility_campaign_result`
- `src/lh2_tno/completion_audit.py`의 `diagnostic_hazop_multiequipment_provider_chain`


## 격리계약 진단 결과 (추가 실행)

밸브와 펌프의 종료근거를 임의로 `explicit_provider_termination`으로 바꾸지 않기 위해, 외부 `lh2dt_models`의 actuator 경로를 별도 진단 어댑터로 연결했다. 밸브는 `StrokeLimitedCommandedValve`를 0 개방으로 명령하고 stroke 이후의 zero-flow 관찰구간을 확인했다. 펌프는 native `MappedPump` 방출구간 뒤에 별도 대기측 isolation valve의 zero-flow 확인구간을 붙였다. 두 경로 모두 upstream 재고와 현장 차단 신뢰도를 추정하지 않는다.

```powershell
python scripts/export_lh2dt_valve_prism_packet.py `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --output-dir results/20261014/hazop_isolation_packets/transfer-valve-01 `
  --duration-s 0.2 --time-step-s 0.01 `
  --isolation-time-s 0.05 --post-isolation-observation-s 0.15 `
  --stroke-time-s 0.05 --available-mass-kg 1.0 `
  --component-id transfer-valve-01 `
  --port-id valve-accident-out `
  --event-id "generic-lh2-full-scope-frequency-example/transfer-valve/AREA_0.01%"

python scripts/export_lh2dt_native_mapped_pump_prism_packet.py `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --output-dir results/20261014/hazop_isolation_packets/liquid-transfer-pump-01 `
  --horizon-s 0.2 --time-step-s 0.01 `
  --isolation-time-s 0.05 --post-isolation-observation-s 0.15 `
  --component-id liquid-transfer-pump-01 `
  --port-id pump-accident-out `
  --event-id "generic-lh2-full-scope-frequency-example/transfer-pump/G1"

python scripts/run_hazop_lh2_multiequipment_provider_diagnostic.py `
  --backend-config results/20261020/equipment_campaign_all_bins_generic_facility/backend_config.json `
  --isolation-packet-root results/20261014/hazop_isolation_packets `
  --output results/20261014/hazop_multiequipment_provider_isolation_diagnostic.json
```

이 실행은 7개 설비 모두 HAZOP → provider → SLABx-LH2 → 현재 기상 IR 경로를 통과했다. 밸브와 펌프의 `provider_termination_basis`는 `reviewed_isolation_success`로 기록되며, 나머지 다섯 설비는 기존 inventory depletion, pressure equalization, emergency relief, two-sided rupture 근거를 유지한다. 총 처리시간은 약 100초였고, `facility_qra_promotion=false`, `physical_validation_claim=false`, `frequency_inference_performed=false`가 계속 유지된다.

따라서 이 결과의 의미는 “모든 구성요소를 같은 코드 경로로 계산할 수 있다”는 진단 증거다. 이것은 현장 ESD/밸브 고장확률, 차단 성공확률, 실제 plant geometry·인구·기상, 또는 IJHE용 qualified facility IR/F-N을 확정하지 않는다. 다음 승격 조건은 각 설비의 reviewed actuator/isolation 시험자료, 현장 포트·좌표 확인, 사고빈도 근거와 독립 SLABx-LH2 holdout 검증이다.
