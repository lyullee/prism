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
from typing import Any, Mapping, TypeAlias

from .consequences import ConsequenceRequest
from .equipment_boundary import ResolvedGasRelease, ResolvedLiquidRelease


PROVIDER_RELEASE_SCHEMA = "prism.resolved_release.v1"
ProviderRelease: TypeAlias = ResolvedGasRelease | ResolvedLiquidRelease


class ProviderReleaseContractError(ValueError):
    """Raised when provider output cannot be promoted to a release boundary."""


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
    opening are rejected.  The returned object is a strict PRISM boundary and
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
    if value.get("failure_opening_diameter_m") is None:
        raise ProviderReleaseContractError(
            "accidental release requires failure_opening_diameter_m"
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


def _same_position(left: Any, right: tuple[float, float, float]) -> bool:
    try:
        return tuple(left) == tuple(right)
    except TypeError:
        return False


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
    if termination.get("basis") is None or termination.get("provenance") is None:
        raise ProviderReleaseContractError(
            "release_termination requires an explicit basis and provenance"
        )
    if not math.isclose(float(termination.get("time_s", -1)), release.duration_s, rel_tol=0, abs_tol=1e-12):
        raise ProviderReleaseContractError(
            "release_termination.time_s must equal the provider duration"
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
    if isinstance(release, ResolvedLiquidRelease):
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
