# 전체 campaign 사건의 HAZOP 운전 모드 바인딩 감사

## 발견된 연결 공백

전체 시설 campaign의 34개 사건을 확인한 결과, 방출 packet·지속시간·재고·피해 계산은 존재하지만 사건 행에 `operating_mode`와 `hazop_scenario_id`가 모두 비어 있었습니다. 이 값은 탱크인지 배관인지, 또는 방출 면적이 얼마인지로 안전하게 추정할 수 없습니다. `receiving`, `supply`, `standby` 중 하나를 정하려면 현장 관측 frame 또는 공정 시뮬레이션 frame이 명시적으로 제공되어야 합니다.

`src/lh2_tno/hazop_event_mode_binding.py`의 `audit_hazop_event_mode_binding()`은 이 경계를 검사합니다.

- 사건에 명시된 모드·scenario ID가 있으면 case와 risk atom까지 같은지 확인
- 별도 mode binding 파일이 있으면 component와 release mode를 exact-match
- 누락 모드는 `MODE_REQUIRED`로 남김
- 모드만 있고 scenario ID가 없으면 `SCENARIO_ID_REQUIRED`
- 충돌은 `MODE_BINDING_CONFLICT`
- 설비 종류·방출 크기·빈도 bin으로 모드를 추정하지 않음

## 재현 명령

```powershell
python scripts/audit_hazop_event_mode_binding.py `
  --campaign-result results/20261110/native_full_scope_union_assessment_latest2_near_vertical_port_bound/campaign_result.json `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --output examples/hazop_event_mode_binding_audit_20261014.json
```

현재 결과는 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| campaign 사건 | 34 |
| 명시적 모드 바인딩 | 0 |
| 모드 입력 필요 | 34 |
| scenario ID 필요 | 0 |
| mode 충돌 | 0 |
| provider frequency event 대조 | 24 |

이 결과의 종료 코드는 2이다. 이는 계산 실패가 아니라, 모드가 없는 사건을 정량 위험도에 자동 포함시키지 않고 명시적 운전 상태 입력을 요구한다는 뜻이다.

## 바인딩 파일 형식

현장 또는 공정 시뮬레이션에서 검토된 값을 다음처럼 공급한다.

```json
{
  "bindings": [
    {
      "event_id": "generic-lh2-full-scope-frequency-example/transfer-line/AREA_100%",
      "component_id": "liquid-transfer-line-01",
      "release_mode": "hole",
      "operating_mode": "supply",
      "hazop_scenario_id": "transfer-line-01-supply-pipe-hole",
      "source_provenance": "reviewed process-state snapshot"
    }
  ]
}
```

바인딩이 제공되면 감사는 해당 event의 case와 risk atom에도 같은 모드와 scenario ID가 전달되었는지 확인한다. 이 감사는 기존 campaign을 수정하거나 재계산하지 않으며, 명시적 바인딩이 없는 사건을 시설 IR/F-N에 임의로 넣지 않는다.

IJHE 완료 감사에는 `--hazop-event-mode-binding examples/hazop_event_mode_binding_audit_20261014.json`을 추가할 수 있다. `diagnostic_hazop_event_mode_binding=PASS`는 누락을 정확히 계수하고 추정 금지 정책을 지켰다는 뜻이며, 34개 사건의 모드가 확보됐다는 의미는 아니다.

