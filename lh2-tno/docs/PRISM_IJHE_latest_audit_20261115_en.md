# PRISM IJHE Readiness Audit — current union evidence

This document is the English companion to the latest PRISM readiness record. It describes the current **generic outdoor liquid-hydrogen (LH2) facility** scope. Inspection-center data are used only as state, operating-mode, and HAZOP diagnostics; they are not converted into accident frequencies or qualified release packets.

## Current result

The latest audit is `INCOMPLETE_EVIDENCE` with **54 checks: 49 pass and 5 blocked**. The metadata verifier passes, but the strict evidence gates remain closed. The repository therefore does not claim a completed facility QRA or independent full-chain physical validation.

| Item | Current evidence |
|---|---:|
| HAZOP-bound events | 34/34 |
| Numerical cases | 44 |
| Risk atoms reaching the facility ledger | 176 |
| Exact native packet matches | 24/24 |
| Frequency-port binding | 44/44 |
| Numerically closed cases | 42/44 |
| Numerically open cases | 2/44 |
| Cases requiring operator review | 29/44 |
| Strict release-boundary eligible cases | 13/44 |
| Provider termination evidence | 42 valid, 2 invalid |
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

1. The release boundary is not closed for every declared case. Only 13 of 44 cases are currently strict-boundary eligible; 29 require operator review and 2 remain numerically open.
2. No facility case currently has an externally qualified provider release packet and qualification sidecar. The 42 valid termination-evidence rows are diagnostic closure evidence, not provider qualification.
3. Independent physical-validation evidence for the complete release-to-dispersion-to-damage chain is not available. The SLABx-LH2 evidence is restricted component evidence.
4. Facility-wide IR/F-N remains withheld while the scope and provider gates are open.

The two counts above answer different questions: **42/44** means the numerical
release/consequence trace reached a closed diagnostic result with valid provider
termination evidence; **13/44** means the stricter promotion gate also accepts
the case for facility release-boundary evidence. Operator-limited cases are kept
in the conditional ledger and are never silently promoted to the latter count.

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

The current status ledger records **1,332 passed and 1 warning** for the full local regression suite. The warning is a Python 3.14 deprecation warning from `pytest-asyncio` and is separate from a failing contract. Re-run the suite before publication because the stored count is provenance, not a substitute for a fresh run.

The latest provider collection manifest is `examples/provider_packet_collection_manifest_current.json` (generated from the latest 2026-11-15 evidence request). It contains 44 exact case rows, all currently `OPEN`; it is an intake worksheet and contains no provider release or qualification result.

The union evidence binder now passes the uncertainty ledger, provider worklist,
adapter registry, facility assessment, and domain-recovery record by named
arguments. This prevents a long optional-argument call from silently treating a
provider worklist as frequency evidence. The regression contract is
`tests/test_bind_native_full_scope_union_evidence.py`; when rebuilding a union,
include `--domain-recovery-audit results/20261024/domain_recovery_audit_flammability_gate_v2.json`.

## Evidence needed for a strict IJHE claim

For each facility case, provide an exact asset/port identity, initial state, time-resolved release history, isolation command and response, termination basis, mass/energy residuals, and a qualification sidecar. Separately provide an independent holdout comparison for the relevant source and consequence domains, plus reviewed receptor geometry, weather, ignition, and population data. Once those records are supplied, the existing fail-closed gates can be rerun without changing the frequency or consequence algorithms.
