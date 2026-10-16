# PRISM per-branch provider identity handoff

## Why this boundary matters

A monitoring point can sit at a shared process boundary while the active HAZOP
rows refer to different physical models. For example, a high-pressure row may
belong to a storage-tank model while a simultaneous liquid two-phase row may
belong to a transfer-line model. Reusing the first provider ID for both rows
would make the release history look complete while connecting one accident to
the wrong equipment.

## Implemented contract

`FacilityRealtimeBinding.provider_component_ids_by_scenario` is an explicit
map from the selected `scenario_id` to the provider component ID. When the map
is present, `run_hazop_facility_runtime()` creates a separate translated state
frame and request template for every mapped scenario. The resolver remains
keyed by `(observed_component_id, scenario_id)`, and the provider response is
checked against the mapped provider ID.

The branch result retains the observed HAZOP component, scenario ID, provider
identity, release termination, consequence output, and frequency binding as
separate evidence. If a selected scenario has no map entry, its result is
`WITHHELD_PROVIDER_IDENTITY_MAPPING`. PRISM never copies another branch's
identity or infers one from a name, tag, position, or geometry.

## Example

```python
FacilityRealtimeBinding(
    component_id="shared-boundary",
    template=template,
    monitor=monitor,
    normalizer=normalizer,
    pressure_tag="PT-01",
    temperature_tag="TT-01",
    provider_component_ids_by_scenario={
        "row-vessel:receiving:vessel_hole": "tank-model-01",
        "row-liquid:receiving:liquid_two_phase": "transfer-line-model-01",
    },
)
```

The scenario-specific frequency map remains independent:
`scenario_frequency_bindings` maps each scenario ID to its reviewed literature
event. Provider identity and initiating frequency therefore cannot be reused
merely because two rows came from the same sensor boundary.

## Verification

- `tests/test_hazop.py` verifies two active branches using different provider
  IDs and verifies that a missing map entry is withheld.
- The complete local suite passes (`1272 passed, 1 warning`).
- The existing three-component header-bound replay still evaluates all three
  branches and remains diagnostic-only; facility annual IR/F-N promotion is
  still false.

This closes an interface ambiguity. It does not qualify external provider
packets, supply independent physical validation, or turn a monitoring snapshot
into a complete facility QRA.
