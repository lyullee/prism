# Native external LH2 facility frequency campaign (2026-10-17)

PRISM now has a reproducible diagnostic campaign that binds seven native
external `lh2dt` equipment packets to one generic outdoor LH2 facility
frequency plan. The campaign is deliberately separate from provider
qualification: it proves the packet identity, frequency-event match and
consequence handoff, while keeping the strict facility QRA gate closed.

Run it from the package directory with:

```powershell
python scripts/run_native_provider_facility_campaign.py `
  --packets `
    .tmp_native_external_facility_packets_20261017/tank/resolved_release.json `
    .tmp_native_external_facility_packets_20261017/pipe/resolved_release.json `
    .tmp_native_external_facility_packets_20261017/valve/resolved_release_with_handoff.json `
    .tmp_native_external_facility_packets_20261017/pump/resolved_release.json `
    .tmp_native_external_facility_packets_20261017/vaporizer/resolved_release_with_handoff.json `
    .tmp_native_external_facility_packets_20261017/reliquefier/resolved_release_with_handoff.json `
    .tmp_native_external_vent_emergency_20261017/resolved_release.json `
  --request-context examples/compressible_plane_chain_context.json `
  --manifest examples/generic_lh2_full_scope_manifest.json `
  --frequency-plan examples/generic_lh2_full_scope_frequency_plan.json `
  --annual-conditions examples/generic_lh2_full_scope_annual_conditions.json `
  --backend-config results/20261009/equipment_campaign/backend_config.json `
  --hazop-event-mode-binding results/20261112/native_isolation_catalog_facility_chain_hazop_mode/hazop_event_mode_binding.json `
  --output-dir results/20261017/native_external_facility_frequency_campaign_20261017 `
  --maximum-physics-cases 30
```

The seven packets are one tank shell opening, one transfer-line opening, one
valve opening, one pump case, one vaporizer case, one reliquefier case, and one
pressure-relief emergency discharge. The ordinary accidental-leak packets are
matched by component and exact hole diameter. The relief packet is matched by
component and `maximum_relief_discharge`; it has no random-hole diameter.
Every matched event retains its provider position, release duration, mass
balance and termination basis before the request is passed to the consequence
service. Liquid packets use the SLABx-LH2 liquid path; gas packets use their
explicit compressible handoff where required, while the relief packet uses the
dedicated relief boundary.

The saved verification record is
[`verification.json`](../results/20261017/native_external_facility_frequency_campaign_20261017/verification.json).
It records 7 matched and executed events out of 24 catalogue events, 17
uncomputed opening bins, 28 conditional diagnostic risk atoms, and an end to
end matched-event chain closure. The uncomputed bins remain `UNCOMPUTED`; they
are never treated as zero risk. The campaign took about 40 s in the recorded
run.

The result is diagnostic only. The packets, facility geometry, weather,
ignition and population are synthetic or declared-sensitivity inputs;
`provider_packet_promoted`, `physical_validation_claim`, and
`facility_qra_claim` are all false. The campaign does not learn frequency from
sensor alarms, does not fill missing opening bins, and does not publish a
facility-wide annual IR/F-N total. Independent provider qualification,
SLABx-LH2 validation and complete facility release-boundary evidence remain
required before promotion.

## Rechecked current record (2026-11-15)

The current packet set is saved under
`results/20261115/native_external_facility_packets_current/` and was replayed
with the same facility manifest, weather/ignition context, population and
frequency plan into
`results/20261115/native_external_facility_campaign_current/`. The replay
matched and executed 7 of the 24 literature events, retained 17 `UNCOMPUTED`
opening bins, produced 28 conditional risk atoms, and evaluated three
literature-frequency scenarios. Four of the seven dynamic equipment packets
carry the provider-owned state-closure digest; the valve and relief rows are
kept as explicit diagnostic/operator-limited boundaries.

The conditional diagnostic facility IR/F-N view is available in
`facility_assessment.json`, while `verification.json` records
`facility_total_risk_available=false` and `facility_qra_claim=false`. No
missing event is assigned zero risk, and no provider qualification,
independent physical validation, or facility-wide promotion is inferred.

