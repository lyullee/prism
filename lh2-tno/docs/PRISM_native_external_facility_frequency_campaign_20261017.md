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
all 24 cases executed through the consequence path. The resulting 13
operator-limited records remain explicit withheld assessments; they are not
converted to zero risk. Eleven cases have a fully closed diagnostic consequence
chain. The 100% tank opening uses the previously validated inventory-depletion
packet because both tank solvers lose finite positive pressure at that declared
full-bore geometry; this fallback is recorded in the catalog audit.

The corresponding `verification.json` therefore reports
`matched_event_case_record_count=24`,
`matched_event_executed_case_count=24`,
`matched_event_failed_case_count=0`,
`matched_event_withheld_case_count=13`,
`conditional_diagnostic_facility_risk_available=true`, and
`facility_qra_claim=false`. This is a coverage and handoff audit, not a claim
that the generic facility has a complete annual IR/F-N result. The next
qualification step is to replace the remaining operator-limited provider
branches with provider-owned closure evidence and independently validate the
consequence boundaries before promoting them.
