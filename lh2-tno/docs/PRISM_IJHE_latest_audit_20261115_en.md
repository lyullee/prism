# PRISM IJHE Readiness Audit — 15 November 2026

This document is the English companion to the latest PRISM readiness record. It describes the current **generic outdoor liquid-hydrogen (LH2) facility** scope. Inspection-center data are used only as state, operating-mode, and HAZOP diagnostics; they are not converted into accident frequencies or qualified release packets.

## Current result

The latest audit is `INCOMPLETE_EVIDENCE` with **49 checks: 45 pass and 4 blocked**. The conditional calculation chain is connected, but the strict evidence gates remain closed. The repository therefore does not claim a completed facility QRA or independent full-chain physical validation.

| Item | Current evidence |
|---|---:|
| HAZOP-bound events | 34/34 |
| Numerical cases | 44 |
| Risk atoms reaching the facility ledger | 176 |
| Exact native packet matches | 24/24 |
| Frequency-port binding | 44/44 |
| Cases with event-level P05/P95 | 35/44 |
| Cases with point rate only | 9/44 |
| Numerically closed cases | 42/44 |
| Strict release-boundary eligible cases | 13/44 |
| Facility IR/F-N promotion | `false` |
| Frequency inference or sensor learning | `false` |

The nine point-rate-only events retain their published point rate and are represented in the five-scenario sensitivity ledger. PRISM does not invent confidence intervals for them.

## Connected calculation path

```text
equipment state + operating mode
        -> HAZOP deviation and scenario identity
        -> literature frequency and explicit release port
        -> provider release history
           (duration, isolation, inventory depletion, residual mass)
        -> SLABx-LH2 / declared consequence backend
        -> weather, ignition, population and protection branches
        -> conditional damage atoms and IR/F-N ledger
```

The current-state monitor can consume a cached or already-computed provider result for low latency. The predicted-state path runs the same gate when the simulation reaches a declared risk condition. A fresh physics call is never described as a 1 Hz calculation merely because the cache path meets a 1 Hz service target.

## Strict blockers

1. The release boundary is not closed for every declared case. A row marked `ELIGIBLE` only has a closed numerical termination ledger; it is not a qualified provider result.
2. No facility case currently has an externally qualified provider release packet and qualification sidecar.
3. Independent physical-validation evidence for the complete release-to-dispersion-to-damage chain is not available. The SLABx-LH2 evidence is restricted component evidence.
4. Facility-wide IR/F-N remains withheld while the scope and provider gates are open.

Unsupported or incomplete accident families remain explicitly `PARTIAL`, `BLOCKED_REVIEW`, or `UNCOMPUTED`. PRISM does not replace a missing family with a similar family and does not treat an omitted family as zero risk.

## Frequency policy

Initiating frequencies come from the reviewed literature catalogue and are bound to an event and release port. They are not learned from sensor alarms or normal-operation time series. When a source supplies a marginal P05/P95 interval, it is preserved with its statistic and source digest. When it supplies only a point rate, the missing interval is reported and sensitivity is used instead. Frequency is applied once per initiating event; a provider packet never creates a new annual frequency.

## Processing-time policy

The realtime benchmark separates cached results from fresh physics. Cached monitor evaluation meets the declared low-latency target in the stored benchmark; fresh provider/consequence calculations are slower and are intended for background or risk-triggered execution. Each case records wall time and quantitative-evaluation time so that a deployment can set a deadline without silently substituting an old result.

## Reproduce the current metadata check

Run from the package directory:

```powershell
python scripts/verify_latest_ijhe_audit.py `
  --scope-matrix results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/scope_matrix.json `
  --release-boundary results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json `
  --output results/20261115/latest_ijhe_audit_verification.json
```

The current verification result is `PASS` with zero metadata-consistency blockers. This verifier confirms that the latest status pointers and gate counts agree; it does not promote provider qualification, physical validation, or facility IR/F-N.

The full local regression suite currently reports **1,264 passed and 1 warning**. The warning is a Python 3.14 deprecation warning from `pytest-asyncio` and is separate from a failing contract.

## Evidence needed for a strict IJHE claim

For each facility case, provide an exact asset/port identity, initial state, time-resolved release history, isolation command and response, termination basis, mass/energy residuals, and a qualification sidecar. Separately provide an independent holdout comparison for the relevant source and consequence domains, plus reviewed receptor geometry, weather, ignition, and population data. Once those records are supplied, the existing fail-closed gates can be rerun without changing the frequency or consequence algorithms.
