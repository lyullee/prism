# Header-bound observed-state to HAZOP chain

The inspection-centre workbooks are useful as a real process-state input
example, but their filenames contain `예측데이터` and their differential
pressure channels do not have an explicit raw unit.  The new header-bound
manifest therefore uses only the five pressure/temperature columns whose
engineering units are printed in the workbook headers:

- `PT1206`, `PT1105A`, and `PT1101`: `MPa`
- `TT1106` and `TT1116`: `degC`

The differential-pressure channels are deliberately left out until their raw
unit and quantity meaning are reviewed.  The three source origins are marked
`model_prediction` because the source owner has not confirmed whether the
prediction-named workbooks are measured, predicted, or reconstructed data.

## Reproduction

Replace `<DATA_ROOT>` with the external data directory.  The commands do not
copy raw workbooks into PRISM and write only local diagnostic JSON records.

```powershell
python scripts/audit_observed_unit_consistency.py `
  --manifest examples/inspection_center_header_bound_state_manifest.json `
  --reviewed-map examples/inspection_center_workbook_header_signal_unit_map.json `
  --output results/<date>/header_bound_unit_audit.json

python scripts/audit_observed_origin_provenance.py `
  --manifest examples/inspection_center_header_bound_state_manifest.json `
  --output results/<date>/header_bound_origin_audit.json

python scripts/audit_observed_equipment_state.py `
  --manifest examples/inspection_center_header_bound_state_manifest.json `
  --source-root "<DATA_ROOT>" `
  --output results/<date>/header_bound_state_evidence.json

python scripts/build_observed_state_runtime_frames.py `
  --manifest examples/inspection_center_header_bound_state_manifest.json `
  --source-root "<DATA_ROOT>" `
  --operating-mode-map examples/inspection_center_header_bound_operating_modes.json `
  --output results/<date>/header_bound_runtime_frames.json

python scripts/audit_observed_hazop_runtime.py `
  --runtime-frames results/<date>/header_bound_runtime_frames.json `
  --hazop-table-set examples/inspection_center_hazop_runtime_tables.json `
  --now-s 20000 `
  --output results/<date>/header_bound_hazop_runtime_audit.json
```

The verified replay on 2026-11-15 produced 8,955 state samples, three latest
runtime frames, five exact unit matches, zero unit conflicts, zero filename
origin conflicts, and three HAZOP selections (`receiving`, `standby`, and
`supply`).  The stable summary is
`examples/inspection_center_header_bound_chain_summary.json`.

## Boundary after HAZOP

This is the reusable general-facility input boundary:

```text
explicit workbook header units
  -> SI state-only evidence
  -> latest component runtime frames
  -> operator/supervisory operating mode
  -> mode-specific HAZOP selection
  -> provider-owned release packet
  -> SLABx-LH2 and facility risk calculation
```

Only the first four arrows and HAZOP selection are demonstrated by this
record.  A normal-operation row never creates a hole, release duration,
isolation result, inventory depletion, or failure frequency.  The next
provider boundary still requires an exact equipment/port mapping and a
qualified release packet with its own termination and mass ledger.

This evidence is therefore diagnostic, portable to other LH2 facilities, and
does not claim physical validation or a complete facility IR/F-N.
