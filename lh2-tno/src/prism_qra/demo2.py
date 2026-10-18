from collections import Counter
from taxonomy import *

site = Site(
    name="LH2 receiving station (demo)",
    sections=[
        Section(id="LH2_TANK",     inventory_kg=5000, isolation_time_s=1800, service=Service.LH2),
        Section(id="LH2_TRANSFER", inventory_kg=  80, isolation_time_s=  30, service=Service.LH2),
        Section(id="GH2_HP",       inventory_kg= 120, isolation_time_s=  15, service=Service.GH2),
    ],
    components=[
        ComponentSpec(primitive=Primitive.VESSEL, service=Service.LH2, tag="TK-101",
                      nominal_diameter_m=0.05, pressure_pa=6e5, temperature_k=22,
                      position=Position(x=0, y=0), section_id="LH2_TANK"),
        ComponentSpec(primitive=Primitive.PIPE, service=Service.GH2, count=8, tag="HP-301",
                      nominal_diameter_m=0.012, pressure_pa=4.5e7, temperature_k=288,
                      position=Position(x=30, y=5), section_id="GH2_HP"),
        ComponentSpec(primitive=Primitive.VALVE, service=Service.GH2, count=12, tag="HP-V",
                      nominal_diameter_m=0.012, pressure_pa=4.5e7, temperature_k=288,
                      position=Position(x=30, y=5), section_id="GH2_HP"),
    ],
    assemblies=[
        AssemblySpec(assembly=Assembly.VJ_LINE, service=Service.LH2, tag="LP-201", count=3,
                     nominal_diameter_m=0.05, pressure_pa=6e5, temperature_k=22,
                     position=Position(x=12, y=0), section_id="LH2_TRANSFER"),
        AssemblySpec(assembly=Assembly.LH2_PUMP, service=Service.LH2, tag="P-401",
                     nominal_diameter_m=0.04, pressure_pa=8e5, temperature_k=22,
                     position=Position(x=18, y=2), section_id="LH2_TRANSFER"),
        AssemblySpec(assembly=Assembly.VAPORIZER, service=Service.COLD_GH2, tag="VAP-501",
                     nominal_diameter_m=0.025, pressure_pa=3e7, temperature_k=150,
                     position=Position(x=24, y=2), section_id="GH2_HP"),
    ],
)

sc = enumerate_scenarios(site)
comp = [s for s in sc if s.computable]
print(f"시나리오 {len(sc)}건, 계산가능 {len(comp)}건 "
      f"({len(comp)/len(sc)*100:.0f}%)   [rev1: 10건 / 15%]\n")

print("등급 분포 :", dict(Counter(s.grade.value for s in sc)))
print("대리 출처 :", dict(Counter(
    (s.frequency_fuel_proxy.value if s.frequency_fuel_proxy else "none") for s in sc)))
print("라우팅    :", dict(Counter(s.physics_route.value for s in sc)))

print("\n-- 대리 체인 동작 확인 --")
for prim, svc in [(Primitive.VALVE, Service.GH2),
                  (Primitive.VALVE, Service.LH2),
                  (Primitive.PUMP_SEAL, Service.LH2),
                  (Primitive.HX_TUBE, Service.COLD_GH2)]:
    r = resolve_frequency(prim, svc)
    fu = r.fuel_used.value if r.fuel_used else "-"
    v = r.values["1%"]
    print(f"  {prim.value:11s} @ {svc.value:9s} -> {fu:6s} "
          f"{r.provenance.grade.value:22s} f(1%)={v:.2e}  cf={r.conservatism:g}")

print("\n-- VJ 라인: 봉쇄 경로가 빈도를 낮춤 --")
for s in sc:
    if s.tag.startswith("LP-201") and s.bin_label == "100%":
        print(f"  {s.tag:18s} {s.release_path.value:11s} f={s.frequency_per_year:.2e}/yr")

print("\n-- 위험 기여 상위 (빈도만, 영향 미반영) --")
for s in sorted(comp, key=lambda x: -x.frequency_per_year)[:6]:
    print(f"  {s.tag:18s} {s.bin_label:>6s} d={s.hole_diameter_m*1000:6.2f}mm "
          f"f={s.frequency_per_year:.2e}  {s.grade.value}")

print("\n-- 여전히 막힌 것 --")
for s in sc:
    if not s.computable:
        why = ("물리 라우팅 없음 (COLD_GH2)" if s.physics_route is PhysicsRoute.UNCOVERED
               else "빈도 없음")
        print(f"  {s.tag:22s} {s.bin_label:>6s}  {why}")
        break
blocked = Counter(s.tag for s in sc if not s.computable)
print("  차단 태그:", dict(blocked))
