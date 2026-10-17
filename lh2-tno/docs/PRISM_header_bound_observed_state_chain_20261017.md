# Fresh inspection-centre state-to-HAZOP replay (2026-10-17)

This record refreshes the reusable outdoor-LH2 input boundary from the current
inspection-centre workbooks.  The workbooks are kept outside the PRISM
repository; only hashes, normalized evidence, and the audit outputs are
recorded here.

## What was replayed

Three explicitly bound XLSX streams were read from the external data root:

| stream | component boundary | mode supplied by the connector |
| --- | --- | --- |
| receiving workbook | intake tank | `receiving` |
| storage/vent workbook | storage vent boundary | `standby` |
| supply workbook | vaporizer/supply boundary | `supply` |

The header-bound manifest uses only the reviewed pressure/temperature units
declared in the workbook headers.  Differential-pressure columns remain out
of the numeric state binding until their raw unit and meaning are reviewed.
The prediction-named workbook files remain `model_prediction` origin; this
replay does not relabel them as field measurements.

## Results

- 3 source files and 8,955 state samples were read.
- Source replay matched all 3 SHA-256 records and regeneration matched the
  reviewed evidence ledger.
- 3 latest runtime frames were produced with explicit operating modes.
- HAZOP evaluation selected 3 mode-specific scenarios: `receiving`,
  `standby`, and `supply`.
- No release packet, accident frequency, isolation duration, SLABx-LH2
  consequence, physical-validation claim, or facility IR/F-N value was
  created by this replay.

## Reproduction

```powershell
python scripts/audit_observed_equipment_state.py `
  --manifest examples/inspection_center_header_bound_state_manifest.json `
  --source-root "<inspection-centre-data-root>" `
  --output results/20261017/inspection_center_header_bound_state_evidence_current.json

python scripts/audit_observed_state_replay.py `
  --manifest examples/inspection_center_header_bound_state_manifest.json `
  --evidence results/20261017/inspection_center_header_bound_state_evidence_current.json `
  --regenerated-evidence results/20261017/inspection_center_header_bound_state_evidence_current.json `
  --source-root "<inspection-centre-data-root>" `
  --output results/20261017/inspection_center_header_bound_state_replay_current.json

python scripts/build_observed_state_runtime_frames.py `
  --manifest examples/inspection_center_header_bound_state_manifest.json `
  --source-root "<inspection-centre-data-root>" `
  --operating-mode-map examples/inspection_center_header_bound_operating_modes.json `
  --output results/20261017/inspection_center_header_bound_runtime_frames_current.json

python scripts/audit_observed_hazop_runtime.py `
  --runtime-frames results/20261017/inspection_center_header_bound_runtime_frames_current.json `
  --hazop-table-set examples/inspection_center_hazop_runtime_tables.json `
  --now-s 20000 `
  --output results/20261017/inspection_center_header_bound_hazop_runtime_current.json
```

The output is state and qualitative HAZOP evidence only.  A downstream
provider must still return an exact component/port accident packet with its
own release clock, isolation or inventory termination, mass ledger, and
qualification sidecar before PRISM can calculate a strict facility result.
