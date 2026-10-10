# PRISM–lh2dt native 사고 방출 현재 점검 (2026-11-04)

## 확인한 현재 상태

외부 액화수소 디지털트윈 정본
`C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\06_액화수소_디지털트윈_물리모델`
을 PRISM의 `generic_lh2_native_model_binding.json`과 다시 대조했다.

현재 감사 결과는 다음과 같다.

| 항목 | 결과 |
|---|---:|
| binding 행 | 8 |
| 외부 설비 클래스 | 7 |
| native `export_accident_history(request)` | 7/7 |
| PRISM diagnostic adapter 계약 | 7/7 |
| 미구현 외부 설비 | 0 |
| qualified provider packet | 0 |
| 빈도 자동 추론 | 아니오 |
| 시설 IR/F-N 승격 | 아니오 |

확인된 native 설비는 `LayeredTank`, `DynamicHEMPipe`,
`StrokeLimitedCommandedValve`, `VentStack`, `MappedPump`,
`DynamicVaporizer`, `DynamicReliquefier`다.

기계 판독 결과는
`results/20261104/lh2dt_native_contract_audit_current.json`에 저장했다.

## 외부 모델 전체 회귀시험 결과

외부 정본의 전용 가상환경에서 아래 명령을 실행했다.

```powershell
.venv-local\Scripts\python.exe -m pytest -q
```

결과는 **1494 passed, 0 failed, 0 skipped, 1192.56초(19분 52초)**다.
기계 판독용 결과는
`results/20261104/lh2dt_native_external_regression_evidence.json`에 저장했다.

이 결과는 외부 모델 코드가 현재 회귀시험에서 안정적으로 동작했다는 근거다.
7개 native 사고방출 export와 PRISM diagnostic adapter의 연결을 다시 확인하는 데
사용할 수 있지만, 실제 설비 provider packet의 자격 인정이나 시설 전체 IR/F-N
승격을 의미하지는 않는다.

## 의미

이제 외부 모델의 정상상태 `simulate()`, `step()`, `evaluate()`를 누출로 바꾸는 추정 경로는 사용하지 않는다. 각 설비가 명시적 사고 요청을 받고, 방출 단계·지속시간·종료 근거·질량/에너지 장부를 반환하는 경계가 존재한다.

이것은 **설비 모델과 PRISM 피해 계산을 연결할 수 있는 코드 경계가 완성되었다**는 뜻이다. 실제 액화수소 시설의 사고 방출로 승격하려면 별도의 provider 자격 증거가 필요하다. 현재 native smoke의 형상·초기상태·대기·재고·차단 조건은 합성 또는 진단용이므로, PRISM은 이를 `synthetic_diagnostic` 또는 `operator-limited`로 유지한다.

## 주요 잔여 게이트

1. 검사센터 또는 일반 시설의 실제 설비별 사고 개구·초기상태·방출 지속시간·차단 결과·재고 장부를 provider packet으로 제출해야 한다.
2. provider 응답과 상태 snapshot의 source/result digest가 동일해야 한다.
3. 설비별 packet을 문헌 빈도 사건과 exact-match한 뒤에도, 모든 주요 사고 가족의 미계산 사건을 포함해 시설 범위 감사를 통과해야 한다.
4. SLABx-LH2/PRISM 피해 결과는 외부 독립 실험 또는 검토된 자료와 비교해야 한다.

따라서 현재 결론은 `NATIVE_INTERFACE_COMPLETE_DIAGNOSTIC_ONLY`다. `qualified_actual`, 독립 물리검증, 시설 전체 IR/F-N으로 표시하지 않는다.

## 재현 명령

```powershell
$py = "C:\Users\lyul\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$root = "C:\Users\lyul\Documents\ChatGPT\TNO 위험성 분석 프로젝트"
$dt = "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\06_액화수소_디지털트윈_물리모델"
& $py "$root\lh2-tno\scripts\audit_lh2dt_native_contract.py" `
  --binding "$root\lh2-tno\examples\generic_lh2_native_model_binding.json" `
  --external-root $dt `
  --output "$root\lh2-tno\results\20261104\lh2dt_native_contract_audit_current.json"
```

외부 모델 전체 회귀시험은 외부 프로젝트의 `.venv-local`에서 별도로 실행한다. 회귀시험이 통과해도 그것은 모델 코드의 회귀 안정성 근거이며, 실제 시설 사고 packet의 자격 증거를 대신하지 않는다.
