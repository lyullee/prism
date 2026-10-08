from __future__ import annotations
import argparse
import json
from pathlib import Path
from .contracts import Facility
from .backend import BackendConfig, IsolatedBackend
from .consequences import ConsequenceRequest
from .pipeline import ResearchPipeline
from .frequency import FrequencyPlan, generate_events, bind_event


def main():
    p=argparse.ArgumentParser(description="LH2-TNO generic facility validation")
    p.add_argument("facility",type=Path)
    p.add_argument('--backend',type=Path,help='Pinned research-model backend configuration')
    p.add_argument('--consequences',type=Path,help='Source-to-harm request JSON')
    p.add_argument('--frequency-plan',type=Path,help='Reviewed physical inventory/frequency profiles JSON')
    p.add_argument('--event-id',help='Bind exactly one generated event to the matching consequence request')
    p.add_argument('--output',type=Path,help='Save complete result JSON')
    args=p.parse_args()
    facility=Facility.model_validate_json(args.facility.read_text(encoding="utf-8"))
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
        encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(encoded,encoding='utf-8')
            print(json.dumps({'status':result['data']['status'],'output':str(args.output.resolve()),'elapsed_ms':result['elapsed_ms']},ensure_ascii=False))
        else:print(encoded)
        return
    if events is not None:
        result={'facility':facility.id, 'plan_digest':plan.digest(), 'events':[x.model_dump(mode='json') for x in events],
                'excluded_model_components':plan.excluded_model_components,
                'total_facility_annual_risk':None, 'physical_validation_claim':False}
        encoded=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(encoded,encoding='utf-8')
        else:print(encoded)
        return
    print(json.dumps({"facility":facility.id,"components":len(facility.components),"edges":len(facility.edges),
                      "configuration_digest":facility.digest(),"physical_validation_claim":False},ensure_ascii=False))


if __name__=="__main__":main()
