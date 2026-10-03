"""Gate 0 scientific validation (GATE0_SPEC). Blocking checks first, then summary.json, then plots.

Usage: python scripts/gate0.py [--quick] [--out DIR] [--no-plots]

Exit status is non-zero if any blocking check fails. ``--quick`` runs reduced sizes for
tests (T-029/T-030) and is marked ``"mode": "quick"``; it must never be used to claim a pass.
matplotlib is imported only by the plotting step (``gate0_plots``), after summary.json exists.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

import mirage
from mirage.biology.conditions import Condition
from mirage.config import ScenarioPrior, canonical_sha256, load_prior, sample_episode
from mirage.evaluation.passive import build_reference

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "experiments" / "configs" / "scenario_v1.json"
DEFAULT_OUT = ROOT / "experiments" / "results" / "gate0"

BP, MA = Condition.BIOLOGICAL_PLATEAU, Condition.MEASUREMENT_ARTIFACT
TAU = 1.5
REF_T, REF_D, REF_REPS = 18, 10.0, 3
SWEEP_D = [1, 2, 5, 10, 20, 50, 100]
G0H_GRID = [1.1, 1.25, 1.5, 2, 3, 5, 10, 20, 50, 100]
G0H_AUROC = 0.95
WILSON_Z = 1.959963984540054

SEEDS = {
    "test": [900000, 900999],
    "knn_train": [901000, 901999],
    "scans": [902000, 911999],
    "sweep": [900000, 900499],
    "robustness": [920000, 929999],
    "passive_reference": [1000000, 1199999],
}
FULL = dict(test=1000, knn_train=1000, scans=10000, sweep=500, robustness=300,
            passive_reference=200000, ceiling=200000, same_seed=10000, stability=100,
            equivalence=1000)
QUICK = dict(test=200, knn_train=200, scans=2000, sweep=100, robustness=40,
             passive_reference=20000, ceiling=20000, same_seed=1000, stability=20,
             equivalence=100)
PLOTS = ["assay_response.png", "passive_overlap.png", "latent_reveal.png",
         "intervention_sweep.png", "separability_before_after.png", "robustness_map.png"]


# ---- vectorised model (identical formulas to mirage.biology / mirage.assay) -------------

def latent(t: NDArray, k: NDArray, r: NDArray, x0: NDArray, nu: float) -> NDArray:
    """Richards X(t) in ODeq for worlds (rows) x times (columns), DESIGN §5.2."""
    t = np.asarray(t, dtype=np.float64)[None, :]
    k, r, x0 = (np.asarray(v, dtype=np.float64)[:, None] for v in (k, r, x0))
    return (k**-nu + (x0**-nu - k**-nu) * np.exp(-nu * r * t)) ** (-1.0 / nu)


def resp(x: NDArray, s: NDArray, n: float) -> NDArray:
    """Noise-free reading f(x) in ODeq, DESIGN §5.3."""
    return x * (1.0 + (x / s) ** n) ** (-1.0 / n)


def kprime(k: NDArray, s: NDArray, n: float) -> NDArray:
    return (k**-n + s**-n) ** (-1.0 / n)


def noisy(mu: NDArray, z: NDArray, prior: ScenarioPrior) -> NDArray:
    """y = round_4(mu + (sigma_abs + sigma_rel mu) z), DESIGN §5.6."""
    return np.round(mu + (prior.sigma_abs + prior.sigma_rel * mu) * z, 4)


def seed_range(name: str, size: int) -> list[int]:
    lo, hi = SEEDS[name]
    if size > hi - lo + 1:
        raise ValueError(f"{name}: {size} seeds requested, block has {hi - lo + 1}")
    return list(range(lo, lo + size))


def worlds(prior: ScenarioPrior, seeds: list[int], cond: Condition) -> dict[str, NDArray]:
    """Hidden parameters and the episode's own noise streams, as LabEnvironment would draw them.

    [seed, 0] -> u_S, u_r, u_X0, u_K;  [seed, 1] -> 19 passive normals;
    [seed, 2, 0] -> normals of the first accepted request (the reference measurement).
    """
    m = len(seeds)
    u = np.empty((m, 4))
    zp = np.empty((m, len(prior.passive_times_h)))
    zm = np.empty((m, REF_REPS))
    for i, seed in enumerate(seeds):
        u[i] = np.random.default_rng(np.random.SeedSequence([seed, 0])).random(4)
        zp[i] = np.random.default_rng(np.random.SeedSequence([seed, 1])).standard_normal(zp.shape[1])
        zm[i] = np.random.default_rng(np.random.SeedSequence([seed, 2, 0])).standard_normal(REF_REPS)
    ls = np.log(prior.s_odeq_loguniform)
    lx = np.log(prior.x0_odeq_loguniform)
    s = np.exp(ls[0] + u[:, 0] * (ls[1] - ls[0]))
    r = prior.r_per_h_uniform[0] + u[:, 1] * (prior.r_per_h_uniform[1] - prior.r_per_h_uniform[0])
    x0 = np.exp(lx[0] + u[:, 2] * (lx[1] - lx[0]))
    lo, hi = prior.kappa_uniform if cond is BP else prior.lambda_uniform
    ratio = lo + u[:, 3] * (hi - lo)
    k = ratio * s
    t = np.asarray(prior.passive_times_h, dtype=np.float64)
    passive = noisy(resp(latent(t, k, r, x0, prior.nu), s[:, None], prior.n), zp, prior)
    return dict(u=u, s=s, r=r, x0=x0, ratio=ratio, k=k, passive=passive, z_meas=zm,
                p_hat=passive[:, 15:19].mean(axis=1))


def measure(w: dict, prior: ScenarioPrior, t: float, d: float, reps: int) -> dict[str, NDArray]:
    """One late/early measurement per world using the [seed, 2, 0] normals."""
    x = latent([t], w["k"], w["r"], w["x0"], prior.nu)[:, 0]
    presented = x / d
    mu = resp(presented, w["s"], prior.n)
    y = noisy(mu[:, None], w["z_meas"][:, :reps], prior)
    c_hat = d * y.mean(axis=1)
    xl = w["s"] * ((1 - prior.eps_lin) ** -prior.n - 1) ** (1 / prior.n)
    return dict(x=x, presented=presented, mu=mu, c_hat=c_hat, R=c_hat / w["p_hat"],
                c_over_k=c_hat / w["k"],
                useful=(presented <= xl) & (mu >= prior.y_loq))


# ---- statistics ------------------------------------------------------------------------

def auroc(neg: NDArray, pos: NDArray) -> float:
    """Mann-Whitney AUROC that ``pos`` exceeds ``neg``; ties count 0.5."""
    allv = np.concatenate([neg, pos])
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    start = np.concatenate([[0], np.cumsum(counts)[:-1]])
    avg_rank = start + (counts + 1) / 2.0
    ranks = avg_rank[inv]
    n0, n1 = len(neg), len(pos)
    return float((ranks[n0:].sum() - n1 * (n1 + 1) / 2) / (n0 * n1))


def wilson(k: int, n: int) -> list[float]:
    z = WILSON_Z
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [max(0.0, c - h), min(1.0, c + h)]


def ks_statistic(a: NDArray, b: NDArray) -> float:
    a, b = np.sort(a), np.sort(b)
    v = np.concatenate([a, b])
    return float(np.max(np.abs(np.searchsorted(a, v, "right") / len(a)
                               - np.searchsorted(b, v, "right") / len(b))))


def balanced(correct_bp: NDArray, correct_ma: NDArray) -> dict[str, Any]:
    acc = 0.5 * (correct_bp.mean() + correct_ma.mean())
    k = int(correct_bp.sum() + correct_ma.sum())
    return {"balanced_accuracy": float(acc), "wilson95": wilson(k, len(correct_bp) + len(correct_ma)),
            "n_per_condition": len(correct_bp)}


def tv_ceiling(prior: ScenarioPrior, seeds: list[int]) -> float:
    """1/2 + 1/2 TV between the log K' distributions (200-bin histogram), GATE0_SPEC §5."""
    lk = [np.log(kprime(w["k"], w["s"], prior.n)) for w in
          (_nuisance(prior, seeds, BP), _nuisance(prior, seeds, MA))]
    edges = np.linspace(min(map(np.min, lk)), max(map(np.max, lk)), 201)
    ha, hb = (np.histogram(v, bins=edges)[0] for v in lk)
    return float(0.5 + 0.25 * np.abs(ha - hb).sum() / len(seeds))


