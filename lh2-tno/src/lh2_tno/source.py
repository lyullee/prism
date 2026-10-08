"""Adapt the explicit latest research source to a bounded common mass ledger."""
import math
import copy
from .backend import BackendError, IsolatedBackend
from .contracts import Contract, PartitionStep, Positive, Fraction, Nonnegative, PropertyBasis, SourceLedger, canonical_digest
from .source_termination import effective_source_duration


def integrated_source(backend: IsolatedBackend, payload: dict, *, available_mass_kg: float,
                      position_enu_m: tuple[float,float,float]) -> tuple[SourceLedger,dict]:
    if isinstance(available_mass_kg,bool) or not isinstance(available_mass_kg,(int,float)) or not math.isfinite(available_mass_kg) or available_mass_kg<=0:
        raise ValueError('finite positive available inventory required')
    if len(position_enu_m)!=3 or not all(math.isfinite(x) for x in position_enu_m):
        raise ValueError('finite ENU source position required')
    if not math.isclose(position_enu_m[2],payload['nozzle']['height_m'],rel_tol=0,abs_tol=1e-9):
        raise ValueError('flat-ground ENU height must match nozzle height')
    response=backend.run("integrated_source",payload)
    return ledger_from_response(payload,response,available_mass_kg=available_mass_kg,position_enu_m=position_enu_m),response


def ledger_from_response(payload: dict, response: dict, *, available_mass_kg: float,
                         position_enu_m: tuple[float,float,float]) -> SourceLedger:
    rows=response["data"]["steps"]
    mode=payload.get("source_duration_mode", "declared")
    try:
        duration=effective_source_duration(payload["duration_s"],payload["time_step_s"],
            [x["time_s"] for x in rows],mode)
    except (KeyError, TypeError, ValueError) as error:
        raise BackendError(str(error)) from error
    direction=payload["nozzle"]["direction_enu"]
    norm=math.sqrt(sum(x*x for x in direction))
    fluid=payload["tank"]["fluid"]
    ledger=SourceLedger(source_stage="nozzle_to_ground_partition",
        property_basis=PropertyBasis(fluid=fluid,energy_reference=f"CoolProp-HEOS:{fluid}:native"),
        position_enu_m=position_enu_m,direction_enu=tuple(x/norm for x in direction),
        duration_s=duration,integration_rule="left_constant",initial_available_mass_kg=available_mass_kg,
        steps=tuple(PartitionStep(time_s=x["time_s"],total_kg_s=x["total_mass_flow_kg_s"],gas_kg_s=x["gas_mass_flow_kg_s"],
                                 airborne_liquid_kg_s=x["airborne_liquid_mass_flow_kg_s"],ground_liquid_kg_s=x["ground_liquid_mass_flow_kg_s"]) for x in rows),
        model_revision=response["backend_config_digest"],request_digest=response["request_digest"],
        energy_balance_scope=response["energy_balance_scope"],
        limitations=(response["limitation"],"not the frozen seven-test FFI concentration calculation route",
                     *(('natural pressure-equalization termination; no flow extrapolation',) if mode=='model_natural' else ())))
    return ledger


class PrescribedState(Contract):
    time_s: Nonnegative
    pressure_pa: Positive
    temperature_k: Positive
    vapour_quality: Fraction


def prescribed_source_history(backend: IsolatedBackend, common_input: dict, states: tuple[PrescribedState,...], *,
                              end_s: float, available_mass_kg: float,
                              position_enu_m: tuple[float,float,float]) -> tuple[SourceLedger,tuple[dict,...]]:
    """Evaluate externally prescribed upstream states with a left hold.

    This does not solve or qualify the tank dynamics that supplied those states.
    Every interval invokes the source solver's steady component route only.
    """
    if not states or states[0].time_s!=0 or not math.isfinite(end_s) or end_s<=states[-1].time_s:
        raise ValueError('valid prescribed state horizon required')
    if any(b.time_s<=a.time_s for a,b in zip(states,states[1:])):
        raise ValueError('prescribed state timestamps must strictly increase')
    ends=[x.time_s for x in states[1:]]+[end_s]
    steps=[]; responses=[]; last_ledger=None
    for state,end in zip(states,ends):
        request=copy.deepcopy(common_input)
        request['tank'].update(pressure_pa=state.pressure_pa,temperature_k=state.temperature_k,vapour_quality=state.vapour_quality)
        request['duration_s']=end-state.time_s;request['time_step_s']=request['duration_s']
        local,response=integrated_source(backend,request,available_mass_kg=available_mass_kg,position_enu_m=position_enu_m)
        values=local.steps[0].model_dump();values['time_s']=state.time_s
        steps.append(PartitionStep(**values));responses.append(response);last_ledger=local
    values=last_ledger.model_dump()
    values.update(duration_s=end_s,steps=tuple(steps),property_basis=last_ledger.property_basis,
                  request_digest=canonical_digest({'common_input':common_input,'states':[s.model_dump(mode='json') for s in states],'end_s':end_s}),
                  limitations=last_ledger.limitations+('externally prescribed upstream states; tank dynamics not solved or qualified',))
    return SourceLedger(**values),tuple(responses)
