from collections import Counter
from taxonomy import *

site = Site(
    name="LH2 station (demo)",
    sections=[
        Section(id="LH2_TANK",     inventory_kg=5000, isolation_time_s=1800, service=Service.LH2),
        Section(id="LH2_TRANSFER", inventory_kg=  80, isolation_time_s=  30, service=Service.LH2),
        Section(id="GH2_HP",       inventory_kg= 120, isolation_time_s=  15, service=Service.GH2),
    ],
    components=[
        ComponentSpec(primitive=Primitive.VESSEL, service=Service.LH2, tag="TK-101",
                      nominal_diameter_m=0.05, pressure_pa=6e5, temperature_k=22,
                      position=Position(x=0,y=0), section_id="LH2_TANK"),
        ComponentSpec(primitive=Primitive.VALVE, service=Service.GH2, count=12, tag="HP-V",
                      nominal_diameter_m=0.012, pressure_pa=4.5e7, temperature_k=288,
                      position=Position(x=30,y=5), section_id="GH2_HP"),
    ],
    assemblies=[
        AssemblySpec(assembly=Assembly.VJ_LINE, service=Service.LH2, tag="LP-201", count=3,
                     nominal_diameter_m=0.05, pressure_pa=6e5, temperature_k=22,
                     position=Position(x=12,y=0), section_id="LH2_TRANSFER"),
        AssemblySpec(assembly=Assembly.LH2_PUMP, service=Service.LH2, tag="P-401",
                     nominal_diameter_m=0.04, pressure_pa=8e5, temperature_k=22,
                     position=Position(x=18,y=2), section_id="LH2_TRANSFER"),
        AssemblySpec(assembly=Assembly.VAPORIZER_UNIT, service=Service.COLD_GH2, tag="VAP-501",
                     nominal_diameter_m=0.025, pressure_pa=3e7, temperature_k=150,
                     position=Position(x=24,y=2), section_id="GH2_HP"),
    ],
)

sc = enumerate_scenarios(site)
comp = [s for s in sc if s.computable]
ver  = [s for s in sc if s.report_verified]
print(f"시나리오 {len(sc)} / 계산가능 {len(comp)} ({len(comp)/len(sc)*100:.0f}%) "
      f"/ 보고서 검증완료 {len(ver)}\n")
print("등급 :", dict(Counter(s.grade.value for s in sc)))
print("전사 :", dict(Counter(p.transcription.value for s in sc for p in s.provenance)))
print("라우팅:", dict(Counter(s.physics_route.value for s in sc)))

print("\n-- LH2 탱크: 유일한 LH2 고유 데이터 --")
lh2v = resolve_frequency(Primitive.VESSEL, Service.LH2)
gh2v = resolve_frequency(Primitive.VESSEL, Service.GH2)
for b in BIN_LABELS:
    print(f"  {b:>6s}  LH2={lh2v.values[b]:.3e}  GH2={gh2v.values[b]:.3e}  "
          f"x{lh2v.values[b]/gh2v.values[b]:5.1f}")
print(f"  등급: {lh2v.provenance.grade.value} ({lh2v.fuel_used.value})")

print("\n-- 데이터 없는 표준 부품 --")
for p in sorted(NO_DATA, key=lambda x: x.value):
    r = resolve_frequency(p, Service.LH2)
    print(f"  {p.value:11s} -> {r.provenance.grade.value}")
print("  (그래서 VAPORIZER_UNIT / LOADING_ARM_UNIT 조립체로 우회)")

print("\n-- 물리 모델 레지스트리 (A: 원논문 구현) --")
for m in MODEL_REGISTRY.values():
    cc = f" | 대조: {m.cross_check_tool}" if m.cross_check_tool else ""
    print(f"  {m.status.value:12s} {m.key:28s} {m.primary_source[:42]}{cc}")

print("\n-- 위험 기여 상위 (빈도만) --")
for s in sorted(comp, key=lambda x: -x.frequency_per_year)[:5]:
    print(f"  {s.tag:20s} {s.bin_label:>6s} f={s.frequency_per_year:.2e} {s.grade.value}")
