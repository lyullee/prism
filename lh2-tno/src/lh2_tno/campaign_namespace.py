"""Rebind a disjoint diagnostic campaign into a common facility namespace.

Some provider campaigns are executed as stand-alone diagnostics.  This
module makes their later facility merge explicit by rebinding event IDs,
asset/component ownership and receptor names together.  It never promotes a
synthetic release, infers a frequency, or turns a partial campaign into a
qualified facility result.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any


def _mapped_event_id(event_id: str, *, source_facility_id: str, namespace: str) -> str:
    prefix = f"{source_facility_id}/"
    if not event_id.startswith(prefix):
        raise ValueError(
            f"campaign event id must start with source facility '{source_facility_id}': {event_id}"
        )
    suffix = event_id[len(prefix) :]
    if not suffix:
        raise ValueError(f"campaign event id has no suffix: {event_id}")
    return f"{namespace.rstrip('/')}/{suffix}"


def rebind_campaign_result(
    result: Mapping[str, Any],
    *,
    source_facility_id: str,
    facility_id: str,
    namespace: str,
    source_asset_id: str,
    asset_id: str,
    source_component_id: str,
    component_id: str,
    receptor_map: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a diagnostic campaign with an explicit facility identity.

    ``source_asset_id`` and ``source_component_id`` must match every source
    event that is being rebound.  A many-to-one receptor map is allowed only
    as an explicit diagnostic operation; colliding harm endpoints use the
    conservative maximum and expected deaths are recomputed from the mapped
    receptor set.
    """
    if not source_facility_id.strip() or not facility_id.strip() or not namespace.strip():
        raise ValueError("facility IDs and namespace must be nonempty")
    output = copy.deepcopy(dict(result))
    events = output.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("campaign result must contain a nonempty events array")
    source_event_ids: list[str] = []
    for row in events:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError("campaign events must contain string IDs")
        if row.get("asset_id") != source_asset_id:
            raise ValueError("campaign contains an unexpected source asset")
        if row.get("model_component_id") != source_component_id:
            raise ValueError("campaign contains an unexpected source component")
        source_event_ids.append(row["id"])
    if len(set(source_event_ids)) != len(source_event_ids):
        raise ValueError("campaign event IDs must be unique")
    event_map = {
        old: _mapped_event_id(
            old,
            source_facility_id=source_facility_id,
            namespace=namespace,
        )
        for old in source_event_ids
    }

    def map_event(value: Any) -> Any:
        if isinstance(value, str):
            return event_map.get(value, value)
        return value

    receptor_mapping = dict(receptor_map or {})
    for key in ("events", "cases", "uncomputed_cases", "risk_atoms"):
        rows = output.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"campaign {key} entries must be objects")
            if "id" in row:
                row["id"] = map_event(row["id"])
            if "event_id" in row:
                row["event_id"] = map_event(row["event_id"])
            if row.get("asset_id") == source_asset_id:
                row["asset_id"] = asset_id
            if row.get("model_component_id") == source_component_id:
                row["model_component_id"] = component_id
            if row.get("component_id") == source_component_id:
                row["component_id"] = component_id
            identity = row.get("provider_packet_identity")
            if isinstance(identity, dict):
                identity["event_id"] = map_event(identity.get("event_id"))
                if identity.get("component_id") == source_component_id:
                    identity["component_id"] = component_id
            if receptor_mapping and "receptor_harm_low_high" in row:
                harm = row.get("receptor_harm_low_high")
                if not isinstance(harm, Mapping):
                    raise ValueError("risk atom receptor harm must be a mapping")
                remapped: dict[str, list[float]] = {}
                for source, endpoints in harm.items():
                    if not isinstance(endpoints, (list, tuple)) or len(endpoints) != 2:
                        raise ValueError("risk atom receptor harm endpoints must have length two")
                    target = receptor_mapping.get(str(source), str(source))
                    values = [float(endpoints[0]), float(endpoints[1])]
                    previous = remapped.get(target)
                    remapped[target] = values if previous is None else [
                        max(previous[0], values[0]),
                        max(previous[1], values[1]),
                    ]
                row["receptor_harm_low_high"] = remapped
                row["expected_deaths_low_high"] = [
                    sum(values[endpoint] for values in remapped.values())
                    for endpoint in range(2)
                ]

    coverage = output.get("coverage")
    if isinstance(coverage, dict):
        rows = coverage.get("by_component")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("component_id") == source_component_id:
                    row["component_id"] = component_id
        else:
            # Some stand-alone diagnostic campaigns predate the facility
            # coverage ledger and only carry event/case accounting.  Rebind
            # that evidence into one explicit component row so the facility
            # merge can distinguish an executed diagnostic from missing
            # coverage metadata.  This is bookkeeping only; it does not
            # promote the campaign or add any frequency inference.
            event_rows = [row for row in output.get("events", []) if isinstance(row, dict)]
            case_rows = [row for row in output.get("cases", []) if isinstance(row, dict)]
            uncomputed_rows = [
                row for row in output.get("uncomputed_cases", []) if isinstance(row, dict)
            ]
            event_ids = {str(row.get("id")) for row in event_rows if row.get("id")}
            frequencies = {
                str(row.get("id")): float(row.get("annual_frequency_per_year", 0.0) or 0.0)
                for row in event_rows
                if row.get("id")
            }
            statuses = [str(row.get("status", "")) for row in case_rows]
            executed = sum(
                status in {
                    "EXECUTED",
                    "EXECUTED_OPERATOR_LIMITED",
                    "EXECUTED_DOMAIN_INCOMPLETE",
                }
                for status in statuses
            )
            fully_validated = sum(status == "EXECUTED" for status in statuses)
            operator_limited = sum(status == "EXECUTED_OPERATOR_LIMITED" for status in statuses)
            domain_incomplete = sum(status == "EXECUTED_DOMAIN_INCOMPLETE" for status in statuses)
            uncomputed_reasons = sorted({
                str(row.get("reason"))
                for row in uncomputed_rows
                if row.get("reason")
            })
            scope_status = (
                "NO_EVENT_GENERATED" if not event_ids else
                "EXECUTED"
                if not uncomputed_rows and all(status == "EXECUTED" for status in statuses)
                else "PARTIAL"
            )
            rows = [{
                "component_id": component_id,
                "kind": "diagnostic_component",
                "scope_status": scope_status,
                "excluded_reason": None,
                "generated_event_count": len(event_ids),
                "generated_initiation_frequency_per_year": sum(frequencies.values()),
                "campaign_case_count": len(case_rows),
                "executed_case_count": executed,
                "fully_validated_case_count": fully_validated,
                "operator_limited_case_count": operator_limited,
                "domain_incomplete_case_count": domain_incomplete,
                "uncomputed_case_count": len(uncomputed_rows),
                "uncomputed_reasons": uncomputed_reasons,
            }]
            coverage["by_component"] = rows

    output["facility_id"] = facility_id
    output["source_facility_id"] = result.get("facility_id")
    output["source_campaign_digest"] = result.get("campaign_digest")
    output["scope_provenance"] = (
        f"{result.get('scope_provenance', 'diagnostic campaign')}; "
        f"explicit facility namespace rebind to {facility_id}"
    )
    output["campaign_namespace_rebind"] = {
        "schema_version": "prism.campaign_namespace_rebind.v1",
        "source_facility_id": source_facility_id,
        "source_campaign_digest": result.get("campaign_digest"),
        "target_facility_id": facility_id,
        "namespace": namespace,
        "source_asset_id": source_asset_id,
        "asset_id": asset_id,
        "source_component_id": source_component_id,
        "component_id": component_id,
        "event_count": len(source_event_ids),
        "event_id_map": event_map,
        "receptor_map": receptor_mapping,
        "receptor_collapse_policy": (
            "many_to_one_endpoint_maximum" if receptor_mapping else None
        ),
        "diagnostic_only": True,
        "physical_validation_claim": False,
        "facility_qra_claim": False,
        "frequency_inference": False,
        "interpretation": (
            "A disjoint provider campaign was explicitly namespaced for facility aggregation. "
            "Source identifiers, partial case accounting and synthetic/operator limitations remain visible."
        ),
    }
    return output


__all__ = ["rebind_campaign_result"]
