# Equipment → HAZOP → Quantitative Campaign

`prism.equipment_hazop_quantitative_campaign.v1` is the facility-neutral
integration boundary for an LH2 digital twin. It joins four kinds of evidence:

1. the equipment manifest (component identity, position, ports, phase and
   property basis);
2. measured or predicted runtime frames (including the explicit operating
   mode such as `receiving`, `supply`, or `standby`);
3. the mode-specific HAZOP table; and
4. the provider-bound HAZOP runtime result plus reviewed annual conditions,
   literature frequencies, release/ignition branches, and partition
   probabilities.

The module does not infer any of these values. It first calls
`build_equipment_hazop_mode_handoff`, then checks an explicit
`scenario_identity_crosswalk`. The crosswalk is needed because an HAZOP table
may call a row `high-pressure:receiving:vessel_hole` while an equipment
provider calls the corresponding branch `TK01-high-pressure-receiving`.

## Input contract

The JSON root accepted by
`scripts/run_equipment_hazop_quantitative_campaign.py` has these fields:

| Field | Meaning |
| --- | --- |
| `equipment_manifest` | JSON-compatible `EquipmentManifest` for one outdoor facility |
| `runtime_frames` | `prism.observed_state_runtime_frames.v1`; one frame per declared component |
| `hazop_table_set` | `prism.hazop_runtime_table_set.v1`; one table per component |
| `runtime_result` | `prism.hazop_facility_runtime.v1`; provider-bound evaluated HAZOP branches |
| `annual_conditions` | Explicit weather, population, and annual probabilities |
| `scenario_bindings` | Explicit event, asset, operating-mode, release-branch, and harm bindings |
| `branch_probabilities` | Reviewed probabilities for each `component_id\|scenario_id` branch |
| `branch_partition_groups` | Partition name for each branch; each partition must sum to one |
| `scenario_identity_crosswalk` | Explicit qualitative-to-quantitative scenario ID mapping |
| `expected_component_ids` | Optional exact component set check |

Each crosswalk row has this shape:

```json
{
  "component_id": "TK-01",
  "qualitative_scenario_id": "high-pressure:receiving:vessel_hole",
  "quantitative_scenario_id": "TK01-high-pressure-receiving"
}
```

## Execution

```powershell
python scripts/run_equipment_hazop_quantitative_campaign.py `
  --manifest examples/equipment_hazop_quantitative_campaign.json `
  --now-s 1710000000 `
  --output build/equipment_hazop_quantitative_campaign.json
```

The example is synthetic and is included to demonstrate the schema. It is not
a qualification record for a real terminal or inspection centre.

`EQUIPMENT_HAZOP_QUANTITATIVE_CAMPAIGN_BUILT_OPERATOR_LIMITED` means the
identity boundary passed and the existing quantitative campaign was called.
The campaign can still be diagnostic-only: provider qualification, release
termination evidence, physical validation, and complete facility scope are
checked downstream. The result deliberately keeps
`complete_facility_qra_claim=false` unless the existing strict gates are
closed.

`EQUIPMENT_HAZOP_QUANTITATIVE_CAMPAIGN_BLOCKED` means the system stopped before
dispatch. Typical reasons are an unknown or missing component, a stale frame,
facility ID mismatch, no HAZOP table, selected-mode drift, a missing
crosswalk row, or a quantitative branch that does not exist. The caller must
repair the upstream digital-twin export or provide reviewed evidence; PRISM
does not substitute another component, mode, event, frequency, release size,
weather, or harm map.

## Downstream meaning

After a successful boundary check, the existing campaign carries the selected
scenario through:

`equipment release path → duration/isolation/inventory ledger → SLABx-LH2 or
declared consequence backend → ignition/weather/population/protection →
conditional risk atoms → facility ledger`.

The adapter itself does not execute SLABx-LH2 or learn frequency from sensors.
It preserves the distinction between a current monitoring snapshot and a
predicted simulation state, so an operator can see which branch was evaluated,
what provider packet was consumed, and which strict evidence gate remains
open.

The returned `facility_ledger` exposes that release gate directly through
`provider_release_boundary_case_count` and `provider_release_boundary_ready`.
For provider-backed cases, a false readiness value keeps
`facility_total_risk_available=false` and retains the blocking reason in the
ledger. Diagnostic risk atoms remain available for review, but an open
inventory, invalid isolation clock, or unsupported pressure-equalization claim
cannot enter a facility total through this HAZOP path.

## Multiple equipment in one facility

The same contract is applied independently to every declared component.  For
example, a receiving storage tank and a supply vaporizer can enter the same
facility campaign with different operating modes, HAZOP rows, provider event
IDs, release ports, and quantitative scenario IDs.  The canonical branch key
is `component_id|scenario_id`, so a reused scenario name cannot accidentally
borrow another equipment's release or frequency.  The campaign then retains
one case and its risk atoms per equipment path before the facility ledger sums
the explicit atoms.

The regression test
`test_equipment_hazop_quantitative_campaign_keeps_two_equipment_paths_separate`
exercises this two-equipment contract.  It verifies that `TK-01` remains in
`receiving`, `VAP-01` remains in `supply`, and the two event/asset identities
stay separate.  This is an integration-contract test with synthetic provider
records; it is not evidence that a real terminal's provider packets are
qualified.
