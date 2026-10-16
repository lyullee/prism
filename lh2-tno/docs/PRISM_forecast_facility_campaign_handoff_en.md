# Forecast HAZOP to facility campaign handoff

`run_hazop_forecast_risk_scan()` detects a predicted HAZOP condition and calls
the supplied quantitative evaluator. The scan is intentionally one trigger at
a time: it does not guess a release packet, frequency, population, ignition
branch, or facility total. When the evaluator has produced an explicit,
reviewed facility campaign, the campaign can be joined to the facility ledger
with `build_hazop_forecast_facility_campaign_result()`.

## Trigger identity

Every quantitative trigger uses one JSON-safe key:

```text
component_id|scenario_id|forecast_time_s
```

The binding must repeat the component, scenario, time, and operating mode. A
mismatch is rejected before any facility merge. This prevents a future state
from being attached to a current-state or another equipment scenario by a
reused HAZOP ID.

## Example

```python
from lh2_tno.integrated_risk import (
    build_hazop_forecast_facility_campaign_result,
)

key = "TK-01|TK-01-pressure|120"
forecast_facility = build_hazop_forecast_facility_campaign_result(
    forecast_scan,
    campaign_bindings={
        key: {
            "component_id": "TK-01",
            "scenario_id": "TK-01-pressure",
            "forecast_time_s": 120.0,
            "operating_mode": "receiving",
            "campaign": reviewed_campaign_result,
        }
    },
    expected_component_ids=("TK-01",),
)
```

`reviewed_campaign_result` must already contain its event, case, risk-atom,
annual-condition, provider-boundary, and consequence records. The helper only
joins those records with `merge_facility_campaign_results()` and records the
forecast provenance in `trigger_bindings`. It does not rerun SLABx-LH2 or
change the provider termination basis.

## Fail-closed rules

- The forecast scan must be complete and contain no withheld quantitative
  evaluations.
- Bindings must cover exactly every quantitative trigger. Missing triggers are
  not treated as zero risk; the join fails with `IntegratedRiskError`.
- A campaign must identify the same facility and must not claim frequency
  inference, sensor-frequency learning, physical validation, or qualified
  facility-QRA promotion.
- Event IDs must be unique across prediction times. If one physical event is
  recalculated at multiple times, the host must namespace the event IDs and
  keep the mapping in its provenance record.
- The merged result remains
  `FORECAST_FACILITY_CAMPAIGN_BUILT_OPERATOR_LIMITED`; facility qualification
  still depends on the ordinary scope, provider, and validation gates.

## Integrated call

The helper can be requested directly by `run_hazop_integrated_risk()` using
`forecast_campaign_bindings=...`. It is mutually exclusive with the older
free-form `forecast_facility_campaign_evaluator` callback. The returned
`forecast_facility_campaign` contains the merged facility ledger and the exact
forecast trigger-to-campaign trace.

```python
result = run_hazop_integrated_risk(
    hazop_table,
    current_frames=measured_frames,
    forecast_frames=predicted_frames,
    forecast_tables_by_component=tables_by_component,
    component_bindings=component_bindings,
    release_resolvers=release_resolvers,
    forecast_quantitative_evaluator=forecast_evaluator,
    forecast_campaign_bindings=campaign_bindings,
    now_s=clock_s,
)
```

This is the explicit bridge for future-state facility aggregation. It keeps
the current response path and the predicted path separate while preserving the
same component, HAZOP scenario, operating mode, provider, and facility-ledger
identity.
