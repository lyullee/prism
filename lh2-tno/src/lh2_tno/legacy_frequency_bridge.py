"""Bridge scenario output from the external legacy TNO taxonomy.

The legacy TNO implementation and the LH2 package deliberately remain
separate distributions.  This module provides the narrow, auditable handoff
between them: a caller runs the pinned legacy ``enumerate_scenarios`` and
passes its serialized scenario rows plus an explicit component map.  PRISM
does not re-resolve a rate, infer a component from a name, or silently turn a
legacy release path into a provider packet.

The resulting :class:`FrequencyEvent` objects can be consumed by the same
``bind_event``/consequence and campaign contracts as native LH2 catalogue
events.  Legacy scenario fields that are outside the frequency contract are
returned in the audit sidecar so release-path and physics-route limitations
remain visible.
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping

from .contracts import Facility, canonical_digest
from .frequency import FrequencyEvent, ReleaseDefinition


_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def _required(row: Mapping[str, Any], key: str) -> Any:
    value = row.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"legacy scenario requires {key}")
    return value


def _finite_nonnegative(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"legacy scenario {field} must be numeric") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"legacy scenario {field} must be finite and nonnegative")
    return number


def _finite_positive(value: Any, *, field: str) -> float:
    number = _finite_nonnegative(value, field=field)
    if number <= 0:
        raise ValueError(f"legacy scenario {field} must be positive")
    return number


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.:/-]+", "_", value.strip())
    value = value.strip("_/")
    if not value:
        raise ValueError("legacy scenario id becomes empty after normalization")
    return value


def _source_digest(source_sha256: str) -> str:
    if not isinstance(source_sha256, str) or not _HEX64.fullmatch(source_sha256):
        raise ValueError("legacy TNO source_sha256 must be a 64-character hexadecimal digest")
    return source_sha256.lower()


def bridge_legacy_scenarios(
    scenarios: Iterable[Mapping[str, Any]],
    component_map: Mapping[str, str],
    *,
    plan_id: str = "legacy-tno",
    source: str = "external legacy TNO taxonomy.enumerate_scenarios",
    source_sha256: str,
    facility: Facility | None = None,
    basis: str | Mapping[str, str] = "TNO_PURPLE_LOC",
) -> tuple[tuple[FrequencyEvent, ...], dict[str, Any]]:
    """Convert serialized legacy scenarios into PRISM frequency events.

    ``component_map`` is keyed by the exact legacy ``scenario_id``.  An
    explicit map is required for every row; tag-prefix or component-kind
    guessing would be unsafe for a facility boundary.  ``basis`` is supplied
    by the caller because the legacy taxonomy may have used a native TNO,
    LH2-literature, or explicitly documented proxy row.

    The bridge preserves the legacy annual rate as a declared event rate by
    using a unit exposure multiplier of one.  The old generator has already
    applied its count and secondary-breach terms.  It therefore does not add
    another count or length multiplier.
    """
    digest = _source_digest(source_sha256)
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise ValueError("plan_id must be a nonempty string")
    if isinstance(basis, str):
        if basis not in {"TNO_PURPLE_LOC", "LH2_LITERATURE"}:
            raise ValueError("basis must be TNO_PURPLE_LOC or LH2_LITERATURE")
    elif not isinstance(basis, Mapping) or not basis:
        raise ValueError("basis must be TNO_PURPLE_LOC, LH2_LITERATURE, or a scenario map")
    if not isinstance(component_map, Mapping) or not component_map:
        raise ValueError("an explicit nonempty legacy scenario component_map is required")

    rows = list(scenarios)
    if not rows:
        raise ValueError("at least one legacy scenario is required")
    component_ids = {component.id for component in facility.components} if facility else None
    events: list[FrequencyEvent] = []
    sidecar_rows: list[dict[str, Any]] = []
    seen_scenario_ids: set[str] = set()
    seen_event_ids: set[str] = set()

    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("legacy scenarios must be mapping rows")
        scenario_id = str(_required(row, "scenario_id"))
        if scenario_id in seen_scenario_ids:
            raise ValueError(f"duplicate legacy scenario_id {scenario_id}")
        seen_scenario_ids.add(scenario_id)
        row_basis = basis if isinstance(basis, str) else basis.get(scenario_id)
        if row_basis not in {"TNO_PURPLE_LOC", "LH2_LITERATURE"}:
            raise ValueError(f"no valid frequency basis for legacy scenario {scenario_id}")
        component_id = component_map.get(scenario_id)
        if not isinstance(component_id, str) or not component_id.strip():
            raise ValueError(f"no explicit component mapping for legacy scenario {scenario_id}")
        if component_ids is not None and component_id not in component_ids:
            raise ValueError(
                f"legacy scenario {scenario_id} maps to unknown facility component {component_id}"
            )

        release_kind = str(_required(row, "release_kind")).upper()
        if release_kind == "CONTINUOUS":
            release_mode = "hole"
            hole_diameter_m = _finite_positive(row.get("hole_diameter_m"), field="hole_diameter_m")
            release = ReleaseDefinition(mode=release_mode, hole_diameter_m=hole_diameter_m)
        elif release_kind == "INSTANTANEOUS":
            release_mode = "instantaneous_inventory"
            hole_diameter_m = None
            release = ReleaseDefinition(mode=release_mode)
        else:
            raise ValueError(
                f"legacy scenario {scenario_id} has unsupported release_kind {release_kind!r}"
            )

        annual_frequency = _finite_nonnegative(row.get("frequency_per_year"), field="frequency_per_year")
        primitive = str(_required(row, "primitive"))
        service = str(_required(row, "service"))
        profile = f"LEGACY_TNO_{_slug(primitive)}_{_slug(service)}"
        event_id = f"{_slug(plan_id)}/{_slug(component_id)}/{_slug(scenario_id)}"
        if event_id in seen_event_ids:
            raise ValueError(f"duplicate bridged event id {event_id}")
        seen_event_ids.add(event_id)

        limitations = [
            "frequency was generated by the external legacy TNO taxonomy; PRISM did not infer or update it",
            "legacy count/secondary-breach arithmetic is already included; no additional exposure multiplier is applied",
            "legacy scenario output is diagnostic until provider release, isolation and physical evidence are qualified",
        ]
        release_path = str(row.get("release_path", "UNSPECIFIED"))
        physics_route = str(row.get("physics_route", "UNSPECIFIED"))
        grade = str(row.get("grade", "UNSPECIFIED"))
        frequency_proxy = str(row.get("frequency_fuel_proxy", ""))
        limitations.extend([
            f"legacy release_path={release_path} is preserved in the bridge audit sidecar",
            f"legacy physics_route={physics_route} and grade={grade} are preserved in the bridge audit sidecar",
        ])
        if frequency_proxy and frequency_proxy.lower() not in {"none", "null"}:
            limitations.append(
                f"legacy frequency_fuel_proxy={frequency_proxy}; this is not a measured facility rate"
            )
        event = FrequencyEvent(
            id=event_id,
            asset_id=f"legacy:{_slug(str(row.get('tag', scenario_id)))}",
            model_component_id=component_id,
            profile=profile,
            loc=str(row.get("bin_label", "legacy")),
            basis=row_basis,
            base_rate=annual_frequency,
            rate_unit="item^-1 year^-1",
            exposure_multiplier=1.0,
            annual_frequency_per_year=annual_frequency,
            statistic="published_default",
            source=source,
            source_sha256=digest,
            catalogue_digest=canonical_digest({
                "source": source,
                "source_sha256": digest,
                "legacy_scenario_id": scenario_id,
            }),
            release=release,
            classification_basis=f"legacy_tno:{primitive}:{service}",
            limitations=tuple(dict.fromkeys(limitations)),
        )
        events.append(event)
        sidecar_rows.append({
            "event_id": event_id,
            "legacy_scenario_id": scenario_id,
            "legacy_tag": str(row.get("tag", "")),
            "legacy_primitive": primitive,
            "legacy_service": service,
            "legacy_release_kind": release_kind,
            "legacy_release_path": release_path,
            "legacy_physics_route": physics_route,
            "legacy_grade": grade,
            "legacy_frequency_fuel_proxy": row.get("frequency_fuel_proxy"),
            "legacy_frequency_per_year": annual_frequency,
            "frequency_basis": row_basis,
            "mapped_component_id": component_id,
            "available_mass_kg": row.get("available_mass_kg"),
            "isolation_time_s": row.get("isolation_time_s"),
            "position": row.get("position"),
        })

    audit = {
        "schema_version": "prism.legacy_tno_frequency_bridge.v1",
        "plan_id": plan_id,
        "source": source,
        "source_sha256": digest,
        "basis": basis if isinstance(basis, str) else "per_scenario",
        "legacy_scenario_count": len(rows),
        "bridged_event_count": len(events),
        "mapped_component_ids": sorted({event.model_component_id for event in events}),
        "release_mode_counts": {
            mode: sum(event.release.mode == mode for event in events)
            for mode in sorted({event.release.mode for event in events})
        },
        "frequency_inference_performed": False,
        "provider_packet_created": False,
        "facility_qra_promotion": False,
        "rows": sidecar_rows,
    }
    return tuple(events), audit


def bridge_digest(audit: Mapping[str, Any]) -> str:
    """Return a stable digest for a bridge audit sidecar."""
    return canonical_digest(audit)
