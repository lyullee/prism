# Header-bound facility HAZOP bridge replay — 2026-10-18

A fresh replay of the header-bound inspection-centre runtime bridge was run
with the current PRISM checkout. The runtime frame includes an explicit
operating mode for each component, and the HAZOP selector dispatches the
corresponding provider scenario.

## Replay result

- Three components were selected and all three reached the provider/SLABx-LH2
  consequence path.
- The modes were `receiving`, `standby`, and `supply`; mode selection came from
  explicit input and was not inferred from telemetry.
- Three conditional current-weather risk atoms were produced.
- Literature frequencies were bound to explicit event/port identities; no
  sensor-frequency learning or frequency inference was used.
- The current replay took **12.827 s** wall time for the three fresh-physics
  branches. This is a background diagnostic measurement, not a 1 Hz claim.

The replay also exposes a stricter current boundary than the older saved
runtime: all three branches are now `operator_limited` because the provider
response does not declare the dynamic pressure/inventory closure contract.
The older runtime record is retained as the historical/authoritative replay;
the new result is a candidate recheck and does not replace it.

The current-weather frequency uncertainty is partial: one branch carries
published/P05/P95 bounds and two branches have no complete bound set. Missing
bounds are not imputed. The conditional IR and expected-death result is zero at
the synthetic worker receptor, while facility annual IR/F-N and facility QRA
remain unavailable.

## Records

- Candidate runtime result:
  `results/20261018/header_bound_facility_bridge_current_recheck_20261018.json`
- Candidate summary and comparison:
  `results/20261018/header_bound_facility_bridge_current_recheck_summary_20261018.json`
- Previous authoritative runtime:
  `results/20261115/header_bound_facility_bridge_runtime.json`
- Reproduction command:
  `scripts/run_header_bound_facility_hazop_bridge.py`

The candidate comparison preserves the exact component, scenario, mode, and
provider-port identities. It records the changed adapter digest and stricter
operator-limited classification for later provider qualification; it does not
promote a release packet or infer a facility QRA.