The replay also consumes the reviewed HAZOP event-mode record at
`results/20261112/native_isolation_catalog_facility_chain_hazop_mode/hazop_event_mode_binding.json`.
All 24 catalogue events were matched by exact event ID, component ID, and
release mode (`bound_event_count=24`, `unbound_event_count=0`). The selected
`receiving`, `supply`, or `standby` mode and its `hazop_scenario_id` are carried
on the event route and on the seven executed case/risk-atom chains. This is a
label binding only: it does not change the literature frequency or release
physics, and the campaign still withholds facility-wide QRA promotion. If the
binding file is omitted, modes remain absent; no mode is inferred from a
component name, pressure, or leak size.

### Current clean-source HAZOP binding

The old 2026-11-12 binding is retained as historical evidence. It contains an
earlier `instantaneous_inventory` label for vaporizer G1 and must not be reused
with the current bounded `inventory_over_600s` packet. The reproducible current
binding is generated directly from the reviewed frequency plan:

```powershell
python scripts/build_hazop_event_mode_binding_from_frequency_plan.py `
  --frequency-plan results/20261115/native_external_facility_full_scope_campaign_current/frequency_plan.json `
  --output results/20261115/native_external_facility_full_scope_campaign_current/hazop_event_mode_binding_clean_source.json
```

The generated file has 24 exact rows and is consumed by the clean external
source replay. The generator fails closed when an event lacks an explicit
component, release mode, operating mode, or HAZOP scenario ID. It performs no
mode inference and does not change frequency, provider qualification, physical
validation, or the facility-QRA gate.

## Full-scope packet replay (2026-11-15)

The tracked full-scope replay is saved under
`results/20261115/native_external_facility_full_scope_packets_current/` and
was evaluated into
`results/20261115/native_external_facility_full_scope_campaign_current/`.
It contains all 24 reviewed event packets: five storage-tank openings, five
transfer-line openings, five transfer-valve openings, one relief discharge,
two pump cases, three vaporizer cases, and three reliquefier cases including
two-sided rupture sets. Every packet matched a frequency event and received a
case record. After regenerating the packets with the manifest port coordinates,
all 24 cases executed through the consequence path. The resulting 11
operator-limited records remain explicit withheld assessments; they are not
converted to zero risk. Thirteen cases have a fully closed diagnostic
consequence chain. The 100% tank opening uses the previously validated
inventory-depletion packet because both tank solvers lose finite positive
pressure at that declared full-bore geometry; this fallback is recorded in the
catalog audit.

The ambient-vaporizer G1 packet was separately rechecked after the provider
reached atmospheric zero flow while retaining inventory. PRISM now rejects
that state as false `inventory_depletion` evidence. G1 is replayed as an
explicit `inventory_over_600s` bounded history, with the frequency event,
HAZOP release-mode binding, provider packet, and consequence case updated
together. The residual inventory remains visible and the case is diagnostic;
it is not promoted to a full-depletion claim.

The corresponding `verification.json` therefore reports
`matched_event_case_record_count=24`,
`matched_event_executed_case_count=24`,
`matched_event_failed_case_count=0`,
`matched_event_withheld_case_count=11`,
`conditional_diagnostic_facility_risk_available=true`, and
`facility_qra_claim=false`. The regenerated `facility_assessment.json` now also
lists the strict QRA blocking reasons directly: incomplete declared scope,
withheld/non-EXECUTED case traces, absent qualified provider promotion, and
absent independent physical-validation evidence. This is a coverage and handoff audit, not a claim
that the generic facility has a complete annual IR/F-N result. The next
qualification step is to replace the remaining operator-limited provider
branches with provider-owned closure evidence and independently validate the
consequence boundaries before promoting them.

## Current scope and evidence-request records

