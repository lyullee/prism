# PRISM native `lh2dt_models` replay (2026-10-16)

This record documents a compatibility fix and a reproducible diagnostic replay against the current public `lh2dt_models` source.

## Source and adapter

- Upstream source: [`lyullee/lh2dt_models`](https://github.com/lyullee/lh2dt_models/tree/b483f7921d7e67a269947f36393fdd3b9ab9e7b3)
- Commit: `b483f7921d7e67a269947f36393fdd3b9ab9e7b3`
- Source tree digest: `cec536c3c69030899982e0e4f7dad5b8ccf2bfd5c056ab335c33a0e51ba07452`
- PRISM adapter: `scripts/export_lh2dt_native_layered_tank_prism_packet.py`

## Compatibility issue found

The historical adapter left the layered tank's distributed boiling model at `off`. With the current upstream API, a depressurising tank can then move a labelled vapor cell into the saturation band without a phase-transfer ledger. The upstream model correctly rejects that state, so the adapter stopped before producing a provider packet.

The adapter now selects the upstream `phase_change_complementarity` closure explicitly by default. The choice is visible in `verification.json` and can be changed with `--distributed-boiling-model`; it is not added to the PRISM release contract. This keeps the external model responsible for phase transfer while preserving PRISM's strict release boundary.

## Reproduction

```powershell
python scripts/export_lh2dt_native_layered_tank_prism_packet.py `
  --lh2dt-root C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016 `
  --output-dir results\20261016\native_layered_tank_actual_smoke_complementarity `
  --horizon-s 1 --time-step-s 0.1 --minimum-step-s 0.001 `
  --isolation-time-s 0.2 --post-isolation-observation-s 0.1 `
  --failure-opening-diameter-m 0.001 --nozzle-height-m 0.05

python scripts/validate_lh2dt_prism_packet_chain.py `
  --packet results\20261016\native_layered_tank_actual_smoke_complementarity\resolved_release.json `
  --output-dir results\20261016\native_layered_tank_actual_smoke_complementarity\chain `
  --backend-config results\20261009\equipment_liquid_release\backend_config.json
```

## Observed result

The native tank export completed with `reviewed_isolation_success` and a 0.3 s diagnostic history. The provider recorded 434.50988 kg available mass, 0.0002821827 kg cumulative release, and a 0.0 kg mass residual. The downstream PRISM chain consumed the exact `prism.resolved_release.v1` packet and reached the `resolved_atmospheric_liquid_exit` boundary.

The result is a current-source integration diagnostic. It does **not** qualify the external provider, infer an initiating frequency, prove field performance, or unlock facility-wide IR/F-N promotion. Those gates remain fail-closed until qualified provider packets and independent full-chain physical evidence are supplied.

## Other native component smoke tests

Current-source diagnostic exports also completed for `DynamicHEMPipe` (`two_phase`) and `MappedPump`. A `StrokeLimitedCommandedValve` gas export completed, but the ordinary low-Mach consequence chain correctly rejected its high-speed gas exit and requested a compressible/underexpanded plane handoff. That rejection is preserved as an explicit scope boundary; the valve packet was not silently downgraded.

