# Forecast facility campaign evidence gate

The forecast HAZOP scan and the quantitative handoff produce a worklist. They
do not prove that a facility risk calculation can be run. The evidence gate is
the explicit boundary between that worklist and a downstream facility
campaign.

## Run the gate

First audit the exact request keys:

```powershell
python scripts/audit_forecast_quantitative_evidence.py `
  --handoff results/20261115/inspection_center_facility_forecast_quantitative_handoff.json `
  --attachments examples/inspection_center_forecast_evidence_pending.json `
  --output results/20261115/inspection_center_facility_forecast_evidence_coverage.json
```

Then build the gate:

```powershell
python scripts/build_forecast_facility_campaign_gate.py `
  --coverage results/20261115/inspection_center_facility_forecast_evidence_coverage.json `
  --output results/20261115/inspection_center_facility_forecast_campaign_gate.json
```

The gate uses the same exact request identity,
`component_id|scenario_id|forecast_time_s`, as the handoff. It requires every
request to be `EVIDENCE_COMPLETE` and rejects extra attachment keys. A complete
request must contain the provider release boundary and inventory fields, a
reviewed literature frequency range and provenance, the SLABx-LH2 result and
processing time, and the facility population/weather/ignition binding.

## Meaning of the result

`FORECAST_FACILITY_CAMPAIGN_READY_FOR_DOWNSTREAM_BINDING` means the downstream
campaign may receive the reviewed bindings. It does not claim qualified
physics, independent validation, or a qualified facility IR/F-N result.

`WITHHELD_FORECAST_FACILITY_CAMPAIGN_MISSING_QUANTITATIVE_EVIDENCE` means at
least one request is incomplete. The missing case stays visible in
`missing_request_ids`; it is not assigned zero risk, copied from another
component, or silently removed.

The current inspection-centre-derived diagnostic record has two requests and
zero complete evidence records, so its gate is intentionally withheld:
`results/20261115/inspection_center_facility_forecast_campaign_gate.json`.
This is a reproducible evidence boundary for a generic outdoor LH2 facility,
not a claim that the inspection-centre data qualify every facility.

## Integrated runner

When using `run_hazop_integrated_risk()`, pass the coverage audit as
`forecast_evidence_coverage=...` together with forecast campaign bindings. An
incomplete gate returns
`WITHHELD_FORECAST_FACILITY_CAMPAIGN_EVIDENCE_COVERAGE` and prevents the
bindings from entering the facility ledger. A complete gate permits the
existing operator-limited join; it still preserves the no-frequency-inference,
no-sensor-learning, no-physical-validation and no-facility-QRA-promotion
policies.
