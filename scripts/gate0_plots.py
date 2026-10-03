"""Gate 0 figures (GATE0_SPEC §6). Called by gate0.py only after summary.json exists."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from mirage.assay.od_reader import response, x_lin  # noqa: E402
from mirage.biology.conditions import Condition  # noqa: E402
from mirage.biology.growth import richards  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "experiments" / "configs" / "demo_pair.json"
BP, MA = Condition.BIOLOGICAL_PLATEAU, Condition.MEASUREMENT_ARTIFACT
COL = {BP: "tab:blue", MA: "tab:red"}
LAB = {BP: "BIOLOGICAL_PLATEAU", MA: "MEASUREMENT_ARTIFACT"}


def _save(fig: plt.Figure, out: Path, name: str) -> str:
    fig.tight_layout()
    fig.savefig(out / name, dpi=120)
    plt.close(fig)
    return name


def assay_response(out: Path, prior: Any) -> str:
    u = np.linspace(0, 6, 1201)
    f = response(u, s_odeq=1.0, n=prior.n)
    ul = x_lin(s_odeq=1.0, n=prior.n, eps_lin=prior.eps_lin)
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax in (a, b):
        ax.axvspan(0, ul, color="0.9", label=f"useful region (x ≤ {ul:.4f} S)")
        ax.axvspan(*prior.kappa_uniform, color=COL[BP], alpha=0.25, label="BP plateau K ∈ [0.80, 0.90] S")
        ax.axvspan(*prior.lambda_uniform, color=COL[MA], alpha=0.15, label="MA latent K ∈ [3, 5] S")
    a.plot(u, u, "k:", label="identity")
    a.plot(u, f, "k-", label="f(x)/S")
    for lo, hi, c in ((*prior.kappa_uniform, BP), (*prior.lambda_uniform, MA)):
        ys = response(np.array([lo, hi]), s_odeq=1.0, n=prior.n)
        a.hlines(ys, 0, [lo, hi], colors=COL[c], linestyles="--", lw=0.8)
    a.set(xlabel="x / S", ylabel="reading / S", ylim=(0, 1.6), title="Assay response")
    a.legend(fontsize=7, loc="upper left")
    comp = np.where(u > 0, 1 - f / np.where(u > 0, u, 1), 0)
    b.plot(u, comp, "k-")
    b.axhline(prior.eps_lin, color="0.4", ls="--", lw=0.8)
    b.set(xlabel="x / S", ylabel="compression 1 − f(x)/x", title="Compression")
    return _save(fig, out, "assay_response.png")


def passive_overlap(out: Path, data: dict) -> str:
    t = np.arange(19)
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2))
    for c in (BP, MA):
        y = data["test"][c]["passive"]
        for row in y[:40]:
            a.plot(t, row, color=COL[c], alpha=0.25, lw=0.7)
        lo, hi = np.quantile(y, [0.05, 0.95], axis=0)
        a.fill_between(t, lo, hi, color=COL[c], alpha=0.15, label=f"{LAB[c]} 5–95 %")
        b.hist(y[:, 13:19].mean(axis=1), bins=40, color=COL[c], alpha=0.5, label=LAB[c])
    a.set(xlabel="time (h)", ylabel="reading (OD)", title="Passive trajectories (40 per condition)")
    a.legend(fontsize=7)
    b.set(xlabel="late passive mean, 13–18 h (OD)", ylabel="episodes", title="Late passive mean")
    b.legend(fontsize=7)
    return _save(fig, out, "passive_overlap.png")


def latent_reveal(out: Path, prior: Any) -> str:
    eps = {e["condition"]: e for e in json.loads(DEMO.read_text(encoding="utf-8"))["episodes"]}
    t = np.linspace(0, 18, 361)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.axvspan(*prior.late_window_h, color="0.92", label="late window")
    for c in (BP, MA):
        e = eps[c.value]
        k = e["k_ratio"] * e["s_odeq"]
        x = richards(t, k_odeq=k, r_per_h=e["r_per_h"], x0_odeq=e["x0_odeq"], nu=prior.nu)
        ax.plot(t, response(x, s_odeq=e["s_odeq"], n=prior.n), color=COL[c], label=f"{LAB[c]} observed")
        ax.plot(t, x, color=COL[c], ls="--", label=f"{LAB[c]} latent X(t)")
        c10 = 10 * float(response(x[-1] / 10, s_odeq=e["s_odeq"], n=prior.n))
        ax.plot([18], [c10], "o", color=COL[c], ms=7, mfc="white", label=f"1:10 corrected = {c10:.2f}")
    ax.set(xlabel="time (h)", ylabel="ODeq", title="Matched demo pair: same observed curve, different biomass")
    ax.legend(fontsize=7, loc="upper left")
    return _save(fig, out, "latent_reveal.png")


def intervention_sweep(out: Path, data: dict, summary_sweep: list[dict]) -> str:
    ds = sorted(data["sweep"])
    rows = {float(r["d"]): r for r in summary_sweep}
    if len(rows) != len(summary_sweep) or set(rows) != {float(d) for d in ds}:
        raise ValueError(f"summary sweep d values {sorted(rows)} do not match the measured grid {ds}")
    summary_sweep = [rows[float(d)] for d in ds]
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(14, 4.2))
    for cond in (BP, MA):
        q = np.array([np.quantile(data["sweep"][d][cond]["c_over_k"], [0.025, 0.5, 0.975]) for d in ds])
        a.plot(ds, q[:, 1], "o-", color=COL[cond], label=LAB[cond])
        a.fill_between(ds, q[:, 0], q[:, 2], color=COL[cond], alpha=0.2)
        b.plot(ds, [np.mean(data["sweep"][d][cond]["useful"]) for d in ds], "o-", color=COL[cond],
               label=LAB[cond])
    a.axhline(1, color="k", lw=0.6)
    a.set(xscale="log", xlabel="dilution d (t = 18 h, 3 reps)", ylabel="Ĉ / K", title="(a) reconstruction")
    b.set(xscale="log", xlabel="dilution d", ylabel="fraction Q1-adequate", ylim=(-0.02, 1.02),
          title="(b) reconstruction-adequate")
    c.plot(ds, [r["auroc"] for r in summary_sweep], "ko-", label="AUROC of R")
    c.plot(ds, [r["tau_balanced_accuracy"] for r in summary_sweep], "s--", color="0.4",
           label="balanced accuracy, τ = 1.5")
    c.set(xscale="log", xlabel="dilution d", ylim=(0.4, 1.02), title="(c) discriminability")
    for ax in (a, b, c):
        ax.legend(fontsize=7)
    return _save(fig, out, "intervention_sweep.png")


def separability(out: Path, checks: dict) -> str:
    A, C, D = checks["G0-A"], checks["G0-C"], checks["G0-D"]
    rows = [("passive: analytic ceiling", A["analytic_ceiling"], None),
            ("passive: PassiveBayes", A["passive_bayes"]["balanced_accuracy"], A["passive_bayes"]["wilson95"]),
            ("passive: 15-NN", A["knn15"]["balanced_accuracy"], A["knn15"]["wilson95"]),
            ("undiluted late (AUROC*)", D["D1_undiluted_discriminability"], None),
            ("early t=3 h, d=10 (AUROC*)", D["D2_early_discriminability"], None),
            ("late d=10, τ rule", C["good_scientist_accuracy"], None)]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    y = np.arange(len(rows))[::-1]
    for yi, (name, v, ci) in zip(y, rows):
        col = "tab:green" if name.startswith("late") else "0.5"
        ax.barh(yi, v, color=col)
        if ci is not None:
            ax.errorbar(v, yi, xerr=[[v - ci[0]], [ci[1] - v]], color="k", capsize=3)
        x_txt = (ci[1] if ci is not None else v) + 0.01
        ax.text(min(x_txt, 0.93), yi, f"{v:.3f}", va="center", fontsize=8)
    ax.axvline(0.65, color="tab:red", ls="--", lw=0.8, label="0.65 passive / non-diagnostic bound")
    ax.set(yticks=y, yticklabels=[r[0] for r in rows], xlim=(0.4, 1.0),
           xlabel="balanced accuracy (*AUROC discriminability max(a, 1−a))",
           title="Separability before and after one experiment")
    ax.legend(fontsize=7, loc="lower right")
    return _save(fig, out, "separability_before_after.png")


def robustness_map(out: Path, checks: dict) -> str:
    vs = checks["G0-G"]["variants"]
    cols = [("passive 15-NN BA", "knn15", lambda v: v <= 0.65),
            ("max BP compression", "max_bp_compression", lambda v: v <= 0.05),
            ("GoodScientist acc.", "good_scientist_accuracy", lambda v: v >= 0.98)]
    ok = np.array([[f(v[k]) for _, k, f in cols] for v in vs], dtype=float)
    fig, ax = plt.subplots(figsize=(6.5, 0.38 * len(vs) + 1.2))
    ax.imshow(ok, cmap=matplotlib.colors.ListedColormap(["#f4a6a6", "#a6e3a6"]), vmin=0, vmax=1,
              aspect="auto")
    for i, v in enumerate(vs):
        for j, (_, k, _) in enumerate(cols):
            ax.text(j, i, f"{v[k]:.3f}", ha="center", va="center", fontsize=8)
    ax.set(xticks=range(len(cols)), xticklabels=[c[0] for c in cols], yticks=range(len(vs)),
           yticklabels=[v["name"] for v in vs],
           title=f"Robustness (non-blocking, {checks['G0-G']['n_per_condition']} per condition)")
    return _save(fig, out, "robustness_map.png")


def make_plots(out: str | Path, data: dict, summary_sweep: list[dict] | None = None) -> list[str]:
    """Write the six Gate 0 PNGs into ``out``; return their file names."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    prior, checks = data["prior"], data["checks"]
    if data.get("sweep") and summary_sweep is None:
        raise ValueError("make_plots: summary_sweep is required when the sweep is non-empty")
    sweep_rows = summary_sweep or []
    return [assay_response(out, prior), passive_overlap(out, data), latent_reveal(out, prior),
            intervention_sweep(out, data, sweep_rows), separability(out, checks),
            robustness_map(out, checks)]
