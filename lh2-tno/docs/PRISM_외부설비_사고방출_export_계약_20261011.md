# PRISM 외부 설비 사고 방출 export 계약

## 목적

PRISM은 외부 액화수소 디지털트윈의 정상 상태를 사고 방출로 바꾸지 않는다. `evaluate()`, `simulate()`, `advance()`가 압력·온도·유량을 반환해도 그것만으로는 사고의 개구, 지속시간, 차단 결과, 재고 소진을 알 수 없다. 따라서 사고 계산을 담당하는 외부 모델은 별도의 `export_accident_history(request)` 메서드를 제공해야 한다.

이번 단계에서 PRISM 쪽 계약과 엄격한 연결 함수를 구현했다.

```text
src/lh2_tno/equipment_accident_export.py
  AccidentReleaseExportRequest
  AccidentHistoryProvider
  export_equipment_gas_accident_history()
  export_equipment_liquid_accident_history()
```

이 계약은 일반 액화수소 설비에 적용한다. 특정 검사센터의 태그·빈도·좌표를 코드에 넣지 않는다.

## 요청에 반드시 들어가는 것

예시는 `examples/equipment_accident_export_request.json`에 있다.

- 설비 ID, 사고 포트 ID, 사건 ID와 고장 형태
- 실제 사고 개구 직경과 계산 시작시각·관찰시계
- 방출 위치·방향·대기 압력·온도
- provider 원본 digest, 상태 snapshot digest, 모델 package/class/revision
- 종료를 provider가 소유한다는 `provider_termination_required=true`
- 자료 자격: `qualified_actual`, `synthetic_diagnostic`, `screening_only`

PRISM은 누락된 값을 압력·센서·설비 종류에서 추정하지 않는다. `horizon_s`는 관찰 요청값일 뿐이며 provider가 반환한 실제 `duration_s`를 대신하지 않는다.

## 정상 상태 snapshot 전달 경계 (2026-10-17)

디지털트윈이 사고 시나리오를 계산하기 직전의 설비 상태를 provider에 전달해야 할 때는 `prism.equipment_state_snapshot.v1` 객체를 요청의 `state_snapshot`에 넣는다. 구현은 `src/lh2_tno/state_snapshot.py`의 `EquipmentStateSnapshot`과 `build_state_snapshot_from_normalized()`에 있다.

snapshot에는 설비 ID, 상태를 읽은 시각, 자료 출처, 압력·온도·재고·상(phase), 위치와 정규화된 SI 측정값만 들어간다. snapshot 자체의 canonical digest가 요청의 `state_snapshot_digest`와 정확히 같아야 provider 호출이 허용된다. provider가 받은 요청에는 원본 snapshot이 그대로 포함되므로, 어떤 상태에서 사고 solver가 실행됐는지 재현할 수 있다.

snapshot에 사고 전용 필드(`annual_frequency_per_year`, 누출구경, `duration_s`, `steps`, 종료 근거, resolved release 등)가 들어가면 즉시 거부한다. 따라서 정상 운전 상태를 사고 방출로 자동 승격할 수 없다. 사고 개구·빈도·지속시간·차단·재고 소진은 여전히 provider의 명시적 `export_accident_history()`가 소유한다. snapshot을 넣지 않은 기존 요청도 호환되지만, 기존 digest 값은 유지되고 사고정보를 추정하지 않는다.

## provider가 반환해야 하는 것

provider 응답의 최상위에는 다음 schema가 있어야 한다.

```json
{
  "provider_export_schema": "prism.external_accident_history.v1",
  "provider_qualification": {
    "schema_version": "prism.provider_qualification_evidence.v1",
    "status": "qualified_actual",
    "provider_origin": "native_provider",
    "evidence_id": "provider-actual-export-001",
    "provider_source_digest": "<same as request provider_source_digest>"
  },
  "data": {
    "event_kind": "accidental_leak",
    "component_id": "storage-tank-01",
    "port_id": "tank-accident-out",
    "event_id": "storage-tank-01/tank-accident-out/AREA_0.01%",
    "duration_s": 12.4,
    "available_mass_kg": 100.0,
    "cumulative_mass_out_kg": 3.2,
    "termination_provenance": "provider isolation success",
    "termination_basis": "reviewed_isolation_success",
    "steps": []
  }
}
```

기체 packet은 각 step에 압력·온도·밀도·면적·속도와 그 출처가 있어야 한다. 액체/2상 packet은 flash 기체, 지상 액체, 공기 중 액적 분할과 reference area를 추가해야 한다. 기존 `equipment_release_adapter.py`가 질량·정적 엔탈피·시간 적분과 `ResolvedGasRelease`/`ResolvedLiquidRelease` 계약을 다시 검사한다.

