# native `VentStack` 방출 연결 기록

`scripts/export_lh2dt_native_vent_stack_prism_packet.py`는 외부 `VentStack.export_accident_history(request)`를 직접 호출해 stack hydraulic 결과와 가스 방출 이력을 PRISM strict gas release로 변환한다. 기본 0.1초 진단시계에서 대기 출구 속도·질량·압력강하를 보존하고, 동일 packet을 SLABx/SLABx-LH2 피해 chain으로 재생할 수 있다.

벤트는 상류 재고·설정압력·차단 신뢰도를 자체적으로 소유하지 않으므로 `available_mass_kg`와 종료 근거를 호출자가 제공한다. 기본 종료는 `synthetic_diagnostic_horizon`이다. 외부 helper의 compact source trace는 원본 응답에 보존하지만 완전한 PRISM throat state가 아니므로 고속 압축성 handoff를 자동 생성하지 않는다.

이 모듈은 비상 릴리프의 현장 setpoint나 빈도를 산정하지 않는다. synthetic diagnostic packet이므로 독립 물리검증·qualified provider·시설 IR/F-N으로 승격하지 않는다.
