# PRISM User Manual (v0.6.4)

PRISM (Process Risk Integration and Scenario Modeling) connects equipment state, HAZOP selection, literature-based initiating frequency, release history, consequence models, and facility risk ledgers. This manual is written for an engineer who wants to run the package and understand each result.

## 1. What PRISM does

PRISM has two practical paths:

1. **Standard mode** for generic process-risk contracts using the bundled, project-authored PRISM QRA implementation.
2. **LH2 mode** for outdoor liquid-hydrogen scenarios. LH2 mode accepts an equipment state frame, selects a HAZOP scenario, consumes a qualified provider release history, and connects the release to the SLABx-LH2 consequence boundary when that provider is available.

The package is a research diagnostic framework. It does not turn a few pressure or temperature readings into a leak size, an accident frequency, or a qualified facility QRA. A provider must supply the accident release history and its termination evidence. A separate `FrequencyPlan` supplies the literature frequency.

## 2. Installation

Python 3.12 or newer is required.

```powershell
python -m pip install "prism-risk[full]==0.6.4"
prism --describe-modes
lh2-tno --help
```

For a source checkout:

```powershell
cd lh2-tno
python -m pip install -e ".[full,test]"
python -m pytest -q
```

The `0.6.4` wheel includes the project-authored PRISM QRA runtime. Its `full`
extra installs public PyPI versions `slabx==1.0.7` and `slabx-lh2==0.1.5`.
Historical source-pinned calculations retain their original backend digests.

The v0.6.3 release baseline was **1214 passed, 1 warning**. The current checkout validation is **1,577 passed, 1 warning**. The warning is reported separately from a failing contract.

## 3. First five minutes

Run these commands from the repository root:

```powershell
prism --describe-modes
lh2-tno --equipment-manifest examples/equipment_manifest.json --output build/manifest_check.json
python -m pytest -q
```

The manifest command checks the equipment boundary. It does not claim that every equipment item has a validated accident provider.

To inspect a known LH2 diagnostic campaign, start with the campaign examples under `examples/` and the reproducible commands referenced by the current audit in `docs/PRISM_IJHE_latest_audit_20261115.md`.

## 4. The calculation in plain language

PRISM follows this sequence:

```text
equipment state + operating mode
        -> HAZOP deviation and scenario ID
        -> equipment provider release history
        -> strict release contract validation
        -> literature frequency binding
        -> SLABx-LH2 / consequence calculation
        -> ignition, weather, population and protection branches
        -> conditional risk ledger and response view
```

The current-state path can use a cached or already-computed provider result and is intended for low-latency monitoring. The prediction path receives a simulated future state and runs again when the simulation reaches a risk condition. The two paths must retain different provenance: `input_origin="measured_state"` and `input_origin="model_prediction"`.

## 5. Operating modes and HAZOP

The operating mode is part of the input, for example `receiving`, `supply`, or `standby`. The HAZOP table compares the measured or simulated value with the row threshold and returns a stable `hazop_scenario_id`.

Example HAZOP row:

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

The scenario ID is carried into the event, case, risk atom, and result ledger. HAZOP selection is qualitative screening; it does not generate an annual accident frequency.

## 6. Equipment manifest

The manifest identifies equipment and the accident ports that a provider can resolve. A minimal entry contains an equipment ID, type, operating modes, and a release-port reference.

```json
{
  "facility_id": "terminal-01",
  "equipment": [
    {
      "component_id": "storage-tank-01",
      "equipment_type": "layered_tank",
      "operating_modes": ["receiving", "supply", "standby"],
      "accident_ports": ["tank-accident-out"]
    }
  ]
}
```

Use the manifest check before connecting live data. It catches duplicate IDs and incompatible equipment boundaries early.

## 7. FrequencyPlan

Frequency is connected separately from telemetry and provider physics. The normal key is:

```text
event_id + component_id + port_id + scenario_family + release_branch_id
```

A frequency plan should record the source, population or length basis, hole-size or failure profile, units, uncertainty range, applicability, and exclusion reason. A sensor alarm count, normal flow rate, or number of data-quality flags must never be silently substituted for an initiating frequency.

The calculation may return `frequency_inference_performed=false`. That is a protective result: PRISM is telling the operator that it used an explicit literature binding and did not learn a new frequency from the sensor stream.

## 8. Provider release history

The equipment model owns the pressure, temperature, phase, inventory, isolation, and release-time history. PRISM accepts it only through the validated `prism.resolved_release.v1` boundary.