def _nuisance(prior: ScenarioPrior, seeds: list[int], cond: Condition) -> dict[str, NDArray]:
    u = np.array([np.random.default_rng(np.random.SeedSequence([s, 0])).random(4) for s in seeds])
    ls = np.log(prior.s_odeq_loguniform)
    s = np.exp(ls[0] + u[:, 0] * (ls[1] - ls[0]))
    lo, hi = prior.kappa_uniform if cond is BP else prior.lambda_uniform
    return dict(s=s, k=(lo + u[:, 3] * (hi - lo)) * s)


def knn15(prior: ScenarioPrior, train: dict, test: dict, k: int = 15) -> dict[str, Any]:
    """Model-free 15-NN on log full passive trajectories (log of max(1e-3, y))."""
    def lt(y):
        return np.log(np.maximum(1e-3, y))
    xtr = np.vstack([lt(train[BP]["passive"]), lt(train[MA]["passive"])])
    ytr = np.r_[np.zeros(len(train[BP]["passive"])), np.ones(len(train[MA]["passive"]))]
    out = {}
    for cond in (BP, MA):
        xq = lt(test[cond]["passive"])
        d2 = (xq**2).sum(1)[:, None] + (xtr**2).sum(1)[None, :] - 2 * xq @ xtr.T
        nn = np.argsort(d2, axis=1, kind="stable")[:, :k]
        pred_ma = ytr[nn].sum(axis=1) >= k / 2  # ties impossible for odd k
        out[cond] = pred_ma == (cond is MA)
    return balanced(out[BP], out[MA])