## 연결 규칙

1. provider 객체에 `export_accident_history(request)`가 없으면 즉시 오류다. `evaluate()`나 `simulate()`를 사고 packet으로 사용하는 fallback은 없다.
2. 응답이 `prism.external_accident_history.v1`를 선언하지 않거나 `event_kind=accidental_leak`가 아니면 거절한다.
3. 응답의 설비·포트·사건 ID가 요청과 다르면 거절한다.
4. 정상 상태 snapshot 표시가 있으면 거절한다.
5. strict adapter가 통과한 packet도 `evidence_status=synthetic_diagnostic` 또는 `screening_only`이면 `DIAGNOSTIC_PACKET_NOT_PROMOTED`로 남긴다.
6. 요청이 `qualified_actual`이라고 선언하면 응답에도 `prism.provider_qualification_evidence.v1` 자격 기록, `qualified_actual` 상태, `native_provider` 또는 `reviewed_actual` 출처, evidence ID와 같은 provider source digest가 있어야 한다. 요청 플래그만으로는 승격되지 않는다.
7. 위 자격 기록까지 있고 `qualified_actual`인 경우에만 함수 결과가 `QUALIFIED_PROVIDER_PACKET`가 된다. 이것은 물리 검증·빈도 결합·시설 QRA 완료를 뜻하지 않으며, 이후 coverage, frequency, validation, facility IR/F-N gate를 모두 통과해야 한다.
8. `state_snapshot`이 있으면 schema·설비 ID·canonical digest를 확인하고, 사고 전용 키가 포함된 snapshot은 거절한다. PRISM은 snapshot에서 누출구경·빈도·지속시간·종료를 역산하지 않는다.
9. `state_snapshot`이 있는 요청의 provider 응답은 `provider_state_snapshot_digest`를 echo해야 한다. digest가 없거나 요청과 다르면 provider가 동일 상태를 사용했다는 증거가 없으므로 strict packet을 거절한다.

## 현재 외부 `lh2dt` 상태

2026-10-11에 확인한 `lh2dt_models`의 `LayeredTank`, `DynamicHEMPipe`, `StrokeLimitedCommandedValve`, `VentStack`, `MappedPump`, `DynamicVaporizer`, `DynamicReliquefier`에는 정상/동적 계산 메서드는 있으나 이 사고 export 메서드는 없다. 따라서 일반 설비 매핑은 여전히 `STATE_ONLY_BOUND`, 사고 provider packet은 0건이다. 기존 합성 `scripts/export_lh2dt_accident_history.py` 결과는 구조 연결 진단으로 보존되며 이 계약의 `qualified_actual`로 승격하지 않는다.

이번 단계에서는 `scripts/export_lh2dt_prism_accident_packet.py`에 첫 실행형 provider adapter를 추가했다. 이 adapter는 외부 `HomogeneousTank`와 `Valve`를 명시적인 failed-opening 시나리오로 실행하고, 외부 모델이 반환한 시간·상태·질량 장부를 새 계약으로 변환한다.

## 외부 LayeredTank 상태 snapshot 실행 증거 (2026-10-17)

`scripts/export_lh2dt_layered_tank_prism_packet.py`는 이제 외부 `LayeredTankNetworkSimulator`가 초기 계산에서 반환한 압력·온도·재고·상을 `prism.equipment_state_snapshot.v1`로 만들고, 그 snapshot digest를 가진 사고 요청을 같은 provider adapter에 전달한다. provider 응답에도 digest를 echo하도록 해 요청·provider 상태가 동일한지 확인한다.

현재 외부 모델 smoke(`1e-6 m²` outlet, `0.05 s` step)는 0.1 s, 2 provider interval, provider mass residual `1.95e-18 kg`, strict packet mass residual `0 kg`, snapshot digest match `true`를 기록했다. 결과는 `results/20261017/layered_tank_state_snapshot_smoke3/`에 저장했다. 이 입력은 합성 탱크·대기 경계·재고 threshold이며 `synthetic_diagnostic`, `provider_packet_promoted=false`를 유지한다. 따라서 상태 전달이 실행됐다는 증거이지 실제 설비 적격 사고방출·빈도·시설 IR/F-N을 의미하지 않는다.

```powershell
.venv\Scripts\python.exe scripts/export_lh2dt_prism_accident_packet.py `
  --lh2dt-root "C:\path\to\lh2dt_models" `
  --output-dir results/20261011/lh2dt_prism_packet_smoke3
```

