"""Digital-twin entry point for known leak scenarios and normalized sensors."""
from __future__ import annotations
from collections import OrderedDict
import copy
from pathlib import Path
import time
from .backend import BackendError, tree_digest
from .consequences import ConsequenceRequest
from .contracts import canonical_digest


def request_from_telemetry(template, normalized, *, pressure_tag, temperature_tag):
    """Use confirmed SI tank state. This is not inverse leak identification."""
    if template.resolved_release is not None or template.resolved_release_set is not None or template.resolved_liquid_release is not None:
        raise ValueError('resolved provider flow must be updated by the equipment model; cannot overwrite its PH boundary from raw P/T tags')
    if pressure_tag==temperature_tag:raise ValueError('distinct pressure and temperature tags required')
    data=template.model_dump(mode='json')
    for tag,quantity,key in ((pressure_tag,'pressure','pressure_pa'),(temperature_tag,'temperature','temperature_k')):
        value=normalized['values'].get(tag)
        if value is None or value['quantity']!=quantity or value['component_id']!=template.component_id:
            raise ValueError('sensor quantity/component does not match the declared source boundary')
        data['source_input']['tank'][key]=value['value_si']
    return ConsequenceRequest.model_validate_json(__import__('json').dumps(data,allow_nan=False))


class ConsequenceService:
    """Bounded exact-result cache; changed states invoke fresh physics.

    No interpolation, tolerance matching, or stale fallback is hidden here.
    A cached lookup is explicitly distinguished from a new model execution.
    """
    def __init__(self,pipeline,capacity=16):
        if isinstance(capacity,bool) or not isinstance(capacity,int) or not 1<=capacity<=1000:
            raise ValueError('positive bounded cache capacity required')
        self.pipeline=pipeline;self.capacity=capacity;self._cache=OrderedDict()

    def evaluate(self,request):
        start=time.perf_counter()
        for pin in self.pipeline.backend.config.packages:
            if tree_digest(Path(pin.root))!=pin.sha256:
                raise BackendError(f'source revision mismatch: {pin.name}')
        adapter=tree_digest(Path(__file__).parent)
        key=canonical_digest([request.digest(),self.pipeline.facility.digest(),self.pipeline.backend.config.digest(),adapter])
        hit=key in self._cache
        if hit:
            result=copy.deepcopy(self._cache[key]);self._cache.move_to_end(key)
        else:
            result=self.pipeline.consequences(request)
            if result['adapter_source_digest']!=adapter:raise BackendError('adapter changed before cache insertion')
            self._cache[key]=copy.deepcopy(result)
            while len(self._cache)>self.capacity:self._cache.popitem(last=False)
        result['service']={'exact_cache_hit':hit,'fresh_physics_this_update':not hit,
            'service_elapsed_ms':(time.perf_counter()-start)*1000,'physics_run_elapsed_ms':result['elapsed_ms'],
            'cache_key':key,'realtime_fresh_physics_claim':False}
        return result

    def update_from_telemetry(self,template,normalized,*,pressure_tag,temperature_tag):
        request=request_from_telemetry(template,normalized,pressure_tag=pressure_tag,temperature_tag=temperature_tag)
        result=self.evaluate(request)
        result['telemetry_boundary']={k:normalized[k] for k in
            ('origin','independent_measurement_claim','data_age_s','frame_digest','mapping_digest')}
        result['telemetry_boundary']['data_age_at_output_s']=normalized['data_age_s']+result['service']['service_elapsed_ms']/1000
        result['telemetry_boundary']['interpretation']='known leak geometry; sensor pressure/temperature update, no inferred leak size or learned frequency'
        return result
