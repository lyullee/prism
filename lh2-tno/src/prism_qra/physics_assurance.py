"""PRISM component reporting contract; not a physical validation certificate.

Intervals are declared model/parameter sets, NOT confidence intervals or
guaranteed conservative bounds. No weighting/averaging of correlated models.
Runtime adapters must supply reviewed evidence and matched source fingerprints.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class EvidenceStatus(str, Enum):
    DIRECT = "direct"
    CONDITIONAL = "conditional"
    DIAGNOSTIC = "diagnostic"
    ADVISORY = "advisory"
    OUT_OF_SCOPE = "out-of-scope"


class AssuranceState(str, Enum):
    QUALIFIED_SINGLE = "QUALIFIED_SINGLE"
    QUALIFIED_ENVELOPE = "QUALIFIED_ENVELOPE"
    MODEL_CONFLICT = "MODEL_CONFLICT"
    WITHHOLD_OR_ESCALATE = "WITHHOLD_OR_ESCALATE"


@dataclass(frozen=True)
class ComponentOutput:
    component: str
    version: str
    quantity: str
    unit: str
    observation_operator: str
    source_fingerprint: str
    receptor_fingerprint: str
    evidence_ids: tuple[str, ...]
    status: EvidenceStatus
    interval: tuple[float, float] | None
    conditions: tuple[str, ...] = ()
    conditions_satisfied: bool = False
    warnings: tuple[str, ...] = ()
    shared_limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("component", "version", "quantity", "unit",
                     "observation_operator", "source_fingerprint", "receptor_fingerprint"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"nonempty {name} required")
        if not isinstance(self.status, EvidenceStatus):
            raise ValueError("explicit EvidenceStatus required")
        if type(self.conditions_satisfied) is not bool:
            raise ValueError("conditions_satisfied must be boolean")
        for name in ("evidence_ids", "conditions", "warnings", "shared_limitations"):
            items = getattr(self, name)
            if (not isinstance(items, tuple)
                    or any(not isinstance(x, str) or not x.strip() for x in items)):
                raise ValueError(f"{name} must be a tuple of nonempty strings")
        if self.status is EvidenceStatus.OUT_OF_SCOPE and self.interval is not None:
            raise ValueError("out-of-scope output must carry no interval")
        if self.status in (EvidenceStatus.DIRECT, EvidenceStatus.CONDITIONAL):
            if not self.evidence_ids or self.interval is None:
                raise ValueError("reportable outputs require evidence and interval")
        if self.status is EvidenceStatus.CONDITIONAL and not self.conditions:
            raise ValueError("conditional output requires declared conditions")
        if self.interval is not None:
            if (not isinstance(self.interval, tuple) or len(self.interval) != 2
                    or any(isinstance(x, bool) or not isinstance(x, (int, float))
                           or not math.isfinite(x) for x in self.interval)
                    or self.interval[0] > self.interval[1]):
                raise ValueError("finite ordered interval required")

    @property
    def comparison_key(self) -> tuple[str, ...]:
        return (self.quantity, self.unit, self.observation_operator,
                self.source_fingerprint, self.receptor_fingerprint)

    @property
    def reportable(self) -> bool:
        return (self.status is EvidenceStatus.DIRECT
                or (self.status is EvidenceStatus.CONDITIONAL
                    and self.conditions_satisfied))


@dataclass(frozen=True)
class AssuranceResult:
    state: AssuranceState
    interval: tuple[float, float] | None
    components: tuple[ComponentOutput, ...]
    reasons: tuple[str, ...]
    shared_limitations: tuple[str, ...]
    physical_validation_claim: bool = False


def assess_outputs(outputs: tuple[ComponentOutput, ...]) -> AssuranceResult:
    """Fail closed on missing/unmatched evidence; preserve conflicting members.

    Qualification means metadata-qualified reporting only. Disjoint intervals
    flag a conflict in declared sets, not a hypothesis test of model accuracy.
    A conflict exposes no management interval until an escalation policy exists.
    """
    if not isinstance(outputs, tuple) or any(not isinstance(x, ComponentOutput) for x in outputs):
        raise ValueError("tuple of ComponentOutput required")
    shared = tuple(sorted({s for x in outputs for s in x.shared_limitations}))

    def result(state, interval=None, reasons=()):
        return AssuranceResult(state, interval, outputs, reasons, shared)

    if not outputs:
        return result(AssuranceState.WITHHOLD_OR_ESCALATE, reasons=("NO_COMPONENT_OUTPUT",))
    identities = [(x.component, x.version) for x in outputs]
    if len(set(identities)) != len(identities):
        return result(AssuranceState.WITHHOLD_OR_ESCALATE, reasons=("DUPLICATE_COMPONENT",))
    if len({x.comparison_key for x in outputs}) != 1:
        return result(AssuranceState.WITHHOLD_OR_ESCALATE, reasons=("UNMATCHED_OBSERVABLE_OR_SOURCE",))
    blocked = tuple(f"{x.component}:{x.status.value}:NOT_REPORTABLE"
                    for x in outputs if not x.reportable)
    if blocked:
        # Do not silently discard unsupported components and qualify the rest.
        return result(AssuranceState.WITHHOLD_OR_ESCALATE, reasons=blocked)
    intervals = tuple(x.interval for x in outputs)
    assert all(x is not None for x in intervals)
    low = min(x[0] for x in intervals)
    high = max(x[1] for x in intervals)
    if max(x[0] for x in intervals) > min(x[1] for x in intervals):
        return result(AssuranceState.MODEL_CONFLICT, reasons=("DISJOINT_DECLARED_SETS",))
    state = (AssuranceState.QUALIFIED_SINGLE if len(outputs) == 1
             else AssuranceState.QUALIFIED_ENVELOPE)
    return result(state, (low, high), ("NOT_A_CONFIDENCE_OR_CONSERVATIVE_BOUND",))
