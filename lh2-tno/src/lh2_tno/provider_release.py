"""Fail-closed adapter from a provider release packet to a PRISM request.

The equipment model owns the thermodynamic and isolation calculation.  This
module only validates the provider's already-resolved JSON boundary and fills
the shared consequence context (weather, ignition, domain, and clock).  It
never estimates a release from pressure, diameter, or a normal-flow result.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence, TypeAlias
from collections.abc import Callable

from .consequences import ConsequenceRequest
from .contracts import Contract, Fraction, Name
from .equipment_boundary import ResolvedGasRelease, ResolvedGasReleaseSet, ResolvedLiquidRelease


PROVIDER_RELEASE_SCHEMA = "prism.resolved_release.v1"
PROVIDER_RELEASE_SET_SCHEMA = "prism.resolved_release_set.v1"
ProviderRelease: TypeAlias = ResolvedGasRelease | ResolvedLiquidRelease
ProviderReleaseSet: TypeAlias = ResolvedGasReleaseSet


class ProviderReleaseContractError(ValueError):
    """Raised when provider output cannot be promoted to a release boundary."""


def _coerce_provider_release(packet: ProviderRelease | Mapping[str, Any] | str | Path) -> ProviderRelease:
    """Return one strict provider release for the reusable runtime adapter."""
    if isinstance(packet, (ResolvedGasRelease, ResolvedLiquidRelease)):
        return packet
    return load_provider_release(packet)


def _coerce_provider_release_set(packet: ProviderReleaseSet | Mapping[str, Any] | str | Path) -> ProviderReleaseSet:
    """Return one strict two-sided provider release set for the runtime adapter."""
    if isinstance(packet, ResolvedGasReleaseSet):
        return packet
    return load_provider_release_set(packet)


class ProviderReleaseBranch(Contract):
    """One provider-resolved conditional branch for an initiating event.

    The release packet remains the provider-owned ``v1`` boundary.  The
    wrapper carries only the conditional barrier/isolation partition so PRISM
    can apply the initiating frequency once and preserve any missing branch
    probability as an explicit uncomputed route.
    """

    id: Name
    probability_given_event: Fraction
    provenance: Name
    release: ProviderRelease | ProviderReleaseSet


def _read_packet(packet: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(packet, (str, Path)):
        path = Path(packet)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderReleaseContractError(f"cannot read provider release packet: {error}") from error
    else:
        value = dict(packet)
    if not isinstance(value, dict):
        raise ProviderReleaseContractError("provider release packet must be a JSON object")
    return value


def load_provider_release(packet: Mapping[str, Any] | str | Path) -> ProviderRelease:
    """Validate one flat ``prism.resolved_release.v1`` accident packet.

    A wrapper envelope, a normal vent, and a packet without an explicit random
    opening are rejected unless the provider explicitly declares an inventory
    termination basis.  The returned object is a strict PRISM boundary and
    is safe to place in a ``ConsequenceRequest`` only after a facility port
    and a frequency event are matched separately.
    """
    value = _read_packet(packet)
    if value.get("provider_export_schema") != PROVIDER_RELEASE_SCHEMA:
        raise ProviderReleaseContractError(
            "provider_export_schema must be prism.resolved_release.v1"
        )
    if value.get("event_kind") != "accidental_leak":
        raise ProviderReleaseContractError(
            "only event_kind=accidental_leak can enter a random-release catalog"
        )
    if value.get("failure_opening_diameter_m") is None and value.get("termination_basis") not in {
        "inventory_depletion", "inventory_over_600s"
    }:
        raise ProviderReleaseContractError(
            "accidental release without an opening requires inventory termination basis"
        )
    boundary = value.get("boundary_kind")
    try:
        if boundary == "resolved_atmospheric_gas_exit":
            return ResolvedGasRelease.model_validate_json(
                json.dumps(value, allow_nan=False)
            )
        if boundary == "resolved_atmospheric_liquid_exit":
            return ResolvedLiquidRelease.model_validate_json(
                json.dumps(value, allow_nan=False)
            )
    except (ValueError, TypeError) as error:
        raise ProviderReleaseContractError(
            f"provider release failed strict PRISM validation: {error}"
        ) from error
    raise ProviderReleaseContractError(
        "boundary_kind must be a resolved atmospheric gas or liquid exit"
    )


def load_provider_emergency_relief(packet: Mapping[str, Any] | str | Path) -> ResolvedGasRelease:
    """Validate an explicit maximum-relief-discharge provider packet.

    Emergency relief is a reviewed initiating event with a provider-owned
    discharge history.  It is kept separate from :func:`load_provider_release`
    so a normal vent or an accidental-leak packet cannot be silently reused.
    """
    value = _read_packet(packet)
    if value.get("provider_export_schema") != PROVIDER_RELEASE_SCHEMA:
        raise ProviderReleaseContractError(
            "provider_export_schema must be prism.resolved_release.v1"
        )
    if value.get("event_kind") != "emergency_relief":
        raise ProviderReleaseContractError(
            "emergency-relief adapter requires event_kind=emergency_relief"
        )
    if value.get("boundary_kind") != "resolved_atmospheric_gas_exit":
        raise ProviderReleaseContractError(
            "emergency-relief adapter requires a resolved atmospheric gas exit"
        )
    if value.get("failure_opening_diameter_m") is not None:
        raise ProviderReleaseContractError(
            "emergency-relief packet must not carry a random leak opening"
        )
    try:
        return ResolvedGasRelease.model_validate_json(json.dumps(value, allow_nan=False))
    except (ValueError, TypeError) as error:
        raise ProviderReleaseContractError(
            f"provider emergency-relief packet failed strict PRISM validation: {error}"
        ) from error


def load_provider_release_catalog(path: str | Path) -> tuple[ProviderRelease, ...]:
    """Load a JSON array or ``{"releases": [...]}`` catalog."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderReleaseContractError(f"cannot read provider release catalog: {error}") from error
    rows = value.get("releases") if isinstance(value, dict) else value
    if not isinstance(rows, list) or not rows:
        raise ProviderReleaseContractError(
            "provider release catalog must contain a non-empty JSON array"
        )
    return tuple(load_provider_release(row) for row in rows)


