# PRISM native 모델 바인딩 일관성 감사

액화수소 디지털트윈을 연결할 때 두 기록이 함께 바뀌어야 한다.

1. 외부 `lh2dt_models` 소스에 `export_accident_history(request)`가 있는가?
2. PRISM 모델 바인딩 카탈로그가 그 사실을 `supported`로 선언하는가?

예전 카탈로그는 두 번째 항목을 `missing`으로 남겨 첫 번째 소스 감사와 어긋났다. 이 상태에서는 실제 native 사고 export가 있어도 작업목록이 설비를 상태 전용 모델로 표시한다. `src/lh2_tno/native_binding_reconciliation.py`와 `scripts/audit_native_binding_reconciliation.py`가 두 장부를 component kind별로 대조한다.

## 재현

```powershell
$py = "C:\path\to\python.exe"
$external = "C:\path\to\lh2dt_models"

& $py scripts/audit_lh2dt_native_contract.py `
  --binding examples/generic_lh2_native_model_binding.json `
  --external-root $external `
  --output results/20261022/lh2dt_native_contract_audit_native_catalog.json

& $py scripts/audit_native_binding_reconciliation.py `
  --binding examples/generic_lh2_native_model_binding.json `
  --contract-audit results/20261022/lh2dt_native_contract_audit_native_catalog.json `
  --output results/20261022/native_binding_reconciliation.json
```

최신 결과는 `RECONCILED_NATIVE_INTERFACES`이며 7개 외부 설비가 7/7 일치한다. 경계 컴포넌트는 사고 빈도 대상이 아닌 PRISM 인터페이스이므로 native 설비 수에 포함하지 않는다.

이 결과가 의미하는 것은 **인터페이스가 연결되었다는 것**이다. native 모델이 합성 형상·초기상태·대기 경계에서 방출 이력과 종료·질량 장부를 반환할 수 있고, PRISM strict adapter가 그 응답을 검사할 수 있다는 뜻이다. 다음 결과를 의미하지 않는다.

- 특정 현장 설비의 포트·배관 길이·차단 순서가 확정되었다.
- 현장 사고빈도가 센서에서 학습되었다.
- native 결과가 qualified provider packet으로 승격되었다.
- 시설 전체 IR/F-N이 열렸다.

바인딩 카탈로그의 `provider_export_schema=prism.resolved_release.v1`은 PRISM strict adapter까지 통과하는 외부 export 경계를 뜻한다. 실제 packet 자격은 별도 provider qualification, 현장 상태·geometry evidence, 독립 물리검증, 주요 사고 범위 완료를 모두 요구한다.

현재 IJHE 감사에서는 이 검사가 진단 전용 `PASS`로 기록된다. 실제 provider packet, 미계산 사고가족, 시설 IR/F-N 차단은 그대로 유지된다.
