"""Acceptance gate for facility-specific hydrogen discharge evidence.

The physics code can calculate a release from pressure, temperature, diameter
and a discharge coefficient.  This module answers the different question:
whether the facility evidence is good enough to replace the conservative
source term or to claim validation.  Geometry, raw time series and certified
capacity are kept separate so that a fitted coefficient cannot silently stand
in for missing apparatus records.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from statistics import median
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EvidenceModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, revalidate_instances="always")


class InletGeometry(str, Enum):
    SHARP_EDGED = "SHARP_EDGED"
    CHAMFERED = "CHAMFERED"
    ROUNDED = "ROUNDED"
    CONICAL = "CONICAL"
    MULTI_STEP = "MULTI_STEP"
    UNKNOWN = "UNKNOWN"


class DifferentiationMethod(str, Enum):
    BACKWARD_DIFFERENCE = "BACKWARD_DIFFERENCE"
    CENTRAL_DIFFERENCE = "CENTRAL_DIFFERENCE"
    SAVITZKY_GOLAY = "SAVITZKY_GOLAY"
    LOCAL_LINEAR_REGRESSION = "LOCAL_LINEAR_REGRESSION"
    INSTRUMENT_DIRECT = "INSTRUMENT_DIRECT"


class CapacityBasis(str, Enum):
    MANUFACTURER_CERTIFIED = "MANUFACTURER_CERTIFIED"
    CAPACITY_TEST = "CAPACITY_TEST"
    CALIBRATED = "CALIBRATED"


class NozzleGeometry(EvidenceModel):
    equipment_tag: str
    drawing_id: str
    drawing_revision: str
    limiting_bore_mm: float = Field(gt=0)
    bore_length_mm: float = Field(gt=0)
    inlet_geometry: InletGeometry
    chamfer_angle_deg: Optional[float] = Field(default=None, gt=0, lt=90)
    chamfer_length_mm: Optional[float] = Field(default=None, gt=0)
    surface_roughness_um: float = Field(ge=0)
    outlet_geometry_note: str
    measurement_method: str
    source_file: str
    reviewer: str
    review_date: str

    @field_validator(
        "equipment_tag", "drawing_id", "drawing_revision",
        "outlet_geometry_note", "measurement_method", "source_file",
        "reviewer", "review_date",
    )
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("required evidence text must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def _chamfer_fields_match_geometry(self):
        if self.inlet_geometry is InletGeometry.CHAMFERED:
            if self.chamfer_angle_deg is None or self.chamfer_length_mm is None:
                raise ValueError(
                    "chamfered inlet requires angle and chamfer length"
                )
        return self


class CapacityCertificate(EvidenceModel):
    equipment_tag: str
    manufacturer: str
    model: str
    serial_number: str
    document_id: str
    revision: str
    test_standard: str
    basis: CapacityBasis
    test_fluid: str
    set_pressure_barg: float = Field(ge=0)
    inlet_temperature_k: float = Field(gt=0)
    backpressure_barg: float = Field(ge=0)
    certified_capacity_kg_s: Optional[float] = Field(default=None, gt=0)
    certified_discharge_coefficient: Optional[float] = Field(
        default=None, gt=0, le=1
    )
    valid_for_hydrogen: bool
    source_file: str

    @field_validator("equipment_tag", "manufacturer", "model", "serial_number",
                     "document_id", "revision", "test_standard", "test_fluid",
                     "source_file")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("certificate identifiers must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def _has_capacity_or_coefficient(self):
        if (self.certified_capacity_kg_s is None
                and self.certified_discharge_coefficient is None):
            raise ValueError(
                "certificate must give capacity or discharge coefficient"
            )
        if not self.source_file.strip():
            raise ValueError("certificate source_file must not be blank")
        return self


class DischargeTestMetadata(EvidenceModel):
    test_id: str
    equipment_tag: str
    raw_data_file: str
    raw_data_sha256: str
    clock_source: str
    nominal_sampling_interval_s: float = Field(gt=0)
    timestamp_uncertainty_s: float = Field(ge=0)
    synchronization_method: str
    measured_sync_offset_s: float = Field(ge=0)
    maximum_allowed_sync_offset_s: float = Field(gt=0)
    pressure_sensor_id: str
    pressure_location: str
    pressure_uncertainty_pa: float = Field(gt=0)
    temperature_sensor_id: str
    temperature_location: str
    temperature_uncertainty_k: float = Field(gt=0)
    mass_sensor_id: str
    mass_resolution_kg: float = Field(gt=0)
    mass_uncertainty_kg: float = Field(gt=0)
    differentiation_method: DifferentiationMethod
    differentiation_window_s: float = Field(gt=0)
    filter_note: str
    valve_signal_note: str
    operator: str
    test_date: str

    @field_validator("raw_data_sha256")
    @classmethod
    def _sha256(cls, value: str) -> str:
        text = value.strip().lower()
        if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
            raise ValueError("raw_data_sha256 must contain 64 hex characters")
        return text

    @model_validator(mode="after")
    def _sync_is_resolved(self):
        if self.measured_sync_offset_s > self.maximum_allowed_sync_offset_s:
            raise ValueError("measured clock offset exceeds acceptance limit")
        if self.maximum_allowed_sync_offset_s > self.nominal_sampling_interval_s:
            raise ValueError(
                "allowed clock offset must not exceed one sampling interval"
            )
        if self.differentiation_window_s < self.nominal_sampling_interval_s:
            raise ValueError(
                "differentiation window cannot be shorter than one sample"
            )
        return self


class DischargeSample(EvidenceModel):
    time_s: float = Field(ge=0)
    tank_pressure_pa: float = Field(gt=0)
    nozzle_upstream_pressure_pa: Optional[float] = Field(default=None, gt=0)
    tank_temperature_k: float = Field(gt=0)
    nozzle_upstream_temperature_k: Optional[float] = Field(default=None, gt=0)
    tank_mass_kg: float = Field(ge=0)
    measured_mass_flow_kg_s: Optional[float] = Field(default=None, ge=0)
    valve_position_pct: Optional[float] = Field(default=None, ge=0, le=100)
    quality_flag: str = "VALID"


@dataclass(frozen=True)
class TimeSeriesAudit:
    n_samples: int
    duration_s: float
    median_interval_s: float
    maximum_interval_s: float
    measured_mass_loss_kg: float
    integrated_flow_kg: Optional[float]
    flow_mass_closure_relative: Optional[float]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SourceEvidenceAssessment:
    claim_level: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    time_series: Optional[TimeSeriesAudit]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_discharge_timeseries(
    metadata: DischargeTestMetadata,
    samples: list[DischargeSample],
) -> TimeSeriesAudit:
    metadata = DischargeTestMetadata.model_validate(metadata)
    samples = [DischargeSample.model_validate(row) for row in samples]
    if len(samples) < 5:
        raise ValueError("raw discharge series requires at least five samples")
    times = [row.time_s for row in samples]
    intervals = [b - a for a, b in zip(times, times[1:])]
    if any(dt <= 0 for dt in intervals):
        raise ValueError("sample time must be strictly increasing")
    typical = median(intervals)
    maximum = max(intervals)
    warnings = []
    if abs(typical - metadata.nominal_sampling_interval_s) > (
            0.20 * metadata.nominal_sampling_interval_s):
        raise ValueError("median sample interval differs from metadata by >20%")
    if maximum > 3.0 * typical:
        raise ValueError("raw series contains a gap longer than three samples")

    tolerance = 3.0 * metadata.mass_uncertainty_kg
    masses = [row.tank_mass_kg for row in samples]
    if any(b > a + tolerance for a, b in zip(masses, masses[1:])):
        raise ValueError("tank mass increases beyond instrument uncertainty")
    mass_loss = masses[0] - masses[-1]
    if mass_loss <= max(5.0 * metadata.mass_uncertainty_kg, 1e-6):
        raise ValueError("net mass loss is not resolved above uncertainty")

    given_flows = [row.measured_mass_flow_kg_s for row in samples]
    if any(value is None for value in given_flows):
        if not all(value is None for value in given_flows):
            raise ValueError("mass-flow column must be complete or entirely blank")
        integrated = None
        closure = None
        warnings.append(
            "mass flow was not supplied; derive it with the declared method "
            "and retain both raw and processed series"
        )
    else:
        flows = [float(value) for value in given_flows]
        integrated = sum(
            0.5 * (a + b) * dt
            for a, b, dt in zip(flows, flows[1:], intervals)
        )
        closure = abs(integrated - mass_loss) / mass_loss
        absolute_limit = 5.0 * metadata.mass_uncertainty_kg
        if abs(integrated - mass_loss) > max(0.05 * mass_loss, absolute_limit):
            raise ValueError(
                "integrated mass flow does not close tank mass within 5% or "
                "five mass-uncertainty intervals"
            )

    if metadata.timestamp_uncertainty_s > 0.5 * typical:
        warnings.append(
            "timestamp uncertainty exceeds half a sampling interval"
        )
    if all(row.nozzle_upstream_pressure_pa is None for row in samples):
        warnings.append("no nozzle-upstream pressure channel was supplied")
    if all(row.nozzle_upstream_temperature_k is None for row in samples):
        warnings.append("no nozzle-upstream temperature channel was supplied")
    if all(row.valve_position_pct is None for row in samples):
        warnings.append("no valve-position channel was supplied")
    if any(row.quality_flag.strip().upper() != "VALID" for row in samples):
        raise ValueError("series contains non-VALID quality flags")

    return TimeSeriesAudit(
        n_samples=len(samples),
        duration_s=times[-1] - times[0],
        median_interval_s=typical,
        maximum_interval_s=maximum,
        measured_mass_loss_kg=mass_loss,
        integrated_flow_kg=integrated,
        flow_mass_closure_relative=closure,
        warnings=tuple(warnings),
    )


def assess_source_evidence(
    geometry: Optional[NozzleGeometry],
    metadata: Optional[DischargeTestMetadata] = None,
    samples: Optional[list[DischargeSample]] = None,
    certificate: Optional[CapacityCertificate] = None,
) -> SourceEvidenceAssessment:
    if geometry is not None:
        geometry = NozzleGeometry.model_validate(geometry)
    if certificate is not None:
        certificate = CapacityCertificate.model_validate(certificate)
    blockers = []
    warnings = []
    audit = None
    if geometry is None:
        blockers.append("actual limiting geometry drawing/metrology is missing")
    elif geometry.inlet_geometry is InletGeometry.UNKNOWN:
        blockers.append("inlet geometry is still UNKNOWN")

    if certificate is not None:
        if geometry is not None and certificate.equipment_tag != geometry.equipment_tag:
            blockers.append("certificate and geometry equipment tags differ")
        if not certificate.valid_for_hydrogen:
            blockers.append(
                "capacity evidence is not declared valid for hydrogen; "
                "conversion and uncertainty justification are required"
            )

    if metadata is not None or samples is not None:
        if metadata is None or samples is None:
            blockers.append("metadata and raw samples must be supplied together")
        else:
            if geometry is not None and metadata.equipment_tag != geometry.equipment_tag:
                blockers.append("time series and geometry equipment tags differ")
            audit = audit_discharge_timeseries(metadata, samples)
            warnings.extend(audit.warnings)

    if blockers:
        level = "BLOCKED"
    elif audit is not None and audit.integrated_flow_kg is not None:
        level = "MEASURED_SOURCE_TERM"
    elif certificate is not None:
        level = {
            CapacityBasis.MANUFACTURER_CERTIFIED: "CERTIFIED_SOURCE_TERM",
            CapacityBasis.CAPACITY_TEST: "CAPACITY_TEST_SOURCE_TERM",
            CapacityBasis.CALIBRATED: "CALIBRATED_SOURCE_TERM",
        }[certificate.basis]
        if certificate.basis is CapacityBasis.CALIBRATED:
            warnings.append("calibration is not certification or independent validation")
    elif audit is not None:
        level = "RAW_SERIES_ONLY"
    else:
        level = "ENGINEERING_SENSITIVITY_ONLY"
        warnings.append(
            "geometry alone cannot validate Cd or certified relief capacity"
        )
    return SourceEvidenceAssessment(
        claim_level=level,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        time_series=audit,
    )


def read_geometry_csv(path: str | Path) -> list[NozzleGeometry]:
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = []
        for raw in csv.DictReader(stream):
            normalized = {
                key: (
                    None
                    if key in {"chamfer_angle_deg", "chamfer_length_mm"}
                    and value.strip() == ""
                    else value
                )
                for key, value in raw.items()
            }
            rows.append(NozzleGeometry.model_validate(normalized))
        return rows


def read_samples_csv(path: str | Path) -> list[DischargeSample]:
    optional = {
        "nozzle_upstream_pressure_pa", "nozzle_upstream_temperature_k",
        "measured_mass_flow_kg_s", "valve_position_pct",
    }
    rows = []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        for raw in csv.DictReader(stream):
            normalized = {
                key: (None if key in optional and value.strip() == "" else value)
                for key, value in raw.items()
            }
            rows.append(DischargeSample.model_validate(normalized))
    return rows
