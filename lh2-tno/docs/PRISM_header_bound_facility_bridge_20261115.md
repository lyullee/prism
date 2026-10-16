# PRISM header-bound multi-equipment facility bridge

This record closes the previously missing **batch connection** between the
inspection-centre state input and the generic outdoor LH2 facility runtime
engine. It is a reusable diagnostic pattern for a general LH2 facility; the
inspection-centre workbooks are only the evidence source used for this replay.

## What is connected

For one coherent runtime batch, the bridge now keeps the following identity
chain for every component:

```text
explicit workbook/header unit
  -> SI state frame
  -> explicit supervisory operating mode
  -> mode-specific HAZOP deviation
  -> explicit provider component and outlet
  -> provider release history and termination
  -> SLABx-LH2/TNO consequence calculation
  -> literature frequency binding
  -> conditional current-weather IR contribution
```

The bridge dispatches each component/scenario pair independently. A provider
packet, termination boundary, frequency event, or geometry cannot be silently
reused because the resolver key is `(observed_component_id, scenario_id)`.

## Reproduction

The following command reproduces the saved facility batch. Replace
`<DATA_ROOT>` with the local inspection-centre data directory when rebuilding
the header-bound frames.

```powershell
python scripts/build_observed_state_runtime_frames.py `
  --manifest examples/inspection_center_header_bound_state_manifest.json `
  --source-root "<DATA_ROOT>" `
  --operating-mode-map examples/inspection_center_header_bound_operating_modes.json `
  --output examples/inspection_center_header_bound_runtime_frames_20261115.json

python scripts/audit_observed_hazop_runtime.py `
  --runtime-frames examples/inspection_center_header_bound_runtime_frames_20261115.json `
  --hazop-table-set examples/inspection_center_hazop_runtime_tables.json `
  --now-s 20000 `
  --output examples/inspection_center_header_bound_hazop_runtime_audit_20261115.json

python scripts/audit_observed_hazop_provider_binding.py `
  --observed-hazop-runtime-audit examples/inspection_center_header_bound_hazop_runtime_audit_20261115.json `
  --provider-worklist results/20261110/native_full_scope_frequency_assessment_latest2/provider_worklist.json `
  --binding-map examples/inspection_center_hazop_provider_event_bindings.json `
  --output examples/inspection_center_header_bound_provider_binding_20261115.json

python scripts/run_header_bound_facility_hazop_bridge.py `
  --runtime-frames examples/inspection_center_header_bound_runtime_frames_20261115.json `
  --hazop-table-set examples/inspection_center_hazop_runtime_tables.json `
  --observed-hazop-runtime-audit examples/inspection_center_header_bound_hazop_runtime_audit_20261115.json `
  --observed-hazop-provider-binding examples/inspection_center_header_bound_provider_binding_20261115.json `
  --provider-worklist results/20261110/native_full_scope_frequency_assessment_latest2/provider_worklist.json `
  --packet-evidence results/20261110/observed_hazop_storage_vaporizer_isolation_overlay/packet_evidence.json `
  --packet-root results/20261110/native_generic_scope_packets_latest2 `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan results/20261110/native_full_scope_frequency_assessment_latest2/frequency_plan.json `
  --provider-defaults-liquid examples/provider_request_defaults_liquid.json `
  --provider-defaults-relief examples/provider_emergency_relief_defaults.json `
  --template examples/equipment_consequence_template.json `
  --backend-config results/20261008/full_chain/backend_config.json `
  --now-s 20000 `
  --output results/20261115/header_bound_facility_bridge_runtime.json
```

## Replay result

The saved replay contains three components and three selected scenarios:

| Observed component | Explicit mode | HAZOP family | Provider outlet | Result |
| --- | --- | --- | --- | --- |
| `lh2-intake-tank` | `receiving` | `vessel_hole` | `storage-tank-01/tank-accident-out` | consequence evaluated |
| `lh2-storage-vent` | `standby` | `vent_hole` | `pressure-relief-vent-01/vent-accident-out` | consequence evaluated |
| `lh2-supply-vaporizer-boundary` | `supply` | `vaporizer_hole` | `ambient-vaporizer-01/vaporizer-accident-out` | consequence evaluated |

All three branches produced a current-weather risk atom. The literature
frequency was attached from the declared frequency event; it was not inferred
from the state samples. The source origin is `model_prediction`, so this replay
is valid as chain and interface evidence only.

The full runtime record is
`results/20261115/header_bound_facility_bridge_runtime.json`; a compact review
record is `results/20261115/header_bound_facility_bridge_summary.json`.

## Processing-time interpretation

The saved fresh-physics batch took about 10.4 s on the development machine for
three branches. That is a diagnostic measurement, not a 1 Hz claim. PRISM's
separate cache benchmark demonstrates sub-second cached evaluation while fresh
SLABx-LH2 physics remains a background/update path. A production digital twin
should therefore use the cached current state for the control-room loop and
refresh fresh physics asynchronously when the state, scenario, weather, or
provider release key changes.

## Deliberate gates

This bridge does **not** create provider releases, learn accident frequency,
claim physical validation, or promote annual facility IR/F-N. Those gates stay
closed until actual provider release artifacts, qualification sidecars,
reviewed facility geometry/population/weather inputs, and independent physical
validation are supplied. A missing or incompatible provider row remains
`WITHHELD_PROVIDER_CHAIN` rather than receiving a guessed duration or
termination boundary.
