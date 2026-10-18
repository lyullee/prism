from source_term import *

print("=== GH2 450 bar, 288 K ===")
print(f"{'d[mm]':>7} {'실기체[kg/s]':>13} {'이상기체':>11} {'오차':>7} {'Pt/P0':>7} {'Z0':>6}")
for d in [0.12e-3, 0.38e-3, 1.2e-3, 3.79e-3, 12e-3]:
    r = discharge(4.5e7, 288.15, "Hydrogen", d)
    qi = ideal_gas_choked(4.5e7, 288.15, d)
    print(f"{d*1000:7.2f} {r.rate_kg_s:13.4e} {qi:11.3e} "
          f"{(qi/r.rate_kg_s-1)*100:+6.1f}% {r.throat_pressure_pa/4.5e7:7.3f} {r.z_stagnation:6.3f}")

print("\n=== LH2 6 bar 포화액 (Tsat=28.1 K) ===")
print(f"{'d[mm]':>7} {'q[kg/s]':>11} {'G[kg/m2s]':>11} {'u[m/s]':>8} {'Pt[bar]':>8} {'목 건도':>8}")
for d in [0.5e-3, 1.58e-3, 5e-3, 15.8e-3, 50e-3]:
    r = discharge(6e5, None, "ParaHydrogen", d, saturated_liquid=True)
    print(f"{d*1000:7.2f} {r.rate_kg_s:11.4e} {r.mass_flux_kg_m2s:11.1f} "
          f"{r.velocity_m_s:8.1f} {r.throat_pressure_pa/1e5:8.2f} {r.throat_quality:8.4f}")

print("\n=== 방출량: LH2 이송배관 (인벤토리 80 kg, ESD 30 s) ===")
print(f"{'구간':>7} {'d[mm]':>7} {'q[kg/s]':>11} {'방출[kg]':>10} {'지속[s]':>8} {'제한요인':>10}")
for lab, d in [("0.01%",0.5e-3),("0.1%",1.58e-3),("1%",5e-3),("10%",15.8e-3),("100%",50e-3)]:
    r = discharge(6e5, None, "ParaHydrogen", d, saturated_liquid=True)
    rel = released_mass(r.rate_kg_s, 80.0, 30.0)
    print(f"{lab:>7} {d*1000:7.2f} {r.rate_kg_s:11.4e} {rel.released_kg:10.3f} "
          f"{rel.duration_s:8.2f} {rel.limited_by:>10}")

print("\n=== 방출량: LH2 저장탱크 (인벤토리 5000 kg, 격리 1800 s) ===")
for lab, d in [("0.01%",0.5e-3),("1%",5e-3),("100%",50e-3)]:
    r = discharge(6e5, None, "ParaHydrogen", d, saturated_liquid=True)
    rel = released_mass(r.rate_kg_s, 5000.0, 1800.0)
    print(f"{lab:>7} q={r.rate_kg_s:10.4e}  방출={rel.released_kg:9.2f} kg "
          f"({rel.fraction_of_inventory*100:5.1f}%)  {rel.limited_by}")
