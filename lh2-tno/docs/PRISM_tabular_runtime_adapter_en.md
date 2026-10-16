# Tabular runtime adapter

`lh2_tno.tabular_runtime_adapter` is the small input adapter for a historian
or process simulator that exports CSV/TSV rows. It turns one reviewed stream
into the existing `prism.observed_state_runtime_frames.v1` contract, so the
same HAZOP and current/forecast risk path can be used for a file replay or a
live connector.

The adapter requires an explicit mapping for every signal used by the row:

- source column and PRISM tag;
- source engineering unit;
- pressure basis and sensor location in the `TelemetryNormalizer` mapping;
- numeric source-time column and its scale to seconds; and
- operating mode, either in a source column or as an explicit constant.

It rejects missing values, non-monotonic timestamps, unit drift, unresolved
normalizer tags, and mode conflicts. Header prefixes such as `PT1105A` are
never treated as proof of a unit or gauge/absolute pressure basis.

```python
from lh2_tno.tabular_runtime_adapter import build_runtime_frames_from_csv

frames = build_runtime_frames_from_csv(
    "historian_export.csv",
    source_id="historian-tk-01",
    component_id="TK-01",
    timestamp_column="time_s",
    operating_mode_column="operating_mode",
    bindings={
        "PT1105A": {"tag": "pressure", "unit": "bar", "quality": "valid"},
        "TT1106": {"tag": "temperature", "unit": "degC", "quality": "valid"},
    },
    normalizer=reviewed_normalizer,
)
latest_frame = frames["frames"][0]
```

The result contains the latest state frame plus the source SHA-256 and all
sample provenance. Pass the frame to the HAZOP runtime handoff. The adapter
does not create a leak, release duration, inventory termination, frequency,
SLABx-LH2 result or facility IR/F-N value. A provider release packet and an
explicit literature frequency binding are still required downstream.

For the inspection-centre data, use this adapter only after the reviewed unit
and pressure-basis map is complete. The current evidence record intentionally
leaves unresolved headers withheld; normal operation records are not used to
learn accident frequency.

