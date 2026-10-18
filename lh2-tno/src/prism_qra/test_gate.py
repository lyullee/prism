import math
from gating import *
from taxonomy import *
from ignition import IgnitionScheme
import pipeline, legacy_physics_stub as phys

print("=== 1. 거부된 값은 읽을 수 없다 ===")
r = phys.lfl_distance(6.08, 1.5)
try:
    x = r.lfl_distance_m.value
    print("  X  값이 읽혔다 (게이트 실패)")
except RefusedError as e:
    print(f"  OK RefusedError: {str(e)[:72]}...")

print("\n=== 2. 수량별로 판정이 갈린다 ===")
for u in [1.5, 6.0]:
    r = phys.lfl_distance(6.08, u)
    print(f"  u={u} m/s (u_crit={r.u_crit_m_s:.2f})")
    for g in (r.lfl_distance_m, r.cloud_top_height_m):
        b = "경계값 있음" if g.has_bound else "경계값 없음"
        print(f"    {g.quantity:20s} {g.verdict.value:15s} {b}")

print("\n=== 3. 정책이 결정을 강제한다 ===")
g = phys.lfl_distance(6.08, 1.5)
print(f"  EXCLUDE  -> {g.lfl_distance_m.resolve(RefusePolicy.EXCLUDE)}")
print(f"  BOUND    -> {g.lfl_distance_m.resolve(RefusePolicy.BOUND):.2f} m")
try:
    g.cloud_top_height_m.resolve(RefusePolicy.BOUND)
except RefusedError as e:
    print(f"  BOUND(높이) -> 거부: {str(e)[62:130]}...")
try:
    g.lfl_distance_m.resolve(RefusePolicy.ESCALATE)
except RefusedError:
    print("  ESCALATE -> 예외 발생")

print("\n=== 4. 파이프라인: 커버리지 회계 ===")
site = Site(name="LH2",
    sections=[Section(id="TR", inventory_kg=80, isolation_time_s=30, service=Service.LH2)],
    components=[ComponentSpec(primitive=Primitive.VALVE, service=Service.LH2, count=4,
        tag="LV", nominal_diameter_m=0.05, pressure_pa=6e5, temperature_k=22,
        position=Position(x=0,y=0), section_id="TR")])

for u in [6.0, 3.0, 1.5]:
    wx = pipeline.rotterdam_like()
    for w in wx: w.wind_m_s = u
    print(f"\n  --- 풍속 {u} m/s ---")
    for pol in [RefusePolicy.EXCLUDE, RefusePolicy.BOUND]:
        res = pipeline.run(site, weather=wx, half_extent_m=100, cell_size_m=25,
                           ignition_scheme=IgnitionScheme.HYRAM, refuse_policy=pol)
        cv = res.coverage
        print(f"   {pol.value:8s} IR={res.max_ir:.3e}  등급={res.grade.value:22s}"
              f" 평가율={cv.evaluated_fraction*100:5.1f}%")
        if not cv.complete:
            print(f"            {cv.statement()[:96]}")

print("\n=== 5. 조용한 과소평가 방지 확인 ===")
wx = pipeline.rotterdam_like()
for w in wx: w.wind_m_s = 1.5
a = pipeline.run(site, weather=wx, half_extent_m=100, cell_size_m=25,
                 refuse_policy=RefusePolicy.EXCLUDE)
print(f"  전부 거부됨 -> IR = {a.max_ir:.3e}")
print(f"  하지만 결과가 스스로 신고: complete={a.coverage.complete}, "
      f"거부빈도={a.coverage.refused_frequency:.3e}/yr")
print(f"  -> {a.statement()[:110]}")
