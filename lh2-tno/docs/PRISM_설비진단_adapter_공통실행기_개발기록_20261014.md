# PRISM 설비 진단 adapter 공통 실행기

## 이번 개발의 목적

기존에는 액화수소 설비별 진단 adapter가 각자 `scripts/export_lh2dt_*_prism_packet.py` 파일에 있었고, 결합 목록에는 파일 이름만 적혀 있었다. 그래서 “어떤 설비가 어떤 adapter를 쓰는가”는 확인할 수 있었지만, 디지털 트윈 실행기가 공통 방식으로 adapter를 찾고 호출할 수 있는지는 별도로 보장되지 않았다.

이번 단계에서 `src/lh2_tno/diagnostic_adapter_runner.py`를 추가했다. 이 모듈은 설비 종류를 adapter 모듈·클래스에 연결하고, host가 만든 provider 인스턴스를 명시적으로 등록한 뒤, 모든 호출을 `export_accident_history(request)` 한 가지 계약으로 보낸다.

## 실행 계약

```python
from lh2_tno.diagnostic_adapter_runner import DiagnosticAdapterRunner

runner = DiagnosticAdapterRunner.from_binding_catalog(
    "examples/generic_lh2_model_binding.json"
)

# 외부 lh2dt 모델과 진단 조건을 host가 직접 준비한다.
provider = make_layered_tank_provider(...)
runner.register_provider("storage_tank", provider)

# 또는 host가 모든 생성자를 명시적으로 채운다.
runner.register_provider_from_config(
    "storage_tank", {"lh2dt_root": root, "time_step_s": 0.05, ...}
)

# request는 개구·포트·시계·경계·증거 상태를 포함하는 명시적 요청이다.
execution = runner.execute(
    "storage_tank", request, release_kind="liquid"
)
consequence_request = runner.to_consequence_request(
    execution, consequence_defaults
)
print(execution.audit_record())
```

`register_provider()`는 `export_accident_history(request)`가 없는 정상상태 모델을 거부한다. `execute()`는 gas, liquid, emergency-relief, inventory gas/liquid 경로를 기존 strict PRISM export 함수에 위임한다. 따라서 adapter가 반환하는 시간별 유량, 종료근거, 누적 질량·엔탈피, 액체·기체 분할 검사는 기존 `equipment_accident_export.py`와 `equipment_release_adapter.py`에서 계속 수행된다. `to_consequence_request()`는 이 strict release를 weather·점화·공간영역·평가시계·종료근거가 들어 있는 consequence context에 붙인다. 빈도는 이 단계에서 추가하지 않고 캠페인 경계에서만 추가한다.

provider 생성자를 자동으로 호출하지 않는 이유는 설비마다 필요한 탱크 재고, 배관 크기, 밸브 상태, 기상, 수치 시간 간격이 다르기 때문이다. 실행기가 이 값을 기본값으로 만들어 버리면 정상상태 snapshot이나 임의의 누출을 사고 packet으로 오인할 수 있다. host는 현재 센서·공정 모델의 상태에서 사고 시나리오를 선택하고, 외부 모델이 계산한 provider 요청과 인스턴스를 넘겨야 한다.

`register_provider_from_config()`는 host가 제공한 생성자 인자만 전달한다. PRISM은 manifest 압력·온도나 센서값을 생성자 인자로 채우지 않으며, 인자가 빠지거나 잘못되면 사고 계산 전에 실패한다. 이 경로는 실제 설비 provider를 연결하기 위한 준비가 완료되었다는 뜻이지, 현재 catalog의 synthetic adapter를 qualified provider로 바꾸는 기능은 아니다.

### 물리 설비 인스턴스별 등록

시설에는 같은 종류의 설비가 여러 개 있을 수 있으므로 runner는 이제 `component_kind`와 별도로 host가 정한 `instance_id`를 보존한다.

```python
runner.register_provider_instance_from_config(
    "storage-tank-01",
    "storage_tank",
    {"lh2dt_root": root, "time_step_s": 0.05, ...},
)
runner.register_provider_instance_from_config(
    "storage-tank-02",
    "storage_tank",
    {"lh2dt_root": root, "time_step_s": 0.05, ...},
)
execution = runner.execute(
    "storage_tank", request, provider_instance_id="storage-tank-02"
)
```

