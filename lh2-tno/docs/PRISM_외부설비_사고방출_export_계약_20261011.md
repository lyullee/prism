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

## provider가 반환해야 하는 것

provider 응답의 최상위에는 다음 schema가 있어야 한다.

```json
{
  "provider_export_schema": "prism.external_accident_history.v1",
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
6. `qualified_actual`인 경우에만 함수 결과가 `QUALIFIED_PROVIDER_PACKET`가 된다. 이것은 물리 검증·빈도 결합·시설 QRA 완료를 뜻하지 않으며, 이후 coverage, frequency, validation, facility IR/F-N gate를 모두 통과해야 한다.

## 현재 외부 `lh2dt` 상태

2026-10-11에 확인한 `lh2dt_models`의 `LayeredTank`, `DynamicHEMPipe`, `StrokeLimitedCommandedValve`, `VentStack`, `MappedPump`, `DynamicVaporizer`, `DynamicReliquefier`에는 정상/동적 계산 메서드는 있으나 이 사고 export 메서드는 없다. 따라서 일반 설비 매핑은 여전히 `STATE_ONLY_BOUND`, 사고 provider packet은 0건이다. 기존 합성 `scripts/export_lh2dt_accident_history.py` 결과는 구조 연결 진단으로 보존되며 이 계약의 `qualified_actual`로 승격하지 않는다.

이번 단계에서는 `scripts/export_lh2dt_prism_accident_packet.py`에 첫 실행형 provider adapter를 추가했다. 이 adapter는 외부 `HomogeneousTank`와 `Valve`를 명시적인 failed-opening 시나리오로 실행하고, 외부 모델이 반환한 시간·상태·질량 장부를 새 계약으로 변환한다.

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

현재 portable test suite는 새 계약 테스트를 포함해 362개가 통과한다. 실제 `lh2dt` 사고 export가 추가되기 전까지 IJHE 완료 감사의 설비 모델 결합, 실제 provider packet, 사고 범위, 시설 IR/F-N gate는 계속 차단된다.
