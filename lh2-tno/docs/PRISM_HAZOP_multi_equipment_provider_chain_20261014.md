# PRISM HAZOP 다중 설비 연결 진단

## 목적

이 진단은 한 개 탱크만 통과시키던 HAZOP 연결을 일반적인 옥외 액화수소 설비 구성으로 확장한다. 같은 시설 테이블 안에 저장탱크, 이송배관, 밸브, 릴리프 벤트, 펌프, 기화기, 재액화기를 넣고, 각 설비의 상태값과 운전 모드를 HAZOP 판단에 전달한다.

운전 모드는 압력값으로 추정하지 않는다. 상태 프레임에 `receiving`, `supply`, `standby`를 명시하고, HAZOP 행의 운전 모드와 일치할 때만 시나리오를 선택한다.

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