2026-10-11 smoke 결과는 0.2초·0.01 m 개구의 `prism.resolved_release.v1` packet을 생성했고 strict 질량 잔차는 0 kg이었다. 그러나 탱크·개구·대기·상태가 합성이고 site-calibrated 사고 이력이 아니므로 `DIAGNOSTIC_PACKET_NOT_PROMOTED`, 실제 적격 packet 0건으로 기록했다. 이 adapter는 연결 경계를 실행한 것이며 실제 시설 QRA 완료를 뜻하지 않는다.

액체 packet을 최종 피해까지 보낼 때는 provider 물성 기준과 풀 모델 기준도 확인한다. 외부 `lh2dt` packet은 현재 `ParaHydrogen` 기준을 사용하고, native `DynamicLH2PoolX`는 `Hydrogen` 기준만 제공하므로 `PoolBoundary`에 `fluid="Hydrogen"`, `fluid_translation="para_hydrogen_to_hydrogen"`, `translation_provenance`를 명시해야 한다. 이 변환은 질량을 바꾸지 않는 계산 경계이지만 교차 물성 검증이 끝난 것은 아니므로 결과에 `thermodynamic_adapters.pool`과 operator-limited 제한을 남긴다. 번역 필드가 없거나 provenance가 없으면 PRISM은 풀 계산을 시작하지 않는다.

첫 외부 packet의 전체 연결은 다음 명령으로 재현할 수 있다.

```powershell
.venv\Scripts\python.exe scripts/export_lh2dt_prism_accident_packet.py `
  --lh2dt-root "C:\path\to\lh2dt_models" `
  --output-dir results/20261011/lh2dt_prism_packet_liquid7 `
  --release-kind liquid
.venv\Scripts\python.exe scripts/validate_lh2dt_prism_packet_chain.py `
  --packet results/20261011/lh2dt_prism_packet_liquid7/resolved_release.json `
  --output-dir results/20261011/lh2dt_prism_chain_liquid8
```

이 smoke는 `HomogeneousTank+Valve` 합성 진단 packet을 DynamicLH2PoolX, SLABx-LH2, SLABx 분산, cloud, 점화, 화재/폭발 및 TNO 인명피해까지 통과시킨다. 결과는 `END_TO_END_DIAGNOSTIC_EXECUTED`이지만 packet 승격, 빈도 추론, 독립 물리검증, 시설 IR/F-N은 계속 거짓이다.

같은 합성 입력에 `--release-kind gas`를 주면 대기 출구 품질이 실제 증기인지 먼저 확인한다. 현재 입력은 포화 2상 상태이므로 기체 packet을 만들지 않고 즉시 실패하며, 이를 액체/2상 packet으로 계산하려면 `--release-kind liquid`를 사용한다.

## PRISM 측 LayeredTank 진단 adapter (2026-10-12)

외부 `lh2dt_models` 클래스 자체에 `export_accident_history()`가 추가된 것은 아니다. 대신 PRISM 저장소의 `scripts/export_lh2dt_layered_tank_prism_packet.py`가 `LayeredTankNetworkSimulator+CommandedValve`를 명시적인 합성 failed-opening 요청으로 호출하고, provider가 계산한 양수 재고 threshold 이력을 strict 계약으로 감싼다. 이 경계는 외부 클래스의 정상 snapshot이나 `simulate()` 결과를 사고 packet으로 자동 승격하는 일반 fallback이 아니다. 스크립트 안의 adapter가 사고 포트·개구·관찰시계·종료 소유권을 고정한 뒤 `_run_provider()`의 상태·유량·누적 질량·누적 엔탈피 장부를 검사한다.

이번 진단 명령은 다음과 같다.

```powershell
.venv\Scripts\python.exe scripts/export_lh2dt_layered_tank_prism_packet.py `
  --lh2dt-root "C:\path\to\lh2dt_models" `
  --output-dir results/20261012/layered_tank_prism_packet5 `
  --time-step-s 0.5 --target-release-kg 0.01 --full-open-area-m2 1e-6
.venv\Scripts\python.exe scripts/validate_lh2dt_prism_packet_chain.py `
  --packet results/20261012/layered_tank_prism_packet5/resolved_release.json `
  --output-dir results/20261012/layered_tank_prism_chain5
```

