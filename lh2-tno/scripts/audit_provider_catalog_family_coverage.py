"""Audit accidental-leak and emergency-relief provider catalogs together.

The equipment worklist contains two strict release families.  Keeping their
catalogs separate prevents a random-hole packet from satisfying a relief event
or a relief history from being reused as a leak.  This report combines only
the identity/contract results; it does not assign frequencies or promote
synthetic packets into facility QRA.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_catalog_coverage import audit_provider_catalog_coverage  # noqa: E402
from lh2_tno.provider_release import (  # noqa: E402
    ProviderReleaseContractError,
    load_provider_emergency_relief_catalog,
    load_provider_release_catalog,
    load_provider_release_set_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-worklist", type=Path, required=True)
    parser.add_argument("--accidental-catalog", type=Path, required=True)
    parser.add_argument("--emergency-relief-catalog", type=Path, required=True)
    parser.add_argument("--two-sided-catalog", type=Path, required=False)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        worklist = json.loads(args.provider_worklist.read_text(encoding="utf-8"))
        accidental = load_provider_release_catalog(args.accidental_catalog)
        relief = load_provider_emergency_relief_catalog(args.emergency_relief_catalog)
        two_sided = load_provider_release_set_catalog(args.two_sided_catalog) if args.two_sided_catalog else ()
        accidental_report = audit_provider_catalog_coverage(worklist, accidental)
        relief_report = audit_provider_catalog_coverage(worklist, relief)
        two_sided_report = audit_provider_catalog_coverage(worklist, two_sided)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProviderReleaseContractError, ValueError) as error:
        raise SystemExit(f"provider family coverage input error: {error}") from error

    accidental_rows = {row["event_id"]: row for row in accidental_report["work_items"]}
    relief_rows = {row["event_id"]: row for row in relief_report["work_items"]}
    two_sided_rows = {row["event_id"]: row for row in two_sided_report["work_items"]}
    rows = []
    matched = 0
    status_counts: dict[str, int] = {}
    for item in worklist["work_items"]:
        event_id = item["event_id"]
        if item.get("release_mode") == "maximum_relief_discharge":
            family = "emergency_relief"
            row = relief_rows[event_id]
        elif item.get("release_mode") == "two_sided_rupture":
            family = "two_sided_rupture"
            row = two_sided_rows[event_id]
        else:
            family = "accidental_leak"
            row = accidental_rows[event_id]
        output = dict(row)
        output["release_family"] = family
        rows.append(output)
        status_counts[output["status"]] = status_counts.get(output["status"], 0) + 1
        if output["status"] == "EXACT_MATCH":
            matched += 1

    extra_packets = accidental_report["extra_packets"] + relief_report["extra_packets"] + two_sided_report["extra_packets"]
    blockers = []
    if status_counts.get("UNMATCHED_NO_PROVIDER_PACKET"):
        blockers.append("one or more declared events have no provider packet")
    if status_counts.get("UNMATCHED_PACKET_CONTRACT"):
        blockers.append("one or more provider packets fail exact worklist identity or boundary checks")
    if extra_packets:
        blockers.append("provider catalogs contain packets outside the declared frequency worklist")
    status = "FULLY_MATCHED" if not blockers else ("NO_EXACT_MATCH" if matched == 0 else "PARTIAL_EXACT_MATCH")
    report = {
        "schema": "prism.provider_release_family_coverage.v1",
        "status": status,
        "worklist_status": worklist.get("status"),
        "worklist_event_count": len(rows),
        "provider_packet_count": len(accidental) + len(relief) + len(two_sided),
        "exact_match_count": matched,
        "unmatched_event_count": len(rows) - matched,
        "extra_packet_count": len(extra_packets),
        "status_counts": dict(sorted(status_counts.items())),
        "blocking_reasons": blockers,
        "work_items": rows,
        "extra_packets": extra_packets,
        "family_reports": {
            "accidental_leak": accidental_report,
            "emergency_relief": relief_report,
            "two_sided_rupture": two_sided_report,
        },
        "promotion_policy": {
            "frequency_is_not_assigned": True,
            "request_defaults_are_not_attached": True,
            "normal_or_screening_flow_is_not_promoted": True,
            "full_match_does_not_claim_physical_validation": True,
            "release_families_are_not_cross_reused": True,
            "campaign_requires_separate_exact_binding": True,
        },
        "provider_worklist": str(args.provider_worklist),
        "accidental_catalog": str(args.accidental_catalog),
        "emergency_relief_catalog": str(args.emergency_relief_catalog),
        "two_sided_catalog": str(args.two_sided_catalog) if args.two_sided_catalog else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "output": str(args.output),
        "worklist_event_count": len(rows),
        "provider_packet_count": len(accidental) + len(relief) + len(two_sided),
        "exact_match_count": matched,
        "unmatched_event_count": len(rows) - matched,
    }, ensure_ascii=False))
    return 0 if status == "FULLY_MATCHED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
