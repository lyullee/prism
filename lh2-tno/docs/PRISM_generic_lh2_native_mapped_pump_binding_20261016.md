# Generic outdoor LH2 facility pump binding

The native `MappedPump` model is now bound to the generic facility identity
`liquid-transfer-pump-01`, rather than only to a diagnostic wrapper. The
component and port are defined in the general outdoor facility manifest, while
the native provider remains the owner of the H-Q-N operating point, liquid
release history, duration, and explicit downstream isolation observation.

The exporter accepts `--position-enu-m EAST NORTH UP`. The replay uses
`[6.0, 0.0, 1.0]`, which is checked against the declared `pump-accident-out`
port position before the consequence chain runs. A packet left at the old
origin default is rejected instead of being silently translated.

```text
generic pump identity + pump-accident-out
  -> native MappedPump liquid release
  -> exact 0.0025 m opening match
  -> TNO_PUMP_STANDARD G2 frequency
  -> SLABx-LH2 pool/consequence path
  -> ignition and conditional IR/F-N ledger
```

The packet is deliberately generated with `component_id=liquid-transfer-pump-01`
and `port_id=pump-accident-out` so the common event binding checks the same
identity used by a normal LH2 facility model. The inspection-center data are
not used as pump frequency or release evidence.

The G2 replay is diagnostic: one weather case executes and G1 remains
`UNCOMPUTED`; TNO's pump default has no published p05/p95 bounds, so the
catalogue point estimate is retained as `fixed`. Provider qualification,
independent physical validation, complete pump failure scope, and facility
IR/F-N promotion remain closed. The recorded end-to-end facility campaign
took approximately 6.5 s for this one-case diagnostic.