def load_provider_release_set(packet: Mapping[str, Any] | str | Path) -> ResolvedGasReleaseSet:
    """Validate one explicit two-ended full-bore provider packet.

    The set has its own schema marker and contains two complete
    ``prism.resolved_release.v1`` endpoint packets.  It is deliberately kept
    separate from the single-exit loader so one endpoint cannot be silently
    reused as a two-sided rupture.
    """
    value = _read_packet(packet)
    if value.get("provider_export_schema") != PROVIDER_RELEASE_SET_SCHEMA:
        raise ProviderReleaseContractError(
            "provider_export_schema must be prism.resolved_release_set.v1 for a two-sided packet"
        )
    payload = dict(value)
    payload.pop("provider_export_schema", None)
    try:
        release_set = ResolvedGasReleaseSet.model_validate_json(
            json.dumps(payload, allow_nan=False)
        )
    except (ValueError, TypeError) as error:
        raise ProviderReleaseContractError(
            f"provider two-sided release set failed strict PRISM validation: {error}"
        ) from error
    if any(release.provider_export_schema != PROVIDER_RELEASE_SCHEMA for release in release_set.releases):
        raise ProviderReleaseContractError(
            "two-sided packet endpoints must use prism.resolved_release.v1"
        )
    return release_set


def load_provider_release_set_catalog(path: str | Path) -> tuple[ResolvedGasReleaseSet, ...]:
    """Load a JSON array or ``{"release_sets": [...]}`` two-sided catalog."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderReleaseContractError(
            f"cannot read provider two-sided release-set catalog: {error}"
        ) from error
    rows = value.get("release_sets") if isinstance(value, dict) else value
    if not isinstance(rows, list) or not rows:
        raise ProviderReleaseContractError(
            "provider two-sided release-set catalog must contain a non-empty JSON array"
        )
    return tuple(load_provider_release_set(row) for row in rows)


def _load_provider_release_branch_catalog(
    path: str | Path,
    *,
    release_loader: Any,
    packet_label: str,
) -> tuple[ProviderReleaseBranch, ...]:
    """Load conditional branches using one explicit provider packet loader."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderReleaseContractError(
            f"cannot read provider {packet_label} branch catalog: {error}"
        ) from error
    rows = value.get("branches") if isinstance(value, dict) else value
    if not isinstance(rows, list) or not rows:
        raise ProviderReleaseContractError(
            f"provider {packet_label} branch catalog must contain a non-empty JSON array"
        )
    branches: list[ProviderReleaseBranch] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ProviderReleaseContractError(
                f"provider release branch {index} must be a JSON object"
            )
        packet = row.get("release")
        if not isinstance(packet, dict):
            raise ProviderReleaseContractError(
                f"provider release branch {index} must contain a release object"
            )
        try:
            release = release_loader(packet)
            branch = ProviderReleaseBranch(
                id=row.get("id"),
                probability_given_event=row.get("probability_given_event"),
                provenance=row.get("provenance"),
                release=release,
            )
        except (ProviderReleaseContractError, ValueError, TypeError) as error:
            raise ProviderReleaseContractError(
                f"provider {packet_label} branch {index} failed strict validation: {error}"
            ) from error
        branches.append(branch)
    if len({branch.id for branch in branches}) != len(branches):
        raise ProviderReleaseContractError(
            f"provider {packet_label} branch ids must be unique"
        )
    return tuple(branches)


