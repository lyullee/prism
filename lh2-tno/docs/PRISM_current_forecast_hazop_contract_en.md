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

The returned `facility_gate_summary.current` and
`facility_gate_summary.forecast` objects are the compact display contract for
a digital-twin UI. They expose the provider release-boundary case count,
boundary readiness, conditional diagnostic IR/F-N availability, strict
facility-total availability, and qualified-QRA availability without requiring
the UI to traverse the full campaign ledger. A missing field is reported as
`null`; it is never changed to an available or zero-risk result.

`forecast` contains one row per predicted component and time. A quantitative
evaluator is called only when a new HAZOP condition is reached (`entry`) or at
every active step (`each_step`). The evaluator owns the equipment release,
isolation, inventory termination, SLABx-LH2 run, and any explicitly reviewed
facility handoff.

A current recheck receipt is available at
[`examples/hazop_integrated_current_forecast_recheck_20261018.json`](../examples/hazop_integrated_current_forecast_recheck_20261018.json).
It records one measured-state path and one forecast trigger using the same
operating-mode HAZOP identity and facility-ledger gate. Both retain
conditional diagnostic risk, while an open provider release boundary keeps the
facility total IR/F-N unavailable.

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
The guard checks both the callback's top-level fields and any nested
`facility_ledger`. A callback that reports `qualified_facility_qra_available`,
`provider_packet_promoted`, or an equivalent promotion/inference flag inside
that ledger is returned as
`WITHHELD_UNSAFE_FORECAST_FACILITY_CAMPAIGN_RESULT`; conditional numerical
totals remain visible only when they are not presented as a qualified QRA.

For a structured handoff, use `forecast_campaign_bindings=...` with
`run_hazop_integrated_risk` or call
`build_hazop_forecast_facility_campaign_result()` directly. The strict adapter
requires one reviewed campaign for every quantitative trigger and binds it by
`component_id|scenario_id|forecast_time_s`, including the operating mode. It
records the merged facility ledger while preserving the operator-limited status;
missing triggers fail closed instead of becoming zero risk. See the detailed
[forecast facility campaign handoff guide](PRISM_forecast_facility_campaign_handoff_en.md).

## Timing and interpretation

Both paths record invocation timing. The timing is a measured diagnostic for
the supplied input size; it is not a 1 Hz guarantee. A control system may use
the current path for near-real-time response and run forecast steps at the
simulation cadence. A withheld result is a missing-evidence signal, not zero
risk.
