# Native external LH2 multi-equipment recheck (2026-10-17)

PRISM now has one reproducible command that executes the external `lh2dt`
accident exporters for the seven declared outdoor equipment families and
records their packet identities in one manifest:

```powershell
python scripts/run_native_external_equipment_recheck.py `
  --lh2dt-root "C:\Users\lyul\Desktop\DocuData\_external_lh2dt_models_20261016" `
  --output-dir results/20261017/native_external_multi_equipment_recheck_20261017
```

The runner calls each model's native `export_accident_history(request)` method
and then uses the existing PRISM strict adapter. It does not reconstruct a
release from a normal steady-state `evaluate()` result. The seven equipment
families are:

| Equipment | Native class | PRISM result |
| --- | --- | --- |
| storage tank | `LayeredTank` | liquid release with reviewed isolation diagnostic |
| transfer line | `DynamicHEMPipe` | two-phase release with reviewed isolation diagnostic |
| transfer valve | `StrokeLimitedCommandedValve` | gas release plus optional compressible handoff |
| transfer pump | `MappedPump` | liquid release with explicit downstream isolation observation |
| ambient vaporizer | `DynamicVaporizer` | gas release with native transient history |
| reliquefier | `DynamicReliquefier` | gas release with native transient history |
| pressure-relief vent | `VentStack` | gas release with native hydraulic history |

The recheck produced seven packets and matched the state-snapshot digest for
each packet. The source tree digest, provider result digests, termination basis,
duration, and adapter status are stored in
[`manifest.json`](../results/20261017/native_external_multi_equipment_recheck_20261017/manifest.json).
The individual provider responses and resolved releases are kept beside the
manifest so an IJHE reviewer can replay the exact handoff.

Two packets use an explicit isolation observation (`LayeredTank` and
`DynamicHEMPipe`); the pump uses a separate downstream valve zero-flow check.
The remaining equipment retains its native diagnostic horizon. The runner
preserves those distinctions instead of turning a bounded horizon into
inventory depletion or field isolation.

This is an integration and reproducibility result, not a qualification result.
The manifest therefore records `provider_packet_promoted_count: 0`,
`physical_validation_claim: false`, `frequency_inference_performed: false`,
and `facility_qra_claim: false`. Independent packet qualification, measured
facility state, literature-frequency selection, SLABx-LH2 physical validation,
and facility IR/F-N promotion remain separate evidence gates. No sensor-based
frequency learning is introduced.

## Consequence-chain replay

The saved packets were then replayed through the PRISM consequence path with
`scripts/run_native_external_equipment_chain_recheck.py`:

```powershell
python scripts/run_native_external_equipment_chain_recheck.py `
  --packet-root results/20261017/native_external_multi_equipment_recheck_20261017 `
  --output-dir results/20261017/native_external_multi_equipment_chain_recheck_20261017 `
  --backend-config <reviewed-backend-config.json> `
  --facility examples/native_external_valve_chain_facility_20261017.json `
  --context examples/compressible_plane_chain_context.json
```

All seven packets reached `END_TO_END_DIAGNOSTIC_EXECUTED`. The valve packet
used the explicit compressible-plane handoff (maximum diagnostic Mach number
about 2.29); the other six used the ordinary SLABx-LH2 path. The aggregate
record is [`chain manifest`](../results/20261017/native_external_multi_equipment_chain_recheck_20261017/manifest.json),
with individual chain verification records beside it. These are consequence
chain execution proofs, not facility-wide annual IR/F-N values.
