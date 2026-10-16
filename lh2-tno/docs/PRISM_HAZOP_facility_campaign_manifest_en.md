# PRISM HAZOP-to-facility campaign manifest

PRISM can replay a multi-branch HAZOP campaign from one JSON object. This is
the handoff format for a digital-twin coordinator that already evaluated the
current plant state and selected the applicable HAZOP branches.

Run it with:

```powershell
python scripts/run_hazop_facility_campaign_manifest.py `
  --manifest examples/my_hazop_facility_campaign_manifest.json `
  --output results/my_campaign_result.json
```

The manifest must contain these fields:

```json
{
  "schema_version": "prism.hazop.facility_campaign_manifest.v1",
  "runtime_result": {},
  "annual_conditions": [],
  "scenario_bindings": [],
  "branch_probabilities": {
    "TK-01|receiving-deviation": 1.0
  },
  "branch_partition_groups": {
    "TK-01|receiving-deviation": "receiving-mode"
  },
  "expected_component_ids": ["TK-01"]
}
```

`runtime_result` is the evaluated HAZOP runtime payload. Each selected branch
must already contain a provider-resolved release boundary, explicit
termination/inventory information, ignition probabilities, and a literature
risk atom. `annual_conditions` supplies reviewed weather and population rows.
`scenario_bindings` attaches the selected HAZOP scenario to its event, asset,
annual condition, release branch, ignition branches, and scenario family.

Branch probabilities are never learned from sensor values or inferred from the
number of HAZOP rows. They must close to one within each named partition group.
The key is always `component_id|hazop_scenario_id`. A bare scenario ID is
accepted only when it is unique across the facility; a reused or ambiguous ID
fails closed. This prevents two tanks or two operating modes with the same
local scenario label from sharing a frequency by accident.

The resulting JSON contains the branch campaigns, the combined conditional
facility ledger, HAZOP identity trace, equipment state-to-release audit, and
risk-atom chain audit. The result remains diagnostic/operator-limited until
provider qualification, independent physical validation, and declared facility
scope gates are closed. This command does not promote a conditional IR/F-N sum
to qualified facility QRA.

## Integration sequence

1. Send normalized equipment state and operating mode to the HAZOP runtime.
2. Keep the runtime result, annual conditions, scenario bindings, and explicit
   branch partitions in one manifest.
3. Run the command above and store the output with the input digest.
4. Use the returned `facility_ledger` and audit records to decide whether the
   result can be shown to an operator or must remain withheld.

For Python integration, call
`lh2_tno.hazop_campaign.build_hazop_facility_campaign_branches_from_manifest`
directly. It performs the same checks without file I/O.
