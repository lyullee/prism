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

The audit output also reports `worst_quantity` and `worst_relative_change`,
which identify the monitored quantity that keeps the numerical gate open. This
prevents a low-error temperature or RMSE value from hiding the larger source
concentration or plume-height change.

## Reproducibility recheck (640 -> 1280)

On 2026-10-17, the external runner was executed again with the actual FFI
source, `puff_steps=120`, `substeps=3`, and the native SLABx path (the
SLABx-LH2 plume-width and ice extensions were disabled for this run). Both
field levels completed successfully:

| field steps | runtime | H2 at 30 m | centre height | cloud depth | sensor MAE | sensor RMSE |
|---:|---:|---:|---:|---:|---:|---:|
| 640 | 10.60 s | 3.6277 vol% | 1.6341 m | 7.9370 m | 1.6442 vol% | 4.4830 vol% |
| 1280 | 19.21 s | 3.0538 vol% | 1.2376 m | 8.2401 m | 1.5586 vol% | 4.4691 vol% |

The final relative changes were 15.818% (H2 volume fraction), 24.265%
(centre height), 3.678% (cloud depth), 0.356% (temperature), 5.209% (MAE),
and 0.309% (RMSE). The two-percent criterion therefore remains open. This
recheck is a reproducibility and processing-time record; because its numerical
substep configuration differs from the six-level authoritative record above,
it does not replace that record or promote physical validation.

Machine-readable recheck records:

- `results/20261115/slabx_lh2_test6_actual_source_numerical_gate_recheck_640_1280/refinement.json`
- `results/20261115/slabx_lh2_test6_actual_source_numerical_gate_recheck_640_1280/provenance.json`

## Higher-resolution recheck (1280 -> 2560 -> 5120)

The same actual source was rerun at 1280, 2560, and 5120 field steps with
`puff_steps=120`, `substeps=3`, and the native SLABx path.  The final
2560 -> 5120 changes were 15.193% for hydrogen volume fraction, 19.167% for
centre height, 3.499% for cloud depth, 0.206% for temperature, 3.957% for
sensor MAE, and 0.263% for sensor RMSE.  The result therefore remains outside
the 2% all-quantity criterion; the denser grid does not close the numerical
gate.  The new records are:

- `results/20261115/slabx_lh2_test6_actual_source_numerical_gate_recheck_1280_5120/refinement.json`
- `results/20261115/slabx_lh2_test6_actual_source_numerical_gate_recheck_1280_5120/provenance.json`

This recheck strengthens the unresolved-evidence record but keeps
`accepted=false`, `physical_validation_claim=false`, and
`facility_qra_claim=false`.  It must not be replaced by the converged
pseudo-source record.
