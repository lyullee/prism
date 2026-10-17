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

The latest audit is `INCOMPLETE_EVIDENCE` with **57 checks: 52 pass and 5 blocked**. The metadata verifier passes, but the strict evidence gates remain closed. The repository therefore does not claim a completed facility QRA or independent full-chain physical validation.

SLABx-LH2 is now treated as a validated consequence-model component. The
current source recheck records 5/5 checks passing, six FFI cases, six FLACS
comparison rows, a pool-radius median ratio of 1.0305, a maximum mass residual
of `1.77e-12 kg`, and zero repeat-run inventory difference. No additional SLABx
validation task is open. Full facility release-to-damage validation remains a
separate gate because it depends on qualified equipment release histories and
site-specific boundary data.

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

These closure counts are intentionally different views of the same 44-case
union. The release-boundary audit reports 42/44 numerically closed and 2/44
numerically open; its stricter promotion gate accepts 13/44 cases. The facility
assessment release ledger separately reports 15 complete rows and 29
`EXECUTED_OPERATOR_LIMITED` rows. The latter is the state used for the
conditional facility view and is not a provider-qualification result. No count
is silently substituted for another.

The conditional facility chain has 44 evaluated cases and 176 risk atoms. The
risk-atom chain audit finds all 44 cases complete across the required source,
pool, near-field/dispersion, cloud-observation, and fire/explosion-damage
stages, with no missing or duplicate atom. At the declared 20 m worker
receptor, all 176 atoms have zero harm in this union, so the conditional IR/F-N
arrays contain no positive point. This result is retained as a geometry-bound
diagnostic output; the qualified facility IR/F-N claim remains withheld.

The unified facility-QRA gate summary is now bound to the same authoritative
34-event/44-case union assessment and scope matrix:
[`facility_qra_gate_summary.json`](../results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_qra_gate_summary.json).
It reports `FACILITY_QRA_WITHHELD` with five incomplete gates and 50 explicit
blocking reasons. The summary is a structural promotion control; it does not
convert the conditional IR/F-N ledger into a qualified facility QRA.

The current release-closure worklist also joins the case-level boundary audit
by the explicit `event_id × annual_condition_id × release_branch_id` key. Its
44/44 join reproduces 42 numerically closed cases, 2 numerically open cases,
29 operator-review cases, 42 valid and 2 invalid termination-evidence rows,
and 13 strict-boundary-eligible cases. A missing or duplicate join is reported
as unmatched; no duration, isolation, inventory, frequency, or qualification
value is inferred.

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

An additional digest-bound record now captures restricted anonymized model
validation from `sci_minimal_release_packet.json`. It reports blind, held-out
validation for 3 independently scored units out of 12 declared units, with an
observed-unit macro accuracy of 95.4155462264504 percent. The unscored units are
not imputed and the full-unit target remains false. This is process-state model
evidence only: it does not qualify an accident-release provider, supply a
literature frequency, close facility IR/F-N, or establish independent
end-to-end physical validation. The promotion boundary is recorded in
[`external_anonymized_model_validation_summary.json`](../results/20261115/external_anonymized_model_validation_summary.json).

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

For accidental gas, liquid, and two-phase source histories, the code now has an explicit
`prism.provider_dynamic_state_closure.v1` opt-in. It requires provider-owned
pressure and inventory feedback flags, a state-history digest, bounded
residuals, and a closed initial/final/outgoing mass ledger before the source
can be considered closure-ready for qualification. The campaign status is not
silently relabelled. The current native campaign contains 20 release identities with
this packet-level closure evidence and 6 identities that still need a release
closure response. Those 20 identities are therefore issued qualification-only
requests; the remaining 6 receive closure-and-qualification requests. This
classification does not create a qualification sidecar or open the facility
QRA gate. The
normal operating-vent path remains outside this accident-state gate. The
contract and integration example are documented in
[`PRISM_dynamic_liquid_state_closure_contract_en.md`](PRISM_dynamic_liquid_state_closure_contract_en.md).

A subsequent external-model recheck confirms that the latest local checkout
(`lh2dt_models` commit `16f7a4b`) and its 22-packet full-scope root contain 13
packets with the same closure record. A three-branch header-bound replay using
the latest tank, relief, and vaporizer packets executed all three selected
consequence paths; the tank and vaporizer branches were closure-ready, while
the emergency-relief branch remained without a dynamic-state field. This is a
candidate replay and does not change the strict IJHE blockers or promote
facility IR/F-N. See [`external model change recheck`](PRISM_external_model_change_recheck_20261018_en.md).

## Strict blockers

