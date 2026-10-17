# Current header-bound LH2 facility bridge replay (2026-10-17)

This record refreshes the complete diagnostic connection from the latest
header-bound operating-state replay to the outdoor LH2 consequence service.
It is a general facility integration pattern. The inspection-centre files are
only the current state source; they do not define the scope of a facility
assessment.

## What was executed

The current replay passed one batch through the following chain:

```text
header-bound state frame
  -> explicit operating mode
  -> mode-specific HAZOP deviation
  -> equipment and outlet identity binding
  -> provider release duration / termination / inventory ledger
  -> SLABx-LH2 consequence service
  -> literature frequency binding
  -> conditional current-weather IR atom
```

The three selected branches were `receiving`/`vessel_hole` for the intake
tank, `standby`/`vent_hole` for the pressure-relief vent, and
`supply`/`vaporizer_hole` for the vaporizer boundary. Each branch kept its own
provider component and outlet; no release packet was shared by scenario name.

## Current result

The full runtime record is
`results/20261017/header_bound_facility_bridge_current.json`. The review-sized
summary is
`results/20261017/header_bound_facility_bridge_current_summary.json`.

| observed boundary | mode | release duration | cumulative mass out | remaining mass | termination basis | consequence | fresh service time |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: |
| `lh2-intake-tank` | receiving | 0.15 s | 0.01677671 kg | 0 kg | reviewed isolation success | executed | 5.109 s |
| `lh2-storage-vent` | standby | 0.50 s | 0.00067393 kg | 0.00013479 kg | emergency relief discharge | executed | 4.608 s |
| `lh2-supply-vaporizer-boundary` | supply | 0.50 s | 0.00000722 kg | 0.00081663 kg | reviewed isolation success | executed | 1.638 s |

The provider release packets are model-prediction inputs and the three
consequence branches are diagnostic executions. The declared release boundary
and its mass ledger are carried into the calculation; a remaining mass value
means that the provider stopped at its declared isolation or diagnostic horizon,
not that the whole connected facility inventory was exhausted.

All three branches produced a conditional current-weather IR atom. In this
replay the single synthetic worker receptor receives an IR interval of zero.
That is a result for the supplied geometry, weather and receptor set, not a
claim that the facility has zero risk.

The following gates remain deliberately closed:

- provider qualification and independent physical validation;
- complete facility release-boundary coverage for every declared accident
  family;
- annual facility IR and F-N aggregation;
- field accident-frequency collection or sensor-based frequency learning.

The frequency attached to each branch is the declared literature event. No
frequency was inferred from the state samples. The bridge therefore proves the
state-to-scenario-to-consequence interface and the release-duration handoff,
while the IJHE facility-QRA claim remains withheld until reviewed provider
packets and facility evidence are available.

## Reproduction

From the package root:

```powershell
python scripts/audit_observed_hazop_provider_binding.py `
  --observed-hazop-runtime-audit results/20261017/inspection_center_header_bound_hazop_runtime_current.json `
  --provider-worklist results/20261110/native_full_scope_frequency_assessment_latest2/provider_worklist.json `
  --binding-map examples/inspection_center_hazop_provider_event_bindings.json `
  --output results/20261017/inspection_center_header_bound_provider_binding_current.json

python scripts/run_header_bound_facility_hazop_bridge.py `
  --runtime-frames results/20261017/inspection_center_header_bound_runtime_frames_current.json `
  --hazop-table-set examples/inspection_center_hazop_runtime_tables.json `
  --observed-hazop-runtime-audit results/20261017/inspection_center_header_bound_hazop_runtime_current.json `
  --observed-hazop-provider-binding results/20261017/inspection_center_header_bound_provider_binding_current.json `
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
  --output results/20261017/header_bound_facility_bridge_current.json
```

This command took about 11.4 s for the three branches in the current replay
and takes several seconds because it executes fresh SLABx-LH2 physics.
It is a background/update path; it is not evidence of a fresh-physics 1 Hz
guarantee. The cached realtime path and its deadline evidence remain separate.