실행 결과는 8.0 s, 16개 provider interval, 질량 잔차 `1.73e-18 kg`, 누적 에너지 잔차 `0 J`였다. packet은 `fluid=Hydrogen`, `phase_basis=liquid`, `termination_basis=inventory_depletion`을 명시하고 `provider_packet_promoted=false`를 유지한다. 이어지는 chain은 `DynamicLH2PoolX → SLABx-LH2/SLABx → cloud → ignition → fire/explosion → TNO damage`까지 `END_TO_END_DIAGNOSTIC_EXECUTED`로 실행되었다. 작은 합성 packet이 native pool의 wet-cell 조건을 갖도록 `radius_m=0.005`의 **선언된 sensitivity footprint**를 사용했으며, 실제 설비 바닥 면적을 추정하거나 누출 면적을 보정한 값이 아니다.

이 adapter가 제공하지 않는 flash gas, airborne liquid, 현장 개구·차단 신뢰도·실제 재고 입력은 미계산으로 남는다. 따라서 이 결과는 provider 구조와 PRISM chain의 연결 증거이지 `qualified_actual`, 빈도 추론, 시설 IR/F-N 또는 독립 물리검증 결과가 아니다.

## PRISM 측 DynamicHEMPipe 진단 adapter (2026-10-12)

`scripts/export_lh2dt_dynamic_pipe_prism_packet.py`는 `lh2dt.DynamicHEMPipe`의 유한체적 질량·내부에너지·벽 온도 상태를 명시적인 full-bore 대기 출구 사고로 실행한다. provider가 계산한 출구 유량과 pipe의 실제 상태 엔탈피를 대기압 `P-H` 상태로 변환하고, 기체·지면 액체 분할과 누적 엔탈피 장부를 `equipment_release_adapter.py`에 넘긴다. duration `0.001 s`, `1e-4 s` step의 10개 구간에서 질량 잔차 `0 kg`, 에너지 잔차 `-5.42e-20 J`를 확인했다.

이 packet은 `synthetic_diagnostic_horizon`으로 끝나며 pipe 재고를 전량 소진했다고 주장하지 않는다. `validate_lh2dt_prism_packet_chain.py`는 declared sensitivity pool radius `0.0001 m`를 사용해 같은 packet을 DynamicLH2PoolX, SLABx-LH2/SLABx, cloud, 점화, 화재·폭발, TNO 피해까지 실행했다. 작은 packet에서 이 footprint는 wet-cell 수치 조건을 위한 명시값이며 실제 배수면적·누출면적 추정이 아니다. 결과는 여전히 `provider_packet_promoted=false`, 빈도·시설 IR/F-N·독립 물리검증 보류다.

## PRISM 측 VentStack 진단 adapter (2026-10-12)

`scripts/export_lh2dt_vent_stack_prism_packet.py`는 외부 `VentStack.evaluate()`의 정상 two-port 함수를 사고 packet으로 재사용하지 않고, 명시적인 사고 포트·개구·0.5 s diagnostic horizon에서 별도 provider adapter로 호출한다. 저 Mach atmospheric gas plane을 만들기 위해 기본 upstream은 `102000 Pa`, `40 K`, stack bore는 `0.01 m`이며 provider의 유량·출구 상태를 10개 왼쪽 유지 구간과 `ResolvedGasRelease` 장부로 보존한다. 기본 packet 질량 잔차는 `0 kg`, 정적 엔탈피 잔차는 `0 J`다.

## PRISM 측 DynamicVaporizer·DynamicReliquefier 진단 adapter (2026-10-12)

`scripts/export_lh2dt_dynamic_vaporizer_prism_packet.py`는 외부 `DynamicVaporizer` 또는 `DynamicReliquefier`의 유한체적 상태를 직접 초기화하고, 각 provider 구간에서 `thermo(state)`와 대기 밸브 `Valve.evaluate()`를 호출한 뒤 `step()`으로 다음 질량·내부에너지·벽 온도를 계산한다. 즉 기화기·재액화기의 상태와 에너지 경계가 packet의 시간 이력에 들어가며, PRISM은 유량·엔탈피를 다시 계산하거나 정상 snapshot을 사고로 바꾸지 않는다.

기본 smoke는 두 모드 모두 0.5 s를 0.05 s 간격 10개 구간으로 실행했다. `DynamicVaporizer`와 `DynamicReliquefier`의 strict gas packet은 각각 질량 잔차 `0 kg`, 정적 엔탈피 잔차 약 `1.78e-15 J`를 보존했고, `validate_lh2dt_prism_packet_chain.py`가 두 packet을 기체 벡터 전이→SLABx 분산→구름→점화→화재/폭발→TNO 피해까지 실행했다. 결과는 `results/20261012/dynamic_vaporizer_prism_packet_default_smoke3/`, `results/20261012/dynamic_reliquefier_prism_packet_default_smoke3/`와 각 chain 기록에 저장했다. 대기 밸브는 `StrokeLimitedCommandedValve`로 구간마다 실제 개방도를 전진시켜, 즉시 완전 개방으로 가정하지 않는다.