각 ID는 하나의 provider 객체에만 연결되고, 다른 설비 종류로 재사용하거나 중복 등록할 수 없다. `DiagnosticAdapterExecution.audit_record()`에도 `provider_instance_id`를 남기므로 시설 ledger가 탱크·배관·밸브별 packet을 섞지 않는다. 이 기능은 다중 설비 연결 계약을 완성한 것이며, 실제 각 설비의 사고 이력·종료 장부·qualified evidence를 공급했다는 뜻은 아니다.

## 현재 확인 결과

```powershell
python scripts/audit_diagnostic_adapter_registry.py `
  --binding examples/generic_lh2_model_binding.json `
  --output results/20261014/diagnostic_adapter_registry_audit_live.json
```

결과는 다음과 같다.

| 항목 | 결과 |
|---|---:|
| catalog adapter | 7개 |
| 클래스 해석 성공 | 7개 |
| 공통 `export_accident_history` 확인 | 7개 |
| host provider 인스턴스 등록 | 0개 |
| qualified provider packet | 0개 |
| 빈도 추정 | 수행 안 함 |
| 시설 QRA 승격 | 수행 안 함 |

저장탱크, 배관, 밸브, 벤트, 펌프, 기화기, 재액화기의 adapter 클래스는 모두 해석되지만, 현재 catalog의 증거 상태는 `synthetic_diagnostic`이다. 따라서 이 감사는 **호출 경로가 연결되었다는 뜻**이며 실제 현장 사고빈도, 실제 설비 재고, qualified accident history, 시설 IR/F-N을 만들었다는 뜻이 아니다.

## 실시간 사용 위치

`RealtimeConsequenceMonitor`는 센서 frame을 정상 공정상태로 정규화하고, `request_from_equipment_resolver()`가 외부 provider가 만든 명시적 `ConsequenceRequest`를 받아 결과를 계산한다. 공통 adapter runner는 이 resolver가 provider packet을 만들기 전의 설비별 실행 계약이다.

`DiagnosticAdapterRunner.make_resolver()`는 이 접점을 반복해서 작성하지 않도록 한다. host는 상태 snapshot을 받아 사고 export request를 만드는 callback과 consequence context를 만드는 callback을 각각 제공한다. 반환된 resolver를 `RealtimeConsequenceMonitor.update_from_frame(..., release_resolver=resolver)`에 넘기면, 상태 정규화 → 설비 provider 방출 → strict packet → consequence 계산 순서가 이어진다. 두 callback에서 빈도·구멍 크기·지속시간을 추정하지 않으며, provider request와 context가 불완전하면 즉시 오류로 남긴다.

실시간 순서는 다음과 같다.

1. 센서 frame을 압력·온도·액면·유량 등의 상태 snapshot으로 정규화한다.
2. 설비 종류와 사고 시나리오를 host가 선택한다. 정상상태 값만으로 PRISM이 구멍 크기나 빈도를 추정하지 않는다.
3. host가 해당 설비의 provider 인스턴스와 명시적 accident export request를 준비한다.
4. `DiagnosticAdapterRunner.execute()`가 공통 `export_accident_history` 경계와 strict packet 검사를 실행한다.
5. 검증된 진단 packet만 `ConsequenceService`와 SLABx-LH2/피해 계산에 전달한다.
6. 증거 상태가 `qualified_actual`이 아니면 결과는 `DIAGNOSTIC_PACKET_NOT_PROMOTED`로 남고 시설 전체 IR/F-N은 보류된다.

이 구조로 설비별 adapter는 하나의 TNO-LH2/PRISM 모드 안에서 선택적으로 호출되며, 별도 모듈이 빈도나 사고 해석을 몰래 생성하지 않는다.

## 다음 승격 조건

1. 외부 `lh2dt` 설비 모델이 각 사고 포트별 실제 방출 이력과 종료·질량 장부를 직접 export해야 한다.
2. 현장 또는 검증된 실험 자료로 packet의 물리량과 종료 거동을 독립 검증해야 한다.
3. 실제 개구·설비 ID와 문헌 `FrequencyPlan`이 exact-match되어야 한다.
4. 주요 사고 범위의 모든 provider packet이 채워지고 미계산 항목이 0이 되어야 한다.
5. 그 뒤에야 qualified facility IR/F-N과 불확실성 구간을 계산한다.

