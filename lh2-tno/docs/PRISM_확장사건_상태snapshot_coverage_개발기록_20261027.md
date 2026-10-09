# PRISM 확장 사건 상태 snapshot coverage 기록

## 목적

기본 native LH2 24개 사건은 `prism.equipment_state_snapshot.v1` payload와 provider echo digest를 요청·결과에 함께 보존한다. 통합 원장에 추가한 vertical handoff 5개와 inventory depletion 5개도 같은 기준으로 연결했다.

## 이번 보완

`src/lh2_tno/consequences.py`에 canonical state payload·선언 digest·provider echo digest를 전달하는 계약을 추가하고, `scripts/validate_vertical_vent.py`와 `scripts/validate_equipment_inventory.py`가 사고 방출을 계산하기 전에 snapshot을 만들도록 연결했다. provider worker는 요청 digest를 응답에 echo한다. `src/lh2_tno/campaign.py`는 이 payload를 각 기상 case의 packet identity에 보존하고, `src/lh2_tno/extension_state_snapshot_coverage.py`는 rebound 결과에서 모든 case의 payload·digest·echo를 다시 검증한다. 결과 파일은 `results/20261026/native_full_scope_union_assessment/extension_state_snapshot_coverage.json`이다.

현재 결과:

- 확장 사건: 10개
- canonical state snapshot이 provider echo까지 확인된 사건: 10개
- 상태 snapshot이 확인되지 않은 사건: 0개
- vertical handoff: 5개 모두 `BOUND_AND_ECHOED`
- inventory depletion: 5개 모두 `BOUND_AND_ECHOED`

통합 원장에서는 기본 native 24개와 확장 10개를 합쳐 34개 event가 상태 연결되고, `strict_facility_state_snapshot_coverage`가 `PASS`가 되었다. 전체 objective 감사는 여전히 `CONDITIONAL_DIAGNOSTIC_COMPLETE_STRICT_GATES_OPEN`이며, 독립 물리검증·qualified provider packet·엄격한 전체 범위·시설 전체 QRA의 4개 gate는 별도 보류된다.

수직 벤트 snapshot은 provider PH 입력의 압력 101,525 Pa와 20.5 K 기준 온도, 0.2 s 경계의 21.0 K 입력을 state-only 측정으로 보존한다. 재고 소진 snapshot은 HomogeneousTank 초기 입력의 압력 101,000 Pa와 액체분율 0.0001을 보존한다. 두 경로 모두 `origin`은 합성 `model_prediction`이고, snapshot에 누출구경·방출시간·빈도·종료 basis·유량 이력을 넣지 않는다.

방출 경계의 유량·압력·온도·질량, provider result digest, 또는 종료시간은 사고 방출 계산의 근거이지 설비 정상 상태 snapshot이 아니다. 이번 구현은 방출 결과에서 상태를 재구성하지 않고, 각 provider 생성기가 원래 사용한 입력 상태에서 snapshot을 만든다.

## 재현

수직 벤트와 재고 소진 생성기를 먼저 실행한다.

```powershell
python scripts/validate_vertical_vent.py --all-area-bins --output-dir results/20261020/vertical_vent_all_bins
python scripts/validate_equipment_inventory.py
```

그 결과를 기본 native state-bound campaign과 합친다. `--inventory-source-component-id terminal_pipe`는 새 재고 생성기의 원래 component ID를 지정하고, 최종 원장에서는 `inventory-depletion-pipe-01`로 namespace를 부여한다.

```powershell
python scripts/run_native_full_scope_union_assessment.py `
  --base-dir results/20261027/native_generic_scope_packets_state_bound/campaign_assessment `
  --vertical-result results/20261020/vertical_vent_all_bins/campaign_result.json `
  --vertical-scope-matrix results/20261020/vertical_handoff_scope_matrix_all_bins.json `
  --inventory-result results/20261009/equipment_inventory_campaign/campaign_result.json `
  --inventory-scope-matrix results/20261019/inventory_depletion_scope_matrix_rebound.json `
  --inventory-source-asset-id terminal_pipe_asset `
  --inventory-source-component-id terminal_pipe `
  --state-snapshot-binding-audit results/20261027/native_generic_scope_packets_state_bound/state_snapshot_binding_audit.json `
  --output-dir results/20261026/native_full_scope_union_assessment
```

`build_ijhe_objective_coverage_audit.py --extension-state-snapshot-coverage`는 이 결과를 strict facility state gate에 반영한다. 확장 결과는 각 campaign identity에서 canonical payload를 읽어 별도 sidecar 없이 검증하며, 필요하면 `--extension-state-snapshot-audit`에 provider의 독립 audit row를 추가할 수 있다.

생성기 입력이 바뀌면 같은 event ID의 snapshot payload와 provider echo digest를 다시 대조한다. 현재 장부는 합성 model-prediction 입력의 상태 경계가 연결됐다는 진단 결과이며, 현장 계측 정확도·시설 QRA 승격·독립 물리검증을 주장하지 않는다.
