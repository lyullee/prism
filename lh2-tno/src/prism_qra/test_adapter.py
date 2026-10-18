import time
import slabx_adapter as sx
from gating import RefusePolicy, RefusedError

print("=== 사전선별 vs applicability 불일치 ===")
print(f"{'q':>7}{'u':>6}{'u_crit':>8}  {'선별':>6} {'status':>10} {'ratio':>9}  {'거리[m]':>9}")
cases = [(0.83, 6.7), (0.83, 2.7), (6.08, 1.5), (6.08, 6.0),
         (0.06, 1.0), (0.06, 6.0)]
t0 = time.perf_counter()
for q, u in cases:
    r = sx.dispersion(q, u)
    worth, uc, _ = sx.prescreen(q, u)
    d = "REFUSE" if r.lfl_distance_m.refused else f"{r.lfl_distance_m.value:9.2f}"
    ucs = f"{uc:8.2f}" if uc else "   range"
    mark = " <<<" if r.prescreen_disagrees else ""
    print(f"{q:7.2f}{u:6.1f}{ucs}  {'통과' if worth else '거부':>6} "
          f"{r.status:>10} {r.premise_ratio:9.4f}  {d}{mark}")
dt = time.perf_counter()-t0
print(f"\n  {len(cases)}회 {dt:.1f}s -> 호출당 {dt/len(cases)*1000:.0f} ms")
print("  <<< = 사전선별은 거부했으나 applicability는 수용")

print("\n=== 수량별 판정 ===")
r = sx.dispersion(6.08, 1.5)
for g in (r.lfl_distance_m, r.flammable_mass_kg, r.footprint_area_m2,
          r.cloud_top_height_m):
    v = "REFUSE" if g.refused else f"{g._value:.3g}"
    print(f"  {g.quantity:20s} {g.verdict.value:15s} {v:>10}")
    if g.refused: print(f"      -> {g.reason[:74]}")
    elif g.flags: print(f"      [{'; '.join(g.flags)[:74]}]")

print("\n=== 풍속 의존성 (q=0.83 kg/s) ===")
for u in [1.5, 2.7, 4.0, 6.7, 10.0]:
    r = sx.dispersion(0.83, u)
    d = "REFUSE" if r.lfl_distance_m.refused else f"{r.lfl_distance_m.value:7.2f}"
    print(f"  u={u:5.1f}  {r.status:>8}  ratio={r.premise_ratio:7.4f}  "
          f"거리 {d}  면적 {r.footprint_area_m2._value:7.1f} m2")