def load_provider_release_branch_catalog(path: str | Path) -> tuple[ProviderReleaseBranch, ...]:
    """Load conditional branches containing flat accidental-leak packets."""
    return _load_provider_release_branch_catalog(
        path,
        release_loader=load_provider_release,
        packet_label="release",
    )


def load_provider_release_set_branch_catalog(path: str | Path) -> tuple[ProviderReleaseBranch, ...]:
    """Load conditional branches containing two-sided release-set packets."""
    return _load_provider_release_branch_catalog(
        path,
        release_loader=load_provider_release_set,
        packet_label="two-sided release-set",
    )


def load_provider_emergency_relief_catalog(path: str | Path) -> tuple[ResolvedGasRelease, ...]:
    """Load a catalog whose rows are all explicit emergency-relief exits."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderReleaseContractError(f"cannot read provider relief catalog: {error}") from error
    rows = value.get("releases") if isinstance(value, dict) else value
    if not isinstance(rows, list) or not rows:
        raise ProviderReleaseContractError(
            "provider emergency-relief catalog must contain a non-empty JSON array"
        )
    return tuple(load_provider_emergency_relief(row) for row in rows)


def _same_position(left: Any, right: tuple[float, float, float]) -> bool:
    try:
        return tuple(left) == tuple(right)
    except TypeError:
        return False


def _resolve_provider_termination(
    termination: Mapping[str, Any],
    *,
    duration_s: float,
    provider_basis: str | None,
    label: str,
) -> dict[str, Any]:
    """Resolve an explicit provider-duration termination template.

    A catalog may contain branches with different provider durations.  The
    defaults file can therefore use ``time_s=provider_duration`` and
    ``basis=provider_declared`` only when the strict packet carries both an
    explicit termination basis and duration.  No duration or basis is guessed
    when a legacy packet omits that metadata.
    """

    resolved = dict(termination)
    basis = resolved.get("basis")
    if basis == "provider_declared":
        if provider_basis is None:
            raise ProviderReleaseContractError(
                f"{label} requires provider termination_basis for provider_declared context"
            )
        resolved["basis"] = provider_basis
    time_value = resolved.get("time_s")
    if time_value == "provider_duration":
        resolved["time_s"] = duration_s
    try:
        termination_time = float(resolved.get("time_s"))
    except (TypeError, ValueError) as error:
        raise ProviderReleaseContractError(
            f"{label}.time_s must be a finite provider duration"
        ) from error
    if not math.isfinite(termination_time) or not math.isclose(
        termination_time, duration_s, rel_tol=0, abs_tol=1e-12
    ):
        raise ProviderReleaseContractError(
            f"{label}.time_s must equal the provider duration"
        )
    if resolved.get("basis") is None or resolved.get("provenance") is None:
        raise ProviderReleaseContractError(
            f"{label} requires an explicit basis and provenance"
        )
    return resolved


def _merge_provider_clock(
    payload: dict[str, Any],
    releases: Sequence[ResolvedGasRelease | ResolvedLiquidRelease],
) -> None:
    """Add provider breakpoints to the declared consequence clock.

    A provider packet owns its interval clock.  The adapter may add those
    already-computed breakpoints and the provider duration to the consequence
    evaluation grid, but it never creates additional release intervals or
    extends the provider history.
    """

    existing = payload.get("evaluation_times_s")
    if not isinstance(existing, Sequence) or isinstance(existing, (str, bytes)):
        return
    times = [float(value) for value in existing]
    for release in releases:
        times.append(float(release.duration_s))
        times.extend(float(step.time_s) for step in release.steps)
    payload["evaluation_times_s"] = sorted(set(times))


def build_consequence_request_from_provider_release(
    release: ProviderRelease,
    request_defaults: Mapping[str, Any],
) -> ConsequenceRequest:
    """Attach a validated provider boundary to an explicit consequence context.

    ``request_defaults`` contains only context such as weather, ignition,
    domain, evaluation clock, radiation range, and a declared termination
    basis.  It must not contain a source or an initiating frequency.  The
    function copies the provider component, position, inventory, and release
    duration into the request and rejects conflicting declarations.
    """
    if not isinstance(release, (ResolvedGasRelease, ResolvedLiquidRelease)):
        raise ProviderReleaseContractError("release is not a supported PRISM provider boundary")
    payload = copy.deepcopy(dict(request_defaults))
    if payload.get("source_input") is not None:
        raise ProviderReleaseContractError(
            "request defaults must not contain an integrated source_input"
        )
    if payload.get("resolved_release") is not None or payload.get("resolved_liquid_release") is not None:
        raise ProviderReleaseContractError(
            "request defaults must not contain a second provider release"
        )
    if payload.get("resolved_release_set") is not None:
        raise ProviderReleaseContractError(
            "two-sided release sets require their dedicated adapter"
        )
    for key in ("annual_frequency_per_year", "annual_frequency_provenance", "frequency_event", "initiation_intensity_per_s"):
        if payload.get(key) is not None:
            raise ProviderReleaseContractError(
                f"request defaults must not contain initiating frequency: {key}"
            )

    existing_component = payload.get("component_id")
    if existing_component is not None and existing_component != release.component_id:
        raise ProviderReleaseContractError("request component_id disagrees with provider release")
    existing_position = payload.get("source_position_enu_m")
    if existing_position is not None and not _same_position(existing_position, release.position_enu_m):
        raise ProviderReleaseContractError("request source position disagrees with provider release")
    existing_mass = payload.get("available_mass_kg")
    if existing_mass is not None and not math.isclose(float(existing_mass), release.available_mass_kg, rel_tol=0, abs_tol=1e-12):
        raise ProviderReleaseContractError("request inventory disagrees with provider release")

    termination = payload.get("release_termination")
    if not isinstance(termination, dict):
        raise ProviderReleaseContractError(
            "request defaults must declare release_termination basis and provenance"
        )
    termination = _resolve_provider_termination(
        termination,
        duration_s=release.duration_s,
        provider_basis=release.termination_basis,
        label="release_termination",
    )
    if payload.get("source_operator") is None:
        raise ProviderReleaseContractError(
            "request defaults must explicitly select the source_operator"
        )

    payload.update(
        component_id=release.component_id,
        available_mass_kg=release.available_mass_kg,
        source_position_enu_m=list(release.position_enu_m),
        source_input=None,
        resolved_release=None,
        resolved_release_set=None,
        resolved_liquid_release=None,
        annual_frequency_per_year=None,
        annual_frequency_provenance=None,
        frequency_event=None,
        initiation_intensity_per_s=None,
        release_termination=termination,
    )
    _merge_provider_clock(payload, (release,))
    if isinstance(release, ResolvedLiquidRelease):
        if release.no_rainout_evidence is not None:
            # Do not let a template's declared sensitivity radius create a
            # pool when the provider explicitly resolved zero ground rainout.
            payload["pool"] = None
        elif release.pool_footprint is not None:
            pool = payload.get("pool")
            if not isinstance(pool, dict):
                raise ProviderReleaseContractError(
                    "provider-resolved pool footprint requires thermal pool context in request defaults"
                )
            pool["footprint_origin"] = release.pool_footprint.origin
            pool["radius_m"] = release.pool_footprint.radius_m
            pool["footprint_provenance"] = release.pool_footprint.provenance
            pool["footprint_evidence_digest"] = release.pool_footprint.source_digest
            payload["pool"] = pool
        payload["resolved_liquid_release"] = release.model_dump(mode="json")
    else:
        payload["resolved_release"] = release.model_dump(mode="json")
    try:
        return ConsequenceRequest.model_validate_json(
            json.dumps(payload, allow_nan=False)
        )
    except (ValueError, TypeError) as error:
        raise ProviderReleaseContractError(
            f"provider release plus consequence context failed validation: {error}"
        ) from error


def provider_release_resolver_from_packet(
    packet: ProviderRelease | Mapping[str, Any] | str | Path,
    request_defaults: Mapping[str, Any],
    *,
    component_id: str | None = None,
    port_id: str | None = None,
) -> Callable[[Any, Mapping[str, Any]], ConsequenceRequest]:
    """Build the explicit equipment-twin seam from one resolved packet.

    The returned callable is suitable for
    :func:`lh2_tno.service.request_from_equipment_resolver` or
    ``ConsequenceService.update_from_equipment_state``.  The packet is
    validated once and then rebound to the live request context on every
    frame.  It carries no initiating frequency and never infers a release
    from the normalized state; a provider must supply a new packet when its
    release boundary changes.
    """
    release = _coerce_provider_release(packet)
    if component_id is not None and release.component_id != component_id:
        raise ProviderReleaseContractError(
            'provider release component_id does not match the requested adapter component'
        )
    if port_id is not None and release.port_id != port_id:
        raise ProviderReleaseContractError(
            'provider release port_id does not match the requested adapter port'
        )
    defaults = copy.deepcopy(dict(request_defaults))

    def resolve(template: Any, normalized: Mapping[str, Any]) -> ConsequenceRequest:
        if template.component_id != release.component_id:
            raise ProviderReleaseContractError(
                'provider release component_id does not match the telemetry template'
            )
        # ``normalized`` is intentionally not used to overwrite P/h/phase or
        # flow.  Those values belong to the provider-resolved packet.
        return build_consequence_request_from_provider_release(release, defaults)

    return resolve


def build_consequence_request_from_provider_release_set(
    release_set: ResolvedGasReleaseSet,
    request_defaults: Mapping[str, Any],
) -> ConsequenceRequest:
    """Attach a validated two-sided provider set to an explicit context."""
    if not isinstance(release_set, ResolvedGasReleaseSet):
        raise ProviderReleaseContractError("release_set is not a supported PRISM two-sided boundary")
    payload = copy.deepcopy(dict(request_defaults))
    forbidden = (
        "source_input", "resolved_release", "resolved_release_set", "resolved_liquid_release",
        "annual_frequency_per_year", "annual_frequency_provenance", "frequency_event",
        "initiation_intensity_per_s",
    )
    if any(payload.get(key) is not None for key in forbidden):
        raise ProviderReleaseContractError(
            "two-sided request defaults must not contain a source, second provider boundary, or initiating frequency"
        )
    existing_component = payload.get("component_id")
    if existing_component is not None and existing_component != release_set.component_id:
        raise ProviderReleaseContractError("request component_id disagrees with provider release set")
    existing_positions = payload.get("source_positions_enu_m")
    positions = [list(position) for position in release_set.positions_enu_m]
    if existing_positions is not None and [list(position) for position in existing_positions] != positions:
        raise ProviderReleaseContractError("request endpoint positions disagree with provider release set")
    existing_mass = payload.get("available_mass_kg")
    if existing_mass is not None and not math.isclose(
        float(existing_mass), release_set.available_mass_kg, rel_tol=0, abs_tol=1e-12
    ):
        raise ProviderReleaseContractError("request inventory disagrees with provider release set")
    termination = payload.get("release_termination")
    if not isinstance(termination, dict):
        raise ProviderReleaseContractError(
            "two-sided request defaults must declare release_termination basis and provenance"
        )
    provider_bases = {release.termination_basis for release in release_set.releases}
    if len(provider_bases) != 1:
        raise ProviderReleaseContractError(
            "two-sided provider endpoints must share one termination basis"
        )
    termination = _resolve_provider_termination(
        termination,
        duration_s=release_set.duration_s,
        provider_basis=next(iter(provider_bases)),
        label="two-sided release_termination",
    )
    if termination.get("basis") != "two_sided_rupture":
        raise ProviderReleaseContractError(
            "two-sided request requires two_sided_rupture termination basis"
        )
    if payload.get("source_operator") != "equipment_two_sided_rupture":
        raise ProviderReleaseContractError(
            "two-sided request requires source_operator=equipment_two_sided_rupture"
        )
    payload.update(
        component_id=release_set.component_id,
        available_mass_kg=release_set.available_mass_kg,
        source_position_enu_m=positions[0],
        source_positions_enu_m=positions,
        source_input=None,
        resolved_release=None,
        resolved_release_set=release_set.model_dump(mode="json"),
        resolved_liquid_release=None,
        annual_frequency_per_year=None,
        annual_frequency_provenance=None,
        frequency_event=None,
        initiation_intensity_per_s=None,
        release_termination=termination,
    )
    _merge_provider_clock(payload, release_set.releases)
    try:
        return ConsequenceRequest.model_validate_json(json.dumps(payload, allow_nan=False))
    except (ValueError, TypeError) as error:
        raise ProviderReleaseContractError(
            f"two-sided provider release set plus consequence context failed validation: {error}"
        ) from error


def provider_release_set_resolver_from_packet(
    packet: ProviderReleaseSet | Mapping[str, Any] | str | Path,
    request_defaults: Mapping[str, Any],
    *,
    component_id: str | None = None,
) -> Callable[[Any, Mapping[str, Any]], ConsequenceRequest]:
    """Build the explicit runtime seam for a provider two-sided rupture set."""
    release_set = _coerce_provider_release_set(packet)
    if component_id is not None and release_set.component_id != component_id:
        raise ProviderReleaseContractError(
            'provider release-set component_id does not match the requested adapter component'
        )
    defaults = copy.deepcopy(dict(request_defaults))

    def resolve(template: Any, normalized: Mapping[str, Any]) -> ConsequenceRequest:
        if template.component_id != release_set.component_id:
            raise ProviderReleaseContractError(
                'provider release-set component_id does not match the telemetry template'
            )
        return build_consequence_request_from_provider_release_set(release_set, defaults)

    return resolve
