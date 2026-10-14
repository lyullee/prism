# 외부 lh2dt native 사고계약 최신 감사 (2026-11-15)

## 확인한 내용

액화수소 설비 디지털트윈 모델 정본
`C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models`를 현재
소스 기준으로 다시 정적 감사했다. PRISM은 모델을 정상상태 `evaluate` 결과로
사고방출로 바꾸지 않고, 사고 전용 `export_accident_history(request)` 경계만
사용한다.

권위 결과는
[`lh2dt_native_contract_audit_current.json`](../results/20261115/lh2dt_native_contract_audit_current.json)이다.

| 항목 | 결과 |
|---|---:|
| binding catalog | 8개 (7개 외부 설비 + PRISM 경계) |
| native 사고 export | 7/7 외부 설비 |
| PRISM diagnostic adapter contract | 7/7 |
| provider packet 승격 | 0 |
| 빈도 추론 | false |
| 시설 QRA 주장 | false |

확인된 설비 클래스는 저장탱크 `LayeredTank`, 배관 `DynamicHEMPipe`, 밸브
`StrokeLimitedCommandedValve`, 벤트 `VentStack`, 펌프 `MappedPump`, 기화기
`DynamicVaporizer`, 재액화기 `DynamicReliquefier`다. 이 결과는 각 모델이 사고
개구·시간 이력·종료 장부를 반환할 수 있는 **코드 경계**를 확인한 것이다.

## 소스 provenance

현재 외부 저장소의 HEAD는 `b483f7921d7e67a269947f36393fdd3b9ab9e7b3`이고, source
tree digest는
`13a65aa75b54aee7677a1286fec1b52a149b7d0805e7908be6a0fa0ef11c1e22`이다. 감사 시점에
외부 worktree가 깨끗하지 않았으며 다음 파일이 수정·추가 상태였다.

- `CHANGELOG.md`
- `src/lh2dt/vaporizer.py`
- `docs/vaporizer_design_point.md`
- `tests/test_vaporizer_design_point.py`

따라서 이번 결과는 변경된 외부 소스의 재현 가능한 진단 기록이지, 배포 태그나
현장 검증판의 qualification 증거가 아니다. Git HEAD·dirty 상태·tree digest를
감사 JSON에 함께 저장해 소스가 바뀐 뒤에도 이전 packet을 현재 모델 결과로
오인하지 않도록 했다.

## 재현 명령

```powershell
python scripts/audit_lh2dt_native_contract.py `
  --binding examples/generic_lh2_native_model_binding.json `
  --external-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --prism-root . `
  --output results/20261115/lh2dt_native_contract_audit_current.json
```

## 다음 승격 조건

이 감사가 통과해도 실제 시설 QRA가 완료되는 것은 아니다. 다음 단계에서 외부
모델 worktree를 고정된 release commit으로 정리하고, 실제 설비별 상태 snapshot과
사고 packet의 event·component·port·종료·격리·재고 digest를 exact-match sidecar로
제출해야 한다. 그 후에야 독립 물리검증과 시설 IR/F-N 승격을 심사할 수 있다.\n