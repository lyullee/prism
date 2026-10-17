# PRISM pressure-equalization candidate evidence

This record documents the first native `lh2dt.DynamicHEMPipe` packet that carries the complete pressure-equalization stop contract required by PRISM.

- External provider commit: [`7072374`](https://github.com/lyullee/lh2dt_models/commit/7072374)
- Provider source digest: `3b186dff343bd787567033e13b62954a748bce0f12ba26b981d03bafe3d02d74`
- Provider result digest: `2d2e974560db55d7eedae5ecc27644ab8c82b8f691097a0ab8e5733275451436`
- Case: synthetic 1 m DynamicHEMPipe full-bore outlet
- Consequence path: provider export → PRISM resolved release → SLABx-LH2/TNO consequence chain

The provider explicitly reports the pressure-equalization time, a 0.2 s post-stop observation tail, terminal source pressure, ambient pressure, successful zero-flow observation, and maximum post-stop flow of 0 kg/s. PRISM's single-case release ledger classifies the row as `provider_declared_pressure_equalization` and the strict release-boundary gate passes for this row.

This is a candidate evidence packet. The authoritative 24-event facility campaign still references the previous provider digest, so the candidate is not silently substituted into the published campaign. Provider qualification, independent physical validation, field calibration, and facility IR/F-N/QRA promotion remain withheld.

Machine-readable record: [`results/20261018/native_dynamic_pipe_pressure_equalization_explicit_candidate.json`](../results/20261018/native_dynamic_pipe_pressure_equalization_explicit_candidate.json).
