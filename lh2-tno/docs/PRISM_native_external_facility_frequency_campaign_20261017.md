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
