"""Facility-aware source evaluation through the existing TNO evidence gate."""
from __future__ import annotations
from dataclasses import dataclass
from .backend import BackendLike
from .contracts import Facility, PropertyBasis, SourceLedger, canonical_digest
from .source import integrated_source


@dataclass(frozen=True)
class SourceEvaluation:
    ledger: SourceLedger
    diagnostic_mass_flow_mean_kg_s: float
    reporting_interval_kg_s: tuple[float,float] | None
    assurance_state: str
    reasons: tuple[str,...]
    provenance: dict
    physical_validation_claim: bool = False


class ResearchPipeline:
    def __init__(self, facility: Facility, backend: BackendLike):
        self.facility=facility
        self.backend=backend

    def consequences(self, request):
        from .consequences import evaluate_consequences
        return evaluate_consequences(self,request)

    def frequency_events(self, plan):
        from .frequency import generate_events
        return generate_events(self.facility, plan)

    def legacy_frequency_events(self, scenarios, component_map, *, plan_id='legacy-tno',
                                source='external legacy TNO taxonomy.enumerate_scenarios',
                                source_sha256, basis='TNO_PURPLE_LOC'):
        """Consume a pinned legacy-TNO scenario export through the same event boundary.

        The external taxonomy remains the owner of its frequency arithmetic.
        This method only performs the explicit scenario-to-facility mapping and
        returns the bridge audit sidecar; it never fabricates a provider
        release or promotes a facility QRA.
        """
        from .legacy_frequency_bridge import bridge_legacy_scenarios
        return bridge_legacy_scenarios(
            scenarios,
            component_map,
            plan_id=plan_id,
            source=source,
            source_sha256=source_sha256,
            facility=self.facility,
            basis=basis,
        )

    def facility_risk(self, campaign):
        from .campaign import evaluate_campaign
        return evaluate_campaign(self, campaign)

    def consequences_for_event(self, plan, event_id, template):
        from .frequency import bind_event
        events = {x.id: x for x in self.frequency_events(plan)}
        if event_id not in events:
            raise ValueError('unknown initiating event')
        return self.consequences(bind_event(template, events[event_id]))

    def source(self, component_id: str, payload: dict, *, available_mass_kg: float,
               position_enu_m: tuple[float,float,float], evidence_ids: tuple[str,...]=(),
               evidence_records: tuple[dict,...]=()) -> SourceEvaluation:
        components={x.id:x for x in self.facility.components}
        if component_id not in components:raise ValueError("source component not in facility")
        if self.facility.environment!='outdoor':raise ValueError("source route currently supports outdoor facilities only")
        component=components[component_id]
        fluid=payload['tank']['fluid']
        basis=PropertyBasis(fluid=fluid,energy_reference=f'CoolProp-HEOS:{fluid}:native')
        if component.property_basis!=basis:raise ValueError("source/facility property basis mismatch")
        if component.kind!='storage_tank':raise ValueError("integrated source requires a tank component")
        if component.parameters_si['volume_m3']!=payload['tank']['volume_m3']:
            raise ValueError("source/facility volume mismatch")
        ledger,response=integrated_source(self.backend,payload,available_mass_kg=available_mass_kg,position_enu_m=position_enu_m)
        mean=ledger.released_mass_kg/ledger.duration_s
        # This integration has no reviewed physical applicability certificate yet.
        # Evidence records are checked, but may not self-promote the diagnostic route.
        output={'component':'LH2-integrated-source','version':ledger.model_revision,
                'quantity':'source_mass_flow','unit':'kg/s','observation_operator':'left-constant-horizon-mean',
                'source_fingerprint':ledger.digest(),'receptor_fingerprint':'source-boundary-no-receptors',
                'evidence_ids':list(evidence_ids),'status':'diagnostic','interval':[mean,mean],
                'conditions_satisfied':False,'warnings':['total energy closure not qualified'],
                'shared_limitations':list(ledger.limitations)}
        gate=self.backend.run('assurance',{'outputs':[output],'records':list(evidence_records)})['data']
        interval=tuple(gate['interval']) if gate['interval'] is not None else None
        return SourceEvaluation(ledger,mean,interval,gate['state'],tuple(gate['reasons']),
            {'facility_digest':self.facility.digest(),'request_digest':response['request_digest'],
             'backend_config_digest':response['backend_config_digest'],'worker_sha256':response['worker_sha256'],
             'environment':response['environment'],'source_elapsed_ms':response['elapsed_ms']})
