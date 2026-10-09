"""Compare a baseline campaign with an explicit larger-domain sensitivity run.

The audit is deliberately diagnostic.  A larger grid does not make a
consequence result complete by itself: an event is recovered only when the
campaign result no longer carries a domain-incomplete copy for that event.
Persistent outside-domain mass remains a blocker and facility IR/F-N values
are never promoted by this comparison.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping


SCHEMA = "prism.domain_recovery_audit.v1"
DOMAIN_STATUSES = {"DOMAIN_INCOMPLETE", "EXECUTED_DOMAIN_INCOMPLETE"}


def _event_statuses(campaign: Mapping[str, Any]) -> dict[str, set[str]]:
    statuses: dict[str, set[str]] = {}
    for key in ("cases", "uncomputed_cases"):
        rows = campaign.get(key, [])
        if not isinstance(rows, list):
            raise ValueError(f"campaign.{key} must be an array")
        for row in rows:
            if not isinstance(row, Mapping) or not row.get("event_id"):
                raise ValueError(f"campaign.{key} contains a row without event_id")
            event_id = str(row["event_id"])
            statuses.setdefault(event_id, set()).add(str(row.get("status", "UNKNOWN")))
    if not statuses:
        raise ValueError("campaign contains no case rows")
    return statuses


def _domain_bounds(defaults: Mapping[str, Any]) -> dict[str, Any]:
    domain = defaults.get("domain")
    if not isinstance(domain, Mapping):
        raise ValueError("request defaults must contain a domain object")
    required = ("downwind_bounds_m", "crosswind_bounds_m", "height_bounds_m", "cell_size_m")
    if any(key not in domain for key in required):
        raise ValueError("domain defaults are missing a required bound")
    return {key: domain[key] for key in required}


def build_domain_recovery_audit(
    baseline_campaign: Mapping[str, Any],
    recovery_campaign: Mapping[str, Any],
    baseline_defaults: Mapping[str, Any],
    recovery_defaults: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an auditable comparison of two campaign result ledgers."""
    baseline = _event_statuses(baseline_campaign)
    recovery = _event_statuses(recovery_campaign)
    baseline_ids = set(baseline)
    recovery_ids = set(recovery)
    if baseline_ids != recovery_ids:
        raise ValueError("baseline and recovery campaigns must contain the same event IDs")

    rows: list[dict[str, Any]] = []
    for event_id in sorted(baseline_ids):
        before = sorted(baseline[event_id])
        after = sorted(recovery[event_id])
        before_domain = bool(DOMAIN_STATUSES & set(before))
        after_domain = bool(DOMAIN_STATUSES & set(after))
        if before_domain and not after_domain:
            disposition = "RECOVERED_BY_EXPLICIT_DOMAIN_RUN"
        elif after_domain:
            disposition = "PERSISTENT_DOMAIN_INCOMPLETE"
        else:
            disposition = "NO_DOMAIN_BLOCKER_IN_BASELINE"
        rows.append({
            "event_id": event_id,
            "baseline_statuses": before,
            "recovery_statuses": after,
            "baseline_domain_incomplete": before_domain,
            "recovery_domain_incomplete": after_domain,
            "disposition": disposition,
        })

    counts = Counter(row["disposition"] for row in rows)
    recovery_domain_ids = [
        row["event_id"] for row in rows if row["recovery_domain_incomplete"]
    ]
    # A sensitivity comparison cannot qualify provider packets or facility QRA.
    return {
        "schema": SCHEMA,
        "status": "DOMAIN_RECOVERY_REVIEWED",
        "scope": "explicit larger-domain sensitivity only",
        "baseline": {
            "status": baseline_campaign.get("status"),
            "campaign_digest": baseline_campaign.get("campaign_digest"),
            "domain": _domain_bounds(baseline_defaults),
        },
        "recovery": {
            "status": recovery_campaign.get("status"),
            "campaign_digest": recovery_campaign.get("campaign_digest"),
            "domain": _domain_bounds(recovery_defaults),
        },
        "event_count": len(rows),
        "event_rows": rows,
        "counts": dict(sorted(counts.items())),
        "baseline_domain_incomplete_event_count": sum(
            row["baseline_domain_incomplete"] for row in rows
        ),
        "recovery_domain_incomplete_event_count": len(recovery_domain_ids),
        "persistent_domain_incomplete_event_ids": recovery_domain_ids,
        "recovered_event_ids": [
            row["event_id"]
            for row in rows
            if row["disposition"] == "RECOVERED_BY_EXPLICIT_DOMAIN_RUN"
        ],
        "facility_ir_fn_promotion": False,
        "qualified_provider_packet_promotion": False,
        "interpretation": (
            "The larger-domain run is a sensitivity check. Persistent domain-incomplete "
            "events require a closed dispersion/observation domain or provider evidence; "
            "this audit never zeros their risk or promotes facility IR/F-N."
        ),
    }