def t95_plus_2(prior: ScenarioPrior, w: dict) -> NDArray:
    """t_q(0.95) + 2 h for each world (DESIGN §5.5)."""
    nu, q = prior.nu, prior.plateau_fraction
    kp = kprime(w["k"], w["s"], prior.n)
    y0 = resp(w["x0"], w["s"], prior.n)
    return np.log((y0**-nu - kp**-nu) / ((q * kp) ** -nu - kp**-nu)) / (nu * w["r"]) + 2.0


def g0c_iv_passes(max_t95_plus_2_h: float, min_ma_x12_over_kprime: float) -> bool:
    """G0-C(iv) as written in GATE0_SPEC §4. Pending science ruling (PR #3): sampled vs support."""
    return max_t95_plus_2_h <= 12.0 and min_ma_x12_over_kprime >= 2.5


def diagnostic_action_set(grid_min_auroc: list[float]) -> tuple[float | None, float | None, bool]:
    """Contiguous diagnostic interval on G0H_GRID containing 10 (1 is never on the grid)."""
    ok = [a >= G0H_AUROC for a in grid_min_auroc]
    if 10 not in G0H_GRID or not ok[G0H_GRID.index(10)]:
        return None, None, False
    idx = [i for i, v in enumerate(ok) if v]
    contiguous = idx == list(range(idx[0], idx[-1] + 1))
    if not contiguous:
        return None, None, False
    return float(G0H_GRID[idx[0]]), float(G0H_GRID[idx[-1]]), True


# ---- the checks ------------------------------------------------------------------------

