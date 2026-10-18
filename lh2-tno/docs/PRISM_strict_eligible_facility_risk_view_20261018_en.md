# Strict-eligible facility-risk contribution (2026-10-18)

PRISM now exports a second, deliberately narrower view beside the conditional
facility risk view. It sums only risk atoms that satisfy all three local
conditions:

1. the case status is `EXECUTED`;
2. the atom is not marked `case_withheld_from_strict_facility_qra`; and
3. the atom is marked `ELIGIBLE_FOR_NUMERICAL_SCOPE`.

Build it from a saved facility assessment:

```powershell
python scripts/build_strict_eligible_facility_risk_view.py `
  --facility-assessment results/20261115/native_external_facility_full_scope_campaign_current/facility_assessment.json `
  --output results/20261018/strict_eligible_facility_risk_view_current.json
```

For the current diagnostic campaign this selects 52 of 96 risk atoms and
explicitly excludes 44 operator-limited or otherwise withheld atoms. The
output includes the selected annual IR and F/N contribution, the exclusion
reasons, source digest, and fail-closed promotion flags.

This export is useful for equipment ranking, review, and digital-twin display.
It is not a complete facility QRA: `facility_qra_promotion`,
`complete_facility_qra_claim`, and `physical_validation_claim` remain false.
Excluded atoms are never treated as zero risk; they are counted and named so a
reviewer can see exactly what remains to be qualified.
