# PRISM Equipment and Digital-Twin Interface Guide (v0.6.3)

This guide defines the boundary between an equipment digital twin, HAZOP logic, a release provider, PRISM, and the SLABx-LH2 consequence model. It is intended for an integration engineer building a monitoring or simulation connector for a generic outdoor LH2 facility.

## 1. Responsibility boundary

The equipment model owns thermodynamics, hydraulics, inventory, isolation behavior, and the accident release history. PRISM owns HAZOP scenario selection, literature frequency binding, consequence orchestration, ignition/weather/population branches, and risk ledgers.

```mermaid
flowchart LR
  T[Equipment digital twin] -->|state frame + operating mode| H[HAZOP selector]
  H -->|hazop_scenario_id| R[Equipment provider resolver]
  R -->|prism.resolved_release.v1| P[PRISM consequence pipeline]
  F[Literature FrequencyPlan] -->|event ID + annual frequency| P
  W[Weather + ignition + population + protection] --> P
  P --> S[Facility ledger + IR/F-N + response view]
```

PRISM does not infer a leak size from pressure and temperature alone, infer an accident history from normal flow, learn an annual frequency from alarm counts, extend a provider interval, or replace a missing accident with a similar-looking case.

## 2. Recommended call sequence

1. The digital twin evaluates the current or simulated equipment state.
2. The connector writes operating mode, values, timestamp, signal quality, and provenance to `prism.hazop_state_frame.v1`.
3. The HAZOP table selects a deviation row and stable `hazop_scenario_id`.
4. The resolver receives the scenario and state snapshot.
5. The provider calculates and returns the accident release history, isolation feedback, inventory ledger, and source digest.
6. An adapter validates the provider output as `prism.resolved_release.v1`.
7. PRISM exact-matches the event to the literature frequency plan and runs SLABx-LH2 or the declared consequence backend.
8. The result ledger returns status, latency, cache/fresh mode, termination, inventory, frequency provenance, and evidence limitations.

## 3. State-frame contract

The state frame contains state only. It may include a measured or predicted value, its unit, signal quality, timestamp, source provenance, component ID, facility ID, and operating mode.

```json
{
  "schema_version": "prism.hazop_state_frame.v1",
  "facility_id": "terminal-01",
  "component_id": "storage-tank-01",
  "operating_mode": "receiving",
  "captured_at_s": 172.0,
  "source_provenance": "historian_measured",
  "values": {
    "tank_pressure": {
      "quantity": "pressure",
      "value_si": 650000.0,
      "sensor_location": "storage-tank-01.vapour",
      "quality": "valid"
    },
    "transfer_flow": {
      "quantity": "mass_flow",
      "value_si": 0.18,
      "sensor_location": "transfer-line-01",
      "quality": "valid"
    }
  }
}
```

Do not place `resolved_release`, opening diameter, annual frequency, release duration, or termination basis in the state frame. Those fields belong to the scenario/provider and frequency contracts.

## 4. HAZOP binding

Compare the state value and operating mode with the HAZOP row. Preserve the selected row ID, operating mode, deviation, and safeguard context downstream.

```json
{
  "id": "TK01-receiving-high-pressure",
  "component_id": "storage-tank-01",
  "operating_modes": ["receiving"],
  "variable_tag": "tank_pressure",
  "quantity": "pressure",
  "trigger": "at_or_above",
  "threshold_high_si": 600000.0,
  "scenario_family": "vessel_hole",
  "release_mode": "hole",
  "safeguards": ["PSV", "ESD"]
}
```

HAZOP selection is a qualitative decision. It does not create or update an annual initiating frequency.

## 5. Provider release contract

The provider response must identify the event, component, accident port, source digest, release intervals, inventory, and termination evidence.

```json
{
  "provider_export_schema": "prism.external_accident_history.v1",
  "data": {
    "event_kind": "accidental_leak",
    "duration_s": 0.2,
    "available_mass_kg": 71.76,
    "cumulative_mass_out_kg": 0.003,
    "termination_basis": "reviewed_isolation_success",
    "termination_provenance": "provider isolation feedback",
    "steps": [
      {
        "time_s": 0.0,
        "mass_flow_kg_s": 0.03,
        "pressure_pa_abs": 101325.0,
        "specific_enthalpy_j_kg": 450000.0,
        "temperature_k": 20.7,
        "density_kg_m3": 1.28,
        "effective_area_m2": 0.0001,
        "velocity_m_s": 234.0,
        "area_provenance": "provider resolved outlet",
        "velocity_origin": "provider_resolved"
      }
    ]
  }
}
```

The adapter checks time ordering, mass balance, area, density, velocity, units, source digest, and event identity. It does not extend the provider duration or correct a residual.

### 5.1 Port state and upstream state

When the equipment model can provide upstream pressure/enthalpy and phase, preserve them in every matching interval.

