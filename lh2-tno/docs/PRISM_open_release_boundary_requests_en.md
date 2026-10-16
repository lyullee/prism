# PRISM open release-boundary evidence requests

PRISM now has a small export step for the cases that remain open in the
release-boundary audit.  It converts the audit rows into provider-facing
requests without changing the risk result.  The output is deliberately
diagnostic: it does not infer a duration, replace a termination basis, learn a
frequency, or promote facility IR/F-N.

## Current open cases

The current vertical/inventory/isolation union contains two numerically open
cases:

* **Emergency relief:** the VentStack packet has a time history and a mass
  balance for a bounded steady diagnostic, but it does not contain the relief
  setpoint, rated/resolved capacity, explicit completion event, or closed
  relief inventory boundary.  PRISM therefore keeps it separate from a random
  hole and leaves the case open.
* **600 s inventory horizon:** the DynamicVaporizer packet is a complete
  600-second diagnostic history, but almost all provider inventory remains and
  the provider did not declare a physical release boundary.  A zero-flow row
  inside the horizon is not silently treated as isolation or depletion.  The
  provider must either continue until a physical stop or export a supported
  termination basis with its own evidence.

## Reproduce the request packet

```powershell
python scripts/build_release_boundary_evidence_requests.py `
  --audit results/20261115/release_boundary_case_audit_union_vertical_inventory_handoff_isolation_current.json `
  --output results/20261115/open_release_boundary_evidence_requests_current.json
```

The request keeps the exact event, component, accident port, operating mode,
HAZOP scenario, provider digest, current mass values, and blocking reasons.  A
provider response can be re-audited against these identities.  Until it is
received and independently reviewed, the strict release gate and facility
IR/F-N promotion remain closed.
