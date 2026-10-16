# Provider response to facility release-boundary handoff

PRISM now exposes one explicit handoff API for the provider-response path:

```python
from lh2_tno.release_boundary_evidence_intake import (
    build_release_boundary_evidence_handoff,
)

handoff = build_release_boundary_evidence_handoff(
    open_requests,
    provider_responses,
    facility_assessment=facility_assessment,
    facility_evidence_request=facility_evidence_request,
)
```

The returned record preserves three stages:

1. `intake` checks exact request identity, superseded provider-result digest,
   stopping rule, duration history, and mass balance.
2. `provider_termination_evidence` emits only responses that passed the intake
   checks. It retains the provider result digest, termination basis, duration,
   available mass, cumulative release, and family-specific evidence.
3. `case_audit` matches that catalog to the consuming facility packet and
   checks the case-level release branch, isolation or inventory boundary, and
   mass ledger. A response that belongs to another case or provider replay is
   withheld.

The two facility arguments must be supplied together. Supplying neither gives
the response-only intake and catalog; supplying only one raises an error so a
caller cannot mistake a provider response for a facility-matched result.

This handoff does not rerun SLABx-LH2, infer a duration, assign a frequency,
qualify a provider, or promote facility IR/F-N. The returned object always
reports `facility_qra_promotion_allowed: false`; the completion audit can
consume its `case_audit` as diagnostic evidence. Provider qualification and
independent physical validation remain separate gates.

The integration is covered by
`tests/test_release_boundary_evidence_intake.py` and preserves the existing
fail-closed behavior for missing, duplicated, stale, or invalid responses.
