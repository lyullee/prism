# Positive inventory-threshold termination reclassification

## Purpose

PRISM now distinguishes a provider diagnostic that stops at a positive
remaining-mass threshold from a true zero-inventory termination.

The new termination basis is:

```text
inventory_depletion_positive_threshold
```

It is accepted by the provider and consequence contracts so a valid provider
history can still be evaluated through the consequence chain. It is excluded
from the strict facility release-boundary gate and cannot promote facility
IR/F-N. A ledger row whose basis is `inventory_depletion` while its provider
residual exceeds the strict tolerance is labelled
`positive_threshold_candidate` and is blocked from being treated as zero
inventory.

## Current evidence boundary

The authoritative 2026-11-15 union contains 34 events and 44 cases. Its
current facility gate remains `FACILITY_QRA_WITHHELD`: 29 cases are operator
limited, qualified provider coverage is zero, and independent full-chain
physical validation is unavailable. The existing result files were generated
before this semantic reclassification and are therefore not rewritten by
metadata substitution. Rebuilding them requires a functioning external
backend packet environment.

The attempted reproduction using
`scripts/run_native_full_scope_frequency_assessment.py` with
`results/20261008/full_chain/backend_config.json` did not produce a new result:
the configured external backend child exited while the parent waited for its
response. The failure is retained as a reproducibility limitation; no new
facility evidence or qualification claim is inferred from it.

## Verification

- `python -m pytest -q`: 1,587 passed, 1 warning.
- GitHub CI for the semantic-audit commit: successful.
- Strict facility promotion remains fail-closed.

