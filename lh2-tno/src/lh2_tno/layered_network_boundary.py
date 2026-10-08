"""Fail-closed inspection of an external LayeredTank network boundary.

The equipment digital-twin project exposes a ``LayeredTankNetworkStepResult``
with a tank result and a solved network result.  That result is useful for
checking inventory feedback and phase-aware routing, but it is not by itself
an atmospheric release packet: it does not contain a flash partition, droplet
fate, or an atmospheric exit geometry.  This module extracts only the
quantities that are actually present and reports whether the boundary can be
promoted to :class:`ResolvedLiquidRelease`.

The adapter deliberately uses duck typing so the optional equipment project is
not a runtime dependency of ``prism-risk``.  A caller may pass provider result
objects directly, or small test doubles with the same public attributes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Literal, Sequence


Phase = Literal["liquid", "vapor"]


@dataclass(frozen=True)
class LayeredBoundaryObservation:
    """One solved link observation, preserving its signed direction."""

    time_s: float
    link_name: str
    source_node: str
    target_node: str
    source_phase: Phase
    signed_mass_flow_kg_s: float
    outward_mass_flow_kg_s: float
    transmitted_specific_enthalpy_j_kg: float
    source_pressure_pa: float
    target_pressure_pa: float
    target_phase: str
    source_port_id: str | None
    target_port_id: str | None


@dataclass(frozen=True)
class LayeredBoundaryAudit:
    """Review result for one explicit source-to-target network boundary."""

    component_id: str
    source_node: str
    target_node: str
    source_phase: Phase
    ambient_pressure_pa: float
    pressure_tolerance_pa: float
    result_count: int
    observations: tuple[LayeredBoundaryObservation, ...]
    provider_cumulative_boundary_mass_kg: float | None
    provider_cumulative_boundary_energy_j: float | None
    atmospheric_boundary: bool
    phase_partition_available: bool
    exit_geometry_available: bool
    termination_available: bool
    ready_for_resolved_liquid_release: bool
    blocking_reasons: tuple[str, ...]

    @property
    def outward_mass_flow_max_kg_s(self) -> float:
        return max((item.outward_mass_flow_kg_s for item in self.observations), default=0.0)

    @property
    def observed_source_pressure_range_pa(self) -> tuple[float, float] | None:
        if not self.observations:
            return None
        values = [item.source_pressure_pa for item in self.observations]
        return min(values), max(values)

    @property
    def observed_target_pressure_range_pa(self) -> tuple[float, float] | None:
        if not self.observations:
            return None
        values = [item.target_pressure_pa for item in self.observations]
        return min(values), max(values)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe, reviewable export without provider objects."""

        data = asdict(self)
        data["observations"] = [asdict(item) for item in self.observations]
        data["outward_mass_flow_max_kg_s"] = self.outward_mass_flow_max_kg_s
        data["observed_source_pressure_range_pa"] = self.observed_source_pressure_range_pa
        data["observed_target_pressure_range_pa"] = self.observed_target_pressure_range_pa
        return data


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _state(node_states: Any, node: str, context: str) -> Any:
    try:
        return node_states[node]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{context} does not expose node state {node!r}") from exc


def _outward_flow(flow: Any, source_node: str, target_node: str, context: str) -> float:
    mass = _finite(getattr(flow, "mass_flow_kg_s", None), f"{context}.mass_flow_kg_s")
    left = str(getattr(flow, "left", ""))
    right = str(getattr(flow, "right", ""))
    if (left, right) == (source_node, target_node):
        return mass
    if (left, right) == (target_node, source_node):
        return -mass
    raise ValueError(
        f"{context} endpoints {left!r}->{right!r} do not match "
        f"{source_node!r}->{target_node!r}"
    )


