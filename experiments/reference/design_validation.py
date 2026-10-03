"""Design-time numerical reference for MIRAGE-Bio parameter construction.

This is not the production Gate 0 implementation.
This is not evidence that Gate 0 has passed.
The production Gate 0 must reproduce or supersede these checks using repository code.

Pure standard-library Python (no numpy), deterministic for a fixed seed.
It is a cleaned consolidation of the scratch calculations used to choose the
`scenario-v1` parameters documented in docs/mirage-bio/DESIGN.md and
docs/mirage-bio/GATE0_SPEC.md.

Usage:
    python3 experiments/reference/design_validation.py           # full (~1-3 min)
    python3 experiments/reference/design_validation.py --quick   # smaller samples
"""

from __future__ import annotations

import argparse
import math
import random
import statistics as st

# --------------------------------------------------------------------------
# scenario-v1 candidate parameters (keep in sync with DESIGN §5.8)
# --------------------------------------------------------------------------
V1 = dict(
    nu=8.0,                     # growth transition sharpness (Richards)
    n=8.0,                      # assay saturation sharpness
    s_range=(0.5, 2.0),         # log-uniform saturation scale S (ODeq)
    kappa=(0.80, 0.90),         # BIOLOGICAL_PLATEAU: K = kappa * S
    lam=(3.0, 5.0),             # MEASUREMENT_ARTIFACT: K = lambda * S
    r_range=(0.6, 0.9),         # growth rate (1/h)
    x0_range=(0.005, 0.02),     # log-uniform inoculum (ODeq)
    sig_abs=0.003,
    sig_rel=0.02,
    eps_lin=0.05,               # useful-region compression bound
    loq_mult=10.0,              # lower bound = 10 * sig_abs (= 0.03)
)
PASSIVE_T = list(range(19))     # 0..18 h
LATE_WINDOW = (12, 18)          # fixed, visible late-stage window (h)
DILUTION_GRID = [1, 2, 5, 10, 20, 50, 100]
TAU = 1.5
BP, MA = "BIOLOGICAL_PLATEAU", "MEASUREMENT_ARTIFACT"


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
def richards(t, k, r, x0, nu):
    inv = k ** -nu + (x0 ** -nu - k ** -nu) * math.exp(-nu * r * t)
    return inv ** (-1.0 / nu)


def resp(x, s, n):
    return 0.0 if x <= 0 else (x ** -n + s ** -n) ** (-1.0 / n)


def kprime(k, s, n):
    return (k ** -n + s ** -n) ** (-1.0 / n)


def x_lin(s, p):
    return s * ((1 - p["eps_lin"]) ** -p["n"] - 1) ** (1.0 / p["n"])


def y_loq(p):
    return p["loq_mult"] * p["sig_abs"]


def sigma(y, p):
    return p["sig_abs"] + p["sig_rel"] * y


def logu(rng, lo, hi):
    return math.exp(rng.uniform(math.log(lo), math.log(hi)))


def sample(rng, cond, p):
    """Nuisance parameters first (condition-independent), then K."""
    s = logu(rng, *p["s_range"])
    r = rng.uniform(*p["r_range"])
    x0 = logu(rng, *p["x0_range"])
    u = rng.random()
    lo, hi = p["kappa"] if cond == BP else p["lam"]
    ratio = lo + u * (hi - lo)
    return dict(cond=cond, s=s, r=r, x0=x0, u=u, ratio=ratio, k=ratio * s)


def latent(e, t, p):
    return richards(t, e["k"], e["r"], e["x0"], p["nu"])


def read(rng, x, s, p):
    mu = resp(x, s, p["n"])
    return round(mu + rng.gauss(0.0, sigma(mu, p)), 4)


def t_q(e, p, q=0.95):
    """Time the noise-free observed curve reaches q*K' (exact when nu == n)."""
    nu = p["nu"]
    kp = kprime(e["k"], e["s"], p["n"])
    y0 = resp(e["x0"], e["s"], p["n"])
    return math.log((y0 ** -nu - kp ** -nu) / ((q * kp) ** -nu - kp ** -nu)) / (nu * e["r"])


