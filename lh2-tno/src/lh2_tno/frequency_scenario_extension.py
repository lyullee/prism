"""Build frequency-scenario inputs for the merged generic LH2 scope.

The generic frequency scenarios predate the vertical-handoff diagnostic.  This
helper extends them to the merged ledger without deriving a rate from telemetry
or from a consequence result: the vertical-handoff events keep their explicitly
declared diagnostic rate and are marked ``published`` in every scenario.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


VERTICAL_HANDOFF_EVENT_IDS = tuple(
    "generic-lh2-full-scope-example/vertical-handoff/terminal-valve/" + area
    for area in ("AREA_0.01%", "AREA_0.1%", "AREA_1%", "AREA_10%", "AREA_100%")
)

_PROVENANCE_SUFFIX = (
    "vertical handoff fixed at declared diagnostic rate; "
    "no field or inferred frequency"
)


def extend_frequency_scenarios_for_vertical_handoff(
    source: Mapping[str, Any],
) -> dict[str, Any]:
    """Return generic frequency scenarios covering the merged vertical scope.

    Asset-quantile scenarios receive the vertical-handoff asset as a fixed
    ``published`` entry.  Event-quantile scenarios receive all five vertical
    event IDs with the same fixed entry.  Existing scenarios and provenance are
    copied, so the source object is never mutated.
    """

    raw_scenarios = source.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("frequency scenario source must contain a non-empty scenarios list")

    scenarios: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_scenarios):
        if not isinstance(raw, Mapping):
            raise ValueError(f"scenario {index} must be an object")
        item = deepcopy(dict(raw))
        has_asset_quantiles = isinstance(item.get("asset_quantiles"), dict)
        has_event_quantiles = isinstance(item.get("event_quantiles"), dict)
        if not has_asset_quantiles and not has_event_quantiles:
            raise ValueError(
                f"scenario {item.get('id', index)!r} must define asset_quantiles or event_quantiles"
            )
        if has_asset_quantiles:
            item["asset_quantiles"]["vertical-handoff-vent"] = "published"
        if has_event_quantiles:
            item["event_quantiles"].update(
                {event_id: "published" for event_id in VERTICAL_HANDOFF_EVENT_IDS}
            )
        provenance = str(item.get("provenance", "")).strip()
        item["provenance"] = (
            f"{provenance}; {_PROVENANCE_SUFFIX}" if provenance else _PROVENANCE_SUFFIX
        )
        scenarios.append(item)

    return {
        "schema_version": "prism.literature_frequency_scenarios.v1",
        "scenarios": scenarios,
        "extension": (
            "Generic native LH2 ledger plus merged vertical-handoff all-bin diagnostic; "
            "transfer-line rates remain the reviewed generic LH2 catalogue values; "
            "vertical handoff rates remain declared diagnostic rates and are not "
            "inferred from telemetry."
        ),
    }


def extend_frequency_scenarios_for_independent_event_bounds(
    source: Mapping[str, Any],
    event_rows: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    """Add independent-event p05/p95 bound scenarios to a merged ledger.

    The existing merged-LH2 scenarios use one quantile for every event that
    belongs to an asset.  That is useful for a shared exposure assumption but
    does not show how the result changes when event bounds are treated
    independently.  This helper adds two explicit comparison scenarios.  An
    event without both published marginal bounds is retained at its declared
    catalogue rate with ``fixed``; it is never assigned a guessed quantile.

    The returned object is a new JSON-ready mapping and the input is not
    mutated.  The output remains a frequency sensitivity report, not a
    statistical confidence interval or a facility-QRA promotion.
    """
    raw_scenarios = source.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("frequency scenario source must contain a non-empty scenarios list")
    event_ids: list[str] = []
    event_quantiles_low: dict[str, str] = {}
    event_quantiles_high: dict[str, str] = {}
    for index, row in enumerate(event_rows):
        if not isinstance(row, Mapping) or not row.get("id"):
            raise ValueError(f"event row {index} must contain an id")
        event_id = str(row["id"])
        if event_id in event_quantiles_low:
            raise ValueError(f"duplicate event id in frequency extension: {event_id}")
        event_ids.append(event_id)
        has_bounds = (
            row.get("marginal_p05_per_year") is not None
            and row.get("marginal_p95_per_year") is not None
        )
        event_quantiles_low[event_id] = "p05" if has_bounds else "fixed"
        event_quantiles_high[event_id] = "p95" if has_bounds else "fixed"
    if not event_ids:
        raise ValueError("independent-event frequency extension requires events")

    scenarios = [deepcopy(dict(raw)) for raw in raw_scenarios]
    scenarios.extend(
        [
            {
                "id": "native-full-scope-independent-event-low",
                "event_quantiles": event_quantiles_low,
                "provenance": (
                    "published marginal p05 bounds applied independently per event; "
                    "events without both published bounds retain their declared rate as fixed; "
                    "frequency sensitivity only; no frequency inference or credible interval"
                ),
                "correlation_assumption": "independent_event_bounds",
            },
            {
                "id": "native-full-scope-independent-event-high",
                "event_quantiles": event_quantiles_high,
                "provenance": (
                    "published marginal p95 bounds applied independently per event; "
                    "events without both published bounds retain their declared rate as fixed; "
                    "frequency sensitivity only; no frequency inference or credible interval"
                ),
                "correlation_assumption": "independent_event_bounds",
            },
        ]
    )
    return {
        "schema_version": "prism.literature_frequency_scenarios.v1",
        "scenarios": scenarios,
        "extension": (
            "Merged native LH2 scenarios retain their original within-asset assumptions; "
            "independent-event p05/p95 comparison scenarios are appended with fixed rates "
            "for events lacking published marginal bounds."
        ),
        "independent_event_bound_event_count": len(event_ids),
        "independent_event_bound_fixed_event_count": sum(
            value == "fixed" for value in event_quantiles_low.values()
        ),
        "frequency_inference_performed": False,
        "facility_credible_interval": False,
    }
