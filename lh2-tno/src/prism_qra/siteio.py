"""
Site definition from a spreadsheet.

A site is currently expressible only as Python, which puts the person who
knows the plant and the person who can write pydantic in the same chair.
This reads the same Site object from three tables that a process engineer
can fill in: sections, components, assemblies.

Validation reports the row
--------------------------
A schema error deep in a nested model produces a message about field
paths. Someone entering forty components needs to know which line is
wrong and why, so every failure here carries the sheet, the row number,
and the value that caused it. Errors are collected rather than raised on
the first one: fixing a spreadsheet one exception per run is miserable.

Units are explicit in the header
--------------------------------
Column names carry the unit -- pressure_barg, diameter_mm, inventory_kg --
because a spreadsheet has no type system and the failure mode is silent.
A pressure entered in bar into a field expecting Pa is off by 100,000 and
nothing complains.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from taxonomy import (Assembly, AssemblySpec, ComponentSpec,
                      DischargeCoefficientBasis, Orientation, Position,
                      Primitive, Section, Service, Site, UpstreamLine)

P_ATM = 101325.0


@dataclass
class RowError:
    sheet: str
    row: int
    column: str
    value: Any
    message: str

    def __str__(self) -> str:
        return (f"[{self.sheet} row {self.row}] {self.column}="
                f"{self.value!r}: {self.message}")


class SheetErrors(ValueError):
    def __init__(self, errors: list[RowError]):
        self.errors = errors
        super().__init__(
            f"{len(errors)} problem(s) in the input:\n  "
            + "\n  ".join(str(e) for e in errors))


# --------------------------------------------------------------------------
# column definitions, which are also the template
# --------------------------------------------------------------------------

SECTION_COLUMNS = ["section_id", "service", "inventory_kg",
                   "isolation_time_s"]
COMPONENT_COLUMNS = ["tag", "primitive", "service", "count", "diameter_mm",
                     "pressure_barg", "temperature_k", "orientation",
                     "release_azimuth_deg", "x_m", "y_m", "z_m",
                     "section_id", "upstream_line_length_m",
                     "upstream_line_diameter_mm",
                     "upstream_line_roughness_mm", "upstream_minor_loss_k",
                     "discharge_coefficient", "discharge_coefficient_basis",
                     "discharge_coefficient_note"]
ASSEMBLY_COLUMNS = ["tag", "assembly", "service", "count", "diameter_mm",
                    "pressure_barg", "temperature_k", "release_azimuth_deg",
                    "x_m", "y_m", "z_m", "section_id",
                    "upstream_line_length_m", "upstream_line_diameter_mm",
                    "upstream_line_roughness_mm", "upstream_minor_loss_k",
                    "discharge_coefficient", "discharge_coefficient_basis",
                    "discharge_coefficient_note"]

TEMPLATE_NOTES = {
    "service": "GH2 | COLD_GH2 | LH2",
    "primitive": " | ".join(p.value for p in Primitive),
    "assembly": " | ".join(a.value for a in Assembly),
    "orientation": "UP | DOWN | HORIZONTAL",
    "release_azimuth_deg": "optional; 0 <= angle < 360, counter-clockwise "
                            "from the +x site axis",
    "pressure_barg": "gauge pressure in bar, not absolute and not Pa",
    "diameter_mm": "nominal bore in millimetres",
    "isolation_time_s": "detection plus valve closure; the model holds the "
                        "rate constant over it",
    "inventory_kg": "mass isolatable as one unit; this is what a full-bore "
                    "release can put out",
    "upstream_line_length_m": "optional finite supply/vent path length; "
                              "requires upstream_line_diameter_mm",
    "upstream_line_diameter_mm": "constant inside bore of the optional "
                                 "upstream line, not the leak diameter",
    "upstream_line_roughness_mm": "optional absolute roughness; blank is a "
                                  "hydraulically smooth upper-flow case",
    "upstream_minor_loss_k": "optional sum of dimensionless fitting and "
                              "valve loss coefficients; blank is zero",
    "discharge_coefficient": "optional equipment-specific Cd in (0, 1]; "
                             "blank is the conservative default 1.0",
    "discharge_coefficient_basis": "required for Cd below 1: "
        + " | ".join(b.value for b in DischargeCoefficientBasis),
    "discharge_coefficient_note": "required for a non-default basis; cite "
                                  "the drawing, certificate, test or fit",
}


def _enum(value: Any, enum_cls, sheet: str, row: int, column: str,
          errors: list[RowError]):
    try:
        return enum_cls(str(value).strip().upper())
    except Exception:
        errors.append(RowError(
            sheet, row, column, value,
            "not one of " + ", ".join(e.value for e in enum_cls)))
        return None


def _number(value: Any, sheet: str, row: int, column: str,
            errors: list[RowError], positive: bool = True,
            default: Optional[float] = None) -> Optional[float]:
    if value in (None, "") and default is not None:
        return default
    try:
        v = float(value)
    except Exception:
        errors.append(RowError(sheet, row, column, value, "not a number"))
        return None
    if not math.isfinite(v):
        errors.append(RowError(sheet, row, column, value,
                               "must be finite"))
        return None
    if positive and v <= 0:
        errors.append(RowError(sheet, row, column, value,
                               "must be greater than zero"))
        return None
    return v


# --------------------------------------------------------------------------
# readers
# --------------------------------------------------------------------------

def _data_lines(lines):
    """Yield CSV lines while ignoring the explanatory ``#`` footer."""
    for line in lines:
        if not line.lstrip().startswith("#"):
            yield line


