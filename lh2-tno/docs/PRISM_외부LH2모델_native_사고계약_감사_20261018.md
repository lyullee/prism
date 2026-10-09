# PRISM 외부 LH2 모델 native 사고계약 감사

## 목적

액화수소 디지털트윈을 위험도 계산에 연결할 때 `simulate()`나 `step()`이 있다는 사실과 실제 사고 방출 이력을 제공한다는 사실을 혼동하면 안 된다. 이 감사는 외부 소스 코드를 실행하지 않고 클래스 정의를 읽어 다음 두 경계를 따로 기록한다.

- 정상 공정상태 계산 메서드: `simulate`, `step`, `evaluate`, `run`
- 사고 방출 계약: `export_accident_history(request)`와 종료·재고 장부 메서드
- PRISM-side 진단 adapter: 외부 native 클래스가 아니라 PRISM 저장소가 합성 진단을 감싼 wrapper

감사 결과만으로 사고 packet, 빈도, SLABx-LH2 검증, 시설 IR/F-N을 승격하지 않는다.

## 재현 명령

```powershell
python scripts/audit_lh2dt_native_contract.py `
  --binding examples/generic_lh2_model_binding.json `
  --external-root "C:\path\to\lh2_models" `
  --output results/20261018/lh2dt_native_contract_audit.json
```

`--prism-root`를 생략하면 현재 PRISM checkout을 사용한다. 감사기는 외부 Python 모듈을 import하거나 solver를 실행하지 않으므로, 소스 구조를 확인하는 계약 감사와 실제 provider 실행을 분리한다.

## 현재 결과

기록 `results/20261018/lh2dt_native_contract_audit.json`의 요약은 다음과 같다.

| 항목 | 결과 |
|---|---:|
| 외부 binding | 8개 |
| 외부 `lh2dt` 설비 native 사고 export | 0/7 |
| 정상 상태 메서드가 확인된 외부 설비 | 7/7 |
| PRISM-side 진단 adapter 계약 확인 | 7/7 |
| qualified provider packet 승격 | 아니오 |

저장탱크·배관·밸브·벤트·펌프·기화기·재액화기의 소스 파일은 모두 발견되지만, 각 클래스에 `export_accident_history(request)`가 없다. 경계 컴포넌트는 PRISM 인터페이스이므로 외부 native 대상에서 제외한다. 따라서 감사 상태는 `NATIVE_ACCIDENT_EXPORT_MISSING`이다.

이 결과는 현재 병목을 구체화한다. 다음 실제 연결은 각 설비 solver가 다음을 자기 모델에서 반환하도록 하는 것이다.

1. 명시된 사고 포트와 고장 mode
2. 시간별 질량·엔탈피·상 분할
3. 검출·차단 branch와 실제 종료시각
4. 남은 재고와 질량 잔차
5. provider source/state digest

그 결과를 `prism.external_accident_history.v1`로 내보내면 PRISM strict adapter가 검증할 수 있다. 진단 wrapper는 개발·회귀 확인용으로 유지하고 native packet으로 자동 대체하지 않는다.

## 판정 정책

- 클래스에 `export_accident_history`가 있어도 qualified packet은 아니다.
- 정상 메서드의 유량·압력·온도를 사고 지속시간이나 재고 소진으로 추정하지 않는다.
- PRISM-side adapter가 같은 이름의 메서드를 제공해도 외부 모델 native 기능으로 기록하지 않는다.
- source digest와 계약 감사는 재현성 자료이며, 독립 물리검증이나 현장 빈도 근거를 대신하지 않는다.

정적 감사 테스트 2건을 포함한 portable test suite는 433건 통과했다.