def run_checks(prior: ScenarioPrior, sz: dict[str, int]) -> tuple[dict, dict]:
    """All Gate 0 checks. Returns (summary fragment, data for the plots)."""
    test = {c: worlds(prior, seed_range("test", sz["test"]), c) for c in (BP, MA)}
    train = {c: worlds(prior, seed_range("knn_train", sz["knn_train"]), c) for c in (BP, MA)}
    scans = {c: worlds(prior, seed_range("scans", sz["scans"]), c) for c in (BP, MA)}
    checks: dict[str, Any] = {}

    # G0-A passive ambiguity
    ceiling = tv_ceiling(prior, seed_range("passive_reference", sz["ceiling"]))
    ref = build_reference(prior, seed_range("passive_reference", sz["passive_reference"]))
    pb = {c: np.array([ref.classify(y)[0] == ("GROWTH_CONTINUED" if c is MA else "GROWTH_STOPPED")
                       for y in test[c]["passive"]]) for c in (BP, MA)}
    pbs = balanced(pb[BP], pb[MA])
    knn = knn15(prior, train, test)
    checks["G0-A"] = {"blocking": True, "threshold": 0.65, "threshold_type": "BDT",
                      "analytic_ceiling": ceiling, "passive_bayes": pbs, "knn15": knn,
                      "passed": bool(max(ceiling, pbs["balanced_accuracy"], knn["balanced_accuracy"]) <= 0.65)}

    # Reference protocol (t = 18, d = 10, 3 reps) on the test worlds
    refm = {c: measure(test[c], prior, REF_T, REF_D, REF_REPS) for c in (BP, MA)}
    comp_bp = 1 - resp(scans[BP]["k"], scans[BP]["s"], prior.n) / scans[BP]["k"]
    fr_r = float(np.mean(np.abs(refm[BP]["R"] - 1) <= 0.15))
    fr_c = float(np.mean(np.abs(refm[BP]["c_over_k"] - 1) <= 0.15))
    checks["G0-B"] = {"blocking": True, "threshold_type": "BDT",
                      "thresholds": {"max_compression": 0.05, "frac_R_within_0_15": 0.95,
                                     "frac_C_over_K_within_0_15": 0.95},
                      "max_compression": float(comp_bp.max()), "frac_R_within_0_15": fr_r,
                      "frac_C_over_K_within_0_15": fr_c,
                      "passed": bool(comp_bp.max() <= 0.05 and fr_r >= 0.95 and fr_c >= 0.95)}

    # G0-C diagnostic separation and late-window validity
    gs_ok = {c: (refm[c]["R"] >= TAU) == (c is MA) for c in (BP, MA)}
    gs_acc = 0.5 * (gs_ok[BP].mean() + gs_ok[MA].mean())
    fr_ma_r = float(np.mean(refm[MA]["R"] >= 2.5))
    fr_ma_c = float(np.mean(np.abs(refm[MA]["c_over_k"] - 1) <= 0.15))
    t95 = max(float(t95_plus_2(prior, scans[c]).max()) for c in (BP, MA))
    x12 = latent([12.0], scans[MA]["k"], scans[MA]["r"], scans[MA]["x0"], prior.nu)[:, 0]
    min_ratio = float((x12 / kprime(scans[MA]["k"], scans[MA]["s"], prior.n)).min())
    iv = g0c_iv_passes(t95, min_ratio)
    checks["G0-C"] = {"blocking": True, "threshold_type": "BDT",
                      "thresholds": {"frac_MA_R_ge_2_5": 0.99, "good_scientist_accuracy": 0.98,
                                     "frac_MA_C_over_K_within_0_15": 0.95, "max_t95_plus_2_h": 12.0,
                                     "min_MA_X12_over_Kprime": 2.5},
                      "frac_MA_R_ge_2_5": fr_ma_r, "good_scientist_accuracy": float(gs_acc),
                      "frac_MA_C_over_K_within_0_15": fr_ma_c, "max_t95_plus_2_h": t95,
                      "min_MA_X12_over_Kprime": min_ratio, "iv_passed": bool(iv),
                      "passed": bool(fr_ma_r >= 0.99 and gs_acc >= 0.98 and fr_ma_c >= 0.95 and iv)}

    # G0-D non-diagnostic interventions and reconstruction limits
    def discr(t, d, reps):
        m = {c: measure(test[c], prior, t, d, reps) for c in (BP, MA)}
        a = auroc(m[BP]["R"], m[MA]["R"])
        return max(a, 1 - a), m
    d1, _ = discr(18, 1.0, 3)
    d2, _ = discr(3, 10.0, 3)
    a3, m3 = discr(18, 2.0, 3)
    checks["G0-D"] = {"blocking": True, "threshold": 0.65, "threshold_type": "BDT",
                      "D1_undiluted_discriminability": d1, "D2_early_discriminability": d2,
                      "D3": {"blocking": False,
                             "frac_outside_useful_region": float(np.mean(~m3[MA]["useful"])),
                             "p95_C_over_K": float(np.quantile(m3[MA]["c_over_k"], 0.95)),
                             "auroc": a3,
                             "passed": bool(np.mean(~m3[MA]["useful"]) >= 0.95
                                            and np.quantile(m3[MA]["c_over_k"], 0.95) <= 0.75)},
                      "passed": bool(d1 <= 0.65 and d2 <= 0.65)}

    # G0-H diagnostic action set (single replicate, worst time in the late window)
    late = range(prior.late_window_h[0], prior.late_window_h[1] + 1)
    min_auc = []
    for d in G0H_GRID:
        aucs = [auroc(*(measure(test[c], prior, t, d, 1)["R"] for c in (BP, MA))) for t in late]
        min_auc.append(float(min(aucs)))
    d_min, d_max, contiguous = diagnostic_action_set(min_auc)
    checks["G0-H"] = {"blocking": True, "threshold": G0H_AUROC, "threshold_type": "BDT",
                      "auroc_threshold": G0H_AUROC, "replicates": 1,
                      "late_window_h": list(prior.late_window_h), "grid": G0H_GRID,
                      "min_auroc_by_d": min_auc, "contiguous": contiguous,
                      "d_min": d_min, "d_max": d_max, "passed": bool(contiguous)}

    # G0-E passive-family equivalence
    tt = np.arange(0, 18.0001, 0.25)
    dev = 0.0
    for c in (BP, MA):
        w = {k: v[: sz["equivalence"]] for k, v in scans[c].items()}
        obs = resp(latent(tt, w["k"], w["r"], w["x0"], prior.nu), w["s"][:, None], prior.n)
        fam = latent(tt, kprime(w["k"], w["s"], prior.n), w["r"], resp(w["x0"], w["s"], prior.n),
                     prior.nu)
        dev = max(dev, float(np.max(np.abs(obs / fam - 1))))
    checks["G0-E"] = {"blocking": True, "threshold": 1e-9, "threshold_type": "SIM",
                      "max_relative_deviation": dev, "passed": bool(dev <= 1e-9)}

    # G0-F nuisance independence and instrument stability
    same = True
    for seed in range(sz["same_seed"]):
        a, b = sample_episode(prior, seed, BP), sample_episode(prior, seed, MA)
        ua = (a.k_ratio - prior.kappa_uniform[0]) / (prior.kappa_uniform[1] - prior.kappa_uniform[0])
        ub = (b.k_ratio - prior.lambda_uniform[0]) / (prior.lambda_uniform[1] - prior.lambda_uniform[0])
        same &= (a.assay.s_odeq == b.assay.s_odeq and a.growth.r_per_h == b.growth.r_per_h
                 and a.growth.x0_odeq == b.growth.x0_odeq and abs(ua - ub) <= 1e-12)
    ks = ks_statistic(np.log(scans[BP]["s"]),
                      np.log(worlds(prior, seed_range("robustness", sz["scans"]), MA)["s"]))
    stable, stable_detail = _within_episode_stable(prior, sz["stability"])
    checks["G0-F"] = {"blocking": True, "threshold": 0.03, "threshold_type": "SIM",
                      "same_seed_identical": bool(same), "ks_logS": ks,
                      "within_episode_stable": stable, "stability_detail": stable_detail,
                      "passed": bool(same and ks <= 0.03 and stable)}

    # G0-G robustness (non-blocking)
    checks["G0-G"] = robustness(prior, sz["robustness"])

    sweep = []
    sweep_w = {c: {k: v[: sz["sweep"]] for k, v in test[c].items()} for c in (BP, MA)}
    sweep_m = {}
    for d in SWEEP_D:
        m = {c: measure(sweep_w[c], prior, REF_T, float(d), REF_REPS) for c in (BP, MA)}
        sweep_m[d] = m
        tau_acc = 0.5 * (np.mean(m[BP]["R"] < TAU) + np.mean(m[MA]["R"] >= TAU))
        sweep.append({"d": d, "auroc": auroc(m[BP]["R"], m[MA]["R"]),
                      "tau_balanced_accuracy": float(tau_acc),
                      "q1_BP": float(np.mean(m[BP]["useful"])), "q1_MA": float(np.mean(m[MA]["useful"])),
                      "C_over_K_BP_q": [float(np.quantile(m[BP]["c_over_k"], q)) for q in (0.025, 0.5, 0.975)],
                      "C_over_K_MA_q": [float(np.quantile(m[MA]["c_over_k"], q)) for q in (0.025, 0.5, 0.975)]})

    in_set = d_min is not None and d_min <= REF_D <= d_max
    frag = {
        "checks": checks,
        "passive_baseline": {"name": "PassiveBayes", "balanced_accuracy": pbs["balanced_accuracy"]},
        "diagnostic_dilution": {"t_h": REF_T, "d": REF_D, "replicates": REF_REPS,
                                "R_BP_p99": float(np.quantile(refm[BP]["R"], 0.99)),
                                "R_MA_p1": float(np.quantile(refm[MA]["R"], 0.01))},
        "diagnostic_action_set": {"late_window_h": list(prior.late_window_h), "d_min": d_min,
                                  "d_max": d_max, "auroc_threshold": G0H_AUROC,
                                  "evaluated_replicates": 1},
        "good_scientist": {"accuracy": float(gs_acc),
                           "diagnostic_control_rate": 1.0 if in_set else None,
                           "reconstruction_adequate_rate": float(
                               np.mean(np.r_[refm[BP]["useful"], refm[MA]["useful"]]))},
        "sweep": sweep,
    }
    data = dict(prior=prior, test=test, refm=refm, sweep=sweep_m, ref=ref, checks=checks)
    return frag, data


