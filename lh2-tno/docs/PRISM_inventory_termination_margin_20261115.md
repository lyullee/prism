# Inventory-termination margin diagnostic (15 November 2026)

The facility release ledger currently has inventory-depletion cases whose
provider histories stop at a positive residual mass. This diagnostic probes
that boundary with the external LH2 dynamic inventory model. The machine
record is [`inventory_termination_margin_probe.json`](../results/20261115/inventory_termination_margin_probe.json).

## Result

The bounded probe used a 120 s provider horizon, 1.2 s time step, a very small
positive threshold (`1e-10 kg`), and five explicit valve areas. It reached the
declared depletion threshold in **0 of 5** runs:

| Valve area | Result | Remaining inventory or reason |
|---:|---|---|
| `1e-9 m²` | horizon open | `98.50%` of initial mass remains |
| `1e-8 m²` | horizon open | `98.01%` remains |
| `1e-7 m²` | horizon open | `96.24%` remains |
| `1e-6 m²` | provider error | provider interval budget exceeded |
| `1e-5 m²` | provider error | provider interval budget exceeded |

This confirms that the current low-pressure, low-inventory diagnostic setup
does not support a qualified inventory-depletion boundary for these cases. The
result is evidence about the provider boundary, not a reason to extrapolate a
tail, force the mass to zero, or relabel the event as a different accident
family.

## How PRISM uses the result

The release-boundary audit keeps these cases open. Their consequence outputs
may remain available as conditional diagnostics, but their strict facility-QRA
promotion is withheld until the equipment model supplies a physically reviewed
termination history with a closed mass balance. The probe itself sets
`no_extrapolation`, `no_termination_basis_substitution`,
`provider_packet_promotion`, `facility_qra_claim`, and
`physical_validation_claim` to false.

## Reproduction

Run from the `lh2-tno` package directory. The backend configuration points to
the external LH2 digital-twin model and is rehashed before execution:

```powershell
python scripts/probe_inventory_termination_margin.py `
  --backend-config results/20261009/equipment_inventory_campaign/backend_config.json `
  --output results/20261115/inventory_termination_margin_probe.json
```

This is a termination-margin diagnostic. It does not change the current
facility campaign or the literature frequency plan.
