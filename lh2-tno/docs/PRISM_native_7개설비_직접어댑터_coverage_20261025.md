# native 7개 설비 직접 어댑터 coverage

`scripts/build_native_direct_adapter_coverage.py`는 외부 `lh2dt` 사고 export를 직접 호출한 일곱 설비의 strict packet과 최종 chain 기록을 한 장부로 묶는다.

현재 장부에는 다음 설비가 들어간다.

| native 설비 | strict packet | 피해 chain |
|---|---|---|
| LayeredTank | 직접 native 탱크 export | 완료 |
| DynamicHEMPipe | 직접 native 배관 export | 완료 |
| StrokeLimitedCommandedValve | 직접 native 밸브 export | 저마하 진단 조건에서 완료 |
| MappedPump | 직접 native 펌프 export | 완료 |
| DynamicVaporizer | 직접 native 기화기 export | 완료 |
| DynamicReliquefier | 직접 native 재액화기 export | 완료 |
| VentStack | 직접 native 벤트 export | 완료 |

재생 명령은 다음과 같다.

```powershell
python scripts/build_native_direct_adapter_coverage.py `
  --output examples/native_direct_adapter_coverage_v1.json
```

장부의 `native_model_count=7`, `end_to_end_chain_count=7`은 코드 경계와 진단 chain의 실행 증거다. source-state completion은 StrokeLimitedCommandedValve·DynamicVaporizer·DynamicReliquefier 3개에서 기록되며, 밸브는 `PROVIDER_NATIVE_SOURCE_THROAT_FIELDS`, 두 열유체 모델은 `COMPLETED_ISENTROPIC_THROAT_FIELDS`를 사용한다. 나머지는 액체·2상 경계이거나 VentStack처럼 native throat 해가 없어 차단된다. 밸브 기본 500 kPa packet은 고속 직접면 범위 초과로 보류되므로, 장부의 밸브 chain은 별도 101.5 kPa 저마하 진단 variant이며 `same_packet_chain=false`로 기록한다. 나머지 6개는 같은 packet을 chain에 재생했다. 모든 항목은 합성 또는 운영자 선언 조건이며 `provider_packet_promoted_count=0`, `frequency_inference_count=0`, `physical_validation_claim_count=0`, `facility_qra_claim_count=0`을 유지한다. 따라서 이 장부는 현장 빈도·qualified provider·독립 물리검증·시설 전체 IR/F-N을 완료했다는 뜻이 아니다.
