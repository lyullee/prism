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
