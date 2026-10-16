# PRISM native multi-equipment facility campaign

This diagnostic demonstrates the facility-level handoff for two different
liquid-hydrogen equipment models in one outdoor manifest:

* a native `MappedPump` liquid packet at `liquid-transfer-pump-01`, and
* a native compressible-plane valve packet at `transfer-valve-01`.

The packets are consumed as provider-owned release histories. The PRISM
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