```json
{
  "component_id": "storage-tank-01",
  "port_id": "tank-accident-out",
  "time_s": 0.0,
  "fluid": "ParaHydrogen",
  "phase": "two_phase",
  "pressure_pa_abs": 650000.0,
  "temperature_k": 20.4,
  "density_kg_m3": 34.0,
  "specific_enthalpy_j_kg": 120000.0,
  "mass_flow_kg_s": 0.03,
  "position_enu_m": [0.0, 0.0, 5.0],
  "direction_enu": [1.0, 0.0, 0.0],
  "provenance": "lh2dt tank port state",
  "source_digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

Optional `provider_source_state` can carry source and throat pressure, temperature, density, enthalpy, entropy, mass flux, choking state, and provenance. The adapter rejects a component, port, time, fluid, phase, or mass-flow mismatch.

### 5.2 Termination and inventory

Use the provider-calculated termination basis:

- `reviewed_isolation_success`: command and feedback closed;
- `inventory_depletion`: provider-calculated inventory end;
- `model_pressure_equalization`: model natural end;
- `two_sided_rupture`: both rupture ends closed together;
- `emergency_relief_discharge`: relief or PSV path;
- `synthetic_diagnostic_horizon`: diagnostic window, not a physical end.

Include initial mass, cumulative outflow, final mass, residual, isolation time, and observation horizon in `provider_meta` whenever available. An unresolved residual must remain visible in the result.

## 6. Python resolver example

```python
from lh2_tno.equipment_release_adapter import (
    build_resolved_gas_release_from_provider_response,
)
from lh2_tno.service import request_from_equipment_resolver


def resolver(template, state_frame):
    provider_response = twin.export_accident_history(
        component_id=template.component_id,
        operating_mode=state_frame["operating_mode"],
        state=state_frame,
    )
    release = build_resolved_gas_release_from_provider_response(
        provider_response,
        component_id=template.component_id,
        port_id="tank-accident-out",
        event_id="terminal-01/tank-accident-out/area-0.01pct",
        provider_source_digest=provider_response["provider_source_digest"],
        upstream_service_provenance="lh2dt provider",
        provider_boundary_reference="tank outlet boundary",
        input_origin="model_prediction",
        position_enu_m=[0.0, 0.0, 5.0],
        direction_enu=[1.0, 0.0, 0.0],
        ambient_pressure_pa_abs=101325.0,
        ambient_temperature_k=288.15,
        failure_opening_diameter_m=0.0127,
    )
    return template.model_copy(update={
        "source_input": None,
        "resolved_release": release,
        "release_termination": {
            "basis": release.termination_basis,
            "time_s": release.duration_s,
            "provenance": release.termination_provenance,
        },
    })


request = request_from_equipment_resolver(
    consequence_template,
    state_frame,
    resolver,
    pressure_tag="PT1105A",
    temperature_tag="TT1106",
)
```

The resolver should never write `annual_frequency_per_year`. Frequency binding belongs to the campaign and `FrequencyPlan` layer.

## 7. Frequency binding

Bind literature frequency using:

```text
event_id + component_id + port_id + scenario_family + release_branch_id
```

Record source citation, population or length basis, failure profile, units, applicability, uncertainty, and exclusions. Keep sensor anomaly counts and normal flow outside the frequency plan unless a separate validated statistical study explicitly defines them as a frequency source.

## 8. Result contract and user interface

```json
{
  "status": "EXECUTED_OPERATOR_LIMITED",
  "operating_mode": "receiving",
  "hazop_scenario_id": "TK01-receiving-high-pressure",
  "event_id": "terminal-01/tank-accident-out/area-0.01pct",
  "provider_release_resolved": true,
  "termination": {"basis": "reviewed_isolation_success", "time_s": 0.2},
  "inventory": {"status": "MASS_BALANCE_CLOSED", "remaining_mass_kg": 71.75},
  "frequency_inference_performed": false,
  "facility_qra_claim": false
}
```

The monitoring screen should show operating mode, HAZOP deviation, provider status, source digest, termination, inventory, frequency citation, consequence backend, cache/fresh mode, latency, and required response. `facility_qra_claim=false` and `frequency_inference_performed=false` are safety guards, not errors.

## 9. Acceptance tests

After connecting a provider, automatically check:

- state frame contains no accident-only fields;
- operating mode matches the HAZOP row;
- scenario ID is retained in event, case, and risk atom;
- packet schema is `prism.resolved_release.v1`;
- interval time, mass, and energy ledgers close;
- port state agrees with interval ID, phase, and flow;
- termination and isolation evidence exist;
- source and result digests are recorded;
- frequency binding is exact-match;
- missing providers are not silently substituted;
- SLABx-LH2 and IR/F-N are labeled conditional.

```powershell
python -m pytest -q tests/test_equipment_release_adapter.py tests/test_equipment_boundary.py tests/test_consequence_service.py
python -m pytest -q
```

## 10. Integration limits

This is a generic LH2 interface and is not tied to one inspection center. Normal operating data must not be promoted automatically to accident evidence. A facility-wide IR/F-N claim requires qualified packets for the declared cases, complete termination and inventory ledgers, independent physical validation, and facility population/protection inputs. The current audit remains fail-closed while those evidence gates are incomplete.