def passive(rng, e, p):
    return [read(rng, latent(e, t, p), e["s"], p) for t in PASSIVE_T]


def diluted_estimate(rng, e, p, t=18, d=10.0, reps=3):
    x = latent(e, t, p)
    return d * st.mean(read(rng, x / d, e["s"], p) for _ in range(reps))


def in_useful_region(e, p, t, d):
    xp = latent(e, t, p) / d
    return xp <= x_lin(e["s"], p) and resp(xp, e["s"], p["n"]) >= y_loq(p)


def valid_control(e, p, t, d):
    return LATE_WINDOW[0] <= t <= LATE_WINDOW[1] and d > 1 and in_useful_region(e, p, t, d)


# --------------------------------------------------------------------------
# statistics helpers
# --------------------------------------------------------------------------
def auroc(neg, pos):
    """Mann-Whitney AUROC that `pos` scores exceed `neg` scores (ties = 0.5)."""
    allv = sorted([(v, 0) for v in neg] + [(v, 1) for v in pos])
    ranks, i = [0.0] * len(allv), 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    r_pos = sum(rk for rk, (_, lab) in zip(ranks, allv) if lab == 1)
    n1, n0 = len(pos), len(neg)
    return (r_pos - n1 * (n1 + 1) / 2) / (n1 * n0)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def tv_ceiling(rng, p, m):
    """Bayes accuracy given exact log K' (noise-free passive limit)."""
    def lk(c):
        e = sample(rng, c, p)
        return math.log(kprime(e["k"], e["s"], p["n"]))
    la = [lk(BP) for _ in range(m)]
    lb = [lk(MA) for _ in range(m)]
    lo, hi = min(la + lb), max(la + lb)
    nb = 200
    w = (hi - lo) / nb or 1.0
    ha, hb = [0] * nb, [0] * nb
    for v in la:
        ha[min(nb - 1, int((v - lo) / w))] += 1
    for v in lb:
        hb[min(nb - 1, int((v - lo) / w))] += 1
    tv = 0.5 * sum(abs(a - b) for a, b in zip(ha, hb)) / m
    return 0.5 + 0.5 * tv, (la, lb, lo, w, ha, hb)


def knn_accuracy(rng, p, n_per, k=15):
    """Model-free 15-NN on log full passive trajectories (balanced)."""
    def lt(ys):
        return [math.log(max(1e-3, y)) for y in ys]
    train = [(lt(passive(rng, sample(rng, c, p), p)), c) for c in (BP, MA) for _ in range(n_per)]
    test = [(lt(passive(rng, sample(rng, c, p), p)), c) for c in (BP, MA) for _ in range(n_per)]
    correct = 0
    for q, c in test:
        nn = sorted((sum((a - b) ** 2 for a, b in zip(q, x)), cc) for x, cc in train)[:k]
        pred = BP if sum(cc == BP for _, cc in nn) > k / 2 else MA
        correct += pred == c
    return correct / len(test)


def good_scientist(rng, e, p):
    ys = passive(rng, e, p)
    p_hat = st.mean(ys[-4:])                    # t = 15..18
    c_hat = diluted_estimate(rng, e, p, 18, 10.0, 3)
    return c_hat / p_hat, c_hat, (MA if c_hat / p_hat >= TAU else BP)


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def matched_twin(e, p):
    """Other-condition world with the same r, X0, K-quantile and the same K'."""
    other = MA if e["cond"] == BP else BP
    lo, hi = p["kappa"] if other == BP else p["lam"]
    ratio = lo + e["u"] * (hi - lo)
    target = kprime(e["k"], e["s"], p["n"])
    c = ratio * (1 + ratio ** p["n"]) ** (-1 / p["n"])   # K'/S for that ratio
    s2 = target / c
    return dict(cond=other, s=s2, r=e["r"], x0=e["x0"], u=e["u"], ratio=ratio, k=ratio * s2)


