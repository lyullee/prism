"""Record completed first development increment without qualifying the goal."""
import json
from pathlib import Path
import platform
import math
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/20261009/campaign_step1'
r=json.loads((OUT/'cli_campaign_result.json').read_text(encoding='utf-8'))
assert r['status']=='PARTIAL_DECLARED_SCOPE'
assert len([x for x in r['cases'] if x['status']=='EXECUTED'])==4
assert len(r['uncomputed_cases'])==4
assert r['total_facility_annual_ir_low_high'] is None
assert all(abs(x['mass_ledger']['end_to_end_residual_kg'])<1e-8 for x in r['cases'] if x['status']=='EXECUTED')
sens=r['frequency_sensitivity']
for entry,m in zip(sens['scenarios'],(.1,1.,10.)):
    for rid,values in r['known_contribution_annual_ir_low_high'].items():
        assert all(math.isclose(a,m*b,rel_tol=1e-12,abs_tol=1e-15) for a,b in zip(entry['known_annual_ir_low_high'][rid],values))
    assert entry['total_facility_annual_ir_low_high'] is None
stress=json.loads((OUT/'stress_probe_result.json').read_text(encoding='utf-8'))
failed=[x for x in stress['cases'] if x['status']=='FAILED']
assert len(failed)==3
record={'date_kst':'2026-10-09','goal_status':'active','baseline_public_release':'0.6.0',
    'development_stage':'post-0.6.0 campaign/sensitivity/natural-termination/literature-uncertainty development; not published',
    'portable_tests_passed':191,'fresh_cli_physics_cases_passed':4,
    'g1_g2_uncomputed_weather_cases':4,'native_tno_ir_expected_death_fn_connected':True,
    'steady_upstream_synthetic_durations_s':[.2,.4],'real_isolation_or_inventory_feedback_qualified':False,
    'frequency_sensitivity_baseline_and_linear_scaling_verified':True,
    'literature_frequency_quantile_uncertainty_implemented':True,
    'literature_frequency_uncertainty_statistical_interval':False,
    'statistical_frequency_uncertainty_complete':False,'total_facility_risk_withheld':True,
    'cli_campaign_digest':r['campaign_digest'],'cli_timing':r['timing'],
    'native_aggregation_provenance':r['aggregation_provenance'],
    'stress_probe_failures':[{'condition':x['annual_condition_id'],'branch':x['release_branch_id'],
        'reason':x['reason'],'elapsed_ms':x['elapsed_ms']} for x in failed],
    'hardware':{'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'processor':platform.processor()},
    'physical_validation_claim':False,'one_hz_fresh_physics_demonstrated':False}
(OUT/'step1_verification.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'frequency_sensitivity.json').write_text(json.dumps(sens,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p=ROOT/'CURRENT_STATUS.json'
status=json.loads(p.read_text(encoding='utf-8'))
status.update({'development_date_kst':'2026-10-09','development_since_public_release':'post-0.6.0 campaign/sensitivity/natural-termination/literature-uncertainty development; unpublished',
    'unit_contract_conservation_tests_passed':191,'ijhe_completion_goal_status':'active',
    'ijhe_completion_goal_record':'docs/PRISM_IJHE_완성목표_20261009.md',
    'multi_event_weather_barrier_campaign_implemented':True,'legacy_tno_ir_fn_aggregator_connected_to_lh2_campaign':True,
    'campaign_actual_fresh_physics_cases_passed':4,'campaign_actual_scope':'one tank-hole; two aligned wind speeds; two steady upstream synthetic durations',
    'campaign_uncomputed_g1_g2_cases':4,'campaign_total_facility_risk_withheld':True,
    'campaign_failure_ledger_implemented':True,'deterministic_frequency_sensitivity_implemented':True,
    'statistical_frequency_uncertainty_complete':False,'campaign_record':'docs/PRISM_시설위험_실행기_개발기록_20261009.md',
    'campaign_results':'results/20261009/campaign_step1',
    'identified_crosswind_case_deadline_s':180.,'transient_source_natural_termination_wrapper_verified':True,
    'transient_source_physical_validation_claim':False,'identified_transient_source_early_stop_remains_unqualified':False})
p.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'goal':'active','cli_checks':'passed','timing':r['timing'],'stress_failures_preserved':len(failed)},indent=2))
