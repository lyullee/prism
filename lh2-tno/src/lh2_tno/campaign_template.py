"""Compile explicit equipment inputs into a fail-closed risk campaign.

The compiler connects four declarations: an executable equipment manifest, a
reviewed frequency plan, a provider/request template and annual
weather/population conditions.  It never invents a consequence route.  Each
generated frequency event gets either a request whose physical opening was
validated by :func:`bind_event`, or an explicit ``UNCOMPUTED`` branch.
"""
from __future__ import annotations

import json
from collections.abc import Sequence

from .campaign import AnnualCondition, EventRoute, ReleaseBranch, RiskCampaign
from .consequences import ConsequenceRequest
from .equipment_manifest import EquipmentManifest, audit_manifest
from .frequency import FrequencyPlan, bind_event, generate_events


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
