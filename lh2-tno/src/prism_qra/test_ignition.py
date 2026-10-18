import math
from ignition import *

print("=== 검증 1: Red Book 10.4 LPG 이벤트트리 ===")
PA, PB, PC, PD = 5.0e-7, 0.7, 0.7, 0.1
calc = {
    "Safe dispersal": PA*(1-PB)*(1-PC),
    "Flash Fire":     PA*(1-PB)*PC*(1-PD),
    "UVCE":           PA*(1-PB)*PC*PD,
    "BLEVE":          PA*PB,
}
book = {"Safe dispersal":4.5e-8, "Flash Fire":9.8e-8, "UVCE":1.05e-8, "BLEVE":3.5e-7}
for k in calc:
    d = abs(calc[k]-book[k])/book[k]
    print(f"  {k:16s} 계산 {calc[k]:.4e}  책 {book[k]:.4e}  "
          f"{'OK' if d<0.02 else f'차이 {d*100:.1f}%'}")
tot = sum(calc.values())
print(f"  합계 {tot:.4e} vs 개시빈도 {PA:.4e}  "
      f"{'닫힘 OK' if abs(tot-PA)/PA<1e-9 else 'X'}")
print(f"  (책 값 합계 {sum(book.values()):.4e} -> 닫히지 않음)")

print("\n=== 검증 2: 트리 닫힘 (모든 조합) ===")
n=0
for sch in IgnitionScheme:
    for rel in ReleaseType:
        for mag in [0.05, 5.0, 50.0, 500.0, 5000.0, 50000.0]:
            for pool in [False, True]:
                if rel is ReleaseType.INSTANTANEOUS and pool: continue
                r = build_ignition_tree(rel, mag, sch, forms_pool=pool)
                assert abs(sum(e.probability for e in r.events)-1.0) < 1e-9
                n += 1
print(f"  {n}개 조합 전부 sum(Pi)=1")

print("\n=== 두 체계 비교: LH2 이송배관 연속유출 ===")
print(f"{'q[kg/s]':>9} | {'PURPLE':^34} | {'HYRAM':^34}")
print(f"{'':>9} | {'제트':>8}{'플래시':>9}{'폭발':>8}{'무점화':>9} | "
      f"{'제트':>8}{'플래시':>9}{'폭발':>8}{'무점화':>9}")
for q in [0.0006, 0.06, 0.6, 6.08, 60.0]:
    row = f"{q:9.4f} |"
    for sch in [IgnitionScheme.PURPLE, IgnitionScheme.HYRAM]:
        r = build_ignition_tree(ReleaseType.CONTINUOUS, q, sch)
        row += (f"{r.by_outcome(Outcome.JET_FIRE):8.3f}"
                f"{r.by_outcome(Outcome.FLASH_FIRE):9.3f}"
                f"{r.by_outcome(Outcome.EXPLOSION):8.3f}"
                f"{r.by_outcome(Outcome.NO_IGNITION):9.3f} |")
    print(row)

print("\n=== 점화 총확률 ===")
for q in [0.06, 6.08]:
    a = build_ignition_tree(ReleaseType.CONTINUOUS, q, IgnitionScheme.PURPLE)
    b = build_ignition_tree(ReleaseType.CONTINUOUS, q, IgnitionScheme.HYRAM)
    print(f"  q={q:6.2f} kg/s  PURPLE {a.p_ignited:.3f}  HYRAM {b.p_ignited:.4f}"
          f"   -> 위험도 비 {a.p_ignited/b.p_ignited:6.1f}배")

print("\n=== Multi-Energy 과압 반경 (LH2 80 kg 전량 가연) ===")
E = 80.0 * 120e6   # H2 연소열 ~120 MJ/kg
for fo in [0.02, 0.08, 0.3]:
    r3, r1 = multi_energy_radii(E, fo)
    print(f"  f_obstr={fo:4.2f}  R(0.3bar)={r3:6.1f} m  R(0.1bar)={r1:6.1f} m")
print("  주의: 5.2.4는 이 등고선의 치사율을 폭굉에 적용 불가로 명시")