Each interval should include time, mass flow, pressure, temperature, density, effective area, velocity, and provenance. The provider must also state why the release stopped, for example:

- `reviewed_isolation_success`
- `inventory_depletion`
- `model_pressure_equalization`
- `two_sided_rupture`
- `emergency_relief_discharge`
- `synthetic_diagnostic_horizon`

The last value is a diagnostic horizon, not evidence that a physical leak ended. PRISM does not extend the last provider interval or repair a mass-balance residual.

## 9. SLABx-LH2 and consequence results

SLABx-LH2 is used at the dispersion boundary when a compatible provider result is present. The consequence stage then applies the selected weather, ignition, population, protection, and receptor conditions. The result is conditional on those inputs.

A healthy result commonly contains:

```json
{
  "status": "EXECUTED_OPERATOR_LIMITED",
  "provider_release_resolved": true,
  "termination": {"basis": "reviewed_isolation_success", "time_s": 0.2},
  "inventory": {"status": "MASS_BALANCE_CLOSED"},
  "frequency_inference_performed": false,
  "facility_qra_claim": false
}
```

`EXECUTED_OPERATOR_LIMITED` means the requested chain ran, while one or more evidence limits still apply. `INCOMPLETE_EVIDENCE`, `BLOCKED`, or `PROVIDER_REQUIRED` must be shown to the operator rather than converted into a number that looks complete.

## 10. Monitoring and prediction integration

For monitoring, send a state frame containing values, units, signal quality, timestamp, facility ID, component ID, and operating mode. HAZOP selects the scenario. A resolver calls the equipment provider. PRISM then performs the quantitative calculation using the current state.

For prediction, use the same contract but set the provenance to `model_prediction` and include the simulation time. Run the quantitative calculation again when a simulated value crosses a HAZOP threshold or another declared risk condition. Do not mix measured and predicted values in one result without preserving both provenance fields.

Recommended operator screen fields:

- facility, component, port, and operating mode
- HAZOP scenario ID and deviation
- current versus predicted state
- provider status and source digest
- release termination basis and duration
- mass-balance status and remaining inventory
- frequency source and uncertainty range
- consequence backend and cache/fresh flag
- latency, response status, and required action

## 11. Reproducibility checklist

Before sharing a result, save:

1. the exact state frame;
2. the selected HAZOP row and scenario ID;
3. provider response and source digest;
4. the `FrequencyPlan` revision and citation;
5. weather, ignition, population, and protection inputs;
6. package version and commit;
7. the result ledger and warning/status fields.

Then rerun:

```powershell
python -m pytest -q
```

The output should be compared by event ID, case ID, risk atom ID, and provider digest. Do not compare only a rounded total risk value.

## 12. Troubleshooting

**`PROVIDER_REQUIRED`**: the scenario has no validated release provider. Attach a provider packet; do not fill the gap with a normal operating flow.

**`BLOCKED` or `INCOMPLETE_EVIDENCE`**: an evidence gate is missing. Inspect the audit path shown in the result and resolve the specific gate.

**Mass-balance failure**: check interval time ordering, mass flow, inventory, and termination basis. PRISM leaves the evidence unresolved rather than changing the provider numbers.

**No HAZOP scenario**: check the operating-mode spelling, signal quality, units, and threshold direction.

**Slow prediction run**: use a cached consequence result for the monitoring path and reserve fresh provider physics for declared simulation checkpoints. Record the cache/fresh choice.

## 13. Current scope

The generic LH2 boundary is intended to connect tanks, pipes, valves, pumps, vaporizers, vents, and external LH2 digital-twin providers. The package is not tied to one inspection center. It is also not a completed regulatory facility QRA: the latest IJHE audit remains fail-closed with five strict evidence gates blocked, and facility IR/F-N promotion is false.

## 14. Further reading

- [Interface Integration Guide](PRISM_INTERFACE_INTEGRATION_GUIDE_en.md)
- [Korean User Manual](PRISM_USER_MANUAL_ko.md)
- [Korean Interface Guide](PRISM_INTERFACE_INTEGRATION_GUIDE_ko.md)
- [IJHE requirement traceability](PRISM_IJHE_requirement_traceability_20261115.md)
- [Latest IJHE audit](PRISM_IJHE_latest_audit_20261115.md)
- [v0.6.3 distribution record](PRISM_v063_PyPI_DOI_배포기록_20261015.md)