def read_rows(source) -> list[dict]:
    """CSV from a path, a file object, or a string of CSV text.

    The generated templates include human-readable comment lines after the
    data rows. They are ignored so a freshly generated template can be edited
    and run without manually deleting its notes.
    """
    if isinstance(source, str) and "\n" in source:
        # CSV text, not a path. Checked before touching the filesystem:
        # passing a whole sheet to Path().exists() raises "file name too
        # long" rather than saying what went wrong.
        return [dict(r) for r in csv.DictReader(_data_lines(io.StringIO(source)))]
    if isinstance(source, (str, Path)):
        p = Path(source)
        if p.exists():
            with open(p, newline="", encoding="utf-8-sig") as f:
                return [dict(r) for r in csv.DictReader(_data_lines(f))]
        raise FileNotFoundError(
            f"{source!r} is neither an existing file nor CSV text "
            f"(no newline found)")
    return [dict(r) for r in csv.DictReader(_data_lines(source))]


def build_site(name: str, sections: Iterable[dict],
               components: Iterable[dict] = (),
               assemblies: Iterable[dict] = ()) -> Site:
    """Assemble a Site, collecting every problem before giving up."""
    errors: list[RowError] = []

    secs: list[Section] = []
    seen: set[str] = set()
    for i, r in enumerate(sections, start=2):
        sid = str(r.get("section_id", "")).strip()
        if not sid:
            errors.append(RowError("sections", i, "section_id", sid,
                                   "must not be empty"))
            continue
        if sid in seen:
            errors.append(RowError("sections", i, "section_id", sid,
                                   "duplicated; section ids must be unique"))
            continue
        seen.add(sid)
        svc = _enum(r.get("service"), Service, "sections", i, "service",
                    errors)
        inv = _number(r.get("inventory_kg"), "sections", i, "inventory_kg",
                      errors)
        iso = _number(r.get("isolation_time_s"), "sections", i,
                      "isolation_time_s", errors, default=600.0)
        if svc and inv and iso:
            secs.append(Section(id=sid, service=svc, inventory_kg=inv,
                                isolation_time_s=iso))

    def _position(r, sheet, i):
        return Position(
            x=_number(r.get("x_m"), sheet, i, "x_m", errors, positive=False,
                      default=0.0) or 0.0,
            y=_number(r.get("y_m"), sheet, i, "y_m", errors, positive=False,
                      default=0.0) or 0.0,
            z=_number(r.get("z_m"), sheet, i, "z_m", errors, positive=False,
                      default=0.0) or 0.0)

    def _azimuth(r, sheet, i):
        raw = r.get("release_azimuth_deg")
        if raw in (None, ""):
            return None
        value = _number(raw, sheet, i, "release_azimuth_deg", errors,
                        positive=False)
        if value is not None and not 0.0 <= value < 360.0:
            errors.append(RowError(
                sheet, i, "release_azimuth_deg", raw,
                "must be at least 0 and less than 360 degrees"))
            return None
        return value

    def _common(r, sheet, i):
        svc = _enum(r.get("service"), Service, sheet, i, "service", errors)
        d_mm = _number(r.get("diameter_mm"), sheet, i, "diameter_mm", errors)
        p_barg = _number(r.get("pressure_barg"), sheet, i, "pressure_barg",
                         errors, positive=False)
        if p_barg is not None and p_barg < 0.0:
            errors.append(RowError(sheet, i, "pressure_barg",
                                   r.get("pressure_barg"),
                                   "must be non-negative"))
            p_barg = None
        t_k = _number(r.get("temperature_k"), sheet, i, "temperature_k",
                      errors)
        n = _number(r.get("count"), sheet, i, "count", errors, default=1.0)
        if n is not None and not n.is_integer():
            errors.append(RowError(sheet, i, "count", r.get("count"),
                                   "must be a whole number"))
            n = None
        sid = str(r.get("section_id", "")).strip()
        if sid and sid not in seen:
            errors.append(RowError(
                sheet, i, "section_id", sid,
                "no section with this id; sections define what mass a "
                "release can put out, so a component without one cannot "
                "be evaluated"))
            sid = ""
        return svc, d_mm, p_barg, t_k, n, sid

    def _upstream_line(r, sheet, i):
        columns = ("upstream_line_length_m", "upstream_line_diameter_mm",
                   "upstream_line_roughness_mm", "upstream_minor_loss_k")
        raw = {column: r.get(column) for column in columns}
        supplied = {column: value for column, value in raw.items()
                    if value not in (None, "")}
        if not supplied:
            return None
        for required in columns[:2]:
            if raw[required] in (None, ""):
                errors.append(RowError(
                    sheet, i, required, raw[required],
                    "required when any upstream-line field is supplied"))
        if any(raw[required] in (None, "") for required in columns[:2]):
            return None
        length = _number(raw[columns[0]], sheet, i, columns[0], errors)
        diameter_mm = _number(raw[columns[1]], sheet, i, columns[1], errors)
        roughness_mm = _number(raw[columns[2]], sheet, i, columns[2], errors,
                               positive=False, default=0.0)
        minor_k = _number(raw[columns[3]], sheet, i, columns[3], errors,
                          positive=False, default=0.0)
        for column, value in ((columns[2], roughness_mm),
                              (columns[3], minor_k)):
            if value is not None and value < 0.0:
                errors.append(RowError(sheet, i, column, raw[column],
                                       "must be non-negative"))
                return None
        if None in (length, diameter_mm, roughness_mm, minor_k):
            return None
        if roughness_mm / diameter_mm >= 0.1:
            errors.append(RowError(
                sheet, i, columns[2], raw[columns[2]],
                "relative roughness must be below 0.1"))
            return None
        return UpstreamLine(
            length_m=length, diameter_m=diameter_mm / 1000.0,
            roughness_m=roughness_mm / 1000.0, minor_loss_k=minor_k)

    def _line_bore(line, nominal_diameter_mm, r, sheet, i):
        if (line is not None and nominal_diameter_mm is not None
                and line.diameter_m < nominal_diameter_mm / 1000.0):
            errors.append(RowError(
                sheet, i, "upstream_line_diameter_mm",
                r.get("upstream_line_diameter_mm"),
                "cannot be smaller than the nominal terminal diameter"))
            return None
        return line

    def _discharge_coefficient(r, sheet, i):
        raw_coefficient = r.get("discharge_coefficient")
        coefficient = _number(
            raw_coefficient, sheet, i, "discharge_coefficient", errors,
            default=1.0)
        if coefficient is not None and coefficient > 1.0:
            errors.append(RowError(
                sheet, i, "discharge_coefficient", raw_coefficient,
                "must not exceed 1.0"))
            coefficient = None
        raw_basis = r.get("discharge_coefficient_basis")
        if raw_basis in (None, ""):
            basis = DischargeCoefficientBasis.CONSERVATIVE_DEFAULT
        else:
            basis = _enum(
                raw_basis, DischargeCoefficientBasis, sheet, i,
                "discharge_coefficient_basis", errors)
        note = str(r.get("discharge_coefficient_note") or "").strip()
        if (coefficient is not None and not math.isclose(coefficient, 1.0)
                and basis
                is DischargeCoefficientBasis.CONSERVATIVE_DEFAULT):
            errors.append(RowError(
                sheet, i, "discharge_coefficient_basis", raw_basis,
                "an explicit non-default basis is required when Cd is "
                "below 1"))
            basis = None
        if (basis is not None
                and basis
                is not DischargeCoefficientBasis.CONSERVATIVE_DEFAULT
                and not note):
            errors.append(RowError(
                sheet, i, "discharge_coefficient_note", note,
                "cite the drawing, certificate, test or calibration source"))
            basis = None
        return coefficient, basis, note

    seen_tags: dict[str, tuple[str, int]] = {}

    def _tag(r, sheet, i):
        tag = str(r.get("tag", "")).strip()
        if not tag:
            errors.append(RowError(sheet, i, "tag", tag,
                                   "must not be empty"))
            return ""
        if tag in seen_tags:
            prior_sheet, prior_row = seen_tags[tag]
            errors.append(RowError(
                sheet, i, "tag", tag,
                f"duplicated; first used in {prior_sheet} row {prior_row}"))
            return ""
        seen_tags[tag] = (sheet, i)
        return tag

    comps: list[ComponentSpec] = []
    for i, r in enumerate(components, start=2):
        tag = _tag(r, "components", i)
        svc, d_mm, p_barg, t_k, n, sid = _common(r, "components", i)
        prim = _enum(r.get("primitive"), Primitive, "components", i,
                     "primitive", errors)
        orient = _enum(r.get("orientation") or "HORIZONTAL", Orientation,
                       "components", i, "orientation", errors)
        upstream_line = _line_bore(
            _upstream_line(r, "components", i), d_mm, r, "components", i)
        coefficient, coefficient_basis, coefficient_note = \
            _discharge_coefficient(r, "components", i)
        if all(v is not None for v in (svc, d_mm, p_barg, t_k, n, prim,
                                       orient, coefficient,
                                       coefficient_basis)) and sid and tag:
            comps.append(ComponentSpec(
                primitive=prim, service=svc, count=int(n),
                nominal_diameter_m=d_mm / 1000.0,
                pressure_pa=p_barg * 1e5 + P_ATM,
                temperature_k=t_k, orientation=orient,
                release_azimuth_deg=_azimuth(r, "components", i),
                position=_position(r, "components", i), section_id=sid,
                tag=tag,
                upstream_line=upstream_line,
                discharge_coefficient=coefficient,
                discharge_coefficient_basis=coefficient_basis,
                discharge_coefficient_note=coefficient_note))

    asms: list[AssemblySpec] = []
    for i, r in enumerate(assemblies, start=2):
        tag = _tag(r, "assemblies", i)
        svc, d_mm, p_barg, t_k, n, sid = _common(r, "assemblies", i)
        asm = _enum(r.get("assembly"), Assembly, "assemblies", i,
                    "assembly", errors)
        upstream_line = _line_bore(
            _upstream_line(r, "assemblies", i), d_mm, r, "assemblies", i)
        coefficient, coefficient_basis, coefficient_note = \
            _discharge_coefficient(r, "assemblies", i)
        if all(v is not None for v in (svc, d_mm, p_barg, t_k, n, asm)) \
                and coefficient is not None and coefficient_basis is not None \
                and sid and tag:
            asms.append(AssemblySpec(
                assembly=asm, service=svc, count=int(n),
                nominal_diameter_m=d_mm / 1000.0,
                pressure_pa=p_barg * 1e5 + P_ATM,
                temperature_k=t_k,
                release_azimuth_deg=_azimuth(r, "assemblies", i),
                position=_position(r, "assemblies", i), section_id=sid,
                tag=tag,
                upstream_line=upstream_line,
                discharge_coefficient=coefficient,
                discharge_coefficient_basis=coefficient_basis,
                discharge_coefficient_note=coefficient_note))

    if errors:
        raise SheetErrors(errors)
    if not secs:
        raise SheetErrors([RowError("sections", 0, "-", None,
                                    "no usable sections")])
    return Site(name=name, sections=secs, components=comps, assemblies=asms)


