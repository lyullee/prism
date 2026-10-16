# Current-source DynamicHEMPipe to conditional facility frequency chain (2026-10-16)

This replay exercises the same frequency-to-facility path for a native `lh2dt.DynamicHEMPipe` gas packet:

```text
native DynamicHEMPipe state and isolation clock
  -> strict PRISM gas packet
  -> source-state-bound compressible plane
  -> exact LH2 pipe literature opening bin
  -> SLABx/SLABx-LH2 consequence and ignition branches
  -> outdoor weather/population risk atoms
  -> conditional facility IR/F-N and frequency sensitivity
```

The packet uses a `0.001 m` opening on the declared `0.1 m` native pipe, matching the `AREA_0.01%` row in the diagnostic pipe frequency plan. The external model reports `reviewed_isolation_success` at `0.15 s`; its mass residual is approximately `-3.4e-21 kg`. The compressible handoff contains eight source-state-bound intervals, including three provider-declared zero-flow termination intervals.

The initiating frequency is supplied independently by the literature catalogue, not inferred from the native packet:

- Brooks, Ehrhart & LaFleur (2021), Table 2
- SAND2021-11595C
- [HySafe paper PDF](https://hysafe.info/uploads/papers/2021/44.pdf)
- central frequency: `3.4e-6 year^-1`
- marginal p05–p95 range: `3.255e-7–3.551e-5 year^-1`

## Reproduction

```powershell
python scripts/export_lh2dt_native_dynamic_pipe_prism_packet.py `
  --lh2dt-root C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016 `
  --output-dir results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2 `
  --component-id native-dynamic-pipe-diagnostic --port-id native-dynamic-pipe-out `
  --event-id native-dynamic-pipe/AREA_0.01pct `
  --length-m 1 --pipe-diameter-m 0.1 `
  --initial-pressure-pa-abs 300000 --initial-temperature-k 50 `
  --source-mode gas --wall-temperature-k 50 `
  --failure-opening-diameter-m 0.001 --horizon-s 0.2 --time-step-s 0.02 `
  --isolation-time-s 0.1 --post-isolation-observation-s 0.05

python scripts/build_compressible_plane_handoff.py `
  --packet results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2\resolved_release.json `
  --provider-response results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2\provider_response.json `
  --lh2dt-root C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016 `
  --output-handoff results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2\compressible_handoff.json `
  --output-audit results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2\compressible_handoff_audit.json

python scripts/attach_compressible_plane_handoff.py `
  --packet results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2\resolved_release.json `
  --handoff results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2\compressible_handoff.json `
  --output-packet results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2\resolved_release_with_handoff.json `
  --output-audit results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2\handoff_attach_audit.json

python scripts/run_native_gas_facility_frequency_case.py `
  --packet results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2\resolved_release_with_handoff.json `
  --request-context results\20261016\native_dynamic_pipe_current_source_frequency_packet_nativeid_v2\chain\request.json `
  --manifest examples\native_dynamic_pipe_gas_facility_manifest.json `
  --frequency-plan examples\native_dynamic_pipe_gas_facility_frequency_plan.json `
  --annual-conditions examples\native_dynamic_pipe_gas_facility_annual_conditions.json `
  --backend-config results\20261009\equipment_liquid_release\backend_config.json `
  --output-dir results\20261016\native_dynamic_pipe_frequency_facility_campaign_current_source
```

## Observed result

| Item | Result |
| --- | --- |
| exact opening match | yes (`0.001 m`) |
| provider termination | `reviewed_isolation_success`, `0.15 s` |
| handoff states | 8, with 3 zero-flow termination intervals |
| facility events / cases | 5 / 10 |
| executed cases | 2 weather cases |
| uncomputed opening-bin cases | 8 |
| operator-limited executed cases | 2 |
| risk atoms | 8 |
| conditional diagnostic IR/F-N | available for four declared receptors |
| facility QRA promotion | withheld |
| campaign elapsed time | approximately 7.2 s on this run |

The eight unmatched cases remain `UNCOMPUTED`. The two executed cases are retained as `EXECUTED_OPERATOR_LIMITED` because the packet is synthetic and the handoff is not independently validated. The conditional IR/F-N values are therefore diagnostic atom reweightings, not a qualified facility total.

The compact replay summary is [`examples/native_lh2dt_dynamic_pipe_frequency_facility_replay_20261016.json`](../examples/native_lh2dt_dynamic_pipe_frequency_facility_replay_20261016.json).

