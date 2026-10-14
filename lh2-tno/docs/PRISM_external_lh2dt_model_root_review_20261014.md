# 외부 lh2dt 모델 정본 재검토 기록 (2026-10-14)

## 검토 대상

액화수소 설비 디지털 트윈 모델의 실제 코드 정본인 `lh2dt_models`를 PRISM의 사고 방출 provider 후보로 다시 점검했다. 모델 root는 다음 위치에 있다.

```text
C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models
```

이 검토는 정상상태 모델, 설비 구성요소 계약, 예제와 검증 코드를 확인하는 provenance 단계다. 모델이 존재하거나 정상 운전 계산이 가능하다는 사실만으로 사고 방출 packet을 만들거나 문헌 빈도에 연결하지 않는다.

## 재현 명령

```powershell
python scripts/review_external_lh2_model_root.py `
  --source-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\lh2dt_models" `
  --closure-audit results/20261106/generic_lh2_provider_closure_requests.json `
  --output results/20261014/external_lh2dt_models_root_review_current.json
```

## 결과

출력: `results/20261014/external_lh2dt_models_root_review_current.json`

| 항목 | 결과 |
|---|---|
| 검토 상태 | `MODEL_ROOT_REVIEWED_NO_PRISM_PROMOTION` |
| provider response artifact | 0 |
| `resolved_release.json` | 0 |
| exact generic PRISM identity match | 0 |
| qualification sidecar | 0 |
| 독립 물리검증 artifact | 0 |
| 시설 QRA artifact | 0 |
| provider packet·빈도·물리검증·시설 QRA 승격 | 모두 `false` |

현재 root에서 확인되는 것은 `lh2dt`의 물리 모델과 구성요소 구현이다. PRISM이 요구하는 사고 packet은 사건 ID·설비 ID·사고 port·source/result digest·provider 소유 시간 이력·종료·격리·재고·질량/에너지 폐합을 함께 가져야 한다. 이번 root에는 이 exact identity를 가진 외부 결과와 `prism.provider_qualification_evidence.v1` sidecar가 없으므로, 일반 모델과 정상상태 출력은 진단 근거로만 남겼다.

## IJHE 완료 감사 연결

`build_ijhe_completion_audit.py --external-model-root-review`를 사용하면 `diagnostic_external_lh2_model_root_review` 검사가 추가된다. 이 검사는 다음을 확인한다.

- root review schema와 `MODEL_ROOT_REVIEWED_NO_PRISM_PROMOTION` 상태
- provider-like artifact 수와 외부 exact-match 감사의 구조
- provider packet·빈도·물리검증·시설 QRA 승격 플래그가 모두 `false`

검사가 PASS여도 외부 모델이 사고 provider로 적격화되었다는 뜻은 아니다. 실제 provider response와 exact digest-bound qualification sidecar가 추가되기 전에는 모든 사고 case가 strict facility QRA gate에서 보류된다.
