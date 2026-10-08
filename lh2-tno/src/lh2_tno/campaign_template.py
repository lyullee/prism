"""Compile explicit equipment inputs into a fail-closed risk campaign.

The compiler connects four declarations: an executable equipment manifest, a
reviewed frequency plan, a provider/request template and annual
weather/population conditions.  It never invents a consequence route.  Each
generated frequency event gets either a request whose physical opening was
validated by :func:`bind_event`, or an explicit ``UNCOMPUTED`` branch.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pydantic import model_validator

from .campaign import AnnualCondition, EventRoute, ReleaseBranch, RiskCampaign
from .contracts import Contract, Fraction, Name
from .consequences import ConsequenceRequest
from .equipment_manifest import EquipmentManifest, audit_manifest
from .frequency import FrequencyPlan, bind_event, generate_events
from .provider_release import (
    ProviderReleaseSet,
    ProviderReleaseBranch,
    ProviderRelease,
    ProviderReleaseContractError,
    build_consequence_request_from_provider_release,
    build_consequence_request_from_provider_release_set,
)


class RequestBranchTemplate(Contract):
    """One provider-resolved barrier/isolation branch for a frequency event.

    The branch probability is conditional on initiation.  It is intentionally
    separate from the consequence request so a provider can supply distinct
    success/failure histories without copying one history into another branch.
    """

    id: Name
    probability_given_event: Fraction
    provenance: Name
    request: ConsequenceRequest

    @model_validator(mode="after")
    def request_has_no_frequency(self):
        request = self.request
        if any(
            value is not None
            for value in (
                request.annual_frequency_per_year,
                request.annual_frequency_provenance,
                request.frequency_event,
                request.initiation_intensity_per_s,
            )
        ):
            raise ValueError("request branch templates must not contain initiating frequency")
        return self


def build_equipment_campaign(
    manifest: EquipmentManifest,
    frequency_plan: FrequencyPlan,
    request_template: ConsequenceRequest,
    annual_conditions: tuple[AnnualCondition, ...],
    *,
    scope_provenance: str,
    maximum_physics_cases: int = 200,
) -> RiskCampaign:
    """Compile an explicit campaign while preserving unsupported LOCs.

    ``request_template`` must not already contain initiating frequency.  A
    matched request is kept as a template; :func:`campaign.prepared_request`
    binds the event and current weather immediately before execution.
    """

    return build_equipment_campaign_from_catalog(
        manifest,
        frequency_plan,
        (request_template,),
        annual_conditions,
        scope_provenance=scope_provenance,
        maximum_physics_cases=maximum_physics_cases,
    )


def build_equipment_campaign_from_catalog(
    manifest: EquipmentManifest,
    frequency_plan: FrequencyPlan,
    request_templates: Sequence[ConsequenceRequest],
    annual_conditions: tuple[AnnualCondition, ...],
    *,
    scope_provenance: str,
    maximum_physics_cases: int = 200,
) -> RiskCampaign:
    """Compile one explicit request per matching equipment opening.

    A real equipment provider normally has more than one source boundary.
    This catalog variant lets each component/opening carry its own request
    template.  Matching is still exact: component identity and physical
    opening must pass :func:`bind_event`; no request is copied between
    components and no diameter is substituted.  An event with no match is
    retained as an explicit ``UNCOMPUTED`` branch.
    """
    if not request_templates:
        raise ValueError("request catalog must contain at least one template")
    manifest_audit = audit_manifest(manifest)
    if manifest_audit["status"] != "EXECUTABLE":
        raise ValueError(
            "equipment manifest is not executable: "
            + "; ".join(manifest_audit["blocking_reasons"])
        )
    for index, request_template in enumerate(request_templates):
        if any(
            value is not None
            for value in (
                request_template.annual_frequency_per_year,
                request_template.annual_frequency_provenance,
                request_template.frequency_event,
                request_template.initiation_intensity_per_s,
            )
        ):
            raise ValueError(f"request template {index} must not contain initiating frequency")
    facility = manifest.to_facility()
    events = generate_events(facility, frequency_plan)
    routes: list[EventRoute] = []
    for event in events:
        matches = []
        errors = []
        for index, request_template in enumerate(request_templates):
            try:
                matches.append((index, bind_event(request_template, event)))
            except (ValueError, TypeError) as error:
                errors.append(f"template {index}: {error}")
        if len(matches) > 1:
            raise ValueError(
                f"multiple request templates match event {event.id}: "
                + ", ".join(str(index) for index, _ in matches)
            )
        try:
            if not matches:
                raise ValueError("; ".join(errors) or "no request template matched event")
            _, bound = matches[0]
            payload = bound.model_dump(mode="json")
            # Campaign templates carry no initiating frequency.  The campaign
            # executor binds the selected event separately for each weather
            # condition, preserving one frequency application per route.
            payload.update(
                annual_frequency_per_year=None,
                annual_frequency_provenance=None,
                frequency_event=None,
                initiation_intensity_per_s=None,
            )
            template = ConsequenceRequest.model_validate_json(
                json.dumps(payload, allow_nan=False)
            )
            branch = ReleaseBranch(
                id="matched-provider-request",
                probability_given_event=1.0,
                provenance=(
                    "explicit request catalog matched component and release opening; "
                    "event frequency is bound at campaign execution"
                ),
                request=template,
            )
        except (ValueError, TypeError) as error:
            branch = ReleaseBranch(
                id="uncomputed-no-matching-request",
                probability_given_event=1.0,
                provenance="no physical request was inferred or size-substituted",
                uncomputed_reason=f"{type(error).__name__}: {error}",
            )
        routes.append(EventRoute(event_id=event.id, branches=(branch,)))
    return RiskCampaign(
        id="equipment-manifest-campaign",
        frequency_plan=frequency_plan,
        annual_conditions=annual_conditions,
        event_routes=tuple(routes),
        scope_provenance=scope_provenance,
        maximum_physics_cases=maximum_physics_cases,
    )


def build_equipment_campaign_from_branch_catalog(
    manifest: EquipmentManifest,
    frequency_plan: FrequencyPlan,
    branch_templates: Sequence[RequestBranchTemplate],
    annual_conditions: tuple[AnnualCondition, ...],
    *,
    scope_provenance: str,
    maximum_physics_cases: int = 200,
) -> RiskCampaign:
    """Compile explicit isolation/barrier branches without dropping probability.

    Each template is matched by component and physical opening.  For an event
    with at least one match, matched conditional probabilities must not exceed
    one; a missing remainder is retained as an explicit ``UNCOMPUTED`` branch.
    This allows a provider to submit isolation-success and isolation-failure
    histories while keeping an absent failure history visible in the campaign.
    """
    if not branch_templates:
        raise ValueError("branch request catalog must contain at least one template")
    manifest_audit = audit_manifest(manifest)
    if manifest_audit["status"] != "EXECUTABLE":
        raise ValueError(
            "equipment manifest is not executable: "
            + "; ".join(manifest_audit["blocking_reasons"])
        )
    if len({item.id for item in branch_templates}) != len(branch_templates):
        raise ValueError("branch request catalog ids must be unique")
    facility = manifest.to_facility()
    events = generate_events(facility, frequency_plan)
    routes: list[EventRoute] = []
    for event in events:
        matches = []
        errors = []
        for item in branch_templates:
            try:
                matches.append((item, bind_event(item.request, event)))
            except (ValueError, TypeError) as error:
                errors.append(f"branch {item.id}: {error}")
        if not matches:
            branch = ReleaseBranch(
                id="uncomputed-no-matching-request",
                probability_given_event=1.0,
                provenance="no physical branch request was inferred or size-substituted",
                uncomputed_reason="; ".join(errors) or "no branch request matched event",
            )
            routes.append(EventRoute(event_id=event.id, branches=(branch,)))
            continue
        total = sum(item.probability_given_event for item, _ in matches)
        if total > 1.0 + 1e-10:
            raise ValueError(
                f"branch probabilities exceed one for event {event.id}: {total}"
            )
        branches: list[ReleaseBranch] = []
        for item, bound in matches:
            payload = bound.model_dump(mode="json")
            payload.update(
                annual_frequency_per_year=None,
                annual_frequency_provenance=None,
                frequency_event=None,
                initiation_intensity_per_s=None,
            )
            template = ConsequenceRequest.model_validate_json(
                json.dumps(payload, allow_nan=False)
            )
            branches.append(
                ReleaseBranch(
                    id=item.id,
                    probability_given_event=item.probability_given_event,
                    provenance=item.provenance,
                    request=template,
                )
            )
        remainder = 1.0 - total
        if remainder > 1e-10:
            branches.append(
                ReleaseBranch(
                    id="uncomputed-provider-branch-remainder",
                    probability_given_event=remainder,
                    provenance="provider branch catalog did not cover the full initiated-event partition",
                    uncomputed_reason=(
                        f"missing provider branch probability {remainder:.12g} for event {event.id}"
                    ),
                )
            )
        routes.append(EventRoute(event_id=event.id, branches=tuple(branches)))
    return RiskCampaign(
        id="equipment-manifest-branch-campaign",
        frequency_plan=frequency_plan,
        annual_conditions=annual_conditions,
        event_routes=tuple(routes),
        scope_provenance=scope_provenance,
        maximum_physics_cases=maximum_physics_cases,
    )


def build_equipment_campaign_from_provider_catalog(
    manifest: EquipmentManifest,
    frequency_plan: FrequencyPlan,
    provider_releases: Sequence[ProviderRelease | ProviderReleaseSet],
    request_defaults: Mapping[str, object],
    annual_conditions: tuple[AnnualCondition, ...],
    *,
    scope_provenance: str,
    maximum_physics_cases: int = 200,
) -> RiskCampaign:
    """Compile strict provider release packets directly into a campaign.

    This is a convenience boundary for a digital-twin adapter.  The provider
    still owns the resolved outlet history; this function only attaches the
    reviewed consequence context and delegates component/opening matching to
    :func:`build_equipment_campaign_from_catalog`.  A malformed packet or a
    context with a missing termination basis is a configuration error, rather
    than an implicit ``UNCOMPUTED`` event.  Callers that need a partial catalog
    report can continue to use ``build_provider_request_catalog.py`` first.
    """
    if not provider_releases:
        raise ValueError("provider release catalog must contain at least one release")
    if len({release.event_id for release in provider_releases}) != len(provider_releases):
        raise ValueError("provider release event_id values must be unique")
    templates = []
    for release in provider_releases:
        try:
            if isinstance(release, ProviderReleaseSet):
                templates.append(
                    build_consequence_request_from_provider_release_set(
                        release, request_defaults
                    )
                )
            else:
                templates.append(
                    build_consequence_request_from_provider_release(
                        release, request_defaults
                    )
                )
        except ProviderReleaseContractError as error:
            raise ValueError(
                f"provider release {release.event_id} cannot be attached to a campaign: {error}"
            ) from error
    return build_equipment_campaign_from_catalog(
        manifest,
        frequency_plan,
        tuple(templates),
        annual_conditions,
        scope_provenance=scope_provenance,
        maximum_physics_cases=maximum_physics_cases,
    )


def build_equipment_campaign_from_provider_branch_catalog(
    manifest: EquipmentManifest,
    frequency_plan: FrequencyPlan,
    provider_branches: Sequence[ProviderReleaseBranch],
    request_defaults: Mapping[str, object],
    annual_conditions: tuple[AnnualCondition, ...],
    *,
    scope_provenance: str,
    maximum_physics_cases: int = 200,
) -> RiskCampaign:
    """Compile provider-resolved accident packets with barrier branches.

    Each wrapper contains one strict provider packet and a probability
    conditional on the initiating event.  The packet is converted to a
    consequence request without adding frequency, then the common branch
    compiler exact-matches component/opening and retains an uncovered
    probability remainder as ``UNCOMPUTED``.
    """
    if not provider_branches:
        raise ValueError("provider release branch catalog must contain at least one branch")
    templates: list[RequestBranchTemplate] = []
    for branch in provider_branches:
        try:
            request = (
                build_consequence_request_from_provider_release_set(
                    branch.release, request_defaults
                )
                if isinstance(branch.release, ProviderReleaseSet)
                else build_consequence_request_from_provider_release(
                    branch.release, request_defaults
                )
            )
        except ProviderReleaseContractError as error:
            raise ValueError(
                f"provider release branch {branch.id} cannot be attached to a campaign: {error}"
            ) from error
        templates.append(
            RequestBranchTemplate(
                id=branch.id,
                probability_given_event=branch.probability_given_event,
                provenance=branch.provenance,
                request=request,
            )
        )
    return build_equipment_campaign_from_branch_catalog(
        manifest,
        frequency_plan,
        tuple(templates),
        annual_conditions,
        scope_provenance=scope_provenance,
        maximum_physics_cases=maximum_physics_cases,
    )
