# Native LH2 inventory-depletion export

PRISM can now call the external `lh2dt.DynamicVaporizer` or
`lh2dt.DynamicReliquefier` accident exporter with an explicit
`inventory_depletion` termination mode. The provider remains responsible for
the transient calculation and for deciding when its finite-volume inventory
has reached its positive stopping threshold.

## Example

```powershell
python scripts/export_lh2dt_dynamic_vaporizer_prism_packet.py `
  --lh2dt-root "C:\path\to\lh2dt_models" `
  --output-dir results/native_inventory_candidate `
  --mode vaporizer `
  --termination-mode inventory_depletion `
  --duration-s 600 `
  --time-step-s 0.05 `
  --opening-diameter-m 0.005 `
  --component-id ambient-vaporizer-01 `
  --port-id vaporizer-accident-out `
  --event-id generic-lh2-full-scope-example/ambient-vaporizer/G2-inventory-depletion-candidate
```

The exporter uses the native provider `export_accident_history` method. It
then records the provider's explicit stopping rule in `provider_meta`:

* `depletion_threshold_kg` — the positive threshold used by the provider;
* `remaining_inventory_kg` — the provider's final finite-volume mass;
* `max_total_mass_residual_kg` — `initial - cumulative_out - final`;
* `available_mass_definition` and `termination_rule` — human-readable
  provenance for the stop.

If the provider stops at the requested horizon instead, the PRISM inventory
adapter rejects the packet as `inventory_depletion`. It is therefore not
converted from a bounded `inventory_over_600s` trace by assumption.

## Relationship to the G2 worklist event

The generic example's `ambient-vaporizer/G2` frequency row is defined as the
`inventory_over_600s` family. A new native inventory-depletion packet has a
different termination basis and must not be silently rebound to that row. The
candidate can be audited and connected to a new frequency event only after a
reviewed frequency definition for that event is supplied. Until then, the G2
facility risk branch remains open by design.

This exporter is a model-prediction diagnostic until site calibration,
provider qualification and independent physical validation are supplied. It
does not infer an initiating frequency and does not promote facility IR/F-N
results.
