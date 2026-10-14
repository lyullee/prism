"""Convert an explicit realtime snapshot into a conditional facility ledger.

The realtime monitor knows the current frame, provider release path, and one
observed-release consequence.  It does not know how that observation should be
split across annual weather, isolation, or ignition branches.  This adapter
accepts those missing dimensions only from an explicit caller-supplied
scenario binding, checks the branch-harm closure against the observed risk
atom, and emits the existing facility-campaign result shape.  The emitted
result remains ``EXECUTED_OPERATOR_LIMITED`` and never opens the qualified
facility-QRA gate.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
import math
from typing import Any

from .contracts import canonical_digest
from .service import build_realtime_facility_risk_handoff


IGNITION_BRANCHES = (
    "direct_fire",
    "delayed_flash_fire",
    "delayed_explosion",
    "no_ignition",
)


class RealtimeCampaignBindingError(ValueError):
    """Raised when explicit realtime-to-facility scenario metadata is invalid."""


def _probability(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise RealtimeCampaignBindingError(
            f"{label} must be a finite probability in [0, 1]"
        )
    return float(value)


def _nonnegative(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise RealtimeCampaignBindingError(
            f"{label} must be a finite nonnegative number"
        )
    return float(value)


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RealtimeCampaignBindingError(f"{label} must be a nonempty string")
    return value


def _validate_annual_conditions(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    if not rows or isinstance(rows, (str, bytes)):
        raise RealtimeCampaignBindingError(
            "annual_conditions must be a nonempty sequence"
        )
    conditions: dict[str, dict[str, Any]] = {}
    probability_sum = 0.0
    receptor_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise RealtimeCampaignBindingError(
                f"annual_conditions[{index}] must be a mapping"
            )
        condition_id = _name(row.get("id"), f"annual_conditions[{index}].id")
        if condition_id in conditions:
            raise RealtimeCampaignBindingError(
                f"duplicate annual condition id: {condition_id}"
            )
        probability = _probability(
            row.get("annual_probability"),
            f"annual_conditions[{index}].annual_probability",
        )
        weather = row.get("weather")
        if not isinstance(weather, Mapping):
            raise RealtimeCampaignBindingError(
                f"annual_conditions[{index}].weather must be a mapping"
            )
        population = row.get("population")
        if not isinstance(population, Sequence) or isinstance(
            population, (str, bytes)
        ) or not population:
            raise RealtimeCampaignBindingError(
                f"annual_conditions[{index}].population must be a nonempty sequence"
            )
        population_ids: set[str] = set()
        normalized_population: list[dict[str, Any]] = []
        for population_index, population_row in enumerate(population):
            if not isinstance(population_row, Mapping):
                raise RealtimeCampaignBindingError(
                    f"annual_conditions[{index}].population[{population_index}] must be a mapping"
                )
            receptor_id = _name(
                population_row.get("receptor_id"),
                f"annual_conditions[{index}].population[{population_index}].receptor_id",
            )
            if receptor_id in population_ids:
                raise RealtimeCampaignBindingError(
                    f"annual condition {condition_id} duplicates receptor {receptor_id}"
                )
            population_ids.add(receptor_id)
            persons = _nonnegative(
                population_row.get("persons"),
                f"annual_conditions[{index}].population[{population_index}].persons",
            )
            presence = _probability(
                population_row.get("presence_probability", 1.0),
                f"annual_conditions[{index}].population[{population_index}].presence_probability",
            )
            provenance = _name(
                population_row.get("provenance", row.get("provenance")),
                f"annual_conditions[{index}].population[{population_index}].provenance",
            )
            normalized_population.append(
                {
                    "receptor_id": receptor_id,
                    "persons": persons,
                    "presence_probability": presence,
                    "provenance": provenance,
                }
            )
        if not receptor_ids:
            receptor_ids = population_ids
        elif population_ids != receptor_ids:
            raise RealtimeCampaignBindingError(
                "all annual conditions must use the same receptor population set"
            )
        provenance = _name(
            row.get("provenance"),
            f"annual_conditions[{index}].provenance",
        )
        conditions[condition_id] = {
            "id": condition_id,
            "annual_probability": probability,
            "weather": copy.deepcopy(dict(weather)),
            "population": normalized_population,
            "provenance": provenance,
        }
        probability_sum += probability
    if not math.isclose(probability_sum, 1.0, rel_tol=0.0, abs_tol=1.0e-10):
        raise RealtimeCampaignBindingError(
            "annual condition probabilities must close to one"
        )
    return conditions, receptor_ids


def _validate_branch_harm(
    value: Any,
    *,
    receptor_ids: set[str],
    probabilities: Mapping[str, float],
    observed_harm: Mapping[str, Any],
    label: str,
) -> dict[str, dict[str, list[float]]]:
    if not isinstance(value, Mapping):
        raise RealtimeCampaignBindingError(f"{label} must be a receptor mapping")
    if set(value) != receptor_ids:
        raise RealtimeCampaignBindingError(
            f"{label} receptors must exactly match the realtime consequence: "
            f"expected={sorted(receptor_ids)}, observed={sorted(value)}"
        )
    normalized: dict[str, dict[str, list[float]]] = {}
    for receptor_id in sorted(receptor_ids):
        receptor_row = value[receptor_id]
        if not isinstance(receptor_row, Mapping) or set(receptor_row) != set(
            IGNITION_BRANCHES
        ):
            raise RealtimeCampaignBindingError(
                f"{label}[{receptor_id}] must contain exactly all ignition branches"
            )
        normalized[receptor_id] = {}
        for branch in IGNITION_BRANCHES:
            endpoints = receptor_row[branch]
            if not isinstance(endpoints, Sequence) or isinstance(
                endpoints, (str, bytes)
            ) or len(endpoints) != 2:
                raise RealtimeCampaignBindingError(
                    f"{label}[{receptor_id}][{branch}] requires two endpoints"
                )
            values = [
                _probability(
                    endpoint,
                    f"{label}[{receptor_id}][{branch}][{endpoint_index}]",
                )
                for endpoint_index, endpoint in enumerate(endpoints)
            ]
            if values[0] > values[1] + 1.0e-12:
                raise RealtimeCampaignBindingError(
                    f"{label}[{receptor_id}][{branch}] endpoints must be ordered"
                )
            if branch == "no_ignition" and any(value != 0.0 for value in values):
                raise RealtimeCampaignBindingError(
                    f"{label}[{receptor_id}][no_ignition] must be zero"
                )
            normalized[receptor_id][branch] = values
        observed = observed_harm.get(receptor_id)
        if not isinstance(observed, Sequence) or isinstance(observed, (str, bytes)) or len(observed) != 2:
            raise RealtimeCampaignBindingError(
                f"realtime risk atom has invalid observed harm for {receptor_id}"
            )
        for endpoint in range(2):
            combined = sum(
                probabilities[branch] * normalized[receptor_id][branch][endpoint]
                for branch in IGNITION_BRANCHES
            )
            if not math.isclose(
                combined,
                float(observed[endpoint]),
                rel_tol=1.0e-8,
                abs_tol=1.0e-12,
            ):
                raise RealtimeCampaignBindingError(
                    f"{label}[{receptor_id}] does not close to observed-release harm"
                )
    return normalized


def _validate_observed_harm(
    value: Any,
    *,
    receptor_ids: set[str],
    label: str,
) -> dict[str, list[float]]:
    """Validate an explicit harm map used by a non-current annual condition.

    A realtime frame supplies one current-weather harm map.  Other annual
    weather conditions may be joined only when the caller supplies a reviewed
    consequence result for that condition.  This helper keeps that evidence
    separate from the current frame instead of silently reusing it.
    """
    if not isinstance(value, Mapping) or set(value) != receptor_ids:
        raise RealtimeCampaignBindingError(
            f"{label} receptors must exactly match the realtime consequence set"
        )
    normalized: dict[str, list[float]] = {}
    for receptor_id in sorted(receptor_ids):
        endpoints = value[receptor_id]
        if not isinstance(endpoints, Sequence) or isinstance(endpoints, (str, bytes)) or len(endpoints) != 2:
            raise RealtimeCampaignBindingError(
                f"{label}[{receptor_id}] requires two endpoints"
            )
        values = [
            _probability(endpoint, f"{label}[{receptor_id}][{index}]")
            for index, endpoint in enumerate(endpoints)
        ]
        if values[0] > values[1] + 1.0e-12:
            raise RealtimeCampaignBindingError(
                f"{label}[{receptor_id}] endpoints must be ordered"
            )
        normalized[receptor_id] = values
    return normalized


def _provider_identity(path: Mapping[str, Any]) -> dict[str, Any] | None:
    boundaries = path.get("boundaries")
    if not isinstance(boundaries, Sequence) or isinstance(boundaries, (str, bytes)):
        return None
    rows = [row for row in boundaries if isinstance(row, Mapping)]
    if not rows:
        return None
    first = rows[0]
    identity = {
        "event_id": first.get("event_id"),
        "component_id": first.get("component_id"),
        "provider_export_schema": "prism.resolved_release.v1",
        "port_ids": [row.get("port_id") for row in rows],
        "provider_source_digests": [
            row.get("provider_source_digest")
            for row in rows
            if row.get("provider_source_digest") is not None
        ],
        "provider_result_digests": [
            row.get("provider_result_digest")
            for row in rows
            if row.get("provider_result_digest") is not None
        ],
        "provider_boundary_references": [
            row.get("provider_boundary_reference")
            for row in rows
            if row.get("provider_boundary_reference") is not None
        ],
        "termination_bases": [
            row.get("termination_basis") for row in rows if row.get("termination_basis")
        ],
        "termination_provenances": [
            row.get("termination_provenance")
            for row in rows
            if row.get("termination_provenance")
        ],
        "event_kinds": [row.get("event_kind") for row in rows],
        "input_origins": [row.get("input_origin") for row in rows],
        "duration_s": [row.get("duration_s") for row in rows],
        "available_mass_kg": [row.get("available_mass_kg") for row in rows],
        "cumulative_mass_out_kg": [
            row.get("cumulative_mass_out_kg") for row in rows
        ],
    }
    balances = [row.get("provider_mass_balance") for row in rows]
    if any(value is not None for value in balances):
        identity["provider_mass_balances"] = balances
    return identity


def _case_timing(component: Mapping[str, Any]) -> float:
    result = component.get("result")
    service = result.get("service") if isinstance(result, Mapping) else None
    value = service.get("service_elapsed_ms") if isinstance(service, Mapping) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and value >= 0:
        return float(value)
    return 0.0


def build_realtime_facility_campaign_result(
    snapshot: Mapping[str, object],
    *,
    annual_conditions: Sequence[Mapping[str, Any]],
    scenario_bindings: Sequence[Mapping[str, Any]],
    expected_component_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a conditional facility-campaign result from explicit metadata.

    ``scenario_bindings`` supplies the dimensions that a realtime frame cannot
    infer: annual condition, release/isolation branch, ignition probabilities,
    branch-specific receptor harm, and accident-family labels.  A component may
    have more than one binding when each annual condition is explicit.  One
    binding may use the current snapshot consequence; every additional annual
    condition must provide its own reviewed observed-harm map.  Missing release
    paths remain ``UNCOMPUTED`` and no risk atom is created for them.

    The result is deliberately marked partial/operator-limited.  It is useful
    for the existing facility ledger's known-contribution and uncertainty
    calculations, but it cannot claim a qualified facility QRA.
    """
    if not isinstance(snapshot, Mapping):
        raise TypeError("snapshot must be a mapping")
    if snapshot.get("status") != "ACCEPTED":
        raise RealtimeCampaignBindingError(
            "an accepted realtime snapshot is required; rejected batches cannot form a campaign"
        )
    handoff = build_realtime_facility_risk_handoff(snapshot)
    conditions, receptor_ids = _validate_annual_conditions(annual_conditions)
    if not isinstance(scenario_bindings, Sequence) or isinstance(
        scenario_bindings, (str, bytes)
    ):
        raise RealtimeCampaignBindingError("scenario_bindings must be a sequence")
    components = snapshot.get("components")
    if not isinstance(components, Mapping):
        raise RealtimeCampaignBindingError("snapshot components must be a mapping")
    declared_components = {str(component_id) for component_id in components}
    expected_components = {
        _name(component_id, "expected_component_ids[]")
        for component_id in expected_component_ids
    }
    if not expected_components:
        expected_components = set(declared_components)

    risk_atoms_by_component = {
        str(row["component_id"]): row["atom"]
        for row in handoff.get("realtime_risk_atoms", ())
        if isinstance(row, Mapping)
        and isinstance(row.get("component_id"), str)
        and isinstance(row.get("atom"), Mapping)
    }
    bindings_by_component: dict[str, list[Mapping[str, Any]]] = {}
    for index, binding in enumerate(scenario_bindings):
        if not isinstance(binding, Mapping):
            raise RealtimeCampaignBindingError(
                f"scenario_bindings[{index}] must be a mapping"
            )
        component_id = _name(
            binding.get("component_id"),
            f"scenario_bindings[{index}].component_id",
        )
        if component_id not in declared_components:
            raise RealtimeCampaignBindingError(
                f"scenario binding references undeclared component: {component_id}"
            )
        bindings_by_component.setdefault(component_id, []).append(binding)

    for component_id, rows in bindings_by_component.items():
        identities: set[tuple[str, str, str]] = set()
        for index, binding in enumerate(rows):
            identity = (
                _name(
                    binding.get("event_id"),
                    f"scenario binding {component_id}[{index}].event_id",
                ),
                _name(
                    binding.get("annual_condition_id"),
                    f"scenario binding {component_id}[{index}].annual_condition_id",
                ),
                _name(
                    binding.get("release_branch_id"),
                    f"scenario binding {component_id}[{index}].release_branch_id",
                ),
            )
            if identity in identities:
                raise RealtimeCampaignBindingError(
                    "duplicate realtime scenario binding: " + "/".join(identity)
                )
            identities.add(identity)
        current_rows = [
            row
            for row in rows
            if row.get("consequence_basis", "realtime_snapshot")
            == "realtime_snapshot"
        ]
        if len(current_rows) > 1:
            raise RealtimeCampaignBindingError(
                f"component {component_id} has multiple realtime_snapshot consequence bindings; "
                "provide one current snapshot binding and reviewed annual-condition bindings for the rest"
            )
        if len(rows) > 1 and any("consequence_basis" not in row for row in rows):
            raise RealtimeCampaignBindingError(
                f"component {component_id} has multiple annual scenarios; consequence_basis is required on every binding"
            )

    events_by_id: dict[str, dict[str, Any]] = {}
    cases: list[dict[str, Any]] = []
    uncomputed_cases: list[dict[str, Any]] = []
    risk_atoms: list[dict[str, Any]] = []
    provider_packet_case_count = 0
    provider_packet_missing_evidence_cases: list[dict[str, Any]] = []
    synthetic_release_horizon_present = False
    scenario_frequencies: dict[str, float] = {}

    for component_id in sorted(bindings_by_component):
        for binding_index, binding in enumerate(bindings_by_component[component_id]):
            event_id = _name(
                binding.get("event_id"),
                f"scenario binding {component_id}[{binding_index}].event_id",
            )
            asset_id = _name(
                binding.get("asset_id"),
                f"scenario binding {component_id}[{binding_index}].asset_id",
            )
            atom = risk_atoms_by_component.get(component_id)
            if not isinstance(atom, Mapping):
                atom = None
            if atom is not None:
                if str(atom.get("asset_id")) != asset_id:
                    raise RealtimeCampaignBindingError(
                        f"scenario binding identity disagrees with realtime risk atom: {component_id}"
                    )
                frequency = _nonnegative(
                    atom.get("initiating_frequency_per_year"),
                    f"realtime risk atom {component_id}.initiating_frequency_per_year",
                )
            else:
                frequency = 0.0
            previous_frequency = scenario_frequencies.get(event_id)
            if previous_frequency is not None and not math.isclose(
                previous_frequency, frequency, rel_tol=0.0, abs_tol=1.0e-15
            ):
                raise RealtimeCampaignBindingError(
                    f"realtime event frequency changed across scenario bindings: {event_id}"
                )
            scenario_frequencies[event_id] = frequency

            condition_id = _name(
                binding.get("annual_condition_id"),
                f"scenario binding {component_id}[{binding_index}].annual_condition_id",
            )
            condition = conditions.get(condition_id)
            if condition is None:
                raise RealtimeCampaignBindingError(
                    f"scenario binding references unknown annual condition: {condition_id}"
                )
            release_branch_id = _name(
                binding.get("release_branch_id"),
                f"scenario binding {component_id}[{binding_index}].release_branch_id",
            )
            release_probability = _probability(
                binding.get("release_branch_probability"),
                f"scenario binding {component_id}[{binding_index}].release_branch_probability",
            )
            probabilities_raw = binding.get("ignition_branch_probabilities")
            if not isinstance(probabilities_raw, Mapping) or set(probabilities_raw) != set(
                IGNITION_BRANCHES
            ):
                raise RealtimeCampaignBindingError(
                    f"scenario binding {component_id}[{binding_index}] must declare all ignition branch probabilities"
                )
            probabilities = {
                branch: _probability(
                    probabilities_raw[branch],
                    f"scenario binding {component_id}[{binding_index}].ignition_branch_probabilities[{branch}]",
                )
                for branch in IGNITION_BRANCHES
            }
            if not math.isclose(sum(probabilities.values()), 1.0, rel_tol=0.0, abs_tol=1.0e-10):
                raise RealtimeCampaignBindingError(
                    f"scenario binding {component_id} ignition probabilities must close to one"
                )
            component = components[component_id]
            if not isinstance(component, Mapping):
                raise RealtimeCampaignBindingError(
                    f"snapshot component entry is invalid: {component_id}"
                )
            ignition = component.get("ignition")
            reported_probabilities = (
                ignition.get("branch_probabilities")
                if isinstance(ignition, Mapping)
                else None
            )
            if isinstance(reported_probabilities, Mapping) and {
                str(key) for key in reported_probabilities
            } == set(IGNITION_BRANCHES):
                for branch in IGNITION_BRANCHES:
                    if not math.isclose(
                        probabilities[branch],
                        float(reported_probabilities[branch]),
                        rel_tol=0.0,
                        abs_tol=1.0e-10,
                    ):
                        raise RealtimeCampaignBindingError(
                            f"scenario ignition probabilities disagree with provider output: {component_id}[{binding_index}]"
                        )

            consequence_basis = binding.get("consequence_basis", "realtime_snapshot")
            if consequence_basis not in {"realtime_snapshot", "reviewed_annual_condition"}:
                raise RealtimeCampaignBindingError(
                    f"scenario binding {component_id}[{binding_index}].consequence_basis is unsupported"
                )
            if consequence_basis == "realtime_snapshot":
                if atom is None:
                    raise RealtimeCampaignBindingError(
                        f"scenario binding {component_id}[{binding_index}] requires an accepted realtime risk atom"
                    )
                observed_harm = atom.get("receptor_harm_low_high")
                if not isinstance(observed_harm, Mapping):
                    raise RealtimeCampaignBindingError(
                        f"realtime risk atom has no receptor harm: {component_id}"
                    )
            else:
                if not isinstance(binding.get("consequence_provenance"), str) or not binding["consequence_provenance"].strip():
                    raise RealtimeCampaignBindingError(
                        f"scenario binding {component_id}[{binding_index}] reviewed annual condition requires consequence_provenance"
                    )
                observed_harm = _validate_observed_harm(
                    binding.get("observed_harm_low_high"),
                    receptor_ids=receptor_ids,
                    label=f"scenario binding {component_id}[{binding_index}].observed_harm_low_high",
                )
            branch_harm = _validate_branch_harm(
                binding.get("branch_harm_low_high"),
                receptor_ids=receptor_ids,
                probabilities=probabilities,
                observed_harm=observed_harm,
                label=f"scenario binding {component_id}[{binding_index}].branch_harm_low_high",
            )
            families_raw = binding.get("scenario_families")
            if not isinstance(families_raw, Sequence) or isinstance(
                families_raw, (str, bytes)
            ) or not families_raw:
                raise RealtimeCampaignBindingError(
                    f"scenario binding {component_id}[{binding_index}] requires explicit scenario_families"
                )
            families = [
                _name(value, f"scenario binding {component_id}[{binding_index}].scenario_families[]")
                for value in families_raw
            ]
            operating_mode = binding.get("operating_mode")
            if operating_mode is not None:
                operating_mode = _name(
                    operating_mode,
                    f"scenario binding {component_id}[{binding_index}].operating_mode",
                )

            event = events_by_id.get(event_id)
            if event is None:
                event = {
                    "id": event_id,
                    "asset_id": asset_id,
                    "model_component_id": component_id,
                    "profile": "REALTIME_PROVIDER_BOUNDARY",
                    "loc": "REALTIME_CURRENT_CONDITION",
                    "annual_frequency_per_year": frequency,
                    "marginal_p05_per_year": (
                        atom.get("frequency_p05_per_year") if atom is not None else None
                    ),
                    "marginal_p95_per_year": (
                        atom.get("frequency_p95_per_year") if atom is not None else None
                    ),
                    "source": (
                        atom.get("frequency_provenance") if atom is not None else None
                    ),
                    "source_sha256": (
                        atom.get("frequency_source_digest") if atom is not None else None
                    ),
                    "release": {"mode": "provider_resolved"},
                    "classification_basis": "explicit realtime scenario binding",
                    "scenario_families": [],
                    "operating_mode": operating_mode,
                    "realtime_snapshot_digest": handoff["source_snapshot_digest"],
                    "physical_validation_claim": False,
                }
                events_by_id[event_id] = event
            elif (
                event["asset_id"] != asset_id
                or event["model_component_id"] != component_id
                or not math.isclose(
                    float(event["annual_frequency_per_year"]),
                    frequency,
                    rel_tol=0.0,
                    abs_tol=1.0e-15,
                )
                or event.get("marginal_p05_per_year")
                != (atom.get("frequency_p05_per_year") if atom is not None else None)
                or event.get("marginal_p95_per_year")
                != (atom.get("frequency_p95_per_year") if atom is not None else None)
                or event.get("source_sha256")
                != (atom.get("frequency_source_digest") if atom is not None else None)
                or event.get("operating_mode") != operating_mode
            ):
                raise RealtimeCampaignBindingError(
                    f"realtime event metadata conflicts across annual scenario bindings: {event_id}"
                )
            event["scenario_families"] = sorted(set(event["scenario_families"]) | set(families))

            path = component.get("equipment_release_path")
            path = path if isinstance(path, Mapping) else None
            case: dict[str, Any] = {
                "event_id": event_id,
                "asset_id": asset_id,
                "component_id": component_id,
                "release_branch_id": release_branch_id,
                "annual_condition_id": condition_id,
                "initiating_frequency_per_year": frequency,
                "release_branch_probability": release_probability,
                "annual_condition_probability": condition["annual_probability"],
                "consequence_basis": consequence_basis,
                "consequence_provenance": (
                    binding.get("consequence_provenance")
                    if consequence_basis == "reviewed_annual_condition"
                    else "accepted realtime snapshot consequence"
                ),
                "scenario_families": families,
                "operating_mode": operating_mode,
                "realtime_snapshot_digest": handoff["source_snapshot_digest"],
            }
            path_available = (
                path is not None and path.get("status") == "AVAILABLE_PROVIDER_RELEASE_PATH"
            )
            if atom is None:
                case.update(
                    status="UNCOMPUTED",
                    reason="realtime component has no accepted current-weather risk atom",
                    elapsed_ms=_case_timing(component),
                )
                cases.append(case)
                uncomputed_cases.append(dict(case))
                continue
            if not path_available:
                case.update(
                    status="UNCOMPUTED",
                    reason="realtime component has no accepted provider release path",
                    elapsed_ms=_case_timing(component),
                )
                cases.append(case)
                uncomputed_cases.append(dict(case))
                continue

            provider_identity = _provider_identity(path)
            if provider_identity is not None:
                provider_packet_case_count += 1
                provider_packet_missing_evidence_cases.append(
                    {
                        "event_id": event_id,
                        "release_branch_id": release_branch_id,
                        "annual_condition_id": condition_id,
                        "reason": "realtime adapter does not evaluate qualified provider evidence",
                    }
                )
            termination = path.get("termination")
            termination = termination if isinstance(termination, Mapping) else {}
            basis = termination.get("basis")
            if basis == "synthetic_diagnostic_horizon":
                synthetic_release_horizon_present = True
            inventory = path.get("inventory")
            inventory = inventory if isinstance(inventory, Mapping) else {}
            case.update(
                status="EXECUTED_OPERATOR_LIMITED",
                reason=(
                    f"{consequence_basis} consequence joined to an explicit scenario; "
                    "annual facility campaign and provider qualification remain open"
                ),
                elapsed_ms=_case_timing(component),
                provider_packet_identity=provider_identity,
                termination={
                    "basis": basis,
                    "time_s": termination.get("time_s"),
                    "provenance": termination.get("provenance"),
                },
                mass_ledger={
                    "released_kg": inventory.get("cumulative_mass_out_kg"),
                    "end_to_end_residual_kg": inventory.get("mass_residual_kg"),
                },
            )
            cases.append(case)
            uncomputed_cases.append(dict(case))
            if branch_harm is None:
                continue
            for branch in IGNITION_BRANCHES:
                weight = (
                    float(condition["annual_probability"])
                    * release_probability
                    * probabilities[branch]
                )
                harm = {
                    receptor_id: list(branch_harm[receptor_id][branch])
                    for receptor_id in sorted(receptor_ids)
                }
                presence_population = {
                    row["receptor_id"]: float(row["persons"])
                    * float(row["presence_probability"])
                    for row in condition["population"]
                }
                risk_atoms.append(
                    {
                        "event_id": event_id,
                        "asset_id": asset_id,
                        "annual_condition_id": condition_id,
                        "release_branch_id": release_branch_id,
                        "ignition_branch": branch,
                        "initiating_frequency_per_year": frequency,
                        "conditional_weight": weight,
                        "scenario_families": families,
                        "operating_mode": operating_mode,
                        "provider_packet_identity": copy.deepcopy(provider_identity),
                        "receptor_harm_low_high": harm,
                        "expected_deaths_basis": "population_weighted",
                        "expected_deaths_low_high": [
                            sum(presence_population[receptor_id] * harm[receptor_id][endpoint] for receptor_id in sorted(receptor_ids))
                            for endpoint in range(2)
                        ],
                        "realtime_snapshot_digest": handoff["source_snapshot_digest"],
                    }
                )

    # At least one explicit branch-complete atom is needed for the existing
    # facility ledger to build a conditional contribution.  An empty output
    # is more dangerous than a clear configuration error at this boundary.
    if not risk_atoms:
        raise RealtimeCampaignBindingError(
            "no realtime component produced a branch-complete risk atom"
        )
    fresh_count = sum(
        bool(
            isinstance(
                component.get("result"), Mapping
            )
            and isinstance(component["result"].get("service"), Mapping)
            and component["result"]["service"].get("fresh_physics_this_update")
        )
        for component in components.values()
        if isinstance(component, Mapping)
    )
    processing_time = snapshot.get("aggregate", {}).get("processing_time", {})
    if not isinstance(processing_time, Mapping):
        processing_time = {}
    timing = {
        "fresh_physics_cases": fresh_count,
        "case_min_ms": min((case.get("elapsed_ms", 0.0) for case in cases), default=0.0),
        "case_median_ms": None,
        "case_max_ms": max((case.get("elapsed_ms", 0.0) for case in cases), default=0.0),
        "case_p95_ms": None,
        "case_p99_ms": None,
        "campaign_elapsed_ms": processing_time.get("total_service_elapsed_ms"),
        "distribution": "one synchronous realtime facility snapshot; not sustained throughput",
        "realtime_processing_time": copy.deepcopy(dict(processing_time)),
    }
    component_coverage = []
    for component_id in sorted(expected_components | declared_components):
        event_count = sum(
            event["model_component_id"] == component_id
            for event in events_by_id.values()
        )
        component_cases = [
            case for case in cases if case.get("component_id") == component_id
        ]
        component_coverage.append(
            {
                "component_id": component_id,
                "scope_status": "PARTIAL" if event_count else "MISSING_COVERAGE",
                "generated_event_count": event_count,
                "campaign_case_count": len(component_cases),
                "executed_case_count": sum(
                    str(case.get("status", "")).startswith("EXECUTED")
                    for case in component_cases
                ),
                "fully_validated_case_count": 0,
                "operator_limited_case_count": sum(
                    case.get("status") == "EXECUTED_OPERATOR_LIMITED"
                    for case in component_cases
                ),
                "uncomputed_case_count": len(
                    [case for case in uncomputed_cases if case.get("component_id") == component_id]
                ),
                "uncomputed_reasons": sorted(
                    {
                        str(case.get("reason"))
                        for case in uncomputed_cases
                        if case.get("component_id") == component_id and case.get("reason")
                    }
                ),
            }
        )
    events = list(events_by_id.values())
    frequency_total = sum(event["annual_frequency_per_year"] for event in events)
    result: dict[str, Any] = {
        "schema_version": "prism.realtime_facility_campaign_result.v1",
        "status": "PARTIAL_DECLARED_SCOPE",
        "facility_id": snapshot["facility_id"],
        "campaign_digest": canonical_digest(
            {
                "snapshot_digest": handoff["source_snapshot_digest"],
                "event_ids": sorted(events_by_id),
            }
        ),
        "scope_provenance": "explicit realtime scenario bindings; current-weather and reviewed annual-condition consequence evidence are kept separate",
        "events": events,
        "annual_conditions": [conditions[key] for key in sorted(conditions)],
        "cases": cases,
        "uncomputed_cases": uncomputed_cases,
        "risk_atoms": risk_atoms,
        "excluded_model_components": {},
        "coverage": {
            "generated_initiation_frequency_per_year": frequency_total,
            "fully_executed_case_weighted_frequency_per_year": 0.0,
            "fraction_of_generated_initiation_frequency": None,
            "meaning": "conditional realtime coverage only; not complete annual facility risk",
            "by_component": component_coverage,
        },
        "declared_scope_numerically_complete": False,
        "synthetic_release_horizon_present": synthetic_release_horizon_present,
        "known_contribution_annual_ir_low_high": None,
        "known_contribution_expected_death_fn_low_high": None,
        "declared_scope_annual_ir_low_high": None,
        "declared_scope_expected_death_fn_low_high": None,
        "total_facility_annual_ir_low_high": None,
        "total_facility_expected_death_fn_low_high": None,
        "timing": timing,
        "provider_packet_case_count": provider_packet_case_count,
        "qualified_provider_packet_case_count": 0,
        "provider_packet_promoted": False,
        "provider_packet_missing_evidence_cases": provider_packet_missing_evidence_cases,
        "physical_validation_claim": False,
        "complete_facility_qra_claim": False,
        "one_hz_fresh_physics_demonstrated": False,
        "realtime_snapshot_digest": handoff["source_snapshot_digest"],
        "realtime_handoff": handoff,
        "semantics": {
            "realtime": "current-weather consequence from accepted frames and provider release paths",
            "scenario_binding": "annual condition, release branch, ignition probabilities and branch-specific harm are caller-supplied; non-current conditions require reviewed consequence evidence",
            "frequency": "copied from the explicit realtime literature binding; no telemetry learning",
            "population": "copied from explicit annual condition population rows with presence probability",
            "facility_promotion": "always withheld because the snapshot is conditional and qualification/physical validation are not evaluated",
        },
    }
    return result


__all__ = [
    "IGNITION_BRANCHES",
    "RealtimeCampaignBindingError",
    "build_realtime_facility_campaign_result",
]
