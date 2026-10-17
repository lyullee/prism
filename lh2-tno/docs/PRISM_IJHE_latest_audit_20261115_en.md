# PRISM IJHE Readiness Audit — current union evidence

This document is the English companion to the latest PRISM readiness record. It describes the current **generic outdoor liquid-hydrogen (LH2) facility** scope. Inspection-center data are used only as state, operating-mode, and HAZOP diagnostics; they are not converted into accident frequencies or qualified release packets.

The inspection-centre vent-sequence CSV is now screened into
`results/20261115/inspection_center_operation_sequence_evidence.json` by
`build_inspection_center_sequence_evidence.py`. The sidecar records the
explicit 6.5 bar vent-operation label and the 6.0 bar operational close label
as **owner-review candidates**. It does not assert a certified PSV setpoint,
relief capacity, discharge completion, inventory depletion, or mass closure.
This keeps the sequence useful as HAZOP provenance while leaving the G1
release-boundary request open.

## Current result

The latest audit is `INCOMPLETE_EVIDENCE` with **56 checks: 51 pass and 5 blocked**. The metadata verifier passes, but the strict evidence gates remain closed. The repository therefore does not claim a completed facility QRA or independent full-chain physical validation.

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

The external-model intake now inventories seven release-shaped exports from the
`lh2dt` equipment model root (layered tank, dynamic pipe, mapped pump, valve,
vaporizer, reliquefier, and vent). They carry equipment/port identity and
time-resolved release fields, but all seven are `model_prediction` rows with no
exact qualification sidecar. The intake is therefore a traceability record and
does not open provider, frequency, physical-validation, or facility-QRA gates.
The machine-readable record is
[`external_native_contract_intake_current.json`](../results/20261115/external_native_contract_intake_current.json).

Each of the seven rows now also has a sibling-response normalization audit.
The native `provider_response.json` agrees with its resolved release on the
event/component/port identity, release clock, available and released mass,
termination declaration, provider source digest, and canonical result digest
(`7/7` normalized). The audit retains native mass residuals and isolation
metadata when present, but does not turn a diagnostic horizon into a physical
termination or replace residual inventory with zero. Thus normalization
improves the model-to-PRISM handoff trace while the strict qualification and
facility-QRA gates remain unchanged. See
[`external release-response normalization`](PRISM_external_release_response_normalization_en.md)
for the exact comparison rules.

The same intake now audits the optional compressible-plane handoff inputs.
Four exports have a gas-shaped `mass_flow_kg_s` series: reliquefier and
vaporizer contain the required provider source/throat state in all intervals,
whereas valve and vent are explicitly blocked because their source-state
records are missing (`2 complete`, `2 incomplete`). The adapter therefore
cannot use atmospheric packet velocity as a substitute. Liquid/two-phase
layered-tank, pipe, and pump exports are recorded as outside this optional gas
handoff and are not silently recast as gas.

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
4. The 44 facility cases have no exact qualified-provider packet coverage; the current provider worklist is an evidence request, not a qualified packet catalog.
5. Facility-wide IR/F-N remains withheld while the scope and provider gates are open.

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

The current status ledger records **1,370 passed and 1 warning** for the full local regression suite. The warning is a Python 3.14 deprecation warning from `pytest-asyncio` and is separate from a failing contract. Re-run the suite before publication because the stored count is provenance, not a substitute for a fresh run.

The latest provider collection manifest is `examples/provider_packet_collection_manifest_current.json` (generated from the latest 2026-11-15 evidence request). It contains 44 exact case rows, all currently `OPEN`; it is an intake worksheet and contains no provider release or qualification result.

To reproduce the operation-sequence screening (the source file is external to
the repository), run:

```powershell
python scripts/build_inspection_center_sequence_evidence.py `
  --source "C:\Users\lyul\Desktop\DocuData\액화수소검사지원센터 데이터\2. 액화수소 저장(벤트) 시나리오 데이터\액화수소저장벤트_운전시퀀스.csv" `
  --scenario "액화수소 저장(벤트)" `
  --output results/20261115/inspection_center_operation_sequence_evidence.json
```

The generated record is an input/provenance artifact. It cannot by itself
rebind the provider packet, close the G1 mass ledger, or open facility IR/F-N.

The release-boundary response intake now has a reproducible handoff to the
case-level audit: `validate_release_boundary_evidence_response.py` can emit a
`prism.provider_termination_evidence_catalog.v1` and a re-audited case ledger
in one run.  Only responses that pass the exact identity, digest, mass-balance,
and family-specific stopping checks enter that catalog.  The handoff does not
rebind a campaign packet or rerun SLABx-LH2; a changed provider-result digest
therefore remains blocked until an explicit packet rebind and consequence
rerun are supplied.

The union evidence binder now passes the uncertainty ledger, provider worklist,
adapter registry, facility assessment, and domain-recovery record by named
arguments. This prevents a long optional-argument call from silently treating a
provider worklist as frequency evidence. The regression contract is
`tests/test_bind_native_full_scope_union_evidence.py`; when rebuilding a union,
include `--domain-recovery-audit results/20261024/domain_recovery_audit_flammability_gate_v2.json`.

## Evidence needed for a strict IJHE claim

For each facility case, provide an exact asset/port identity, initial state, time-resolved release history, isolation command and response, termination basis, mass/energy residuals, and a qualification sidecar. Separately provide an independent holdout comparison for the relevant source and consequence domains, plus reviewed receptor geometry, weather, ignition, and population data. Once those records are supplied, the existing fail-closed gates can be rerun without changing the frequency or consequence algorithms.
