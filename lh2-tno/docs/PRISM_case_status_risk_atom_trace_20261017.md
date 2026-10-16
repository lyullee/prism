# PRISM case-status trace from facility cases to risk atoms

## Purpose

The facility ledger can contain a numerical `risk_atom` for a case whose
release evidence is still withheld.  This is useful for a conditional
diagnostic IR/F-N view, but it must not look like a completed facility-QRA
case when a user inspects the atom by itself.  The ledger now attaches the
case identity and case status to every risk atom.

## What is matched

The primary identity is the four-part case key already used by the facility
ledger:

1. `event_id`
2. `annual_condition_id`
3. `release_branch_id`
4. `ignition_branch`

An evaluated row in `cases` takes precedence over a duplicate explanatory row
in `uncomputed_cases`.  A case row may intentionally stop at the release
boundary and omit `ignition_branch`; a unique
`event_id`/`annual_condition_id`/`release_branch_id` parent then binds to its
ignition outcome atoms. Legacy rows that contain only `event_id` are accepted
only when there is exactly one atom for that event.  If the dimensions cannot
be matched uniquely, the trace is `BLOCKED`; PRISM does not guess which case
produced the atom.

## Per-atom fields

Each merged `risk_atoms[*]` row receives:

- `case_identity`: the resolved identity used for matching;
- `case_status`: the matched case status, or `null` when no unique case exists;
- `case_status_source`: `cases`, `uncomputed_cases`, or both;
- `case_match_kind`: `EXACT_CASE`, `CASE_PARENT_NO_IGNITION`,
  `LEGACY_EVENT_ONLY`, `UNMATCHED_CASE`, or `AMBIGUOUS_EVENT_ONLY`;
- `case_eligibility`: `ELIGIBLE`, `WITHHELD`, `UNMATCHED`, or `AMBIGUOUS`;
- `risk_atom_eligibility`: a machine-readable strict-scope interpretation;
- `case_withheld_from_strict_facility_qra`: whether the case is withheld from
  strict facility-QRA promotion.

Only an exact or unambiguous case with status exactly `EXECUTED` is marked
`ELIGIBLE`.  `EXECUTED_OPERATOR_LIMITED`, domain-incomplete, failed, and other
statuses remain in the conditional diagnostic sum but are marked
`WITHHELD_FROM_STRICT_SCOPE`.  Their frequency is not changed or reallocated.

## Facility-level audit

The merged result contains `risk_atom_case_traceability` with schema
`prism.facility_case_risk_atom_trace.v1`.  It reports matched, eligible,
withheld, unmatched, and ambiguous atom counts, the retained
`uncomputed_case_row_count`, status-by-atom counts, and the blocking reasons.
A trace is `CLOSED` when every atom has a unique match; it is `BLOCKED` when an
atom has no unique case.  A closed trace can still contain withheld atoms or
uncomputed case rows, in which case
`strict_facility_qra_promotion_blocked` remains `true` and the facility total
remains unavailable.

This distinction preserves both required views:

- the conditional diagnostic IR/F-N sum keeps evaluated atoms so a reviewer
  can inspect the numerical chain;
- strict facility QRA promotion excludes withheld or unbound atoms and keeps
  the qualification gate closed.

The audit never infers a missing status, learns a frequency, substitutes a
provider packet, or converts a diagnostic result into physical validation.

## Verification

The contract is covered by
`tests/test_facility_ledger.py::test_facility_ledger_traces_risk_atoms_to_executed_and_withheld_cases`
and
`tests/test_facility_ledger.py::test_facility_ledger_blocks_unmatched_risk_atom_case_identity`.
