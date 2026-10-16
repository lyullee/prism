# Equipment-twin to HAZOP mode handoff

The equipment model sends two separate inputs to PRISM:

1. a facility-neutral equipment manifest that declares component identity,
   topology, positions, and model-property basis; and
2. a runtime frame set containing measured or predicted process values plus an
   explicit operating mode such as `receiving`, `supply`, or `standby`.

The HAZOP table set is then evaluated against the state values and the explicit
mode. The handoff does not infer a mode from pressure, temperature, tag names,
or source IDs.

Run the audit with:

```powershell
python scripts/audit_equipment_hazop_mode_handoff.py `
  --manifest examples/equipment_manifest.json `
  --runtime-frames examples/my_runtime_frames.json `
  --hazop-table-set examples/my_hazop_table_set.json `
  --now-s 123.0 `
  --output results/equipment_hazop_mode_handoff.json
```

`EQUIPMENT_HAZOP_MODE_HANDOFF_READY` means the declared outdoor manifest is
executable, the runtime component set matches exactly, and each frame reached a
valid HAZOP result (`SCENARIOS_SELECTED`, `NO_DEVIATION`, or
`NO_APPLICABLE_MODE_ROW`). `PARTIAL` preserves missing manifest components or
incomplete topology. `BLOCKED` identifies unknown components, a facility-ID
mismatch, missing HAZOP tables, invalid state values, or an invalid operating
mode.

The output includes digests for the manifest, runtime frames, and HAZOP table
set, component coverage, the complete HAZOP audit, and a policy record. A ready
handoff still has no release packet, initiating frequency, SLABx-LH2 result, or
facility IR/F-N value. The selected scenario must cross the provider release
resolver and the explicit literature-frequency/facility campaign contracts
before quantitative risk is calculated.

Python integrations can call
`lh2_tno.equipment_hazop_handoff.build_equipment_hazop_mode_handoff` directly.
