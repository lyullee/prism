# FFI Test 6 actual-source high-resolution recheck (2026-10-17)

The authoritative FFI Test 6 numerical gate remained open after the earlier
640 to 1280 field-grid comparison. A higher-resolution recheck was run with
the same actual source, fixed observation operator, native SLABx source, and
`puff_steps=120`, `substeps=3`. No sensor value, release rate, wind value, or
source parameter was fitted.

The recheck used field grids of 640, 1280, 2560, and 5120 steps. The final
2560 to 5120 changes were:

| quantity | relative change |
| --- | ---: |
| H2 volume fraction at 30 m | 13.414% |
| centre height at 30 m | 15.451% |
| cloud depth at 30 m | 3.094% |
| temperature at 30 m | 0.201% |
| sensor MAE | 3.381% |
| sensor RMSE | 0.239% |

The strict acceptance rule is less than 2% for every monitored quantity. The
actual-source numerical gate therefore remains **open**. Higher resolution
did not justify promoting this comparison to independent physical validation;
the result is evidence of a remaining numerical-resolution problem rather
than evidence that the model has converged.

Machine-readable records:

- [`refinement.json`](../results/20261017/slabx_lh2_test6_actual_source_numerical_gate_recheck_640_5120/refinement.json)
- [`provenance.json`](../results/20261017/slabx_lh2_test6_actual_source_numerical_gate_recheck_640_5120/provenance.json)

The recorded wall times were approximately 11.1 s, 19.7 s, 47.1 s, and 72.9
s for 640, 1280, 2560, and 5120 field steps, respectively. This provides a
processing-time reference for the digital-twin design while preserving the
fail-closed physical-validation policy.