def _within_episode_stable(prior: ScenarioPrior, n_episodes: int) -> tuple[bool, str]:
    """S unchanged across 6 accepted requests per episode (G0-F iii), via the real environment.

    Fails (never passes vacuously) if the environment is unavailable or any request is rejected.
    """
    try:
        from mirage.lab.environment import LabEnvironment
    except ImportError:
        return False, "unavailable: mirage.lab.environment cannot be imported"
    rng = np.random.default_rng(np.random.SeedSequence([SEEDS["robustness"][0], 99]))
    for seed in range(n_episodes):
        cfg = sample_episode(prior, seed, MA if seed % 2 else BP)
        s0 = cfg.assay.s_odeq
        env = LabEnvironment(cfg)
        for _ in range(6):
            env.call("measure_od", {"time_h": int(rng.integers(0, 19)),
                                    "dilution_factor": float(rng.uniform(1, 100)), "replicates": 1})
        if len(env.accepted) != 6:
            return False, f"episode {seed}: {len(env.accepted)} of 6 requests accepted"
        for m in env.accepted:
            mu = float(resp(np.array(m.presented_biomass_odeq), np.array(s0), prior.n))
            if not math.isclose(mu, m.noise_free_reading, rel_tol=1e-12) or env.config.assay.s_odeq != s0:
                return False, f"episode {seed}: S or the response changed within the episode"
    return True, f"{n_episodes} episodes x 6 accepted requests"


