# PRISM mass-basis handoff contract

PRISM now carries an optional `mass_basis_id` on the equipment state snapshot
and on the provider mass-balance evidence. The token identifies the declared
inventory ownership or scope of a mass value, such as a local vessel inventory
or a provider-side upstream reserve.

The field is optional for backwards compatibility and is omitted from the
serialized wire shape when absent, so legacy state snapshot digests remain
stable. When both sides declare a token, the consequence request rejects the
handoff if the tokens differ. The numeric state-mass/provider-inventory check
continues to run independently.

External provider responses may expose an explicit `provider_meta.mass_basis_id`
or `provider_meta.native_inventory_owner`. The normalization layer preserves
that declaration as `provider_mass_balance.mass_basis_id`. This is a direct
provider declaration; PRISM does not derive a basis from a component ID,
packet name, or release port.

The diagnostic mass audit reports a large numeric mismatch with no explicit
tokens as `MASS_BASIS_UNDECLARED_REVIEW_REQUIRED`. A mismatch between two
declared tokens is reported as `MASS_BASIS_ID_MISMATCH_REVIEW_REQUIRED`.
Neither classification changes a mass, promotes a provider packet, assigns a
frequency, or opens facility IR/F-N/QRA.

## Facility trace output

When a provider mass balance reaches the facility release ledger, the ledger
preserves `provider_mass_basis_ids` and a diagnostic
`provider_mass_basis_status` for each case. The status is one of
`EXPLICIT_ALIGNED`, `EXPLICIT_MISMATCH`, `PARTIAL`, `MALFORMED`, or
`UNDECLARED`. The case-level release-boundary audit and conditional facility
risk trace expose the same fields. `EXPLICIT_MISMATCH`, `PARTIAL`, and
`MALFORMED` block that case's strict release boundary; `UNDECLARED` remains a
review flag for legacy packets and is never filled by inference.

This contract closes an input ambiguity in the digital-twin handoff. It does
not claim that the current 44-case facility campaign has qualified provider
packets; the existing campaign-level release and qualification gates remain
in force.