def audit_layered_liquid_boundary(
    results: Sequence[Any],
    *,
    component_id: str,
    source_node: str,
    target_node: str,
    source_phase: Phase,
    ambient_pressure_pa: float,
    link_name: str,
    pressure_tolerance_pa: float = 250.0,
    phase_partition_available: bool = False,
    exit_geometry_available: bool = False,
    termination_available: bool = False,
) -> LayeredBoundaryAudit:
    """Inspect a provider link without inventing an atmospheric release.

    ``phase_partition_available`` and the geometry/termination flags must be
    set only when a separate provider adapter has supplied those data.  The
    LayeredTank network result itself sets none of them.  The function still
    records tank inventory ledger values so the missing conversion is visible
    in a review artifact.
    """

    if not component_id.strip():
        raise ValueError("component_id is required")
    if source_phase not in {"liquid", "vapor"}:
        raise ValueError("source_phase must be 'liquid' or 'vapor'")
    ambient = _finite(ambient_pressure_pa, "ambient_pressure_pa")
    tolerance = _finite(pressure_tolerance_pa, "pressure_tolerance_pa")
    if ambient <= 0.0 or tolerance < 0.0:
        raise ValueError("ambient pressure must be positive and tolerance non-negative")
    if not results:
        raise ValueError("LayeredTank provider returned no network results")

    observations: list[LayeredBoundaryObservation] = []
    cumulative_mass = None
    cumulative_energy = None
    previous_time = None
    for index, result in enumerate(results):
        context = f"LayeredTank result {index}"
        network = getattr(result, "network_solution", None)
        if network is None:
            raise ValueError(f"{context} does not expose network_solution")
        flows = getattr(network, "link_flows", None)
        states = getattr(network, "node_states", None)
        if flows is None or states is None:
            raise ValueError(f"{context} network solution lacks link_flows or node_states")
        try:
            flow = flows[link_name]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"{context} does not expose link {link_name!r}") from exc
        time_s = _finite(getattr(result, "time_s", getattr(getattr(result, "tank", None), "time_s", None)), f"{context}.time_s")
        if previous_time is not None and time_s <= previous_time:
            raise ValueError("provider result times must be strictly increasing")
        previous_time = time_s
        signed = _outward_flow(flow, source_node, target_node, f"{context}.{link_name}")
        source_state = _state(states, source_node, context)
        target_state = _state(states, target_node, context)
        observations.append(LayeredBoundaryObservation(
            time_s=time_s,
            link_name=link_name,
            source_node=source_node,
            target_node=target_node,
            source_phase=source_phase,
            signed_mass_flow_kg_s=signed,
            outward_mass_flow_kg_s=max(0.0, signed),
            transmitted_specific_enthalpy_j_kg=_finite(
                getattr(flow, "transmitted_specific_enthalpy_J_kg", None),
                f"{context}.{link_name}.transmitted_specific_enthalpy_J_kg",
            ),
            source_pressure_pa=_finite(getattr(source_state, "pressure_Pa", None), f"{context}.{source_node}.pressure_Pa"),
            target_pressure_pa=_finite(getattr(target_state, "pressure_Pa", None), f"{context}.{target_node}.pressure_Pa"),
            target_phase=str(getattr(target_state, "phase", "unknown")),
            source_port_id=getattr(flow, "source_port_id", None),
            target_port_id=getattr(flow, "target_port_id", None),
        ))
        tank_result = getattr(result, "tank", None)
        if tank_result is not None:
            if hasattr(tank_result, "cumulative_boundary_mass_kg"):
                cumulative_mass = _finite(
                    tank_result.cumulative_boundary_mass_kg,
                    f"{context}.tank.cumulative_boundary_mass_kg",
                )
            if hasattr(tank_result, "cumulative_boundary_energy_J"):
                cumulative_energy = _finite(
                    tank_result.cumulative_boundary_energy_J,
                    f"{context}.tank.cumulative_boundary_energy_J",
                )

    atmospheric = all(
        abs(item.target_pressure_pa - ambient) <= tolerance
        for item in observations
    )
    reasons: list[str] = []
    if not atmospheric:
        reasons.append("target boundary pressure is not ambient")
    if not phase_partition_available:
        reasons.append("provider result has no flash-gas/ground-liquid/airborne-liquid partition")
    if not exit_geometry_available:
        reasons.append("provider result has no atmospheric exit geometry and direction")
    if not termination_available:
        reasons.append("provider result does not declare an atmospheric release termination contract")
    ready = atmospheric and phase_partition_available and exit_geometry_available and termination_available
    return LayeredBoundaryAudit(
        component_id=component_id,
        source_node=source_node,
        target_node=target_node,
        source_phase=source_phase,
        ambient_pressure_pa=ambient,
        pressure_tolerance_pa=tolerance,
        result_count=len(observations),
        observations=tuple(observations),
        provider_cumulative_boundary_mass_kg=cumulative_mass,
        provider_cumulative_boundary_energy_j=cumulative_energy,
        atmospheric_boundary=atmospheric,
        phase_partition_available=phase_partition_available,
        exit_geometry_available=exit_geometry_available,
        termination_available=termination_available,
        ready_for_resolved_liquid_release=ready,
        blocking_reasons=tuple(reasons),
    )


__all__ = [
    "LayeredBoundaryAudit",
    "LayeredBoundaryObservation",
    "audit_layered_liquid_boundary",
]