def load_site(name: str, sections_csv, components_csv=None,
              assemblies_csv=None) -> Site:
    return build_site(name, read_rows(sections_csv),
                      read_rows(components_csv) if components_csv else (),
                      read_rows(assemblies_csv) if assemblies_csv else ())


# --------------------------------------------------------------------------
# templates
# --------------------------------------------------------------------------

def template(sheet: str) -> str:
    """A CSV header with one commented example row."""
    cols = {"sections": SECTION_COLUMNS, "components": COMPONENT_COLUMNS,
            "assemblies": ASSEMBLY_COLUMNS}[sheet]
    examples = {
        "sections": ["LH2_TANK", "LH2", "5000", "1800"],
        "components": ["TK-101", "VESSEL", "LH2", "1", "50", "5",
                       "22", "HORIZONTAL", "", "0", "0", "0", "LH2_TANK",
                       "", "", "", "", "", "", ""],
        "assemblies": ["VJ-201", "VJ_LINE", "LH2", "3", "50", "5",
                       "22", "", "12", "0", "0", "LH2_TANK",
                       "", "", "", "", "", "", ""],
    }[sheet]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(cols)
    w.writerow(examples)
    notes = [f"# {c}: {TEMPLATE_NOTES[c]}" for c in cols
             if c in TEMPLATE_NOTES]
    return out.getvalue() + "\n".join(notes) + "\n"


def all_templates() -> dict[str, str]:
    return {s: template(s) for s in ("sections", "components", "assemblies")}
