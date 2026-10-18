"""Cross-check (path D): run HyRAM as a black box, never read its source."""
import math, warnings
warnings.filterwarnings("ignore")
import fire as F
from source_term import discharge
from hyram.phys import api

def mine(P0, T0, d):
    r = discharge(P0, T0, "Hydrogen", d)
    rho_t = r.mass_flux_kg_m2s / max(r.velocity_m_s, 1e-9)
    nz = F.notional_nozzle(r.rate_kg_s, r.throat_pressure_pa, r.velocity_m_s,
                           rho_t, d)
    fl = F.flame_length(r.rate_kg_s, nz)
    return r, nz, fl

def theirs(P0, T0, d):
    fluid = api.Fluid(species="hydrogen", T=T0, P=P0)
    amb = api.Fluid(species="air", T=288.15, P=101325.)
    orif = api.Orifice(d)
    fl = api.Flame(fluid, orif, amb, nn_conserve_momentum=True,
                   nn_T='solve_energy', verbose=False)
    fl.solve()
    return fl

print(f"{'d[mm]':>7}{'P[bar]':>8} | {'q[kg/s]':>10}{'q_hy':>10} | "
      f"{'Lf(mine)':>10}{'Lf(hyram)':>11}{'비':>7} | {'Fr':>9} {'regime':>9}")
for d_mm, P in [(3.0, 1.0e7), (6.0, 3.5e7), (12.0, 4.5e7), (25.0, 7.0e7)]:
    d = d_mm/1000.
    r, nz, fl = mine(P, 288.15, d)
    try:
        hf = theirs(P, 288.15, d)
        mf = getattr(hf, 'mass_flow_rate', None)
        q_hy = float(mf() if callable(mf) else mf) if mf is not None else float('nan')
        L_hy = float(hf.length() if callable(hf.length) else hf.length)
    except Exception as e:
        q_hy, L_hy = float('nan'), float('nan')
        print("  hyram:", type(e).__name__, str(e)[:60])
    ratio = fl.length_m/L_hy if L_hy==L_hy and L_hy>0 else float('nan')
    print(f"{d_mm:7.1f}{P/1e5:8.0f} | {r.rate_kg_s:10.4f}{q_hy:10.4f} | "
          f"{fl.length_m:10.2f}{L_hy:11.2f}{ratio:7.2f} | {fl.froude:9.3g} {fl.regime:>9}")

print("\n--- 복사열: 35 kW/m2 도달거리 ---")
for d_mm, P in [(6.0, 3.5e7), (12.0, 4.5e7)]:
    d = d_mm/1000.
    r, nz, fl = mine(P, 288.15, d)
    dist = F.distance_to_flux(fl, 35e3)
    d125 = F.distance_to_flux(fl, 12.5e3)
    print(f"  d={d_mm}mm P={P/1e5:.0f}bar  Lf={fl.length_m:6.2f} m  "
          f"Q_rad={fl.radiant_power_w/1e6:6.2f} MW  "
          f"35kW/m2 @ {dist if dist is None else round(dist,1)} m  "
          f"12.5kW/m2 @ {d125 if d125 is None else round(d125,1)} m")