이 adapter의 사고 경계는 명시한 대기 밸브 개구와 합성 진단시계다. 실제 열교환기 내부 고장 위치, 수소측 재고, PSV/차단 동작, 현장 개구와 빈도, 독립 실험 검증은 공급하지 않으므로 상태는 `EXECUTED_OPERATOR_LIMITED`이고 `provider_packet_promoted=false`다. 따라서 이 결과는 일반 LH2 설비 결합의 구조·장부·처리시간을 확인하는 진단이며 시설 연간 IR/F-N 산출로 승격되지 않는다.

## PRISM 측 MappedPump 진단 adapter (2026-10-12)

`scripts/export_lh2dt_mapped_pump_prism_packet.py`는 `lh2dt.MappedPump`를 명시한 액체 inlet, downstream pressure, H-Q-N map으로 평가하고, 펌프 출구의 `P-h` 상태를 별도 atmospheric `Valve`에 전달한다. 펌프가 계산한 질량유량과 밸브가 계산한 대기 방출유량의 상대오차가 2%를 넘으면 strict packet을 만들지 않는다. 따라서 펌프의 압력 상승과 출구 엔탈피를 다시 추정하지 않고, 두 hydraulic boundary가 실제로 맞는 경우만 `ResolvedLiquidRelease`에 기록한다.

기본 smoke는 0.2 s를 0.02 s 간격 10개 구간으로 실행했다. packet 질량 잔차는 `0 kg`, 정적 엔탈피 잔차는 약 `-1.39e-17 J`였고, 액체 출구는 DynamicLH2PoolX→SLABx→점화→피해 chain을 통과했다. `MappedPump`는 재고를 소유하지 않으므로 종료는 `synthetic_diagnostic_horizon`이고 `available_mass_kg`는 선언된 feed-through reserve다. 실제 pump-seal/shaft failure, 탱크 재고, 차단 정책, 현장 빈도와 물리 검증이 없으므로 이 adapter도 `EXECUTED_OPERATOR_LIMITED`이며 `provider_packet_promoted=false`다.

steady 결과를 horizon 동안 반복한 것은 탱크 재고·PSV setpoint·현장 vent duty를 의미하지 않는다. `validate_lh2dt_prism_packet_chain.py`는 이 기체 packet을 gas vector transition, SLABx dispersion, cloud, ignition, fire/explosion 및 TNO damage까지 실행하지만 실제 빈도·facility IR/F-N·독립 검증은 계속 보류한다. upstream 압력을 크게 올려 underexpanded/high-Mach plane이 되면 PRISM low-Mach gate가 fail-closed로 거절한다.

## provider 구현 예

외부 모델이 다음 형태를 구현하면 PRISM 연결 함수를 호출할 수 있다.

```python
class MyLayeredTankProvider:
    def export_accident_history(self, request):
        # request의 명시적 사고 포트·개구·시계로 외부 solver를 실행한다.
        # 정상 snapshot을 재사용하거나 duration을 늘려서는 안 된다.
        return {
            "provider_export_schema": "prism.external_accident_history.v1",
            "data": self._run_explicit_accident(request),
        }

result = export_equipment_liquid_accident_history(provider, request)
release = result.release  # strict ResolvedLiquidRelease
```

provider는 실제 차단 명령, 검출 지연, 재고/에너지 장부, 종료시각을 자기 모델에서 계산해야 한다. PRISM은 그 이력을 SLABx-LH2/SLABx, 점화, 피해, 문헌 `FrequencyPlan`과 결합할 뿐, 누출률이나 사고 빈도를 역산하지 않는다.

## 확인 명령

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_equipment_accident_export.py
.venv\Scripts\python.exe scripts/audit_equipment_model_binding.py `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --binding examples/generic_lh2_model_binding.json `
  --output results/20261011/equipment_accident_export_interface_audit.json
```

현재 portable test suite는 새 계약·물성 기준 테스트를 포함해 371개가 통과한다. 실제 `lh2dt` 사고 export가 추가되기 전까지 IJHE 완료 감사의 설비 모델 결합, 실제 provider packet, 사고 범위, 시설 IR/F-N gate는 계속 차단된다.
