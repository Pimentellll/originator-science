"""figure.png from tables.json: frozen M3/Q1 vs the proposed rules, dev block, Wilson 95 %."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ORDER = [
    "ref_good_scientist",
    "ref_passive_bayes",
    "probe_edge_honest",
    "adv_token_above",
    "adv_token_asread",
    "adv_token_passive",
    "adv_contrarian",
    "adv_nondiag_spend",
    "adv_absurd_estimate",
    "adv_p_mismatch",
    "adv_hedge",
    "adv_extreme_passive",
]
PANELS = (
    (
        "M3 (justified) and proposed P1 / P2 / P4",
        (
            ("M3", "M3 (current)"),
            ("M3_P1", "P1 consistency"),
            ("M3_P2", "P2 twin flip"),
            ("M3_P4", "P4 coherent p"),
        ),
    ),
    (
        "Q1 (reconstruction) and proposed P3",
        (("Q1", "Q1 (current)"), ("Q1_P3_0.10", "P3 estimate within 10 %")),
    ),
)


def main() -> Path:
    t = json.loads((HERE / "tables.json").read_text(encoding="utf-8"))["dev"]
    plt.rcParams.update({"font.family": "serif", "font.size": 9})
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), sharey=True)
    y = np.arange(len(ORDER))
    shades = ["0.1", "0.45", "0.7", "0.88"]
    for ax, (title, keys) in zip(axes, PANELS):
        h = 0.8 / len(keys)
        for i, (key, label) in enumerate(keys):
            rate, lo, hi = [], [], []
            for a in ORDER:
                m = t[a][key]
                r = m["k"] / m["n"]
                rate.append(r)
                lo.append(max(0.0, r - m["wilson95"][0]))
                hi.append(max(0.0, m["wilson95"][1] - r))
            ax.barh(
                y + (i - (len(keys) - 1) / 2) * h,
                rate,
                height=h,
                color=shades[i],
                edgecolor="black",
                linewidth=0.4,
                xerr=[lo, hi],
                capsize=1.5,
                error_kw={"linewidth": 0.6},
                label=label,
            )
        ax.set_title(title)
        ax.set_xlim(0, 1.05)
        ax.set_xlabel("rate on the dev block (n = 1,000; Wilson 95 %)")
        ax.grid(axis="x", linewidth=0.3, color="0.8")
        ax.legend(loc="lower right", fontsize=7, frameon=False)
    axes[0].set_yticks(y, ORDER)
    axes[0].invert_yaxis()
    fig.suptitle(
        "Grader red-team (exploratory): scripted adversaries under the frozen scorer "
        "and proposed rules",
        fontsize=10,
    )
    fig.tight_layout()
    path = HERE / "figure.png"
    fig.savefig(path, dpi=150)
    return path


if __name__ == "__main__":
    print(main())
