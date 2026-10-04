"""Figures for RESULT.md, drawn only from results.json (run analysis.py first).

    PYTHONPATH=src .venv/bin/python experiments/exploratory/calibration/figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
AGENTS = ["C1 Opus", "C2 Sonnet", "GoodScientist", "PassiveBayes"]
CASE = "s500028-BP"
TAU = 1.5
plt.rcParams.update({
    "font.family": "serif", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "figure.dpi": 150, "savefig.bbox": "tight", "legend.frameon": False,
})
INK, GREY, RED = "#222222", "#8a8a8a", "#b2182b"


def reliability(d: dict) -> None:
    fig, axes = plt.subplots(1, 4, figsize=(10.5, 2.9), sharey=True)
    y = np.array([c == "MA" for c in d["condition"]], float)
    rng = np.random.default_rng(0)
    for ax, name in zip(axes, AGENTS):
        a = d["agents"][name]
        p = np.array([d["per_episode"][e][name]["p"] if name != "PassiveBayes" else d["per_episode"][e]["pb_p"]
                      for e in d["episode_ids"]])
        ax.plot([0, 1], [0, 1], color=GREY, lw=0.6, ls="--")
        for edge in (0.1, 0.3, 0.7, 0.9):
            ax.axvline(edge, color="#dddddd", lw=0.5, zorder=0)
        jit = rng.uniform(-0.035, 0.035, len(p))
        case = np.array(d["episode_ids"]) == CASE
        ax.scatter(p[~case], y[~case] + jit[~case], s=9, facecolor="none", edgecolor=GREY, lw=0.6, zorder=2)
        ax.scatter(p[case], y[case] + jit[case], s=22, marker="x", color=RED, lw=1.0, zorder=3)
        for j, (row, (lo, hi)) in enumerate(zip(a["reliability"], a["reliability_wilson95"])):
            f = row["k"] / row["n"]
            ax.errorbar(row["mean_p"], f, yerr=[[max(f - lo, 0)], [max(hi - f, 0)]], fmt="o", ms=4, color=INK,
                        ecolor=INK, elinewidth=0.8, capsize=2, zorder=4)
            ax.annotate(f"n={row['n']}", (row["mean_p"], f), xytext=(4, -9 if f > 0.5 else 5 + 10 * (j % 2)),
                        textcoords="offset points", fontsize=7)
        pt = a["point"]
        ax.set_title(f"{name}\nBrier {pt['brier']:.3f}  ECE {pt['ece']:.3f}", fontsize=9)
        ax.set_xlim(-0.03, 1.03)
        ax.set_ylim(-0.08, 1.08)
        ax.set_xlabel("stated P(above reading)")
    axes[0].set_ylabel("observed MA frequency")
    fig.text(0.5, -0.06, "Bins [0,.1) [.1,.3) [.3,.7) [.7,.9) [.9,1]; black = bin mean p vs observed frequency, "
             "Wilson 95%; grey circles = raw episodes (jittered); red x = s500028-BP.", ha="center", fontsize=7.5)
    fig.savefig(HERE / "fig1_reliability.png")
    plt.close(fig)


def decomposition(d: dict) -> None:
    metrics = [("brier", "Brier"), ("rel", "Reliability (REL)"), ("res", "Resolution (RES)"),
               ("log_loss", "Log loss"), ("ece", "ECE")]
    fig, axes = plt.subplots(1, 5, figsize=(10.5, 2.2), sharey=True)
    for ax, (m, label) in zip(axes, metrics):
        for i, name in enumerate(AGENTS):
            v = d["agents"][name]["point"][m]
            lo, hi = d["agents"][name]["ci"][m]
            ax.errorbar(v, i, xerr=[[max(v - lo, 0)], [max(hi - v, 0)]], fmt="o", ms=3.5, color=INK, elinewidth=0.8, capsize=2)
        if m == "res":
            ax.axvline(0.25, color=GREY, lw=0.6, ls="--")
            ax.text(0.25, 3.45, "UNC", fontsize=7, color=GREY, ha="center")
        ax.set_title(label, fontsize=9)
        ax.set_ylim(3.6, -0.6)
    axes[0].set_yticks(range(4), AGENTS)
    fig.text(0.5, -0.1, "Point estimate and stratified-bootstrap 95% interval (B = 10,000, 15 BP + 15 MA per resample).",
             ha="center", fontsize=7.5)
    fig.savefig(HERE / "fig2_decomposition.png")
    plt.close(fig)


def by_condition(d: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.2), sharey=True)
    for ax, c in zip(axes, ("BP", "MA")):
        for i, name in enumerate(AGENTS):
            r = d["agents"][name]["by_condition"][c]
            v, (lo, hi) = r["mean_p"], r["mean_p_ci"]
            ax.errorbar(v, i, xerr=[[max(v - lo, 0)], [max(hi - v, 0)]], fmt="o", ms=3.5, color=INK, elinewidth=0.8, capsize=2)
            ax.text(1.04, i, f"{r['k_correct']}/15", va="center", fontsize=7.5)
        ax.axvline(0 if c == "BP" else 1, color=GREY, lw=0.6, ls="--")
        ax.set_xlim(-0.03, 1.03)
        ax.set_title(f"hidden {c}: mean stated p (ideal {0 if c == 'BP' else 1})", fontsize=9)
        ax.set_ylim(3.6, -0.6)
    axes[0].set_yticks(range(4), AGENTS)
    fig.savefig(HERE / "fig3_by_condition.png")
    plt.close(fig)


def case_study(d: dict) -> None:
    cs = d["case_study"]
    bp = [e for e in d["episode_ids"] if d["per_episode"][e]["condition"] == "BP"]
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.0), gridspec_kw={"width_ratios": [1.2, 1, 1.1]})
    ax = axes[0]
    t, od = np.array(cs["passive"]).T
    ax.plot(t, od, "o-", ms=2.5, color=GREY, lw=0.7, label="passive reading")
    ax.axhline(cs["latent_18h"], color=INK, lw=0.7, ls="--", label=f"true K = {cs['latent_18h']:.3f}")
    marks = {"C1 Opus": ("s", -0.25), "C2 Sonnet": ("^", 0.0), "GoodScientist": ("D", 0.25)}
    for name, (mk, dx) in marks.items():
        for req in cs["agents"][name]["requests"]:
            if req["time_h"] >= 12:
                ax.scatter([req["time_h"] + dx] * len(req["corrected"]), req["corrected"], marker=mk, s=14,
                           facecolor="none", edgecolor=RED if name != "GoodScientist" else INK, lw=0.8)
        ax.scatter([], [], marker=mk, s=14, facecolor="none", edgecolor=RED if name != "GoodScientist" else INK,
                   label=f"{name}: d x reading")
    ax.set_xlim(5.5, 19)
    ax.set_ylim(1.25, 1.6)
    ax.set_xlabel("time (h)")
    ax.set_ylabel("OD600")
    ax.set_title("(a) s500028-BP: plateau and dilution reads", fontsize=9)
    ax.legend(fontsize=6.5, loc="upper left")

    ax = axes[1]
    gaps = [d["per_episode"][e]["noise_free_gap"] * 100 for e in bp]
    order = np.argsort(gaps)
    for j, i in enumerate(order):
        e = bp[i]
        ax.barh(j, gaps[i], color=RED if e == CASE else "#bbbbbb", height=0.7)
        ax.text(gaps[i] + 0.05, j, e.split("-")[0][1:], va="center", fontsize=6)
    ax.set_yticks([])
    ax.set_xlabel("noise-free under-read K/f(K) - 1 (%)")
    ax.set_title("(b) 15 plateau cultures: hidden gap", fontsize=9)

    ax = axes[2]
    for k, name in enumerate(["C1 Opus", "C2 Sonnet", "GoodScientist"]):
        rs = [d["per_episode"][e][name]["ratio"] for e in bp if e != CASE]
        ax.scatter(rs, np.full(len(rs), k) + np.linspace(-0.15, 0.15, len(rs)), s=9, facecolor="none",
                   edgecolor=GREY, lw=0.6)
        a = cs["agents"][name]
        lo, med, hi = a["sim_ratio_q"]
        ax.plot([lo, hi], [k + 0.3, k + 0.3], color=INK, lw=0.8)
        ax.plot(med, k + 0.3, "|", color=INK, ms=6)
        ax.scatter(a["ratio"], k, marker="x", color=RED, s=30, lw=1.1, zorder=3)
    ax.axvline(d["gate0"]["diagnostic_dilution"]["R_BP_p99"], color=GREY, lw=0.6, ls=":")
    ax.text(d["gate0"]["diagnostic_dilution"]["R_BP_p99"] - 0.002, -0.55, "Gate 0 BP p99", fontsize=6.5,
            color=GREY, ha="right")
    ax.set_yticks(range(3), ["C1 Opus", "C2 Sonnet", "GoodSci."])
    ax.set_ylim(2.7, -0.7)
    ax.set_xlabel("late corrected / plateau ratio R  (tau = 1.5, off scale)")
    ax.set_title("(c) R on s500028 (x) vs other BP (o)", fontsize=9)
    fig.text(0.5, -0.07, "(c) black bar: 95% range of R expected from noise alone under the true s500028 culture, "
             "for that agent's own measurement design (200,000 simulations).", ha="center", fontsize=7.5)
    fig.tight_layout()
    fig.savefig(HERE / "fig4_s500028.png")
    plt.close(fig)


def passive_bayes(d: dict) -> None:
    ids = d["episode_ids"]
    p = np.array([d["per_episode"][e]["pb_p"] for e in ids])
    y = np.array([d["per_episode"][e]["condition"] == "MA" for e in ids])
    cor = (p > 0.5) == y
    conf = np.maximum(p, 1 - p)
    fig, ax = plt.subplots(figsize=(5.2, 1.9))
    for k, (mask, lab) in enumerate([(cor, f"correct ({cor.sum()})"), (~cor, f"wrong ({(~cor).sum()})")]):
        v = np.sort(conf[mask])
        ax.scatter(v, np.full(len(v), k) + np.linspace(-0.2, 0.2, len(v)), s=12, facecolor="none",
                   edgecolor=INK if k == 0 else RED, lw=0.7)
        ax.text(1.02, k, lab, va="center", fontsize=8)
    ax.set_yticks([])
    ax.set_ylim(1.6, -0.6)
    ax.set_xlim(0.49, 1.01)
    pb = d["passive_bayes"]
    lo, hi = pb["auroc_ci"]
    ax.set_xlabel("PassiveBayes confidence max(p, 1 - p)")
    ax.set_title(f"PassiveBayes: AUROC(confidence -> correct) {pb['auroc']:.2f} [{lo:.2f}, {hi:.2f}]", fontsize=9)
    fig.savefig(HERE / "fig5_passive_bayes.png")
    plt.close(fig)


def main() -> None:
    d = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    reliability(d)
    decomposition(d)
    by_condition(d)
    case_study(d)
    passive_bayes(d)


if __name__ == "__main__":
    main()
