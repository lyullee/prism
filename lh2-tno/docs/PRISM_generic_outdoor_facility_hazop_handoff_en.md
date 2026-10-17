# Generic outdoor-LH2 facility HAZOP handoff

PRISM now ships a facility-neutral replay that demonstrates the digital-twin
boundary for three representative outdoor units: a storage tank, a liquid
transfer line, and a pressure-relief vent. The replay uses one exact forecast
time grid and carries the operating mode with every state frame:

`process state + operating mode -> HAZOP deviation -> scenario ID -> quantitative request`

The example is deliberately separate from the inspection-center data. It is a
generic contract example, not a claim that these thresholds, locations, or
equipment records describe a real site.

## Reproduce the handoff

From the `lh2-tno` directory:

```powershell
python scripts/run_generic_facility_hazop_handoff.py `
  --frames examples/generic_facility_forecast_frames.json `
  --tables examples/generic_facility_hazop_tables.json `
  --current-frames examples/generic_facility_current_frames.json `
  --output results/20261115/generic_outdoor_facility_hazop_quantitative_handoff.json
```

The replay has three components and three predicted times (`0`, `10`, and
`20 s`). At `10 s`, one declared deviation is selected for each component:

| Component | Mode | Deviation | Scenario family |
| --- | --- | --- | --- |
| `storage-tank-01` | `receiving` | high pressure | `vessel_hole` |
| `liquid-transfer-line-01` | `supply` | low flow | `pipe_hole` |
| `pressure-relief-vent-01` | `standby` | high pressure | `vent_hole` |

The output contains three stable request keys of the form
`component_id|scenario_id|forecast_time_s`. Each request lists the exact
downstream evidence required before quantitative evaluation:

- qualified equipment release packet, including release start/end,
  termination, isolation, and inventory fields;
- reviewed literature frequency and uncertainty bounds;
- SLABx-LH2 consequence output; and
- facility weather, ignition, population, and endpoint bindings.

The optional current-state file contains one historian-style frame per
component at the same active deviations. Those selections are written to a
separate current-state worklist with `CURRENT_HAZOP_DEVIATION` request keys.
The current and predicted worklists share the same component, scenario-family,
operating-mode, and evidence contracts, so a control-room monitor and a
process-model forecast can feed the same downstream quantitative adapter.

The output adds `current_evidence_coverage` and `forecast_evidence_coverage`.
Each audit uses the exact request key and checks all four evidence blocks. With
the shipped synthetic inputs and no attachment file, both gates correctly
report `WITHHELD_QUANTITATIVE_EVIDENCE_MISSING` for three requests. Optional
attachment maps can be supplied with `--current-attachments` and
`--forecast-attachments`; extra keys and missing fields remain visible as gate
failures rather than being reassigned or treated as zero risk.

## What this proves and what it does not

The replay proves that a multi-equipment forecast can preserve component
identity and operating mode, select the correct HAZOP row, and produce a
separate quantitative work item for each newly reached condition. The
quantitative evaluator is intentionally absent, so the record reports three
withheld evaluations. It creates no release packet, does not infer an annual
frequency from the forecast, does not run SLABx-LH2, and does not calculate or
promote facility IR/F-N.

To use a real digital-twin source, replace the synthetic frame and table files
with reviewed process-model exports. Keep the explicit component IDs, units,
operating modes, forecast origin, and exact time-grid contract. Then attach
qualified provider and facility evidence through the existing forecast
evidence gate before a campaign can enter the facility ledger.
