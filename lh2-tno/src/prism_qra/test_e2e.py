import math, numpy as np
import damage as dmg
from damage import *
from taxonomy import *
from ignition import IgnitionScheme
import pipeline

print("=== (B) 피해모델 검증 ===")
print(f"  옷/건물 발화 임계 Q = {Q_IGNITION_W_M2/1e3:.2f} kW/m2  (책 35)")
print(f"  최대 노출시간 = {MAX_EXPOSURE_S:.0f} s")
pin, pout = population_fractions()
print(f"  인구분율(주야 혼합) 실내 {pin:.3f} / 실외 {pout:.3f}\n")

print("  복사열: IR 경로 vs SR 경로")
print(f"  {'Q[kW/m2]':>9} {'PE':>8} | {'IR FEin':>8}{'IR FEout':>9} | {'SR FEin':>8}{'SR FEout':>9}")
for qk in [5, 12.5, 25, 34.9, 35.4, 60]:
    a = heat_radiation(qk*1e3, 20, RiskRoute.INDIVIDUAL)
    b = heat_radiation(qk*1e3, 20, RiskRoute.SOCIETAL)
    print(f"  {qk:9.1f} {a.pe:8.4f} | {a.fe_in:8.4f}{a.fe_out:9.4f} | "
          f"{b.fe_in:8.4f}{b.fe_out:9.4f}")
print("  -> 35 kW/m2 경계에서 FEin 0->1 계단. 임계 아래 SR 실외는 0.14배")

print("\n  플래시화재 셀 피복분율 (6.2.6 note 1)")
for r in [0, 12, 25, 40, 60]:
    f = cell_coverage_fraction(30, 0, 25.0, r)
    print(f"    envelope R={r:3d} m -> 셀(30,0) 피복 {f:.3f} -> Pd {flash_fire(f).pe:.3f}")

print("\n  Fd = FEin*fpop_in + FEout*fpop_out  (6.13)")
d = heat_radiation(20e3, 20, RiskRoute.SOCIETAL)
print(f"    Q=20 kW/m2, SR: FEin={d.fe_in:.4f} FEout={d.fe_out:.4f} "
      f"-> Fd={d.fraction_of_deaths(pin,pout):.5f}")

print("\n=== (D) end-to-end 파이프라인 ===")
site = Site(
    name="LH2 station",
    sections=[
        Section(id="LH2_TR", inventory_kg=80, isolation_time_s=30, service=Service.LH2),
        Section(id="GH2_HP", inventory_kg=120, isolation_time_s=15, service=Service.GH2),
    ],
    components=[
        ComponentSpec(primitive=Primitive.VALVE, service=Service.LH2, count=4, tag="LV",
                      nominal_diameter_m=0.05, pressure_pa=6e5, temperature_k=22,
                      position=Position(x=0,y=0), section_id="LH2_TR"),
        ComponentSpec(primitive=Primitive.VALVE, service=Service.GH2, count=12, tag="HV",
                      nominal_diameter_m=0.012, pressure_pa=4.5e7, temperature_k=288,
                      position=Position(x=40,y=0), section_id="GH2_HP"),
    ],
)

res = pipeline.run(site, half_extent_m=150, cell_size_m=25,
                   ignition_scheme=IgnitionScheme.HYRAM,
                   population_per_cell=2.0)

print(f"  시나리오 {res.n_scenarios} / 계산 {res.n_computed} / 건너뜀 {res.n_skipped}")
print(f"  기여 항목 {len(res.contributions):,}건")
print(f"  최대 IR {res.max_ir:.3e} /yr")
print(f"  ★ 결과 등급: {res.grade.value}")
print(f"  premise 위반 알림 {len(res.notes)}건")
for n in res.notes[:2]:
    print(f"    - {n}")

print("\n  IR 격자 (중앙 7x7, 1e-9 단위)")
g = res.grid.values
c = len(res.grid.x)//2
for iy in range(c-3, c+4):
    print("   " + " ".join(f"{g[iy,ix]*1e9:7.2f}" for ix in range(c-3, c+4)))

print("\n  IR 등고선 존재 여부")
for lv in res.grid.contour_levels():
    n = int((g >= lv).sum())
    print(f"    {lv:.0e} : {n:4d} 셀 {'✓' if n else '-'}")

N, F = res.fn()
print(f"\n  FN 커브: {len(N)}점", end="")
if len(N): print(f", N_max={N.max():.1f}, F_max={F.max():.2e}/yr")
else: print()

print(f"\n  두 점화 체계 비교:")
for sch in IgnitionScheme:
    r = pipeline.run(site, half_extent_m=100, cell_size_m=25, ignition_scheme=sch)
    print(f"    {sch.value:7s} 최대 IR {r.max_ir:.3e} /yr")
