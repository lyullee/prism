# Provider pressure-equalization candidate (2026-10-18)

PRISM now has a read-only audit for gas-unit histories that appear to stop
because the provider source pressure reaches the non-outward boundary.  The
audit does not rewrite a packet or turn a bounded horizon into a qualified
release.  It reports a candidate `model_pressure_equalization` termination
only when all of the following are present in the provider history:

- a positive-flow interval immediately before the first zero-flow interval;
- provider source pressure at or below ambient at that interval;
- at least two consecutive zero-flow observation rows;
- a closed provider mass ledger; and
- an explicitly closed provider dynamic pressure/inventory state ledger.

The audit was run against the current native external campaign route
`generic-lh2-full-scope-frequency-example/ambient-vaporizer/G2` with:

```powershell
python scripts/audit_provider_pressure_equalization.py `
  --campaign results/20261115/native_external_facility_full_scope_campaign_current/campaign.json `
  --event-id generic-lh2-full-scope-frequency-example/ambient-vaporizer/G2 `
  --output .tmp_pressure_equalization_g2.json
```

It returned `PRESSURE_EQUALIZATION_CANDIDATE` with a first non-outward
interval at 6.3 s and a 6.3 s zero-flow observation tail.  The source
pressure at the end of that tail was 100,916.54 Pa against 101,325 Pa ambient;
the provider mass and dynamic-state residuals were closed.

This is a useful closure candidate, not a completed provider packet.  The
current route remains `inventory_over_600s` until the equipment model exports a
new packet whose termination basis and result digest explicitly bind this
pressure-equalization boundary.  The audit sets
`packet_mutation_allowed=false`, `qualified_provider_packet_allowed=false`,
`frequency_inference_allowed=false`, and `facility_qra_allowed=false`.

The dynamic-vaporizer adapter now also accepts an explicit
`--termination-mode pressure_equalization` export.  Its provider metadata
records the equalization time, the post-equalization observation interval, the
terminal source pressure, the ambient pressure, and the maximum observed
post-stop flow.  A synthetic diagnostic run with the current external model
source produced an 84-interval, 12.6 s packet whose provider closure audit was
`CLOSURE_READY_FOR_QUALIFICATION`; it remains diagnostic because its initial
state and geometry are synthetic and no qualification sidecar or independent
facility validation is present.

The implementation is [`src/lh2_tno/pressure_equalization.py`](../src/lh2_tno/pressure_equalization.py), with the command-line wrapper
[`scripts/audit_provider_pressure_equalization.py`](../scripts/audit_provider_pressure_equalization.py).