def diagnosticity(e, twin, p, t, d, reps):
    """Single-outcome AUROC between world and matched twin (Gaussian approx)."""
    mu1 = resp(latent(e, t, p) / d, e["s"], p["n"])
    mu2 = resp(latent(twin, t, p) / d, twin["s"], p["n"])
    sd = math.sqrt((sigma(mu1, p) ** 2 + sigma(mu2, p) ** 2) / reps)
    return phi(abs(mu1 - mu2) / sd)


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def main(quick: bool) -> None:
    rng = random.Random(20261004)
    p = dict(V1)
    n_big, n_mid, n_knn, n_rob = (4000, 1000, 250, 150) if quick else (20000, 5000, 500, 300)
    print(f"MIRAGE-Bio design-time reference ({'quick' if quick else 'full'})  seed=20261004")
    print(f"x_lin/S = {x_lin(1.0, p):.4f}; reading at x_lin = {resp(x_lin(1.0, p), 1.0, p['n']):.4f} S;"
          f" lower useful bound = {y_loq(p):.3f} (= {p['loq_mult']:.0f} x sigma_abs;"
          f" per-replicate rel. SD there = {sigma(y_loq(p), p) / y_loq(p):.3f})")

    # C1 passive-family equivalence
    maxerr = 0.0
    for _ in range(500):
        for c in (BP, MA):
            e = sample(rng, c, p)
            kp, y0 = kprime(e["k"], e["s"], p["n"]), resp(e["x0"], e["s"], p["n"])
            for i in range(73):
                t = 0.25 * i
                a = resp(latent(e, t, p), e["s"], p["n"])
                b = richards(t, kp, e["r"], y0, p["nu"])
                maxerr = max(maxerr, abs(a - b) / b)
    print(f"[C1 equivalence] max rel. deviation f(X(t)) vs Richards(K',y0,r,nu): {maxerr:.1e}")

    # C2 Condition A trustworthiness
    comp = [1 - resp(e["k"], e["s"], p["n"]) / e["k"] for e in (sample(rng, BP, p) for _ in range(n_big))]
    print(f"[C2 BP compression at K] min {min(comp):.4f} max {max(comp):.4f} -> K/K' max {1 / (1 - max(comp)):.4f}")

    # C3 analytic passive ceiling + S-range sensitivity
    ceil, (la, lb, lo, w, ha, hb) = tv_ceiling(rng, p, 10 * n_big)
    print(f"[C3 passive ceiling] Bayes accuracy given exact K' = {ceil:.3f}")
    for sr in [(1.0, 1.0 + 1e-9), (0.8, 1.25), (0.6, 1.5), (0.5, 2.0), (0.4, 2.5)]:
        q = dict(p, s_range=sr)
        print(f"    S range {sr[0]:.1f}-{sr[1]:.2f}: ceiling {tv_ceiling(rng, q, 10 * n_big)[0]:.3f}")

    # C4 timing and fixed late window
    t95s, late_ratio_12, late_ratio_t95 = [], [], []
    for _ in range(n_big):
        for c in (BP, MA):
            e = sample(rng, c, p)
            t95 = t_q(e, p)
            t95s.append(t95)
            if c == MA:
                kp = kprime(e["k"], e["s"], p["n"])
                late_ratio_12.append(latent(e, LATE_WINDOW[0], p) / kp)
                late_ratio_t95.append(latent(e, t95 + 2, p) / kp)
    print(f"[C4 timing] t95 in [{min(t95s):.2f}, {max(t95s):.2f}] h; max t95+2 = {max(t95s) + 2:.2f} h"
          f" (window starts {LATE_WINDOW[0]} h)")
    print(f"    MA: min X(12 h)/K' = {min(late_ratio_12):.3f}; min X(t95+2)/K' = {min(late_ratio_t95):.3f}")

    # C5/C6 GoodScientist reference protocol (t=18, d=10, 3 reps)
    res = {BP: [], MA: []}
    for c in (BP, MA):
        for _ in range(n_mid):
            e = sample(rng, c, p)
            res[c].append((good_scientist(rng, e, p), e))
    r_bp = [g[0] for g, _ in res[BP]]
    r_ma = [g[0] for g, _ in res[MA]]
    acc = (sum(g[2] == BP for g, _ in res[BP]) + sum(g[2] == MA for g, _ in res[MA])) / (2 * n_mid)
    valid = sum(valid_control(e, p, 18, 10.0) for c in (BP, MA) for _, e in res[c]) / (2 * n_mid)
    print(f"[C5 GoodScientist] R_BP median {st.median(r_bp):.3f} p99 {pct(r_bp, .99):.3f} max {max(r_bp):.3f};"
          f" R_MA min {min(r_ma):.3f} p1 {pct(r_ma, .01):.3f} median {st.median(r_ma):.3f}")
    print(f"    accuracy {acc:.4f}; valid-control rate {valid:.4f}")
    cbp = [g[1] / e["k"] for g, e in res[BP]]
    cma = [g[1] / e["k"] for g, e in res[MA]]
    print(f"[C6 reconstruction] BP C/K 95% [{pct(cbp, .025):.3f}, {pct(cbp, .975):.3f}];"
          f" MA C/K 95% [{pct(cma, .025):.3f}, {pct(cma, .975):.3f}]")
    print(f"    BP |R-1|<=0.15: {sum(abs(x - 1) <= .15 for x in r_bp) / n_mid:.3f};"
          f" MA R>=2.5: {sum(x >= 2.5 for x in r_ma) / n_mid:.3f}")

    # C7/C8 intervention sweep at t = 18 h, 3 replicates
    print("[C8 intervention sweep] t=18 h, 3 replicates; R = d*mean(y)/P_hat")
    print("     d | BP C/K median [95%]   | MA C/K median [95%]   | BP valid | MA valid | AUROC(R) | tau-rule bal.acc")
    for d in DILUTION_GRID:
        rows = {BP: [], MA: []}
        for c in (BP, MA):
            for _ in range(n_mid // 2):
                e = sample(rng, c, p)
                ys = passive(rng, e, p)
                c_hat = diluted_estimate(rng, e, p, 18, float(d), 3)
                rows[c].append((c_hat / e["k"], c_hat / st.mean(ys[-4:]), valid_control(e, p, 18, float(d))))
        ck = {c: [x[0] for x in rows[c]] for c in rows}
        rr = {c: [x[1] for x in rows[c]] for c in rows}
        vf = {c: sum(x[2] for x in rows[c]) / len(rows[c]) for c in rows}
        bal = 0.5 * (sum(x < TAU for x in rr[BP]) / len(rr[BP]) + sum(x >= TAU for x in rr[MA]) / len(rr[MA]))
        print(f"   {d:>3} | {st.median(ck[BP]):.3f} [{pct(ck[BP], .025):.3f},{pct(ck[BP], .975):.3f}]"
              f" | {st.median(ck[MA]):.3f} [{pct(ck[MA], .025):.3f},{pct(ck[MA], .975):.3f}]"
              f" | {vf[BP]:.3f}    | {vf[MA]:.3f}    | {auroc(rr[BP], rr[MA]):.4f}   | {bal:.4f}")

    # C7 inadequate interventions: undiluted late, early diluted (AUROC of R)
    for label, (t_s, d_s) in (("undiluted late (t=18, d=1)", (18, 1.0)), ("early diluted (t=3, d=10)", (3, 10.0))):
        rr = {BP: [], MA: []}
        for c in (BP, MA):
            for _ in range(n_mid // 2):
                e = sample(rng, c, p)
                ys = passive(rng, e, p)
                rr[c].append(diluted_estimate(rng, e, p, t_s, d_s, 3) / st.mean(ys[-4:]))
        print(f"[C7 inadequate] {label}: AUROC(R) = {auroc(rr[BP], rr[MA]):.3f}")

    # C9 empirical passive classifiers
    def plateau_clf(ys):
        v = math.log(max(1e-6, st.mean(ys[-6:])))            # t = 13..18
        i = min(len(ha) - 1, max(0, int((v - lo) / w)))
        return BP if ha[i] > hb[i] else MA
    test = [(passive(rng, sample(rng, c, p), p), c) for c in (BP, MA) for _ in range(n_mid // 2)]
    acc_plug = sum(plateau_clf(y) == c for y, c in test) / len(test)
    print(f"[C9 passive classifiers] plug-in plateau classifier {acc_plug:.3f};"
          f" 15-NN full trajectory {knn_accuracy(rng, p, n_knn):.3f}")

    # C10 robustness neighbourhood (15-NN passive accuracy, BP max compression, GS accuracy)
    print("[C10 robustness] variant: 15-NN passive acc | BP max compression | GoodScientist acc")
    variants = [("nu=6", dict(nu=6.0)), ("nu=7", dict(nu=7.0)), ("nu=9", dict(nu=9.0)), ("nu=10", dict(nu=10.0)),
                ("noise x0.5", dict(sig_abs=0.0015, sig_rel=0.01)), ("noise x2", dict(sig_abs=0.006, sig_rel=0.04)),
                ("r x0.8", dict(r_range=(0.48, 0.72))), ("r x1.2", dict(r_range=(0.72, 1.08))),
                ("X0 /2", dict(x0_range=(0.0025, 0.01))), ("X0 x2", dict(x0_range=(0.01, 0.04))),
                ("S 0.6-1.5", dict(s_range=(0.6, 1.5))),
                ("n=7 (nu=8)", dict(n=7.0)), ("n=10 (nu=8)", dict(n=10.0))]
    for name, delta in variants:
        q = dict(p, **delta)
        kn = knn_accuracy(rng, q, n_rob)
        cm = max(1 - resp(e["k"], e["s"], q["n"]) / e["k"] for e in (sample(rng, BP, q) for _ in range(2000)))
        ga = (sum(good_scientist(rng, sample(rng, BP, q), q)[2] == BP for _ in range(n_rob))
              + sum(good_scientist(rng, sample(rng, MA, q), q)[2] == MA for _ in range(n_rob))) / (2 * n_rob)
        print(f"    {name:<11}: {kn:.3f} | {cm:.4f} | {ga:.3f}")

    # C11 logistic counterexample
    print(f"[C11 logistic growth nu=1 with assay n=8] 15-NN passive acc {knn_accuracy(rng, dict(p, nu=1.0), n_rob):.3f}")

    # C12 matched demo pair and matched-twin diagnosticity
    b = dict(cond=MA, s=1.0, r=0.75, x0=0.01, u=0.5, ratio=4.0, k=4.0)
    a = matched_twin(b, p)
    mx = max(abs(resp(latent(a, i / 10, p), a["s"], p["n"]) - resp(latent(b, i / 10, p), b["s"], p["n"]))
             for i in range(181))
    print(f"[C12 demo pair] BP: S={a['s']:.4f} K={a['k']:.4f} | MA: S={b['s']} K={b['k']};"
          f" max passive difference {mx:.1e}; t95 = {t_q(b, p):.2f} h")
    for w_ in (a, b):
        x = latent(w_, 18, p)
        print(f"    {w_['cond']:<20} raw {resp(x, w_['s'], p['n']):.3f} | d=2 -> {2 * resp(x / 2, w_['s'], p['n']):.3f}"
              f" | d=10 -> {10 * resp(x / 10, w_['s'], p['n']):.3f}")
    print("    matched-twin diagnosticity D(a) (single outcome, 3 reps) at t=18 h vs d:",
          ", ".join(f"d={d}: {diagnosticity(b, a, p, 18, d, 3):.3f}" for d in DILUTION_GRID))
    print("    D(a) at d=10 vs t:", ", ".join(f"t={t}: {diagnosticity(b, a, p, t, 10, 3):.3f}" for t in (2, 4, 6, 8, 12, 18)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="smaller samples")
    main(ap.parse_args().quick)
