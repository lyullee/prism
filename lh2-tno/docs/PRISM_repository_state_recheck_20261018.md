# PRISM repository state recheck (2026-10-18)

This record reconciles the current checkout, GitHub `main`, CI history, package distribution, and the latest LH2 diagnostic campaign after the external-model compatibility recheck.

## Findings

- The latest executable code commit validated by GitHub is `534d1b4f96e016570293f2e1f2deadafc196e01c`; later `main` commits in this record are documentation-only reconciliations of that validated code state.
- The tracked worktree was clean before this record was added.
- The complete local test suite passes: **1,504 passed, 1 warning**. The warning is the existing `pytest-asyncio` deprecation warning.
- The latest executable GitHub Actions run is [run 1384](https://github.com/lyullee/prism/actions/runs/39067568932), a successful validation of commit `534d1b4f`.
- GitHub release `v0.6.3` and PyPI `prism-risk` `0.6.3` are present.
- SLABx-LH2 has no code change in this recheck. It remains the frozen, validated external consequence component used by the PRISM handoff.
- The current 24-event diagnostic campaign has 24 cases and 96 risk atoms. `facility_total_risk_available`, provider-packet promotion, and physical-validation promotion remain false.

## Corrected metadata

`CURRENT_STATUS.json` and `DEVELOPMENT_GOAL.json` previously referenced older local test counts and an older successful CI run. Their current pointers now record 1,504 tests and Actions run 1384. This is metadata reconciliation; it does not promote the diagnostic campaign to a qualified facility QRA.

## Subsequent pressure-equalization boundary update

The release ledger now accepts `model_pressure_equalization` as a strict boundary only when the provider packet includes explicit equalization time, observation tail, zero-flow, pressure, and post-stop-flow fields. The current transfer-line packet does not include those fields, so the facility gate remains fail-closed. The regression suite after this change is **1,504 passed, 1 warning**.

The machine-readable evidence is [`results/20261018/repository_state_recheck_20261018.json`](../results/20261018/repository_state_recheck_20261018.json).
