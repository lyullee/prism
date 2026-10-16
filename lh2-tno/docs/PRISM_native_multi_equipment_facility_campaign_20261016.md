# PRISM native multi-equipment facility campaign

This diagnostic demonstrates the facility-level handoff for two different
liquid-hydrogen equipment models in one outdoor manifest:

* a native `MappedPump` liquid packet at `liquid-transfer-pump-01`, and
* a native compressible-plane valve packet at `transfer-valve-01`.

The packets are consumed as provider-owned release histories. Multiple packets
for the same component are allowed when they map to different exact opening
events. The PRISM
frequency catalogue supplies the initiating annual frequency after an exact
component and opening match. Every other opening bin remains `UNCOMPUTED`; it
is never assigned zero risk or silently replaced by a generic release.

## Run

```powershell
python scripts/export_lh2dt_native_mapped_pump_prism_packet.py `
  --lh2dt-root C:\path\to\lh2dt_models `
  --output-dir results/20261016/native_mapped_pump_generic_component_frequency_packet_positioned `
  --component-id liquid-transfer-pump-01 --port-id pump-accident-out `
  --event-id generic-lh2-full-scope-frequency-example/transfer-pump/G2 `
  --failure-opening-diameter-m 0.0025 --position-enu-m 6 0 1 `
  --nozzle-height-m 1.0 --horizon-s 0.2 --time-step-s 0.05 `
  --isolation-time-s 0.1 --post-isolation-observation-s 0.05 `
  --available-mass-kg 1.0

python scripts/run_native_provider_facility_campaign.py `
  --packets `
    results/20261016/native_mapped_pump_generic_component_frequency_packet_positioned/resolved_release.json `
    results/20261016/native_valve_frequency_packet_positioned/resolved_release_with_handoff.json `
  --request-context results/20261009/equipment_liquid_release/request.json `
  --manifest examples/generic_lh2_native_pump_valve_facility_manifest.json `
  --frequency-plan examples/generic_lh2_native_pump_valve_frequency_plan.json `
  --annual-conditions examples/generic_lh2_full_scope_annual_conditions.json `
  --backend-config results/20261009/equipment_liquid_release/backend_config.json `
  --output-dir results/20261016/native_pump_valve_facility_campaign `
  --maximum-physics-cases 20
```

The verification record reports the matched events, executed and withheld
cases, the number of risk atoms, facility IR/F-N availability, and elapsed
time. The example remains diagnostic because the geometry, conditions,
provider qualification, and independent physical validation are not yet
production evidence.

## Independent ledger audit

After the campaign, independently recompute equipment contributions and the
literature-frequency sensitivity from the saved `facility_risk_ledger`:

```powershell
python scripts/audit_native_provider_facility_campaign.py `
  --campaign-result results/20261016/native_pump_valve_facility_campaign/campaign_result.json `
  --facility-assessment results/20261016/native_pump_valve_facility_campaign/facility_assessment.json `
  --output results/20261016/native_pump_valve_facility_campaign/audit.json
```

The recorded result is
`NATIVE_PROVIDER_MULTI_EQUIPMENT_AUDIT_CLOSED_DIAGNOSTIC`. Partial campaigns
are accepted only when withheld event bins are explicit; the audit never treats
those bins as zero risk and never promotes a facility QRA claim. A compact
tracked summary is in
`examples/generic_lh2_native_pump_valve_facility_audit_20261016.json`.

The same audit can be supplied to the IJHE completion-audit builder with
`--native-provider-multi-equipment-audit`. It produces a separate diagnostic
check named `diagnostic_native_provider_multi_equipment_audit: PASS`; the
overall audit remains `INCOMPLETE_EVIDENCE` because the larger facility scope
still has qualified-provider and independent-validation gates.
The tracked IJHE replay summary is
`examples/generic_lh2_native_pump_valve_ijhe_audit_replay_20261016.json`.
