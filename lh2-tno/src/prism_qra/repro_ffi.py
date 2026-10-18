import math, time
from slabx.core.plume import run_dispersion
from slabx.thermo.base import Substance
from slabx.thermo.coolprop import CoolPropThermo, coolprop_water
from slabx_lh2.trials.conditions import FFI, ffi_source
from slabx_lh2.diagnostics import applicability, critical_wind, rise_scaling
from slabx_lh2.lfl import flammable_distance
from slabx_lh2.plume_width import plume_width_coupling
from slabx_lh2.water_ice import with_sublimation

H2 = Substance(name="H2", mw=0.002016, cp_vapour=14300., cp_liquid=9800.,
               dh_vap=445000., T_boil=20.3, rho_liquid=70.8)

OBS = {1:(0,30), 3:(30,50), 4:(50,100), 5:(30,50), 6:(30,50), 7:(0,30)}

def run(trial, rh=75.0):
    src, atm, t = ffi_source(trial, H2, humidity_pct=rh)
    with plume_width_coupling():
        traj,_ = run_dispersion(src, atm, CoolPropThermo(H2, fluid="Hydrogen"),
                                with_sublimation(coolprop_water()),
                                x_max=300., n_puff_steps=40)
    d = flammable_distance(traj, atm, t_avg=t.averaging_window_s,
                           t_release=t.duration_s)
    return traj, atm, t, d

print("=== FFI 6시험 재현 (rh=75% 가정) ===")
print(f"{'T':>2} {'dir':>10} {'q':>6} {'u':>5} {'dur':>5} {'avg':>5} | "
      f"{'raw':>7} {'x1.25':>7} | {'관측':>9} {'판정':>6} | {'status':>6}")
res={}
t0=time.perf_counter()
for k in [1,3,4,5,6,7]:
    traj, atm, t, d = run(k)
    app = applicability(traj)
    lo,hi = OBS[k]
    v = d['factored']
    ok = "IN" if lo <= v <= hi else ("HIGH" if v>hi else "LOW")
    res[k]=(t,d,app)
    print(f"{k:2d} {t.orientation:>10} {t.rate_kg_s:6.3f} {t.wind_m_s:5.1f} "
          f"{t.duration_s:5.0f} {t.averaging_window_s:5.0f} | "
          f"{d['raw']:7.2f} {v:7.2f} | {lo:4.0f}-{hi:<4.0f} {ok:>6} | {app['status']:>6}")
print(f"\n  6회 {time.perf_counter()-t0:.1f}s")

print("\n=== T4 vs T6: 소스 거의 동일, 풍속만 다름 ===")
for k in [6,4]:
    t,d,app = res[k]
    lo,hi = OBS[k]
    print(f"  T{k}  u={t.wind_m_s:4.1f}  dur={t.duration_s:5.0f}s  "
          f"모델 {d['factored']:6.2f} m   관측 {lo}-{hi} m")
t6,d6,_ = res[6]; t4,d4,_ = res[4]
print(f"\n  관측 방향: u 2.7 -> 6.7 로 올라갈 때 거리 (30-50) -> (50-100)  증가")
print(f"  모델 방향: {d6['factored']:.1f} -> {d4['factored']:.1f}  "
      f"{'증가' if d4['factored']>d6['factored'] else '감소'}")

print("\n=== 습도 민감도 (T4/T6) ===")
for k in [4,6]:
    row=f"  T{k}: "
    for rh in [30., 50., 75., 95.]:
        _,_,_,d = run(k, rh)
        row += f"rh{rh:.0f}%->{d['factored']:6.2f}  "
    print(row)
