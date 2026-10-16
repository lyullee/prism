# PRISM release-boundary response intake

PRISM now exports the two unresolved release-boundary cases as a provider
request packet.  This companion intake contract checks a provider's returned
packet before the case-level audit consumes it.  It is useful for the next
LH2 equipment-model handoff because the provider can return the same JSON
contract regardless of whether the source model is a tank, relief device,
vaporizer, pump, valve, or another declared outdoor component.

## Reproduce the blank response template

```powershell
python scripts/build_release_boundary_evidence_response_template.py `
  --requests results/20261115/open_release_boundary_evidence_requests_current.json `
  --output results/20261115/open_release_boundary_evidence_response_template.json
```

The template contains the exact event, case, component, port, operating mode,
HAZOP scenario, and the digest being superseded.  All provider values are
`null`; the template is not evidence and must not be used for a risk result.

## Validate a returned provider packet

```powershell
python scripts/validate_release_boundary_evidence_response.py `
  --requests results/20261115/open_release_boundary_evidence_requests_current.json `
  --responses path/to/provider_responses.json `
  --output results/20261115/provider_response_intake_audit.json
```

To hand the validated rows directly to the case-level release audit, add a
catalog output and the current facility assessment.  This performs no packet
rebind and no consequence rerun; it simply makes the response-to-audit handoff
reproducible and fail-closed:

```powershell
python scripts/validate_release_boundary_evidence_response.py `
  --requests results/20261115/open_release_boundary_evidence_requests_current.json `
  --responses path/to/provider_responses.json `
  --output results/20261115/provider_response_intake_audit.json `
  --catalog-output results/20261115/provider_termination_evidence_catalog.json `
  --facility-assessment results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_assessment.json `
  --facility-evidence-request results/20261115/native_full_scope_union_assessment_vertical_inventory_handoff_port_bound_isolation_current/facility_evidence_request.json `
  --case-audit-output results/20261115/release_boundary_case_audit_reaudited.json
```

Only rows with `RELEASE_BOUNDARY_REAUDIT_READY` are written to the provider
termination catalog.  A response with a new provider-result digest or changed
source masses remains blocked until the equipment packet is explicitly rebound
and the consequence chain is rerun; the helper never edits the facility
assessment to make those values appear consistent.

The validator checks exact identity, source/result SHA-256 values, the
superseded digest, provider-owned stopping history, mass balance and a
family-specific termination rule.

* The emergency-relief case requires an emergency-relief event, the relief
  operator, positive setpoint and capacity, an explicit completion event, and
  a closed mass residual.  It cannot be converted to a random hole.
* The 600-second vaporizer case cannot be closed by repeating the 600-second
  horizon.  The provider must supply isolation, inventory depletion, or
  releasable-inventory closure evidence.

The existing provider closure gate treats `model_pressure_equalization` as a
model-natural diagnostic endpoint rather than a strict provider termination
ledger.  It can still be carried through the consequence chain for diagnostic
work, but it does not make this response `RELEASE_BOUNDARY_REAUDIT_READY`.

`RELEASE_BOUNDARY_REAUDIT_READY` means that the response can be handed back to
the case-level audit.  It does not mean that the provider is qualified, that
the model has independent physical validation, or that facility IR/F-N is
allowed.  Frequency inference, sensor learning, unsupported accident
substitution, and facility-QRA promotion remain disabled.