현재 공통 실행기 감사 파일은 `results/20261014/diagnostic_adapter_registry_audit_live.json`이다. 인스턴스 분리 계약을 포함한 portable suite는 386개로 통과했으며, 전체 IJHE 완료 감사의 qualified provider gate는 계속 차단 상태다.

재현 가능한 축약 결과는 `examples/diagnostic_adapter_registry_audit.json`에도 보존했다.

## 외부 LayeredTank 인스턴스 smoke

공통 registry 감사만으로는 provider 객체가 실제로 만들어지고 호출되는지 확인할 수 없으므로, 외부 `lh2dt` 소스 루트를 명시적으로 넘기는 smoke 명령을 추가했다.

```powershell
python scripts/run_diagnostic_adapter_runner_smoke.py `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\액화수소 저장탱크_밴트 시스템\06_액화수소_디지털트윈_물리모델" `
  --output results/20261014/diagnostic_adapter_runner_layered_tank_smoke.json
```

이 명령은 `LayeredTankAccidentProvider`를 명시적 생성자 설정으로 등록하고, liquid accident request를 `export_accident_history()`에 전달한다. 실행 결과는 다음과 같다.

| 항목 | 결과 |
|---|---:|
| provider 인스턴스 | 1 |
| strict liquid packet | 실행됨 |
| 방출 시계 | 0.1 s, 양수 재고 임계값 종료 |
| 질량 잔차 | 0 kg |
| 엔탈피 잔차 | 약 -4.44×10⁻¹⁶ J |
| 신규 physics 호출시간 | 약 1556 ms |
| evidence status | `synthetic_diagnostic` |
| qualified packet | 0 |
| 빈도·시설 QRA | 계산하지 않음 |

이 결과는 외부 모델과 공통 실행기 사이의 호출·strict packet 경계가 실제로 통과했다는 뜻이다. 개구, 저장탱크 형상, 대기 경계, 임계값은 진단용 합성 설정이며 현장 사고 이력이나 검증된 방출빈도로 승격하지 않는다. 액체 flash·비산 액적·현장 차단 신뢰도·시설 IR/F-N도 이 smoke에 포함되지 않는다. 원본 결과는 `examples/diagnostic_adapter_runner_layered_tank_smoke.json`에 고정하고, 실행 스크립트는 `scripts/run_diagnostic_adapter_runner_smoke.py`에 둔다.

### worklist exact-match 실행

다중 설비 registry가 실제 worklist 항목을 보존하는지도 저장탱크 `AREA_0.01%` 항목으로 확인했다.

```powershell
python scripts/run_diagnostic_adapter_runner_smoke.py `
  --lh2dt-root "<외부 lh2dt 루트>" `
  --provider-worklist results/20261014/generic_lh2_provider_release_worklist_diagnostic_adapter.json `
  --component-id storage-tank-01 `
  --worklist-event-id "generic-lh2-full-scope-frequency-example/storage-shell/AREA_0.01%" `
  --output results/20261014/diagnostic_adapter_runner_worklist_storage_001.json
```

실행 결과는 `provider_instance_id=storage-tank-01`, event/component/port/opening 네 항목 exact-match `true`, 방출시간 `0.05 s`, 질량·엔탈피 잔차 `0`이었다. 같은 strict release를 명시적 consequence context에 붙이고 synthetic facility·receptor·weather를 사용한 최종 consequence chain까지 실행해 `END_TO_END_DIAGNOSTIC_EXECUTED`, chain 약 `10.32 s`, 최종 질량 잔차 약 `-9.92×10⁻¹⁸ kg`를 확인했다. `consequence_context_frequency_bound=false`, `worklist_frequency_bound=false`, `qualified_provider_packet_count=0`을 유지하므로 문헌 빈도를 자동 부여하지 않는다. pool 반경 `0.005 m`는 작은 합성 packet의 선언 sensitivity 값이다. 이 결과는 [worklist 실행 예시](../examples/diagnostic_adapter_runner_worklist_storage_001.json)와 [chain 기록](../results/20261014/diagnostic_adapter_runner_worklist_storage_001_consequence_chain)에 보존했다.
