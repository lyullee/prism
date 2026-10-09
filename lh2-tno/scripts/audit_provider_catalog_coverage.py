"""Audit provider accident packets against the generated equipment worklist."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lh2_tno.provider_catalog_coverage import audit_provider_catalog_coverage
from lh2_tno.provider_packet_promotion import (
    ProviderPacketPromotionError,
    load_provider_packet_evidence_catalog,
)
from lh2_tno.provider_release import (
    ProviderReleaseContractError,
    load_provider_emergency_relief_catalog,
    load_provider_release_catalog,
    load_provider_release_set_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-worklist", type=Path, required=True)
    parser.add_argument("--provider-release-catalog", type=Path, required=True)
    parser.add_argument(
        "--provider-evidence-catalog",
        type=Path,
        help="optional prism.provider_packet_evidence.v1 object/array for qualification audit",
    )
    parser.add_argument(
        "--release-kind",
        choices=("accidental_leak", "emergency_relief", "two_sided_rupture"),
        default="accidental_leak",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        worklist = json.loads(args.provider_worklist.read_text(encoding="utf-8"))
        loader = {
            "accidental_leak": load_provider_release_catalog,
            "emergency_relief": load_provider_emergency_relief_catalog,
            "two_sided_rupture": load_provider_release_set_catalog,
        }[args.release_kind]
        packets = loader(args.provider_release_catalog)
        evidence = (
            load_provider_packet_evidence_catalog(args.provider_evidence_catalog)
            if args.provider_evidence_catalog
            else None
        )
        report = audit_provider_catalog_coverage(
            worklist, packets, provider_packet_evidence=evidence
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProviderReleaseContractError, ProviderPacketPromotionError, ValueError) as error:
        raise SystemExit(f"provider catalog coverage input error: {error}") from error
    report["provider_release_kind"] = args.release_kind
    report["provider_worklist"] = str(args.provider_worklist)
    report["provider_release_catalog"] = str(args.provider_release_catalog)
    report["provider_evidence_catalog"] = (
        str(args.provider_evidence_catalog) if args.provider_evidence_catalog else None
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "output": str(args.output),
        "worklist_event_count": report["worklist_event_count"],
        "provider_packet_count": report["provider_packet_count"],
        "exact_match_count": report["exact_match_count"],
        "unmatched_event_count": report["unmatched_event_count"],
        "qualification_status": report["qualification_status"],
        "qualified_provider_packet_count": report["qualified_provider_packet_count"],
        "unqualified_exact_match_count": report["unqualified_exact_match_count"],
    }, ensure_ascii=False))
    return 0 if report["status"] == "FULLY_MATCHED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
