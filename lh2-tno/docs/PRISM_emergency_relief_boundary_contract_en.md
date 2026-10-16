# PRISM emergency-relief release-boundary contract

PRISM treats an emergency-relief discharge as its own accident family. It is
not converted into a random hole, a normal vent, or an inventory-depletion
case. The provider packet must preserve the relief event identity all the way
to the release-boundary audit.

## Required provider evidence

For `termination_basis=emergency_relief_discharge`, the provider termination
catalog must carry all of the following fields:

| Field | Required value or meaning |
| --- | --- |
| `event_kind` | `emergency_relief` |
| `source_operator` | `equipment_emergency_relief` |
| `failure_opening_diameter_m` | absent or `null`; a relief device is not a random leak |
| `duration_s` | finite and greater than zero |
| `termination_history_sample_count` | at least two provider time-history samples |
| `relief_setpoint_pa` | positive provider relief setpoint |
| `relief_capacity_kg_s` | positive provider-rated or resolved capacity |
| `discharge_complete` | explicitly `true` |
| `termination_provenance` | non-empty provider explanation of the stopping event |
| `max_abs_mass_residual_kg` | present and within the configured tolerance |

The event and packet digest, available mass, and cumulative release must also
match the facility release ledger. A row is `VALID` only when every check
passes. A valid row is eligible for the case-level release-boundary gate; it
still does not claim provider qualification, physical validation, or facility
IR/F-N promotion.

## Current LH2 status

The current VentStack G1 diagnostic packet supplies an emergency-relief event,
ten time-history samples, a duration, and a mass-balanced consequence input.
It does **not** supply a relief setpoint, relief capacity, explicit completion
event, or the required emergency-relief source operator. It therefore remains
`INVALID` and `NUMERICALLY_OPEN` for strict facility release closure. This is
intentional: the existing packet is synthetic and bounded diagnostic evidence,
not a qualified relief-device record.

The ambient-vaporizer G2 case remains a separate open case. Its
`inventory_over_600s` horizon leaves almost all provider inventory present and
is not accepted as inventory depletion.

## Implementation and replay

The contract is implemented in:

- `src/lh2_tno/provider_termination_evidence_catalog.py`
- `src/lh2_tno/release_boundary_case_audit.py`
- `scripts/build_provider_termination_evidence_catalog.py`
- `scripts/audit_release_boundary_cases.py`

The emergency-relief tests cover both a fully populated valid row and a
diagnostic row that is correctly kept open. The catalog builder now preserves
the relief-specific fields so a reviewed provider packet can be re-audited
without hand editing the facility ledger.
