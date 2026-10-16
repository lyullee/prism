# Current and forecast HAZOP risk contract

PRISM has two time views of the same LH2 facility:

1. **Current state** comes from measured or historian-bound runtime frames.
2. **Forecast state** comes from an explicit process simulation and carries
   `origin="model_prediction"` plus `forecast_time_s`.

Both views use the same HAZOP table, operating-mode value, component identity,
provider release resolver, and SLABx-LH2 consequence boundary. A predicted
pressure excursion therefore selects the same declared accident family as an
observed pressure excursion. The forecast path does not copy a current result
or silently reuse a provider release.

## One integrated call

```python
from lh2_tno.integrated_risk import run_hazop_integrated_risk

result = run_hazop_integrated_risk(
    hazop_table,
    current_frames=measured_frames,
    forecast_frames=predicted_frames,
    forecast_tables_by_component=tables_by_component,
    component_bindings=component_bindings,
    release_resolvers=release_resolvers,
    population_binding=population_binding,
    now_s=clock_s,
)
```

`current` contains the facility runtime ledger. When every selected branch
has an explicit literature frequency and the population binding is complete,
it may contain a conditional current-weather IR and expected-death F/N
contribution. This is a response-screen result; it is not the all-weather
annual facility F/N curve.

`forecast` contains one row per predicted component and time. A quantitative
evaluator is called only when a new HAZOP condition is reached (`entry`) or at
every active step (`each_step`). The evaluator owns the equipment release,
isolation, inventory termination, SLABx-LH2 run, and any explicitly reviewed
facility handoff.

## Why forecast facility F/N is withheld by default

A predicted component frame is not enough to aggregate a facility risk. The
caller must provide the future-state population/weather/ignition and branch
bindings, and must show which provider packet belongs to each component and
scenario. Until that evidence is supplied, the forecast result reports:

```text
WITHHELD_FORECAST_FACILITY_AGGREGATOR_REQUIRED
```

with `facility_annual_ir_available=false` and `facility_fn_available=false`.
The optional `forecast_facility_campaign_evaluator` in
`run_hazop_integrated_risk` is the explicit handoff point for that future
aggregation. Its output is still guarded against frequency inference,
physical-validation claims, and premature facility-QRA promotion.

## Timing and interpretation

Both paths record invocation timing. The timing is a measured diagnostic for
the supplied input size; it is not a 1 Hz guarantee. A control system may use
the current path for near-real-time response and run forecast steps at the
simulation cadence. A withheld result is a missing-evidence signal, not zero
risk.
