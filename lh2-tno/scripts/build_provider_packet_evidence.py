"""Build exact campaign evidence from a saved provider packet and qualification record."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lh2_tno.provider_packet_promotion import (  # noqa: E402
    ProviderPacketPromotionError,
    build_provider_packet_evidence_from_records,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = build_provider_packet_evidence_from_records(
            args.release, args.qualification
        )
    except (OSError, UnicodeDecodeError, ValueError, ProviderPacketPromotionError) as error:
        raise SystemExit(f"provider packet evidence input error: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "QUALIFIED_PROVIDER_PACKET_EVIDENCE",
        "event_id": evidence.event_id,
        "component_id": evidence.component_id,
        "evidence_id": evidence.evidence_id,
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