The full-scope replay now also writes a [`scope_matrix.json`](../results/20261115/native_external_facility_full_scope_campaign_current/scope_matrix.json)
and a [`facility_evidence_request.json`](../results/20261115/native_external_facility_full_scope_campaign_current/facility_evidence_request.json).
The matrix covers all 12 declared outdoor accident families and retains nine
family-level blockers, including `NO_EVENT_GENERATED` rows; an unsupported
family is never silently assigned zero frequency. The evidence request contains
24 exact case requests and 12 family requests, with 11 requests currently
marked `EXECUTED_OPERATOR_LIMITED`. Each request preserves the event,
component, port, operating-mode/HAZOP identity and required provider evidence.
Its promotion policy continues to forbid frequency inference from sensors and
keeps facility QRA promotion closed until the provider and validation gates are
actually satisfied.

The packet qualification readiness audit is saved in
[`provider_qualification_readiness.json`](../results/20261115/native_external_facility_full_scope_campaign_current/provider_qualification_readiness.json).
It finds 24 packet candidates and 13 exact strict diagnostic matches, but zero
qualified provider packets. The exact matches remain `BLOCKED_REVIEW` because
qualification sidecars and independent physical-validation evidence are absent;
the remaining candidates are retained as non-promoted packet evidence. This
audit does not turn an exact digest match into a qualified accident release.

Processing-time evidence is saved in
[`processing_time_summary.json`](../results/20261115/native_external_facility_full_scope_campaign_current/processing_time_summary.json).
The 24-case fresh-physics replay took 814,290.39 ms in total; case p95 was
105,548.90 ms and the slowest case was 143,849.69 ms. These are offline
campaign measurements. The cached monitoring path has a separate
`cached_diagnostic_1hz` contract, and this replay does not claim fresh-physics
1 Hz operation.

The next evidence intake is compiled in
[`provider_qualification_requests.json`](../results/20261115/native_external_facility_full_scope_campaign_current/provider_qualification_requests.json).
It contains 24 identity-preserving requests. Although the readiness audit found
13 exact diagnostic matches, the request builder independently checks the
family-specific termination ledger. The current catalog has 7
qualification-only requests and 19 requests that first need release-closure
evidence and then qualification evidence. A bounded horizon or an
emergency-relief packet without its setpoint/capacity and end-event evidence is
placed in the latter group. The catalog is an intake worksheet,
not a promotion step. It keeps qualified-provider count at zero and leaves
frequency inference, independent physical validation and facility QRA disabled.

A fillable sidecar manifest is also generated at
[`provider_qualification_sidecar_manifest_template.json`](../results/20261115/native_external_facility_full_scope_campaign_current/provider_qualification_sidecar_manifest_template.json).
It contains 26 release identities grouped from the 24 event rows, preserves
source/result digests and packet indexes, and gives each identity a placeholder
sidecar path. Placeholder paths are never treated as evidence; a reviewed
`prism.provider_qualification_evidence.v1` file is required before the audit can
qualify a provider packet.

The native request catalog is audited directly by
`scripts/audit_native_full_scope_provider_qualification.py`. The current audit
record is
`results/20261115/native_external_facility_full_scope_campaign_current/provider_qualification_audit.json`: 24 event rows and 26 release identities are checked, all 26 sidecars are currently missing, and the qualified-provider count is zero. An exact sidecar match would still remain diagnostic until its release-closure status and independent validation evidence are present.

The audit is consumed by a derived assessment at
`results/20261115/native_external_facility_full_scope_campaign_current/facility_assessment_provider_qualification_current.json`. This assessment reuses the saved risk ledger and frequency scenarios, adds the native qualification gate, and keeps `qualified_facility_qra_available=false` when the audit has no qualified packets. It does not rerun physics or modify risk atoms.

### Clean-source isolation replay

The clean external-source replay was repeated with the provider isolation
branch enabled after correcting the valve adapter's split-step horizon
accounting. The packet catalog and facility campaign are recorded under
`results/20261115/native_external_facility_full_scope_clean_source_isolation_replay_20261017/`.
All 24 event identities matched and executed, with 0 uncomputed cases, 0
failed cases, 96 diagnostic risk atoms, and five transfer-valve opening bins
confirming the provider's declared zero-flow observation. The replay took
388,256.043 ms offline. The result remains diagnostic: field isolation
reliability, provider qualification, independent physical validation,
facility IR/F-N and facility QRA are still withheld.
