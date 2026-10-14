# 검사센터 HAZOP 운전 모드 근거 감사

이 기록은 `액화수소검사지원센터 데이터` 폴더의 운전순서 자료를 일반적인 액화수소 시설의 HAZOP 운전모드 근거로 읽는 방법을 정리한다. 특정 검사센터 전용 모듈로 고정하지 않고, `receiving`, `storage_vent`, `supply_gas`, `supply_liquid`라는 공통 모드 사전으로 보존한다.

## 확인된 근거

세 개의 CSV 운전순서 표에는 다음 단계가 명시되어 있다.

| 근거 그룹 | 행 수 | PRISM에서 보존하는 내용 |
| --- | ---: | --- |
| 액화수소 인수 | 19 | 탱크, 절차번호, 동작, 누출·화재·폭발 예상고장·위험·조치·근거 |
| 액화수소 저장(벤트) | 3 | 압력상승 감시, 벤트 개방, 벤트 종료와 각 위험 정보 |
| 수소 공급 | 30 | 기체수소 18행, 액화수소 12행과 공급 절차별 위험 정보 |

따라서 이번 감사가 확인한 명시적 운전모드 행은 총 52개다. 이 행은 `operating_mode`와 HAZOP 후보를 선택하는 정성 근거로 사용할 수 있다. 공급 CSV의 `공급모드` 열을 그대로 읽어 기체수소와 액화수소를 구분한다.

설명 PDF에는 인수·저장/벤트·공급의 세 시나리오, 6.5 bar 벤트 시작과 6.0 bar 벤트 종료, 인수 19단계와 공급 12단계 학습모델 설명이 있다. 이 내용은 절차와 보호기준의 출처를 보강하지만 사고 빈도나 방출 유량을 제공하지 않는다.

## 디지털트윈 연결 방식

현장 입력은 측정값과 운전모드를 함께 보낸다. HAZOP 표는 두 입력을 비교해 현재 활성 절차와 이탈을 선택한다. 선택된 행은 정량평가기가 사용할 `hazop_scenario_id` 후보와 설비·사고 family 검토 요청을 만든다.

```text
현장 센서 + 명시적 운전모드
        │
        ▼
HAZOP 표: 값/이탈 기준 + 모드별 절차
        │
        ▼
시나리오 선택(정성) ──► 문헌 빈도 event와 exact binding 검토
        │
        ├─ 현재 상태 ──► 설비 모델의 사고 방출 packet ──► SLABx-LH2/점화/피해
        └─ 예측 상태 ──► 위험조건 도달 시 별도 정량평가 요청
```

여기서 운전순서 표는 HAZOP 입력의 출처다. 정상 운전 행을 사고 방출로 바꾸거나, 설비 종류·방출 크기·센서 값만 보고 모드를 추정하지 않는다. 실제 정량평가는 기존 PRISM의 문헌 빈도, 설비 공정 모델, 방출 종료·차단·재고 장부, SLABx-LH2 및 시설 조건을 모두 별도 계약으로 확인한 뒤 실행한다.

## 수치 시계열의 현재 상태

검사센터의 예측·학습 엑셀에는 PT, TT, DPT 태그와 절차 메타데이터가 있다. 그러나 현재 감사에서 태그별 공학 단위와 교정·매핑 문서가 확인되지 않아 다음 값은 아직 만들지 않는다.

* 수치 시계열에서 `HazopStateFrame`을 자동 생성하지 않는다.
* 센서 정상 운전 자료로 사고 빈도를 학습하지 않는다.
* 시계열을 사고 방출량, 지속시간, 종료근거 또는 provider packet으로 바꾸지 않는다.
* 단위·태그 매핑이 검토된 뒤에만 현재 상태 정량평가 입력으로 승격한다.

따라서 최신 산출물의 상태는 `HAZOP_OPERATING_MODE_EVIDENCE_AUDIT_WITH_STATE_BINDING_WITHHELD`다. 이는 운전모드·HAZOP 정성 근거가 없다는 뜻이 아니라, 수치 상태를 정량평가에 연결하는 마지막 계측 게이트가 열리지 않았다는 뜻이다.

## 재현 명령

```powershell
python scripts/audit_hazop_operating_mode_evidence.py `
  --source-root "C:\Users\lyul\Desktop\DocuData\액화수소검사지원센터 데이터" `
  --timeseries-audit results/20261106/external_support_center_timeseries_audit.json `
  --output results/20261014/support_center_hazop_operating_mode_evidence_audit.json
```

코드 감사기는 각 CSV와 설명자료의 SHA-256, 인코딩, 행 수, 모드별 행 수, 위험 범주, 문서 anchor를 함께 남긴다. `frequency_binding`과 `release_packet_binding`은 각 원본 행에서 명시적으로 보류된다. 수치 단위 검토가 끝나면 별도의 reviewed tag/unit map을 입력으로 추가하고, 그때만 상태 snapshot binding gate를 다시 평가해야 한다.

## 적용 범위와 남은 일

이 결과는 일반 액화수소 시설용 모드 사전과 HAZOP 시나리오 입력으로 재사용할 수 있다. 탱크·배관·밸브·펌프·벤트·기화기 모델과 결합할 때는 각 설비가 같은 `operating_mode`, `hazop_scenario_id`, 명시적 사고 event ID를 공유하는지 확인해야 한다.

아직 닫히지 않은 항목은 계측 단위·태그 매핑, 설비별 사고 방출 packet, 문헌 빈도 exact binding, 차단·재고소진 근거, 독립 물리검증, 시설 전체 IR/F-N이다. 이 감사가 해당 항목을 대신 충족한다고 해석하지 않는다.
