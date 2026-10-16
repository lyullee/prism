# PRISM FFI Test 6 actual-source numerical gate — 2026-11-15

## Purpose

This record tests numerical refinement using the same source boundary as the
FFI Test 6 comparison: `0.8317 kg/s`, `25.4 mm` nozzle diameter, liquid mass
fraction `0.559`, release height `0.5 m`, source temperature `20.37 K`, and a
120 s release. No sensor value is fitted.

## Result

The field grid was evaluated at `n_field_steps = 40, 80, 160, 320, 640,
1280`. The final 640 → 1280 changes were:

| quantity | relative change |
|---|---:|
| H2 volume fraction at 30 m | 19.719% |
| centre height at 30 m | 31.188% |
| cloud depth at 30 m | 4.152% |
| temperature at 30 m | 0.494% |
| sensor MAE | 4.618% |
| sensor RMSE | 0.237% |

The numerical acceptance criterion is less than 2% for every monitored value.
The actual FFI source therefore remains **not accepted**. The machine-readable
records are:

- `results/20261115/slabx_lh2_test6_actual_source_numerical_gate/refinement.json`
- `results/20261115/slabx_lh2_test6_actual_source_numerical_gate/provenance.json`
- `results/20261115/slabx_lh2_test6_numerical_sensitivity.json`

## Interpretation

The existing 30-sensor comparison remains a diagnostic result with MAE
`1.8671 vol%`, RMSE `4.5359 vol%`, and LFL TP/FN/FP `3/3/0`, but its actual
source/grid numerical gate is still open. A separate pseudo-source refinement
must not be substituted for this result. Consequently this record does not
open independent physical validation, qualified provider evidence, or facility
IR/F-N/QRA promotion.

The failure is useful: it identifies a real numerical-resolution issue in the
actual LH2 source path. The next technical step is to resolve the grid/source
convergence (or document a reviewed convergence criterion) before using this
comparison as an IJHE validation claim.

The sensitivity record shows why simply increasing the grid is not a safe fix:
at 320 field steps, increasing RK substeps from 16 to 64 changes the 30-metre
hydrogen volume fraction from 3.077 to 2.258 vol% and increases one fresh
calculation from about 30 s to 112 s. A strict adaptive run at `rtol` 0.005
also fails to meet its tolerance at the source region after 16 refinements.

The recorded gate can be rechecked without rerunning the external physics:

```powershell
python scripts/audit_ffi_test6_actual_source_numerical_gate.py `
  --record results/20261115/slabx_lh2_test6_actual_source_numerical_gate/provenance.json `
  --output results/20261115/slabx_lh2_test6_actual_source_numerical_gate/recomputed_gate.json
```

The command returns a nonzero status while the actual-source gate is open.

## Reproducible external-physics runner

The calculation can be repeated from the PRISM checkout when the separately
versioned SLABx and SLABx-LH2 source trees are available. The runner fixes the
published source and mean-wind observation operator; it never fits a sensor
value or infers a release parameter:

```powershell
python scripts/run_ffi_test6_actual_source_numerical_gate.py `
  --slabx-src <SLABx checkout>/slabx/src `
  --slabx-lh2-src <SLABx-LH2 checkout>/source/slabx-lh2 `
  --observations <SLABx-LH2 checkout>/PSEP_STATISTICS_REVISION_20260831/data/ffi_sensor_statistics.csv `
  --output-dir results/20261115/slabx_lh2_test6_actual_source_numerical_gate_rerun
```

The runner writes the same schemas consumed by the audit script. A run that
does not meet the two-percent criterion exits nonzero and remains diagnostic;
it cannot be replaced by the earlier pseudo-source refinement record.
