# Generic outdoor-LH2 facility HAZOP handoff

PRISM now ships a facility-neutral replay that demonstrates the digital-twin
boundary for three representative outdoor units: a storage tank, a liquid
transfer line, and a pressure-relief vent. The replay uses one exact forecast
time grid and carries the operating mode with every state frame:

`process state + operating mode -> HAZOP deviation -> scenario ID -> quantitative request`

The example is deliberately separate from the inspection-center data. It is a
generic contract example, not a claim that these thresholds, locations, or
equipment records describe a real site.

## Reproduce the handoff

From the `lh2-tno` directory:

```powershell
python scripts/run_generic_facility_hazop_handoff.py `
  --frames examples/generic_facility_forecast_frames.json `
  --tables examples/generic_facility_hazop_tables.json `
  --current-frames examples/generic_facility_current_frames.json `
  --output results/20261115/generic_outdoor_facility_hazop_quantitative_handoff.json
```

The replay has three components and three predicted times (`0`, `10`, and
`20 s`). At `10 s`, one declared deviation is selected for each component:

| Component | Mode | Deviation | Scenario family |
| --- | --- | --- | --- |
| `storage-tank-01` | `receiving` | high pressure | `vessel_hole` |
| `liquid-transfer-line-01` | `supply` | low flow | `pipe_hole` |
| `pressure-relief-vent-01` | `standby` | high pressure | `vent_hole` |

The output contains three stable request keys of the form
`component_id|scenario_id|forecast_time_s`. Each request lists the exact
downstream evidence required before quantitative evaluation:

- qualified equipment release packet, including release start/end,
  termination, isolation, and inventory fields;
- reviewed literature frequency and uncertainty bounds;
- SLABx-LH2 consequence output; and
- facility weather, ignition, population, and endpoint bindings.

The optional current-state file contains one historian-style frame per
component at the same active deviations. Those selections are written to a
separate current-state worklist with `CURRENT_HAZOP_DEVIATION` request keys.
The current and predicted worklists share the same component, scenario-family,
operating-mode, and evidence contracts, so a control-room monitor and a
process-model forecast can feed the same downstream quantitative adapter.

The output adds `current_evidence_coverage` and `forecast_evidence_coverage`.
Each audit uses the exact request key and checks all four evidence blocks. With
the shipped synthetic inputs and no attachment file, both gates correctly
report `WITHHELD_QUANTITATIVE_EVIDENCE_MISSING` for three requests. Optional
attachment maps can be supplied with `--current-attachments` and
`--forecast-attachments`; extra keys and missing fields remain visible as gate
failures rather than being reassigned or treated as zero risk.

## Provider-bound diagnostic attachment

The generic facility package includes compact evidence summaries for all three
declared HAZOP requests. The tank summary is the explicit liquid/two-phase
diagnostic; the transfer-line and relief-vent summaries are exact joins to one
executed case from the native multi-equipment campaign. Each summary records
the provider-owned duration, isolation/termination and inventory boundary, the
`SLABx_dispersion` and TNO damage stages, conditional risk and timing. The
campaign join is evidence accounting only: it does not qualify the provider or
promote a facility total.

Run the exact-match adapter with all three summaries:

```powershell
python scripts/attach_generic_provider_chain.py `
  --handoff results/20261115/generic_provider_bound_hazop_quantitative_handoff.json `
  --evidence results/20261115/generic_storage_provider_bound_hazop_evidence_summary.json `
  --evidence results/20261115/generic_line_provider_bound_hazop_evidence_summary.json `
  --evidence results/20261115/generic_vent_provider_bound_hazop_evidence_summary.json `
  --output results/20261115/generic_provider_chain_attachment_all_components.json
```

The attachment matches one current and one forecast request per component (six
requests total). Exact component, operating-mode and scenario-family matching
is required; a mismatch fails closed. The provider packets are
synthetic/model-prediction or operator-limited diagnostic evidence, so the
attachment does not claim provider qualification, independent physical
validation, facility IR/F-N closure, or facility QRA. Missing cases are never
assigned zero frequency.

To regenerate a line or vent summary from the campaign evidence, use
`scripts/build_generic_campaign_provider_evidence.py` and provide the campaign
result, the matching `resolved_release.json`, and the exact component/event and
scenario-family identity. The script rejects duplicate or mismatched cases.

The attached provider evidence can be reshaped into the quantitative handoff's
four required blocks with
`scripts/build_generic_quantitative_attachments.py`. Write separate current
and forecast maps, then pass them to `run_generic_facility_hazop_handoff.py`
using `--current-attachments` and `--forecast-attachments`. The resulting
record reports `QUANTITATIVE_EVIDENCE_COVERAGE_COMPLETE` for all six requests,
and adds `current_diagnostic_evaluation` and
`forecast_diagnostic_evaluation` rows. These rows expose the exact provider
release boundary, literature-frequency identity, SLABx-LH2 chain stages,
weather/ignition binding, and processing time already present in the attached
record. Each row also carries `provider_release_boundary_status` and
`provider_release_boundary_blocking_reasons`. For example, the shipped tank
diagnostic declares `inventory_depletion` while retaining a nonzero residual
mass, so its consequence chain remains visible but its release boundary is
marked `BOUNDARY_EVIDENCE_WITHHELD`; PRISM does not silently convert that
residual to zero. A row with a missing annual frequency is explicitly reported as
`CONDITIONAL_CHAIN_ATTACHED_FREQUENCY_VALUE_WITHHELD`; PRISM does not infer a
rate from the state frame. The evaluator reuses attached evidence and does not
run fresh release or consequence physics. Its policy keeps facility IR/F-N
calculation, independent physical validation, and facility-QRA promotion false.
Coverage completeness therefore means that every evidence block is present and
traceable; it does not mean that the provider or facility has been qualified.
If all four evidence blocks are present but the provider termination or
inventory boundary is open, the row is reported as
`WITHHELD_RELEASE_BOUNDARY_EVIDENCE`. The consequence chain remains visible for
diagnostics, while the row is excluded from the attached quantitative-risk
count.

## What this proves and what it does not

The replay proves that a multi-equipment forecast can preserve component
identity and operating mode, select the correct HAZOP row, and produce a
separate quantitative work item for each newly reached condition. When exact
provider-chain evidence is attached, the diagnostic evaluator exposes the
existing consequence result for each matched current and forecast request. It
creates no release packet, does not infer an annual frequency from the
forecast, does not rerun SLABx-LH2, and does not calculate or promote a
facility-wide IR/F-N total.

To use a real digital-twin source, replace the synthetic frame and table files
with reviewed process-model exports. Keep the explicit component IDs, units,
operating modes, forecast origin, and exact time-grid contract. Then attach
qualified provider and facility evidence through the existing forecast
evidence gate before a campaign can enter the facility ledger.
