# Native provider packet facility-frequency runner

`run_native_gas_facility_frequency_case.py` is the compatibility entry point
for both native gas and native liquid/two-phase provider packets. The filename
is retained for existing workflows, but the output schema is now
`prism.native_provider_facility_frequency_case.v1`.

The runner performs one explicit binding:

```text
native provider packet
  -> exact component and opening match
  -> literature initiating frequency
  -> PRISM campaign engine
  -> SLABx/SLABx-LH2 consequence path
  -> conditional outdoor IR/F-N atoms
```

For a gas packet, `compressible_plane_handoff` is required and is consumed by
the consequence request. For a liquid or two-phase packet, the provider's
resolved liquid boundary is consumed directly and a declared pool-footprint
sensitivity is attached. A `ParaHydrogen` property label is translated to the
native `Hydrogen` pool label only at this explicit compatibility boundary.

The runner does not infer missing frequency bins. Every unmatched opening bin
is written as `UNCOMPUTED`, and provider qualification, independent physical
validation, and facility-total QRA promotion remain closed. This makes the
runner suitable for digital-twin diagnostics while preserving the fail-closed
evidence policy.

## Command shape

The gas and liquid commands use the same interface:

```powershell
python scripts/run_native_gas_facility_frequency_case.py `
  --packet <resolved_release.json> `
  --request-context <request-context.json> `
  --manifest <single-scope-facility.json> `
  --frequency-plan <single-scope-frequency-plan.json> `
  --annual-conditions <outdoor-conditions.json> `
  --backend-config <backend_config.json> `
  --output-dir <output-directory>
```

The liquid/two-phase smoke replay used the current external `lh2dt_models`
DynamicHEMPipe packet and produced one executed case, four withheld opening
bins, four diagnostic risk atoms, and `facility_total_risk_available=false`.
The result is evidence that the packet can traverse the common chain; it is
not a qualified facility risk result.