1. The release boundary is not closed for every declared case. Only 13 of 44 cases are currently strict-boundary eligible; 29 require operator review and 2 remain numerically open.
2. No facility case currently has an externally qualified provider release packet and qualification sidecar. The 42 valid termination-evidence rows are diagnostic closure evidence, not provider qualification.
3. Independent physical-validation evidence for the complete facility release-to-dispersion-to-damage chain is not available. This is a facility/provider gate; it is not an open SLABx component-validation task.
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

For the current 44-case facility diagnostic campaign, fresh physics has a
case median/p95/p99 of **2.193/10.400/12.738 s**. The three-campaign wall
totals have median/p95/p99 of **19.298/134.471/144.709 s**. These values
exclude the cached monitor path and do not support a 1 Hz fresh-physics claim.


## Reproduce the current metadata check

Run from the package directory:

```powershell
python scripts/verify_latest_ijhe_audit.py `
  --scope-matrix results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/scope_matrix.json `
  --release-boundary results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json `
  --facility-qra-gate-summary results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_qra_gate_summary.json `
  --output results/20261115/latest_ijhe_audit_verification.json
```

The current verification result is `PASS` with zero metadata-consistency blockers. This verifier confirms that the latest status pointers and gate counts agree; it does not promote provider qualification, physical validation, or facility IR/F-N. The saved facility assessment now consumes the validation-evidence matrix explicitly: its physical-validation gate is `RESTRICTED_EVIDENCE_MATRIX` with decision `FACILITY_QRA_WITHHELD`, and its `physical_validation_gate_complete` flag is `false`.

The current status ledger records **1,496 passed and 1 warning** for the full local regression suite. The warning is a Python 3.14 deprecation warning from `pytest-asyncio` and is separate from a failing contract. Re-run the suite before publication because the stored count is provenance, not a substitute for a fresh run.

The current validation matrix includes the hash-reverified PRESLHY Trial 10
outdoor observation bundle and a measured-source SLABx comparison. It is
recorded as restricted component evidence: 4,960 of 5,053 receptor rows were
matched, while the diagnostic replay produced RMSE 31.10 vol% and a zero
predicted peak against an 87.78 vol% observed peak. The mismatch and the
unresolved source-relative axis definition are retained as validation blockers;
the record does not support independent physical-validation or facility-QRA
promotion.

The latest provider collection manifest is `examples/provider_packet_collection_manifest_current.json` (generated from the latest 2026-11-15 evidence request). It contains 44 exact case rows, all currently `OPEN`; it is an intake worksheet and contains no provider release or qualification result. The facility request and sidecar template are now checked by `facility_provider_intake_audit.json`, which reports `ALIGNED_TEMPLATE_ONLY` with 44/44 entries. This alignment check does not qualify a provider packet or open facility QRA.

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

The current worklist can also join the case-level boundary audit with the
explicit `event_id × annual_condition_id × release_branch_id` key:

```powershell
python scripts/build_release_closure_worklist.py `
  --facility-assessment results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json `
  --facility-evidence-request results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_evidence_request.json `
  --release-boundary-case-audit results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json `
  --output results/20261115/release_closure_worklist_current.json
```

This join is observational: it reports 44/44 matched cases and exposes the
42/44 numerical closure, 2/44 numerical-open, 29/44 operator-review, 42 valid
and 2 invalid termination-evidence, and 13/44 strict-boundary-eligible counts.
It does not infer a missing boundary or promote a provider.

The union evidence binder now passes the uncertainty ledger, provider worklist,
adapter registry, facility assessment, and domain-recovery record by named
arguments. This prevents a long optional-argument call from silently treating a
provider worklist as frequency evidence. The regression contract is
`tests/test_bind_native_full_scope_union_evidence.py`; when rebuilding a union,
include `--domain-recovery-audit results/20261024/domain_recovery_audit_flammability_gate_v2.json`.

## Frequency-uncertainty evidence

The authoritative `facility_frequency_uncertainty_audit.json` closes the
diagnostic sensitivity ledger for **five explicit literature scenarios** with
zero recomputation mismatches across 176 risk atoms. It includes central,
literature P05/P95, and independent event-bound P05/P95 scenarios; 34 events
use independent bounds and nine events retain fixed catalogue rates. The record
sets `frequency_inference_performed=false`, `facility_credible_interval=false`,
and `provider_packet_promoted=false`. Thus the calculation reports literature
frequency sensitivity without learning frequencies from sensors or normal
operation data.

## Evidence needed for a strict IJHE claim

For each facility case, provide an exact asset/port identity, initial state, time-resolved release history, isolation command and response, termination basis, mass/energy residuals, and a qualification sidecar. Separately provide an independent holdout comparison for the relevant source and consequence domains, plus reviewed receptor geometry, weather, ignition, and population data. Once those records are supplied, the existing fail-closed gates can be rerun without changing the frequency or consequence algorithms.
