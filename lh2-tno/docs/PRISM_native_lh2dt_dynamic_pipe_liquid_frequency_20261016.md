# Current-source DynamicHEMPipe liquid/two-phase frequency replay (2026-10-16)

This replay confirms that the current public `lh2dt_models` DynamicHEMPipe liquid/two-phase branch can be bound to the existing LH2 pipe literature frequency and passed through the liquid release, pool and consequence chain.

```text
native two-phase pipe state
  -> provider-owned outlet history and mass/energy ledger
  -> strict ResolvedLiquidRelease
  -> declared LH2 pool sensitivity footprint
  -> SLABx-LH2/SLABx liquid consequence path
  -> ignition and outdoor receptor risk atoms
  -> conditional frequency-weighted campaign result
```

The exact `LH2_PIPE AREA_0.01%` opening is `0.00025 m`. The literature row provides a central rate of `3.4e-5 year^-1` and a marginal p05–p95 range of `3.255e-6–3.551e-4 year^-1`:

- Brooks, Ehrhart & LaFleur (2021), Table 2
- SAND2021-11595C
- [HySafe paper PDF](https://hysafe.info/uploads/papers/2021/44.pdf)

## Reproduction

```powershell
python scripts/run_lh2dt_native_dynamic_pipe_frequency_case.py `
  --lh2dt-root C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016 `
  --compiled-campaign results\20261014\generic_mixed_provider_campaign.json `
  --manifest examples\generic_lh2_full_scope_manifest.json `
  --backend-config results\20261009\equipment_liquid_release\backend_config.json `
  --output-dir results\20261016\native_dynamic_pipe_liquid_frequency_current_source
```

The campaign request is rebuilt from the compiled route, while the native external model owns the liquid/two-phase history. The packet is passed through the standard liquid consequence chain and the result is written as a partial declared-scope campaign.

## Observed result

| Item | Result |
| --- | --- |
| phase basis | `two_phase` |
| exact opening match | yes (`0.00025 m`) |
| provider mass-accounting residual | `0.0 kg` |
| provider energy-accounting residual | approximately `-2.8e-17 J` |
| native export time | approximately `0.2 s` |
| consequence campaign time | approximately `11–13 s` |
| consequence chain | executed |
| facility QRA promotion | withheld |

The zero mass residual is the provider's accounting residual for the returned history. It does not mean that the entire upstream facility inventory was exhausted; the bounded diagnostic horizon and native pipe state remain explicitly documented. Airborne-liquid transfer is also not inferred beyond the provider contract.

The result is diagnostic evidence. The provider packet is not qualified, the pool footprint is a declared sensitivity input, and independent liquid release/near-field validation is still required before facility IR/F-N promotion.

The compact replay summary is [`examples/native_lh2dt_dynamic_pipe_liquid_frequency_replay_20261016.json`](../examples/native_lh2dt_dynamic_pipe_liquid_frequency_replay_20261016.json).

