# PRISM provider port state contract

## 목적

액화수소 설비 디지털트윈과 PRISM 사이에서 설비 상태를 잃지 않고 방출
계산으로 넘기기 위한 공통 경계다. `prism.provider_port_state.v1`은 한
방출 시간구간의 포트 상태를 기록한다.

필수로 보존하는 값은 다음과 같다.

- `component_id`, `port_id`, `time_s`
- 유체(`Hydrogen` 또는 `ParaHydrogen`)와 상(`liquid`, `vapour`, `two_phase`)
- 절대압력, 온도, 밀도, 비엔탈피 `specific_enthalpy_j_kg`
- 질량유량, ENU 위치와 유동 방향
- 출처 설명과 원자료 SHA-256

따라서 외부 모델의 `P/T`만 복사하는 연결과, 액체 상태를 기체로 바꾸어
넘기는 연결을 구분할 수 있다. 이 계약은 누출구멍, 지속시간, 차단 성공률,
재고 소진, 사고빈도를 계산하지 않는다. 그런 값은 설비 모델이 계산한
`prism.resolved_release.v1` 방출 패킷에 별도로 들어가야 한다.

## 코드 사용

`ResolvedGasStep.provider_port_state` 또는
`ResolvedLiquidStep.provider_port_state`에 시간구간별 상태를 넣는다. PRISM은
다음 항목을 자동 확인한다.

1. 컴포넌트와 포트가 방출 경계와 같은지
2. 상태 시각이 방출 시계와 같은지
3. 유체와 물성 기준이 같은지
4. 기체 방출이면 기체/2상, 액체 방출이면 액체/2상인지
5. 포트 유량과 방출 구간 유량이 질량 기준으로 닫히는지

검사가 통과한 패킷은 다음 리졸버로 반복 사용할 수 있다.

```python
from lh2_tno.provider_release import provider_release_resolver_from_packet

resolver = provider_release_resolver_from_packet(
    "provider_resolved_release.json",
    request_defaults,
    component_id="storage-tank-01",
    port_id="liquid-out",
)
```

실시간 결과의 `equipment_release_path.boundaries[*].provider_port_state`에는
구간 수, 결합된 구간 수, 상별 개수, 원자료 해시, 누락 시각이 요약된다. 따라서
시설 모니터 화면에서 “방출 패킷은 있으나 upstream 포트 상태 증거가 없는
경우”를 별도로 표시할 수 있다.

`resolver`는 실시간 상태 프레임을 받아도 압력이나 온도로 방출을 재추정하지
않는다. 설비 모델에서 새 방출 패킷을 생성한 뒤 새 리졸버를 만들거나,
애플리케이션이 프레임별로 검증된 패킷을 공급해야 한다. 주파수도 이 경계에서
생성하지 않는다. 주파수는 별도의 문헌 `FrequencyEvent` 연결 단계에서 한 번만
부여한다.

프레임마다 설비 모델을 호출하려면 `provider_release_resolver_from_provider`
를 사용한다. 콜백이 반환한 패킷은 매 프레임 다시 strict 검증되며, 콜백이
정상상태 스냅샷만 반환하거나 포트가 바뀌면 계산이 중단된다.

## 현재 적용 범위와 남은 검증

합성 및 모델 예측 패킷에는 계약 검증과 방출→SLABx-LH2→피해 계산 연결이
가능하다. 액화수소검사지원센터와 외부 `액화수소 설비 디지털 트윈 모델링#2`
자료는 현재 정상상태·토폴로지 스크리닝 자료로만 확인되었으며, 실제 사고
방출 패킷·차단 이력·재고 장부·독립 물리 검증은 아직 공급되지 않았다.
따라서 이 계약을 추가해도 시설 전체 IR/F-N 또는 현장 사고빈도 승격이
자동으로 이루어지지 않는다.
