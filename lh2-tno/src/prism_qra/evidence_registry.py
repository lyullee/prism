"""Version-locked evidence authorization for the PRISM reporting boundary.

Digest integrity is not experimental accuracy. Reviewed replay metadata must
be supported by an audit; no document-only entry can authorize model output.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
from pathlib import Path
import re

from physics_assurance import (
    AssuranceResult, AssuranceState, ComponentOutput, EvidenceStatus, assess_outputs,
)


class ReplayLevel(str, Enum):
    DOCUMENTED = "documented-only"
    METRICS = "saved-prediction-metrics-recomputed"
    MODEL = "model-replayed"


class EvidenceUse(str, Enum):
    DEVELOPMENT = "development-or-selection"
    RETROSPECTIVE = "retrospective-external-evaluation"
    HOLDOUT = "independent-campaign-holdout"


@dataclass(frozen=True)
class Artifact:
    role: str
    path: str
    sha256: str

    def __post_init__(self):
        if not self.role.strip() or not self.path.strip():
            raise ValueError("artifact role/path required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("lower-case SHA256 required")

    def intact(self) -> bool:
        try:
            return hashlib.sha256(Path(self.path).read_bytes()).hexdigest() == self.sha256
        except OSError:
            return False


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    component: str
    revision: str
    quantity: str
    unit: str
    observation_operator: str
    campaign: str
    evidence_kind: str  # experiment / CFD / synthetic / software
    use: EvidenceUse
    replay: ReplayLevel
    maximum_status: EvidenceStatus
    artifacts: tuple[Artifact, ...]
    conditions: tuple[str, ...] = ()
    reviewed: bool = False

    def __post_init__(self):
        for name in ("evidence_id", "component", "revision", "quantity", "unit",
                     "observation_operator", "campaign"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} required")
        if self.evidence_kind not in ("experiment", "CFD", "synthetic", "software"):
            raise ValueError("explicit evidence kind required")
        if (not isinstance(self.use, EvidenceUse) or not isinstance(self.replay, ReplayLevel)
                or not isinstance(self.maximum_status, EvidenceStatus)
                or type(self.reviewed) is not bool):
            raise ValueError("typed evidence metadata required")
        if (not isinstance(self.artifacts, tuple) or not self.artifacts
                or any(not isinstance(x, Artifact) for x in self.artifacts)):
            raise ValueError("nonempty artifact tuple required")
        roles = [x.role for x in self.artifacts]
        if len(set(roles)) != len(roles):
            raise ValueError("artifact roles must be unique")
        if (not isinstance(self.conditions, tuple)
                or any(not isinstance(x, str) or not x.strip() for x in self.conditions)):
            raise ValueError("conditions must be explicit strings")
        if self.maximum_status is EvidenceStatus.CONDITIONAL and not self.conditions:
            raise ValueError("conditional evidence requires conditions")

    @property
    def independent(self) -> bool:
        return self.use is EvidenceUse.HOLDOUT and self.evidence_kind == "experiment"


class EvidenceRegistry:
    def __init__(self, records: tuple[EvidenceRecord, ...]):
        if not isinstance(records, tuple) or any(not isinstance(x, EvidenceRecord) for x in records):
            raise ValueError("tuple of EvidenceRecord required")
        self._records = {x.evidence_id: x for x in records}
        if len(self._records) != len(records):
            raise ValueError("duplicate evidence id")

    def check(self, output: ComponentOutput) -> tuple[str, ...]:
        reasons = []
        for evidence_id in output.evidence_ids:
            record = self._records.get(evidence_id)
            if record is None:
                reasons.append(f"UNKNOWN_EVIDENCE:{evidence_id}")
                continue
            expected = (record.component, record.revision, record.quantity,
                        record.unit, record.observation_operator)
            actual = (output.component, output.version, output.quantity,
                      output.unit, output.observation_operator)
            if actual != expected:
                reasons.append(f"EVIDENCE_SCOPE_OR_REVISION_MISMATCH:{evidence_id}")
            if not record.reviewed:
                reasons.append(f"UNREVIEWED_EVIDENCE:{evidence_id}")
            if record.replay is not ReplayLevel.MODEL:
                reasons.append(f"MODEL_REPLAY_NOT_CONFIRMED:{evidence_id}")
            if not {"code", "configuration", "observations", "predictions", "replay-audit"}.issubset(
                    {x.role for x in record.artifacts}):
                reasons.append(f"INCOMPLETE_EVIDENCE_CHAIN:{evidence_id}")
            if any(not x.intact() for x in record.artifacts):
                reasons.append(f"STALE_OR_MISSING_ARTIFACT:{evidence_id}")
            if record.evidence_kind != "experiment":
                reasons.append(f"NOT_EXPERIMENTAL_EVIDENCE:{evidence_id}")
            if record.maximum_status not in (EvidenceStatus.DIRECT, EvidenceStatus.CONDITIONAL):
                reasons.append(f"EVIDENCE_NOT_REPORTABLE:{evidence_id}")
            if record.maximum_status is EvidenceStatus.CONDITIONAL:
                if (output.status is not EvidenceStatus.CONDITIONAL
                        or not set(record.conditions).issubset(output.conditions)):
                    reasons.append(f"EVIDENCE_CONDITIONS_NOT_PROPAGATED:{evidence_id}")
        if not output.evidence_ids:
            reasons.append("NO_EVIDENCE_IDS")
        return tuple(reasons)


def assess_registered_outputs(outputs: tuple[ComponentOutput, ...],
                              registry: EvidenceRegistry) -> AssuranceResult:
    """Production-facing gate: unknown/changed evidence cannot self-qualify.

    Applicability parameter ranges and condition truth need adapter checks in
    addition to this identity/integrity boundary. Independent evidence is NOT
    mandatory for transparent conditional reporting and is never inferred.
    """
    base = assess_outputs(outputs)
    reasons = tuple(f"{x.component}:{r}" for x in outputs for r in registry.check(x))
    if reasons:
        return replace(base, state=AssuranceState.WITHHOLD_OR_ESCALATE,
                       interval=None, reasons=base.reasons + reasons)
    return base