PERTURBATIONS: list[tuple[str, dict[str, Any]]] = [
    *[(f"nu={v}", {"nu": v}) for v in (6, 7, 9, 10)],
    *[(f"n={v}", {"n": v}) for v in (7, 10)],
    ("noise x0.5", {"sigma_abs": 0.0015, "sigma_rel": 0.01}),
    ("noise x2", {"sigma_abs": 0.006, "sigma_rel": 0.04}),
    ("r x0.8", {"r_per_h_uniform": (0.48, 0.72)}),
    ("r x1.2", {"r_per_h_uniform": (0.72, 1.08)}),
    ("X0 /2", {"x0_odeq_loguniform": (0.0025, 0.01)}),
    ("X0 x2", {"x0_odeq_loguniform": (0.01, 0.04)}),
    ("S [0.6, 1.5]", {"s_odeq_loguniform": (0.6, 1.5)}),
    ("S [0.4, 2.5]", {"s_odeq_loguniform": (0.4, 2.5)}),
]


def robustness(prior: ScenarioPrior, n: int) -> dict[str, Any]:
    """G0-G: one-at-a-time perturbations (non-blocking; failures are documented boundaries)."""
    variants = []
    lo = SEEDS["robustness"][0]
    for name, upd in PERTURBATIONS:
        p = prior.model_copy(update=upd)
        tr = {c: worlds(p, list(range(lo, lo + n)), c) for c in (BP, MA)}
        te = {c: worlds(p, list(range(lo + n, lo + 2 * n)), c) for c in (BP, MA)}
        knn = knn15(p, tr, te)["balanced_accuracy"]
        m = {c: measure(te[c], p, REF_T, REF_D, REF_REPS) for c in (BP, MA)}
        gs = float(0.5 * (np.mean(m[BP]["R"] < TAU) + np.mean(m[MA]["R"] >= TAU)))
        comp = float((1 - resp(te[BP]["k"], te[BP]["s"], p.n) / te[BP]["k"]).max())
        variants.append({"name": name, "knn15": knn, "good_scientist_accuracy": gs,
                         "max_bp_compression": comp,
                         "passed": bool(knn <= 0.65 and gs >= 0.98 and comp <= 0.05)})
    return {"blocking": False, "threshold_type": "BDT", "n_per_condition": n,
            "passed": bool(all(v["passed"] for v in variants)), "variants": variants}


