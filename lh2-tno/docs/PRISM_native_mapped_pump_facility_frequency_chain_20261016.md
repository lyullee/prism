# Native MappedPump facility-frequency chain

The current external `lh2dt.MappedPump` packet now uses the same facility
frequency runner as the native pipe and valve packets. The integration keeps
the pump's liquid release, duration, explicit downstream isolation observation,
and mass ledger intact, then binds the exact `0.001 m` opening to the TNO
`TNO_PUMP_STANDARD` G2 literature row.

```text
MappedPump H-Q-N state
  -> native liquid release and explicit isolation observation
  -> exact G2 pump opening match
  -> literature pump frequency
  -> SLABx-LH2 / pool consequence path
  -> outdoor ignition, receptor and conditional IR/F-N atoms
```

## Reproduction

The packet is produced by
`scripts/export_lh2dt_native_mapped_pump_prism_packet.py`. The facility
binding uses the common gas/liquid-compatible runner:

```powershell
python scripts/run_native_gas_facility_frequency_case.py `
  --packet results\20261016\native_mapped_pump_actual_smoke\resolved_release.json `
  --request-context results\20261009\equipment_liquid_release\request.json `
  --manifest examples\native_mapped_pump_facility_manifest.json `
  --frequency-plan examples\native_mapped_pump_facility_frequency_plan.json `
  --annual-conditions examples\generic_lh2_full_scope_annual_conditions.json `
  --backend-config results\20261009\equipment_liquid_release\backend_config.json `
  --output-dir results\20261016\native_mapped_pump_frequency_facility_campaign_v2
```

The diagnostic replay has one executed weather case, one uncomputed full-bore
opening case, four ignition-branch risk atoms, and a conditional IR/F-N
diagnostic (zero at the declared 20 m receptor for this geometry). The
facility-total QRA flag remains false. G1, additional pump connection locations, qualified
failure data, and independent liquid/near-field validation are intentionally
not inferred from this single packet. The end-to-end facility campaign took
approximately 28.4 s on the recorded run; this is a diagnostic timing result,
not a real-time performance guarantee for a larger facility.
