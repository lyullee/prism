# Inventory-termination boundary evidence

PRISM keeps a finite-inventory release open until the external equipment model
proves its declared stopping condition. It does not turn a positive numerical
threshold into a claim that the vessel is empty, and it never extends the last
flow value after the provider horizon.

The provider basis `inventory_depletion_positive_threshold` is reserved for a
diagnostic that stops after reaching a positive remaining-mass threshold. It
preserves the provider's stopping rule while explicitly avoiding a zero-
inventory claim. The consequence chain may consume such a packet when its
other contract fields are valid, but the basis is excluded from the strict
facility release-boundary gate and cannot promote facility IR/F-N.

## Reproducible probe

The current diagnostic uses the same `lh2dt` backend configuration as the
inventory campaign and probes five outlet-area bins:

```powershell
python scripts/probe_inventory_termination_margin.py `
  --backend-config results/20261009/equipment_inventory_campaign/backend_config.json `
  --output results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/inventory_termination_margin_probe.json
```

The probe uses a `1e-10 kg` positive-mass threshold, a `120 s` horizon, and a
`1.2 s` requested interval. The provider is limited to 100 intervals. The
result is recorded in
`results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/inventory_termination_margin_probe.json`.

## Result and interpretation

All five bins remain open: `depleted_case_count = 0` and
`open_case_count = 5`. The smallest three openings reach the provider horizon
with 96.2–98.5% of the initial mass still present. The two larger openings hit
the provider row budget before reaching the `1e-10 kg` threshold. Their status
is `PROVIDER_ERROR`, so PRISM withholds the release boundary rather than
substituting a different termination basis.

This is an evidence result, not a failure of the consequence chain. The
provider has shown a bounded, positive-mass history, but it has not shown
complete inventory depletion for this synthetic terminal-pipe setup. The
facility audit therefore keeps the five `inventory_depletion` cases out of a
strict facility QRA total. A future qualified provider packet must either:

1. reach a reviewed inventory threshold with a documented physical meaning and
   closed mass/energy balances; or
2. declare a different physically reviewed termination condition, such as
   isolation or pressure equalisation, with the corresponding equipment
   evidence.

No frequency is inferred from this probe, no sensor-frequency learning is used,
and the result does not promote the synthetic model to site evidence.