# ---- summary ---------------------------------------------------------------------------

def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_summary(prior: ScenarioPrior, frag: dict, quick: bool, runtime_s: float) -> dict:
    sha = canonical_sha256(prior)
    checks = frag["checks"]
    passed = all(c["passed"] for c in checks.values() if c["blocking"])
    status = _git("status", "--porcelain")
    dset = dict(frag["diagnostic_action_set"], scenario_sha256=sha)
    return {
        "schema_version": "gate0-summary-v2",
        "mode": "quick" if quick else "full",
        "passed": bool(passed),
        "scenario_version": prior.scenario_version,
        "scenario_sha256": sha,
        "source_commit": _git("rev-parse", "HEAD"),
        "source_dirty": None if status is None else bool(status),
        "parameters": {"nu": prior.nu, "n": prior.n, "sigma_abs": prior.sigma_abs,
                       "sigma_rel": prior.sigma_rel, "resolution": prior.resolution,
                       "eps_lin": prior.eps_lin, "lower_useful_bound": prior.y_loq,
                       "late_window_h": list(prior.late_window_h), "passive_times_h": "0..18",
                       "budget_units": prior.budget_units,
                       "dilution_range": list(prior.dilution_range)},
        "nuisance_distributions": {"S": "loguniform(0.5, 2.0)", "r": "uniform(0.6, 0.9)",
                                   "X0": "loguniform(0.005, 0.02)", "u": "uniform(0, 1)",
                                   "kappa": "0.80 + 0.10*u", "lambda": "3 + 2*u"},
        "seeds": SEEDS,
        "sizes": QUICK if quick else FULL,
        "checks": checks,
        "passive_baseline": frag["passive_baseline"],
        "diagnostic_dilution": frag["diagnostic_dilution"],
        "diagnostic_action_set": dset,
        "good_scientist": frag["good_scientist"],
        "sweep": frag["sweep"],
        "plots": [],
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "matplotlib": _dist_version("matplotlib"), "mirage": mirage.__version__},
        "runtime_s": runtime_s,
    }


def _dist_version(name: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def write_summary(out: Path, summary: dict) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "summary.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="reduced sizes; never a pass claim")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    prior = load_prior(SCENARIO)
    frag, data = run_checks(prior, QUICK if args.quick else FULL)
    summary = build_summary(prior, frag, args.quick, time.perf_counter() - t0)
    path = write_summary(args.out, summary)
    if not args.no_plots:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from gate0_plots import make_plots
        except ImportError:
            print("gate0: plotting module not available; summary written without plots")
        else:
            summary["plots"] = make_plots(args.out, data, summary["sweep"])
            summary["runtime_s"] = time.perf_counter() - t0
            write_summary(args.out, summary)
    failed = [k for k, c in summary["checks"].items() if c["blocking"] and not c["passed"]]
    print(f"gate0 ({summary['mode']}): passed={summary['passed']} failed={failed} -> {path}")
    missing = missing_outputs(args.out)
    if not args.quick and missing:
        print(f"gate0 (full): required outputs missing: {missing}", file=sys.stderr)
        return 2
    return 0 if summary["passed"] else 1


def missing_outputs(out: Path) -> list[str]:
    """Full mode requires summary.json and every GATE0_SPEC plot."""
    return [f for f in ["summary.json", *PLOTS] if not (out / f).is_file()]


if __name__ == "__main__":
    sys.exit(main())
