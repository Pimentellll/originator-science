"""Registered analysis for the measurement-price experiment (REGISTRATION.md §6-7).

  PYTHONPATH=src .venv/bin/python experiments/exploratory/cost-sensitivity/analyze.py

Reads the episode records of the three price runs (plus, read-only, the frozen C2 summary
as a reproducibility reference) and writes ``analysis.json``, ``table.md`` and
``price_vs_control.png`` next to this file. All k/n intervals are the evaluator's Wilson
95 % intervals (``mirage.evaluation.metrics.wilson``).
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mirage.evaluation import runner  # noqa: E402
from mirage.evaluation.metrics import PRIMARY_STATUSES, EpisodeResult, wilson  # noqa: E402

PRICES = (1, 3, 6)
C2_FROZEN = runner.ROOT / "experiments" / "results" / "20261004-0049_claude_strong"
CONF_DROP = 0.10
MIN_NO_CONTROL = 3


def _kn(k: int, n: int) -> dict[str, Any]:
    if n == 0:
        return {"k": 0, "n": 0, "rate": None, "wilson95": None}
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": k / n, "wilson95": [lo, hi]}


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _group(records: list[EpisodeResult]) -> dict[str, Any]:
    diagnosed = [r for r in records if r.diagnosis is not None]
    ps = [r.diagnosis.p_biomass_above_reading for r in diagnosed]
    return {
        "n": len(records),
        "n_diagnosed": len(diagnosed),
        "correct": sum(r.scores.correct for r in records),
        "mean_p_above": _mean(ps),
        "mean_confidence": _mean([max(p, 1 - p) for p in ps]),
        "mean_brier": _mean([r.scores.brier for r in diagnosed]),
        "episodes": [
            {"episode_id": r.episode.episode_id,
             "p_above": r.diagnosis.p_biomass_above_reading if r.diagnosis else None,
             "correct": r.scores.correct, "brier": r.scores.brier}
            for r in records
        ],
    }


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    (alo, ahi), (blo, bhi) = a["wilson95"], b["wilson95"]
    return not (ahi < blo or bhi < alo)


def price_row(price: int, records: list[EpisodeResult]) -> dict[str, Any]:
    primary = [r for r in records if r.status in PRIMARY_STATUSES]
    n = len(primary)
    control = [r for r in primary if r.scores.diagnostic_control]
    no_control = [r for r in primary if not r.scores.diagnostic_control]
    units = sorted(price * r.scores.cost_units for r in primary)
    rejected = sum(1 for r in primary for e in r.events
                   if e.tool == "measure_od" and not e.ok and e.error
                   and "exceeds remaining budget" in e.error)
    row = {
        "price": price,
        "n": n,
        "status_counts": {s: sum(r.status == s for r in records)
                          for s in ("DIAGNOSED", "NO_DIAGNOSIS", "API_FAILURE", "REFUSED")},
        "M1": _kn(sum(r.scores.correct for r in primary), n),
        "M2": _kn(len(control), n),
        "M3": _kn(sum(r.scores.justified for r in primary), n),
        "lucky_correct": _kn(sum(r.scores.correct and not r.scores.diagnostic_control
                                 for r in primary), n),
        "Q1": _kn(sum(r.scores.reconstruction_adequate for r in primary), n),
        "mean_brier": _mean([r.scores.brier for r in primary if r.scores.brier is not None]),
        "replicates": {"mean": _mean([r.scores.cost_units for r in primary]),
                       "max": max((r.scores.cost_units for r in primary), default=None)},
        "units_spent": {"mean": _mean(units), "median": statistics.median(units) if units
                        else None, "max": units[-1] if units else None},
        "budget_rejections": rejected,
        "control": _group(control),
        "no_control": _group(no_control),
        "by_condition": {},
    }
    for cond in sorted({r.episode.condition.value for r in primary}):
        rs = [r for r in primary if r.episode.condition.value == cond]
        row["by_condition"][cond] = {
            "M1": _kn(sum(r.scores.correct for r in rs), len(rs)),
            "M2": _kn(sum(r.scores.diagnostic_control for r in rs), len(rs)),
            "M3": _kn(sum(r.scores.justified for r in rs), len(rs)),
        }
    return row


def _confidence_rule(control: dict, no_control: dict) -> str:
    if no_control["n_diagnosed"] < MIN_NO_CONTROL:
        return f"not assessed (< {MIN_NO_CONTROL} diagnosed no-control episodes)"
    if control["n_diagnosed"] == 0:
        return "not assessed (no control episodes to compare)"
    gap = control["mean_confidence"] - no_control["mean_confidence"]
    verdict = "drop" if gap >= CONF_DROP else f"no drop of >= {CONF_DROP:.2f}"
    return f"{verdict} (control minus no-control mean confidence = {gap:+.3f})"


def analyse(runs: dict[int, Path], c2_frozen: Path | None = None) -> dict[str, Any]:
    records = {p: runner.load_results(d) for p, d in runs.items()}
    by_price = {str(p): price_row(p, rs) for p, rs in sorted(records.items())}
    all_primary = [r for rs in records.values() for r in rs if r.status in PRIMARY_STATUSES]
    pooled = {
        "control": _group([r for r in all_primary if r.scores.diagnostic_control]),
        "no_control": _group([r for r in all_primary if not r.scores.diagnostic_control]),
    }
    prices = sorted(records)
    stop = next((p for p in prices if by_price[str(p)]["n"]
                 and by_price[str(p)]["M2"]["rate"] <= 0.5), None)
    base = by_price[str(prices[0])]
    decision: dict[str, Any] = {"stop_price": stop, "vs_lowest_price": {},
                                "confidence": {}}
    for p in prices[1:]:
        row = by_price[str(p)]
        if not row["n"] or not base["n"]:
            continue
        decision["vs_lowest_price"][str(p)] = {
            m: ("no detectable difference (Wilson intervals overlap)"
                if _overlap(row[m], base[m]) else "detectable difference (no overlap)")
            for m in ("M1", "M2", "M3", "lucky_correct")
        }
    for p in prices:
        row = by_price[str(p)]
        decision["confidence"][str(p)] = _confidence_rule(row["control"], row["no_control"])
    decision["confidence"]["pooled"] = _confidence_rule(pooled["control"], pooled["no_control"])
    out = {"by_price": by_price, "pooled": pooled, "decision": decision}
    if c2_frozen is not None and (c2_frozen / "summary.json").exists():
        s = json.loads((c2_frozen / "summary.json").read_text(encoding="utf-8"))
        ov = s["metrics"]["primary"]["overall"]
        ref = {m: {"k": ov[m]["k"], "n": ov["n"], "wilson95": ov[m]["wilson95"]}
               for m in ("M1", "M2", "M3")}
        out["c2_frozen_reference"] = {"run_id": s["run_id"], **ref, "mean_brier": ov["O1"]}
        if "1" in by_price and by_price["1"]["n"]:
            out["decision"]["p1_vs_c2_frozen"] = {
                m: ("no detectable difference (Wilson intervals overlap)"
                    if _overlap(by_price["1"][m], ref[m]) else "detectable difference")
                for m in ("M1", "M2", "M3")
            }
    return out


def _fmt(kn: dict[str, Any]) -> str:
    if not kn["n"]:
        return "n/a"
    lo, hi = kn["wilson95"]
    return f"{kn['k']}/{kn['n']} [{lo:.2f}, {hi:.2f}]"


def _f(x: float | None, nd: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def render_table(a: dict[str, Any]) -> str:
    lines = [
        "| Price (units/replicate) | n | M1 | M2 (control) | M3 (justified) | Lucky-correct "
        "(M1 & not M2) | Mean Brier | Mean replicates | Mean units | Budget rejections |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for p, r in a["by_price"].items():
        lines.append(
            f"| {p} | {r['n']} | {_fmt(r['M1'])} | {_fmt(r['M2'])} | {_fmt(r['M3'])} | "
            f"{_fmt(r['lucky_correct'])} | {_f(r['mean_brier'])} | "
            f"{_f(r['replicates']['mean'], 2)} | {_f(r['units_spent']['mean'], 2)} | "
            f"{r['budget_rejections']} |")
    lines += [
        "",
        "| Price | Group | n diagnosed | correct | mean p(above) | mean confidence max(p,1-p) "
        "| mean Brier |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    groups = [(p, r) for p, r in a["by_price"].items()] + [("pooled", a["pooled"])]
    for p, r in groups:
        for g in ("control", "no_control"):
            x = r[g]
            lines.append(f"| {p} | {g.replace('_', ' ')} | {x['n_diagnosed']} | {x['correct']} | "
                         f"{_f(x['mean_p_above'])} | {_f(x['mean_confidence'])} | "
                         f"{_f(x['mean_brier'])} |")
    lines += ["", "Per condition (M1 / M2 / M3):", "",
              "| Price | Condition | M1 | M2 | M3 |", "| --- | --- | --- | --- | --- |"]
    for p, r in a["by_price"].items():
        for cond, b in r["by_condition"].items():
            lines.append(f"| {p} | {cond} | {_fmt(b['M1'])} | {_fmt(b['M2'])} | "
                         f"{_fmt(b['M3'])} |")
    return "\n".join(lines) + "\n"


def write_figure(a: dict[str, Any], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    prices = [int(p) for p in a["by_price"]]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    for key, label, marker, dx in (("M2", "M2 diagnostic control", "o", -0.08),
                                   ("M3", "M3 justified", "s", 0.0),
                                   ("lucky_correct", "lucky-correct (M1 & not M2)", "^", 0.08)):
        ys, lo, hi = [], [], []
        for p in prices:
            kn = a["by_price"][str(p)][key]
            ys.append(kn["rate"])
            lo.append(kn["rate"] - kn["wilson95"][0])
            hi.append(kn["wilson95"][1] - kn["rate"])
        ax1.errorbar([p + dx for p in prices], ys, yerr=[lo, hi], marker=marker, capsize=3,
                     label=label)
    ax1.set_xticks(prices, [f"{p}\n({6 // p} affordable)" for p in prices])
    ax1.set_xlabel("price per replicate (units; budget 6)")
    ax1.set_ylabel("rate (Wilson 95 % CI)")
    ax1.set_ylim(-0.05, 1.05)
    ax1.set_title("Price vs diagnostic-control rate")
    ax1.legend(fontsize=8, loc="center left")
    for i, p in enumerate(prices):
        row = a["by_price"][str(p)]
        for g, color, dx in (("control", "tab:blue", -0.1), ("no_control", "tab:red", 0.1)):
            eps = [e for e in row[g]["episodes"] if e["p_above"] is not None]
            xs = [p + dx + 0.02 * ((j % 5) - 2) for j in range(len(eps))]
            ys = [max(e["p_above"], 1 - e["p_above"]) for e in eps]
            ax2.scatter(xs, ys, s=14, color=color, alpha=0.6,
                        label=(g.replace("_", " ") if i == 0 else None))
    ax2.set_xticks(prices)
    ax2.set_xlabel("price per replicate (units)")
    ax2.set_ylabel("stated confidence max(p, 1 - p)")
    ax2.set_ylim(0.45, 1.02)
    ax2.set_title("Stated confidence by episode")
    ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120, metadata={"Software": None})
    plt.close(fig)


def main() -> int:
    from driver import RUNS, run_id_for

    runs = {p: RUNS / run_id_for(p) for p in PRICES}
    a = analyse(runs, C2_FROZEN)
    (HERE / "analysis.json").write_text(json.dumps(a, indent=2, sort_keys=True) + "\n")
    (HERE / "table.md").write_text(render_table(a))
    write_figure(a, HERE / "price_vs_control.png")
    print(render_table(a))
    print(json.dumps(a["decision"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
