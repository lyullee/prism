# Native LH2 valve packet to conditional facility frequency chain (2026-10-16)

This diagnostic demonstrates the complete **conditional** path for one valve opening bin:

```text
lh2dt StrokeLimitedCommandedValve
  -> strict PRISM gas release packet
  -> source-state-bound compressible plane
  -> exact opening match to the literature frequency plan
  -> SLABx/SLABx-LH2 consequence calculation
  -> direct and delayed ignition branches
  -> outdoor weather and population risk atoms
  -> conditional facility IR/F-N and frequency sensitivity
```

The native packet was placed at `transfer-valve-01` / `valve-accident-out` in the small diagnostic facility manifest. Its `0.00025 m` opening exactly matches the `AREA_0.01%` valve row. The provider packet supplies the release history and compressible handoff; the initiating frequency is supplied independently by the published catalogue row:

- Brooks, Ehrhart & LaFleur (2021), Table 2
- SAND2021-11595C
- [HySafe paper PDF](https://hysafe.info/uploads/papers/2021/44.pdf)
- central frequency: `1.20e-4 year^-1`
- marginal p05–p95 range: `4.414e-5–3.262e-4 year^-1`

## Reproduction

```powershell
python scripts/export_lh2dt_native_valve_prism_packet.py `
  --lh2dt-root C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016 `
  --output-dir results\20261016\native_valve_frequency_packet_positioned `
  --component-id transfer-valve-01 --port-id valve-accident-out `
  --event-id native-stroke-valve/transfer-valve-AREA_0.01pct `
  --source-pressure-pa-abs 300000 --source-temperature-k 50 `
  --failure-opening-diameter-m 0.00025 --stroke-time-s 0.1 `
  --horizon-s 0.2 --time-step-s 0.02 --available-mass-kg 5 `
  --position-enu-m 7 0 1 --compressible-handoff

python scripts/run_native_gas_facility_frequency_case.py `
  --packet results\20261016\native_valve_frequency_packet_positioned\resolved_release_with_handoff.json `
  --request-context results\20261016\native_valve_frequency_packet_positioned\chain\request.json `
  --manifest examples\native_lh2dt_valve_frequency_manifest.json `
  --frequency-plan examples\native_lh2dt_valve_frequency_plan.json `
  --annual-conditions examples\generic_lh2_full_scope_annual_conditions.json `
  --backend-config results\20261009\equipment_liquid_release\backend_config.json `
  --output-dir results\20261016\native_valve_frequency_facility_campaign_generic
```

## Observed result

| Item | Result |
| --- | --- |
| provider packet | consumed; exact source/result digests retained |
| compressible handoff | consumed; 10 states; source-state bound |
| frequency event | exact `AREA_0.01%` opening match |
| facility event/case count | 5 / 5 |
| executed case | 1 |
| uncomputed opening bins | 4 |
| operator-limited executed case | 1 |
| risk atoms | 4 |
| conditional diagnostic IR/F-N | available for the declared worker receptor |
| facility QRA promotion | withheld |
| campaign elapsed time | approximately 4.6 s on this run |

The four unmatched opening bins remain `UNCOMPUTED`; they are never assigned zero frequency or copied from the selected packet. The selected packet is numerically executed but remains `EXECUTED_OPERATOR_LIMITED`, so the campaign records five withheld rows in total: four genuinely uncomputed bins and one operator-limited executed row. The conditional IR/F-N result is a diagnostic reweighting of the four saved atoms. The run does not claim a complete facility QRA because the provider is synthetic/operator-limited, the inventory is not depleted, and the independent physical-validation and qualification gates remain closed.

The compact replay summary is [`examples/native_lh2dt_valve_frequency_facility_replay_20261016.json`](../examples/native_lh2dt_valve_frequency_facility_replay_20261016.json).

