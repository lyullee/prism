from __future__ import annotations
import argparse
import json
from pathlib import Path
from .contracts import Facility
from .equipment_manifest import EquipmentManifest, audit_manifest
from .backend import BackendConfig, IsolatedBackend
from .consequences import ConsequenceRequest
from .pipeline import ResearchPipeline
from .frequency import FrequencyPlan, generate_events, bind_event


def main(argv=None):
    p=argparse.ArgumentParser(description="PRISM LH2 mode: generic facility validation and risk-model orchestration")
    p.add_argument("facility",type=Path,nargs='?',help='Strict Facility JSON (use --equipment-manifest for a provider export)')
    p.add_argument('--equipment-manifest',type=Path,help='Facility-neutral digital-twin manifest; promoted only when its audit is EXECUTABLE')
    p.add_argument('--backend',type=Path,help='Pinned research-model backend configuration')
    p.add_argument('--consequences',type=Path,help='Source-to-harm request JSON')
    p.add_argument('--frequency-plan',type=Path,help='Reviewed physical inventory/frequency profiles JSON')
    p.add_argument('--event-id',help='Bind exactly one generated event to the matching consequence request')
    p.add_argument('--risk-campaign',type=Path,help='Declared LOC/weather/barrier/population campaign JSON')
    p.add_argument('--frequency-sensitivity',type=Path,help='Explicit asset multiplier scenarios for a risk campaign')
    p.add_argument('--frequency-uncertainty',type=Path,help='Published literature-frequency quantile scenarios for a risk campaign')
    p.add_argument('--frequency-distribution',type=Path,help='Published lognormal frequency-distribution scenarios for a risk campaign')
    p.add_argument('--frequency-distribution-draws',type=int,default=1000,help='Number of frequency-only draws (100-100000)')
    p.add_argument('--frequency-distribution-seed',type=int,default=20261009,help='Deterministic seed for frequency-only draws')
    p.add_argument('--output',type=Path,help='Save complete result JSON')
    args=p.parse_args(argv)
    if (args.facility is None) == (args.equipment_manifest is None):
        p.error('provide exactly one positional facility JSON or --equipment-manifest')
    if args.equipment_manifest is not None:
        manifest=EquipmentManifest.from_json(args.equipment_manifest)
        audit=audit_manifest(manifest)
        if audit['status'] != 'EXECUTABLE':
            p.error('equipment manifest is not executable: ' + '; '.join(audit['blocking_reasons']))
        facility=manifest.to_facility()
    else:
        facility=Facility.model_validate_json(args.facility.read_text(encoding="utf-8"))
    if (args.frequency_sensitivity or args.frequency_uncertainty or args.frequency_distribution) and not args.risk_campaign:
        p.error('--frequency-sensitivity/--frequency-uncertainty/--frequency-distribution requires --risk-campaign')
    if args.risk_campaign:
        if args.consequences or args.frequency_plan or args.event_id:
            p.error('--risk-campaign owns frequency plan and cases; cannot mix single-event options')
        if not args.backend:
            p.error('--backend is required with --risk-campaign')
        from .campaign import RiskCampaign
        campaign=RiskCampaign.model_validate_json(args.risk_campaign.read_text(encoding='utf-8'))
        sensitivities=None
        uncertainties=None
        distributions=None
        if args.frequency_sensitivity:
            from .sensitivity import FrequencySensitivity, frequency_sensitivity
            rows=json.loads(args.frequency_sensitivity.read_text(encoding='utf-8'))
            if not isinstance(rows,list):
                p.error('--frequency-sensitivity must contain an array of explicit scenarios')
            sensitivities=tuple(FrequencySensitivity.model_validate_json(json.dumps(r,allow_nan=False)) for r in rows)
        if args.frequency_uncertainty:
            from .uncertainty import LiteratureFrequencyScenario
            rows=json.loads(args.frequency_uncertainty.read_text(encoding='utf-8'))
            if not isinstance(rows,list):
                p.error('--frequency-uncertainty must contain an array of explicit scenarios')
            uncertainties=tuple(LiteratureFrequencyScenario.model_validate_json(json.dumps(r,allow_nan=False)) for r in rows)
        if args.frequency_distribution:
            from .uncertainty import LiteratureFrequencyDistributionScenario
            rows=json.loads(args.frequency_distribution.read_text(encoding='utf-8'))
            if not isinstance(rows,list):
                p.error('--frequency-distribution must contain an array of explicit scenarios')
            distributions=tuple(LiteratureFrequencyDistributionScenario.model_validate_json(json.dumps(r,allow_nan=False)) for r in rows)
        backend=IsolatedBackend(BackendConfig.model_validate_json(args.backend.read_text(encoding='utf-8')))
        result=ResearchPipeline(facility,backend).facility_risk(campaign)
        if sensitivities is not None:
            result['frequency_sensitivity']=frequency_sensitivity(result,sensitivities)
        if uncertainties is not None:
            from .uncertainty import literature_frequency_uncertainty
            result['literature_frequency_uncertainty']=literature_frequency_uncertainty(result,uncertainties)
        if distributions is not None:
            from .uncertainty import sample_literature_frequency_distributions
            result['literature_frequency_distribution']=sample_literature_frequency_distributions(
                result, distributions, draws=args.frequency_distribution_draws,
                seed=args.frequency_distribution_seed)
        result['execution_mode']='lh2'
        encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(encoded,encoding='utf-8')
            print(json.dumps({'status':result['status'],'output':str(args.output.resolve()),
                'uncomputed_cases':len(result['uncomputed_cases']), 'total_facility_annual_risk_available':result['total_facility_annual_ir_low_high'] is not None},ensure_ascii=False))
        else:
            print(encoded)
        return
    events = None
    if args.frequency_plan:
        plan = FrequencyPlan.model_validate_json(args.frequency_plan.read_text(encoding='utf-8'))
        events = generate_events(facility, plan)
    if args.event_id and (events is None or not args.consequences):
        p.error('--event-id requires --frequency-plan and --consequences')
    if events is not None and args.consequences and not args.event_id:
        p.error('select --event-id explicitly; never aggregate unevaluated LOCs')
    if args.consequences:
        if not args.backend:p.error('--backend is required with --consequences')
        backend=IsolatedBackend(BackendConfig.model_validate_json(args.backend.read_text(encoding='utf-8')))
        request=ConsequenceRequest.model_validate_json(args.consequences.read_text(encoding='utf-8'))
        if args.event_id:
            selected={x.id:x for x in events}
            if args.event_id not in selected:p.error('unknown --event-id')
            request=bind_event(request,selected[args.event_id])
        result=ResearchPipeline(facility,backend).consequences(request)
        result['execution_mode']='lh2'
        result['mode_dispatch']={'engine':'lh2_extension','automatic_fallback':False,'legacy_total_facility_qra_selected':False}
        encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(encoded,encoding='utf-8')
            print(json.dumps({'status':result['data']['status'],'output':str(args.output.resolve()),'elapsed_ms':result['elapsed_ms']},ensure_ascii=False))
        else:print(encoded)
        return
    if events is not None:
        result={'execution_mode':'lh2','facility':facility.id, 'plan_digest':plan.digest(), 'events':[x.model_dump(mode='json') for x in events],
                'excluded_model_components':plan.excluded_model_components,
                'total_facility_annual_risk':None, 'physical_validation_claim':False}
        encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(encoded,encoding='utf-8')
        else:print(encoded)
        return
    print(json.dumps({"execution_mode":"lh2","facility":facility.id,"components":len(facility.components),"edges":len(facility.edges),
                      "configuration_digest":facility.digest(),"physical_validation_claim":False},ensure_ascii=False))


if __name__=="__main__":main()
