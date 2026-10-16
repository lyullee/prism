# Live HAZOP runtime: conditional current-weather F/N

`run_hazop_facility_runtime(...)` is the low-latency bridge for a facility
digital twin. It accepts one verified runtime frame per component, carries the
explicit operating mode into the HAZOP table, dispatches each selected branch
to its equipment release resolver, and sends the returned release through the
existing realtime consequence service. The release packet remains the owner of
release geometry, isolation, duration, and inventory depletion; PRISM does not
infer those values from a sensor signal.

When every accepted branch has an explicit reviewed literature frequency, the
result includes a conditional current-weather individual-risk contribution in
`conditional_current_weather_risk`. A caller may also pass a
`RealtimePopulationBinding` containing an explicit receptor population:

```python
from lh2_tno.hazop import run_hazop_facility_runtime
from lh2_tno.service import RealtimePopulationBinding

result = run_hazop_facility_runtime(
    hazop_table,
    runtime_frames_by_component,
    now_s=clock_s,
    component_bindings=component_bindings,
    release_resolvers=release_resolvers,
    population_binding=RealtimePopulationBinding(
        persons_by_receptor={"worker-zone-1": 12.0},
        provenance="reviewed outdoor receptor ledger",
        source_digest="<64-character SHA-256>",
    ),
)
```

The returned `conditional_current_weather_expected_death_fn` is the sum of
the explicit literature frequency, current-weather receptor harm, and supplied
population. It is useful for a response screen and for checking the final harm
side of the live chain:

```text
runtime state + operating mode
  -> HAZOP deviation/scenario
  -> equipment release and termination
  -> SLABx-LH2/TNO consequence
  -> ignition-weighted receptor harm
  -> conditional current-weather IR and expected-death contribution
```

The field is intentionally conditional. `facility_fn_available` remains
`false`, `facility_annual_ir_available` remains `false`, and the promotion
policy remains closed. A missing population ledger, missing literature
frequency, incomplete component set, or multiple active branches produces an
explicit `WITHHELD_*` result. Multiple active HAZOP branches are never added
together without an explicit branch probability.

This output is not a replacement for the annual facility campaign. A complete
facility IR/F-N result still requires the declared outdoor accident families,
all annual weather and ignition branches, qualified provider packets,
independent physical validation, and reviewed receptor/protection data.
