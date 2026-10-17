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

The inventory dynamic-vaporizer adapter now also accepts an explicit
`--release-mode pressure_equalization` export.  Its provider metadata records
the equalization time, the post-equalization observation interval, the
terminal source pressure, the ambient pressure, and the maximum observed
post-stop flow.  A diagnostic re-export against the current external model
source produced a 96-interval, 600 s packet with a 6.3 s equalization time;
its provider closure audit was `CLOSURE_READY_FOR_QUALIFICATION`.

The exact result is recorded in
[`results/20261018/g2_pressure_equalization_reexport_diagnostic.json`](../results/20261018/g2_pressure_equalization_reexport_diagnostic.json).
The re-export digest is `b59fefcf...`, while the current authoritative G2
facility record is bound to `67353da6...`.  Because PRISM selects provider
evidence by exact result digest, the new packet is intentionally not consumed
by the current campaign.  A campaign rebind and a new facility audit are
required before it can affect any release-boundary count.  The initial state,
geometry, and valve area are synthetic, so the packet remains diagnostic and
does not claim physical validation, frequency inference, or facility QRA.

The implementation is [`src/lh2_tno/pressure_equalization.py`](../src/lh2_tno/pressure_equalization.py), with the command-line wrapper
[`scripts/audit_provider_pressure_equalization.py`](../scripts/audit_provider_pressure_equalization.py).
