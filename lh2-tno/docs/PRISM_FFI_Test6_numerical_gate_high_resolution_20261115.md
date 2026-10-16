# PRISM FFI Test 6 high-resolution numerical gate — 2026-11-15

## Purpose

This record documents a higher-resolution repeat of the independent FFI Test 6
SLABx comparison. The calculation uses the published Hansen–Hansen cold
hydrogen pseudo-source and does not fit any sensor value. It is a numerical
stability check for the outdoor dispersion component, not a new accident source
term and not a facility QRA result.

## What was run

The same audited SLABx source and the same source boundary were evaluated at
`n_field_steps = 640, 1280, 2560, 5120`. The four monitored values at 30 m
were hydrogen volume fraction, centre height, cloud depth, and temperature.
The last refinement (2560 → 5120) changed every monitored value by less than
2%, so the numerical acceptance gate is now **accepted**.

| quantity | 640 | 1280 | 2560 | 5120 |
|---|---:|---:|---:|---:|
| H2 volume fraction (vol%) | 4.790863 | 4.251247 | 3.783937 | 3.783918 |
| centre height (m) | 3.013550 | 2.431275 | 1.991599 | 1.991600 |
| cloud depth (m) | 7.538416 | 7.773116 | 8.007171 | 8.007084 |
| temperature (K) | 267.621971 | 268.542799 | 269.325867 | 269.325901 |

The relative changes for the final pair are `5.10e-6`, `7.07e-7`, `1.09e-5`,
and `1.28e-7`, respectively. Single-run elapsed times were approximately
45.2, 94.5, 130.3, and 241.6 s; these are fresh-physics diagnostic timings and
do not support a 1 Hz real-time claim.

## Comparison result

The independent comparison audit remains review-ready with 30 sensor rows.
The reported metrics are MAE `1.8671 vol%`, RMSE `4.5359 vol%`, and LFL
classification TP/FN/FP `3/3/0` (six observed LFL pairs and three predicted
LFL pairs). The numerical gate is no longer the blocking reason for this
comparison.

The machine-readable records are:

- `results/20261115/slabx_lh2_test6_high_resolution_gate/refinement.csv`
- `results/20261115/slabx_lh2_test6_high_resolution_gate/provenance.json`
- `results/20261115/slabx_lh2_test6_high_resolution_gate/independent_comparison_audit.json`

## Promotion boundary

Passing a numerical refinement gate only shows that this particular SLABx
calculation is stable at the tested resolution. It does **not** establish an
independent physical-validation claim. External review of the published source
and observation operator is still required, and the comparison does not validate
equipment release, isolation, inventory depletion, initiating frequency,
ignition, IR/F-N, or facility-wide QRA. Those gates remain explicitly closed in
the IJHE objective audit.

The audit can be reproduced from the package directory with:

```powershell
python scripts/audit_slabx_lh2_independent_comparison.py `
  --predictions results/20261115/slabx_lh2_test6_high_resolution_gate/sensor_predictions.csv `
  --summary results/20261115/slabx_lh2_test6_high_resolution_gate/summary.json `
  --numerical-gate results/20261115/slabx_lh2_test6_high_resolution_gate/provenance.json `
  --source-ledger results/20261115/slabx_lh2_test6_high_resolution_gate/source_ledger.json `
  --output results/20261115/slabx_lh2_test6_high_resolution_gate/independent_comparison_audit.json
```
