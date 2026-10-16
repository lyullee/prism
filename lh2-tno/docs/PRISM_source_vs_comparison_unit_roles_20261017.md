# PRISM unit roles for monitored LH2 signals

PRISM now keeps two different unit claims separate when inspection-centre or
digital-twin data are reviewed:

- `source_unit` is the unit printed on the incoming time-series column. It is
  the only unit that can be passed to the telemetry normalizer.
- `comparison_unit` is a procedure, alarm, or setpoint context. It is useful
  when a procedure says “6 bar” while the historian column is recorded in MPa,
  but it is never substituted into the runtime frame.
- `unit` remains a backward-compatible alias for `source_unit`.

This distinction resolves a false unit conflict without claiming that the
signal is ready for state promotion. Pressure basis, calibration/quality,
sensor identity, and unreviewed tags still have to be closed separately.

## Example

```json
{
  "PT1105A": {
    "source_unit": "MPa",
    "comparison_unit": "bar",
    "quantity": "pressure",
    "pressure_basis": "unresolved",
    "evidence": [{"page": 24, "anchor": "PT-1105A"}]
  }
}
```

The observed-state manifest is compared with `source_unit` (`MPa`). The
`comparison_unit` (`bar`) is retained in the audit output for traceability and
is not used for conversion. `normalise_unit_claims()` exposes both roles;
`normalise_unit_map()` continues to return the legacy source-unit-only view.

## Safety and scope policy

The unit-role change does not create an accident, release history, frequency,
or provider packet. It also does not resolve absolute-versus-gauge pressure.
Consequently the inspection-centre state gate remains closed until the
pressure basis, calibration/quality, and all required tag mappings are
independently reviewed. This is a diagnostic input-quality improvement for the
outdoor LH2 digital-twin path, not a facility-QRA completion claim.

The behavior is covered by:

- `tests/test_observed_unit_consistency.py`
- `tests/test_reviewed_signal_unit_evidence.py`
- `tests/test_inspection_timeseries.py`

The inspection-centre example
[`inspection_center_reviewed_signal_unit_role_map_diagnostic.json`](../examples/inspection_center_reviewed_signal_unit_role_map_diagnostic.json)
shows the resulting diagnostic audit: the two pressure bindings match the
workbook source unit (MPa) while retaining bar as procedure context, but the
remaining missing tags and unresolved pressure basis keep the state gate
closed.
