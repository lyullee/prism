"""Purple Book Appendix 6.B reproduction."""
import math
from risk import *

# ---- Given by the book -------------------------------------------------
f_S      = 5e-7            # pipe rupture, /yr
q        = 100.0           # kg/s CO, continuous
R        = 361.0           # m, source (0,0) -> grid point (200,300)
C_axis   = 21300.0         # mg/m3  <- from the book's Gaussian plume step
t_exp    = 30.0            # min
nws      = 12

wx = WeatherSector("D 5.0", (196.0, 225.0), p_day=0.0376, p_night=0.0362)

def chk(name, got, want, tol):
    ok = abs(got-want) <= tol*max(abs(want),1e-30)
    print(f"  {'OK ' if ok else 'X  '} {name:34s} {got:>12.4g}  (book {want:g})")
    return ok

print("Purple Book Appendix 6.B")
print(f"  R = {math.hypot(200,300):.0f} m\n")
all_ok = []

# 3. weather
all_ok.append(chk("PM x Pphi", wx.pm_pphi, 0.0368, 2e-3))

# 4.1 distance
all_ok.append(chk("distance R [m]", math.hypot(200,300), 361, 2e-3))

# 4.3 probit on the centre line
pr = CO_PROBIT.probit(C_axis, t_exp)
all_ok.append(chk("probit Pr", pr, 5.97, 2e-3))
Pcl = probit_to_probability(pr)
all_ok.append(chk("Pcl", Pcl, 0.835, 3e-3))

# 5. probability integral -> effective cloud width
#    sigma_y is not printed in the book; back it out from PI = 72 m,
#    then confirm the forward calculation returns 72 m.
lo, hi = 1.0, 500.0
for _ in range(200):
    mid = 0.5*(lo+hi)
    (lo, hi) = (mid, hi) if gaussian_lateral_pi(pr, mid) < 72.0 else (lo, mid)
sigma_y = 0.5*(lo+hi)
PI = gaussian_lateral_pi(pr, sigma_y)
print(f"      implied sigma_y = {sigma_y:.2f} m  "
      f"(1% lethality half-width {sigma_y*math.sqrt(2*(pr-PR_1PCT)):.1f} m)")
all_ok.append(chk("PI [m]", PI, 72.0, 1e-3))

ECW = effective_cloud_width(PI, Pcl)
print(f"      ECW = {ECW:.2f} m")

# 5.1 - 5.2
Pci = probability_covered(ECW, R, nws)
Pd  = Pcl * Pci
all_ok.append(chk("Pci", Pci, 0.456, 1.5e-2))
all_ok.append(chk("Pd", Pd, 0.381, 1e-2))

# 6. contribution
c = RiskContribution(loc_id="pipe rupture", weather_class="D 5.0",
                     sector_deg=(196,225), ignition_event=None,
                     pm_pphi=wx.pm_pphi, p_ignition=1.0, p_death=Pd,
                     frequency_per_year=f_S, route=PdRoute.TOXIC)
all_ok.append(chk("delta IR [1/yr]", c.delta_ir, 7.0e-9, 1.5e-2))

# 7. other sectors contribute zero here
print(f"\n  total IR over 12 sectors x 6 classes = "
      f"{total_individual_risk([c]):.3g} /yr  (only this combination is non-zero)")

print(f"\n{'ALL CHECKS PASSED' if all(all_ok) else 'FAILURES PRESENT'}"
      f"  ({sum(all_ok)}/{len(all_ok)})")

# ---- FN curve smoke test ----------------------------------------------
print("\nFN curve mechanics:")
outs = [SocietalOutcome(1e-6, 2.0), SocietalOutcome(3e-7, 15.0),
        SocietalOutcome(5e-8, 60.0), SocietalOutcome(2e-6, 0.4)]
N, F = fn_curve(outs)
for n, f in zip(N, F):
    lim = dutch_sr_limit(n)
    print(f"   N>={n:5.1f}  F={f:.2e}/yr   limit={lim:.2e}"
          f"   {'초과' if n>=10 and f>lim else 'ok'}")
