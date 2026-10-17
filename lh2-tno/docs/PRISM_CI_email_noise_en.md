# PRISM CI email noise control

PRISM has two different kinds of commits:

1. executable changes under `lh2-tno/src`, `lh2-tno/tests`, or package metadata;
2. evidence-ledger and documentation updates under `lh2-tno/results`, `lh2-tno/docs`,
   `CURRENT_STATUS.json`, and `DEVELOPMENT_GOAL.json`.

The `PRISM CI` workflow now runs for `main` pushes and pull requests unless the
change contains only the second, bookkeeping-only group. This keeps the
contract and numerical tests mandatory for code changes while avoiding a new
email-producing run for every audit-ledger refresh.

The PyPI workflow is unchanged. It runs only for a `v*` tag or an explicit
manual dispatch.

This filter does not change any risk result, frequency, provider qualification,
or facility-QRA promotion gate. A skipped run means that no executable input
changed; it does not mean that a skipped commit was tested.

## Historical failure

The recent burst of failure emails came from earlier runs that rejected a
duplicate JSON key in `CURRENT_STATUS.json`. The duplicate key was removed and
the current `main` revision has successful CI runs. The workflow path filter is
an additional noise-control measure for future evidence-only commits.
