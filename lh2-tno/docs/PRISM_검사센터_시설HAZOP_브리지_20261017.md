# Reconstructed inspection-center facility HAZOP bridge

This record closes the missing **facility-coordinator** step in the diagnostic
demonstration. The earlier provider-chain example executed one selected supply
scenario in isolation. The new command sends all three reconstructed component
frames through `FacilityRealtimeConsequenceMonitor` in one coherent batch.

```powershell
python scripts/run_inspection_center_facility_hazop_bridge.py
```

The input is deliberately explicit:

1. `inspection_center_reconstructed_runtime_frames.json` supplies one
   state-only frame for the intake tank, storage vent, and supply vaporizer
   boundary. Each frame carries its operating mode (`receiving`, `standby`, or
   `supply`).
2. `inspection_center_hazop_runtime_tables.json` supplies the three
   component-specific HAZOP rows. The script forms a facility table by taking
   the declared union of those rows; it does not infer rows from names,
   pressure, or geometry.
3. The HAZOP selector evaluates the observed component identity and mode. The
   receiving and standby rows are below their diagnostic thresholds and are
   recorded as `WITHHELD_HAZOP_NO_DEVIATION`.
4. The supply frame selects exactly one `vaporizer_hole` scenario. Its provider
   event, component, and port are taken from the explicit binding map:
   `ambient-vaporizer-01` / `vaporizer-accident-out` / `.../G3`.
5. Only the selected branch is translated to the provider component identity.
   The provider packet is rebased to its declared exit position, then sent
   through the existing provider release contract, SLABx-LH2 dispersion,
   ignition branches, radiation/blast, human-damage, and conditional-risk
   stages.

The generated artifact is:

```text
examples/inspection_center_facility_hazop_bridge.json
```

The latest diagnostic run reports:

| Field | Result |
| --- | --- |
| Facility status | `FACILITY_HAZOP_RUNTIME_EVALUATED` |
| Components in one batch | 3 |
| Selected components | 1 (supply vaporizer) |
| Normal components withheld | 2 (intake tank, storage vent) |
| Executed risk atoms | 1 |
| Current-weather conditional IR | Available as a diagnostic contribution |
| Facility annual IR | Withheld |
| Facility F/N | Withheld |
| Operating-mode inference | False |
| Frequency learning | False |
| Provider packet created by PRISM | False |
| Provider qualification / physical validation | Diagnostic only / false |

The recorded wall-clock time is evidence for that invocation only. It is not a
fresh-physics 1-Hz service guarantee. The reconstructed source frames,
synthetic HAZOP thresholds, provider `model_prediction` packet, diagnostic
geometry rebase, and absent independent facility validation keep the result
outside qualified facility QRA promotion.

The corresponding regression test is
`tests/test_inspection_center_facility_bridge.py`. It verifies that the three
component frames are evaluated together, that only the supply branch reaches
the provider, that the explicit observed-to-provider identity is preserved,
and that annual facility IR/F-N remain fail-closed.
