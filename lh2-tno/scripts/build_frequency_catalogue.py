"""Reproduce the reviewed frequency snapshot; no provider code is copied."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT/'results/20261008/prism_qra_function_inventory/frequency_library.json'
BOOK = Path(__import__('os').environ['PRISM_PURPLE_BOOK']) if __import__('os').environ.get('PRISM_PURPLE_BOOK') else None
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest() if p and p.is_file() else None
profiles = {}

def add(name, rows, table, limitations, unit='item^-1 year^-1'):
    profiles[name] = dict(basis='TNO_PURPLE_LOC', statistic='published_default', unit=unit,
        source=f'Purple Book Chapter 3 {table}; published method reference',
        source_sha256=sha(BOOK), limitations=limitations + [
            'Generic industrial default, not an empirically validated LH2 failure rate.',
            'Equipment classification/applicability requires engineering review; no automatic cryogenic jacket credit.'],
        events=rows)

def event(loc, rate, mode, **kwargs):
    return dict(loc=loc, rate=rate, release=dict(mode=mode, **kwargs))

for name, rates in [('TNO_PRESSURE_VESSEL', [5e-7, 5e-7, 1e-5]),
                    ('TNO_PROCESS_VESSEL', [5e-6, 5e-6, 1e-4]),
                    ('TNO_REACTOR_VESSEL', [5e-6, 5e-6, 1e-4])]:
    add(name, [event('G1', rates[0], 'instantaneous_inventory'),
        event('G2', rates[1], 'inventory_over_600s'), event('G3', rates[2], 'hole', hole_diameter_m=.01)],
        'Tables 3.2/3.3, printed pp.3.2-3.4', [
        'Includes vessel and associated instrumentation pipework; connected process pipes are separate.',
        'External impact/operating error, when not excluded, adds 5e-6/year separately to G1 and G2.',
        'Near-atmospheric cryogenic tanks must not automatically use the pressure-vessel profile.',
        'No lower-frequency special-provision reduction implemented.'])
add('TNO_PIPE', [dict(loc='G1', rates_by_diameter=[1e-6, 3e-7, 1e-7],
        release=dict(mode='two_sided_rupture', diameter_rule='full_bore')),
    dict(loc='G2', rates_by_diameter=[5e-6, 2e-6, 5e-7],
        release=dict(mode='hole', diameter_rule='ten_percent_max_50mm'))],
    'Tables 3.6/3.7 and notes, printed pp.3.7-3.8', [
        'Above-ground process/inter-unit pipes; not buried transport pipelines.',
        'Diameter bins: <75 mm, 75-150 mm inclusive, >150 mm.',
        'Full-bore rupture releases from both ends; one source nozzle is insufficient.'], 'm^-1 year^-1')
for name, rates in [('TNO_PUMP_STANDARD', [1e-4, 5e-4]),
                    ('TNO_PUMP_STEEL_CONTAINMENT', [5e-5, 2.5e-4]),
                    ('TNO_PUMP_CANNED', [1e-5, 5e-5])]:
    add(name, [event('G1', rates[0], 'hole', diameter_rule='full_bore'),
        event('G2', rates[1], 'hole', diameter_rule='ten_percent_max_50mm')],
        'Tables 3.8/3.9, printed pp.3.8-3.9', ['Reference diameter is the largest connecting pipeline, not the pump body.'])
add('TNO_HX_OUTSIDE_TUBES', [event('G1', 5e-5, 'instantaneous_inventory'),
    event('G2', 5e-5, 'inventory_over_600s'), event('G3', 1e-3, 'hole', hole_diameter_m=.01)],
    'Tables 3.10/3.11, printed pp.3.9-3.10', ['Dangerous fluid outside tubes; connecting pipeline outflow also requires modelling.'])
add('TNO_HX_INSIDE_WEAK_SHELL', [event('G4', 1e-5, 'two_sided_rupture', diameter_rule='full_bore', ruptured_tubes=10),
    event('G5', 1e-3, 'two_sided_rupture', diameter_rule='full_bore'),
    event('G6', 1e-2, 'hole', diameter_rule='ten_percent_max_50mm')],
    'Tables 3.10/3.11, printed pp.3.9-3.10', ['Shell design pressure below maximum hazardous-fluid pressure; nominal diameter is tube diameter.'])
add('TNO_HX_INSIDE_STRONG_SHELL', [event('G4', 1e-6, 'two_sided_rupture', diameter_rule='full_bore', ruptured_tubes=10)],
    'Tables 3.10/3.11, printed pp.3.9-3.10', [
    'Shell design pressure at least maximum hazardous-fluid pressure; nominal diameter is tube diameter.',
    'Blank G5/G6 table cells mean not specified here; they are not measured zero failure rates.'])
add('TNO_RELIEF_DEVICE', [event('G1', 2e-5, 'maximum_relief_discharge')],
    'Tables 3.12/3.13, printed pp.3.10-3.11', [
    'Maximum atmospheric discharge LOC; not failure-to-open probability or a normal operating vent frequency.',
    'Shared initiating causes/normal vent/control demand must be de-duplicated before facility aggregation.'])

rows = json.loads(AUDIT.read_text(encoding='utf-8'))['entries']
areas = [.0001, .001, .01, .1, 1.]
for row in rows:
    if row['fuel'] != 'LH2': continue
    profiles['LH2_'+row['primitive']] = dict(basis='LH2_LITERATURE', statistic='published_median',
        unit='m^-1 year^-1' if row['primitive']=='PIPE' else 'item^-1 year^-1',
        source='Brooks, Ehrhart & LaFleur (2021), Table 2; DOI/report SAND2021-11595C; https://hysafe.info/uploads/papers/2021/44.pdf',
        source_sha256=sha(AUDIT), limitations=[
            'GH2/LNG-informed Bayesian LH2 estimates, not independently validated against LH2 field leak experience.',
            'Discrete fractional flow-area bins; do not interpolate, smooth, or add Purple LOCs for the same physical scope.',
            'Five published medians retained; distribution bounds use published ln-rate mu/sigma.',
            'Pipe exposure is metre-years (HyRAM+ manual), not the number of arbitrary pipe objects.',
            'Vessel bins need an explicitly reviewed reference flow diameter; do not use vessel diameter.'],
        events=[dict(loc=f'AREA_{label}', rate=rate, mu=row['mu'][i], sigma=row['sigma'][i],
            release=dict(mode='hole', area_fraction=areas[i], diameter_rule='area_fraction'))
            for i, (label, rate) in enumerate(row['medians'].items())])

out = dict(schema_version='1.0', reviewed_date_kst='2026-10-08',
    profiles=profiles, unresolved_profiles=[
    'atmospheric/membrane/multiple-containment storage', 'vacuum-loss initiation',
    'reliquefier special failure modes', 'normal control vent demands',
    'transfer/loading operational failures', 'cold-service sensor leaks'],
    source_files=([dict(path=str(BOOK), sha256=sha(BOOK))] if BOOK else []) + [dict(path=str(AUDIT), sha256=sha(AUDIT))],
    interpretation='Source table snapshot, not universal facility certification or complete Purple Chapter 3.')
target=ROOT/'src/lh2_tno/data/frequency_catalogue.json'
target.parent.mkdir(exist_ok=True)
target.write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
print(json.dumps({'profiles':len(profiles), 'event_rows':sum(len(p['events']) for p in profiles.values()), 'output':str(target)}, ensure_ascii=False))
