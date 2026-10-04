"""Compare model/effort configurations with frozen C1/C2 on the strong matrix.

Reads run directories only (episodes, summary.json, usage.jsonl); never rescores frozen runs.
Writes analysis.json, analysis.md and cost_vs_m3.png next to this file.

    PYTHONPATH=src .venv/bin/python experiments/exploratory/model-effort/analyze.py \
        --run X1=experiments/exploratory/model-effort/runs/<id> --run X2=... [--run X3=...]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from mirage.evaluation import metrics, runner

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FROZEN = {
    "C1": ROOT / "experiments/results/20261003-2323_claude_strong",
    "C2": ROOT / "experiments/results/20261004-0049_claude_strong",
}
REFERENCE = {"X1": "C2", "X2": "C2", "X3": "C1"}
LABELS = {
    "C1": "C1 Opus 5.5 high (frozen)",
    "C2": "C2 Sonnet 5.5 high (frozen)",
    "X1": "X1 Haiku 4.5 high",
    "X2": "X2 Sonnet 5.5 low",
    "X3": "X3 Opus 5.5 low",
}
# USD per million tokens (REGISTRATION §6).
PRICES = {
    "claude-haiku-4-5-20251001": (1.0, 5.0, 1.25, 0.10),
    "claude-sonnet-5-5": (2.0, 10.0, 2.50, 0.20),
    "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20),
}
WATCH = "s500028-BP"
CLASSES = (
    "justified",
    "correct_without_control",
    "wrong_after_control",
    "wrong_without_control",
    "NO_DIAGNOSIS",
    "API_FAILURE",
    "REFUSED",
)


def classify(r: metrics.EpisodeResult) -> str:
    if r.status != "DIAGNOSED":
        return r.status
    s = r.scores
    if s.correct:
        return "justified" if s.diagnostic_control else "correct_without_control"
    return "wrong_after_control" if s.diagnostic_control else "wrong_without_control"


def call_cost(line: dict) -> float:
    p_in, p_out, p_cw, p_cr = PRICES[line["model"]]
    return (
        line["input_tokens"] * p_in
        + line["output_tokens"] * p_out
        + line.get("cache_write", 0) * p_cw
        + line.get("cache_read", 0) * p_cr
    ) / 1e6


def usage(run_dir: Path, n_episodes: int) -> dict:
    lines = [
        json.loads(x)
        for x in (run_dir / "usage.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    tin = sum(x["input_tokens"] for x in lines)
    tout = sum(x["output_tokens"] for x in lines)
    usd = sum(call_cost(x) for x in lines)
    return {
        "calls": len(lines),
        "input_tokens": tin,
        "output_tokens": tout,
        "usd": usd,
        "models": sorted({x["model"] for x in lines}),
        "per_episode": {
            "calls": len(lines) / n_episodes,
            "input_tokens": tin / n_episodes,
            "output_tokens": tout / n_episodes,
            "usd": usd / n_episodes,
        },
    }


def _close(a, b, tol: float = 1e-12) -> bool:
    """Equal, except floats may differ by summation-order rounding."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(a - b) <= tol
    return a == b


def analyse_run(run_dir: Path) -> dict:
    records = runner.load_results(run_dir)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    recomputed = json.loads(json.dumps(metrics.aggregate(records)))
    if not _close(recomputed, summary["metrics"]):
        raise ValueError(f"{run_dir}: summary.json disagrees with the evaluator")
    episodes = {}
    for r in records:
        failures = []
        if classify(r) != "justified":
            for m in r.audit:
                fc = metrics.failed_clauses(m, r.episode)
                failures.append({"event_index": m.event_index, **fc})
        d = r.diagnosis
        episodes[r.episode.episode_id] = {
            "condition": r.episode.condition.value,
            "status": r.status,
            "class": classify(r),
            "diagnosis": d.diagnosis if d else None,
            "p_above": d.p_biomass_above_reading if d else None,
            "estimate_od": d.late_biomass_estimate_od if d else None,
            "units": r.scores.cost_units,
            "brier": r.scores.brier,
            "q1": r.scores.reconstruction_adequate,
            "latent_odeq": r.audit[0].latent_biomass_odeq if r.audit else None,
            "failed_clauses": failures,
        }
    prim = summary["metrics"]["primary"]
    return {
        "run_dir": str(run_dir.relative_to(ROOT)),
        "model": manifest.get("model"),
        "effort": manifest.get("effort"),
        "matrix": manifest.get("matrix"),
        "matrix_sha256": manifest.get("matrix_sha256"),
        "n_records": len(records),
        "status_counts": dict(Counter(r.status for r in records)),
        "class_counts": {c: sum(e["class"] == c for e in episodes.values()) for c in CLASSES},
        "primary": prim,
        "itt": summary["metrics"]["intention_to_treat"],
        "usage": usage(run_dir, len(records)),
        "episodes": episodes,
    }


def decide(x: dict, ref: dict) -> str:
    xm, rm = x["primary"]["overall"]["M3"], ref["primary"]["overall"]["M3"]
    if xm["wilson95"][1] < rm["wilson95"][0]:
        return "detectable drop"
    if rm["k"] - xm["k"] >= 3:
        return "lower, worth following up"
    return "no detectable difference at n = 30"


def failure_vocabulary(a: dict) -> set[str]:
    out = set()
    for e in a["episodes"].values():
        if e["class"] != "justified":
            out.add(f"class:{e['class']}")
        for f in e["failed_clauses"]:
            out.update(f"M2:{c}" for c in f["M2"])
            out.update(f"Q1:{c}" for c in f["Q1"])
    return out


def fmt_k(block: dict, key: str) -> str:
    m = block[key]
    lo, hi = m["wilson95"]
    return f"{m['k']}/{block['n']} [{lo:.2f}, {hi:.2f}]"


def render_md(res: dict) -> str:
    keys = [k for k in ("C1", "C2", "X1", "X2", "X3") if k in res["runs"]]
    out = [
        "# Model/effort analysis (generated by analyze.py)",
        "",
        "Primary analysis, strong matrix (n = scored episodes). Wilson 95 % intervals.",
        "",
        "| Config | Model | Effort | M1 | M2 | M3 | M4 mean | Q1 | Brier | in tok/ep"
        " | out tok/ep | calls/ep | USD/ep | USD total |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for k in keys:
        a = res["runs"][k]
        o = a["primary"]["overall"]
        u = a["usage"]
        q1k = round(o["Q1"] * o["n"])
        out.append(
            f"| {LABELS[k]} | {a['model']} | {a['effort']} | {fmt_k(o, 'M1')} | "
            f"{fmt_k(o, 'M2')} | {fmt_k(o, 'M3')} | {o['M4']['mean']:.2f} | {q1k}/{o['n']} | "
            f"{o['O1']:.3f} | {u['per_episode']['input_tokens']:,.0f} | "
            f"{u['per_episode']['output_tokens']:,.0f} | {u['per_episode']['calls']:.2f} | "
            f"{u['per_episode']['usd']:.4f} | {u['usd']:.3f} |"
        )
    out += ["", "## M3 by condition", "", "| Config | BP M3 | MA M3 |", "|---|---|---|"]
    for k in keys:
        p = res["runs"][k]["primary"]
        out.append(
            f"| {k} | {fmt_k(p['BIOLOGICAL_PLATEAU'], 'M3')} | "
            f"{fmt_k(p['MEASUREMENT_ARTIFACT'], 'M3')} |"
        )
    out += ["", "## Episode classes (audit breakdown)", "",
            "| Config | " + " | ".join(CLASSES) + " |",
            "|---|" + "---|" * len(CLASSES)]
    for k in keys:
        cc = res["runs"][k]["class_counts"]
        out.append(f"| {k} | " + " | ".join(str(cc[c]) for c in CLASSES) + " |")
    out += ["", "## Non-justified episodes", ""]
    for k in keys:
        for eid, e in res["runs"][k]["episodes"].items():
            if e["class"] == "justified":
                continue
            clauses = "; ".join(
                f"ev{f['event_index']}: M2 {f['M2'] or 'ok'}, Q1 {f['Q1'] or 'ok'}"
                for f in e["failed_clauses"]
            ) or "no measurements"
            out.append(
                f"- {k} {eid}: {e['class']}, answer {e['diagnosis']}, p_above {e['p_above']}, "
                f"estimate {e['estimate_od']}, units {e['units']}. Clauses: {clauses}"
            )
    out += ["", "## Q1 failures in any class (post hoc, descriptive; not in REGISTRATION §5)", ""]
    for k in keys:
        for eid, e in res["runs"][k]["episodes"].items():
            if e["q1"] is False:
                latent = e["latent_odeq"]
                out.append(
                    f"- {k} {eid}: {e['class']}, estimate {e['estimate_od']}, true late biomass "
                    f"{'n/a' if latent is None else f'{latent:.2f}'} OD-eq"
                )
    out += ["", f"## {WATCH}", ""]
    for k in keys:
        e = res["runs"][k]["episodes"].get(WATCH)
        out.append(f"- {k}: " + (
            "not run" if e is None else
            f"{e['class']}, answer {e['diagnosis']}, p_above {e['p_above']}, "
            f"estimate {e['estimate_od']}"
        ))
    out += ["", "## Decision rule (REGISTRATION §5)", ""]
    for k, ref in res["decisions"].items():
        out.append(f"- {k} vs {ref['reference']}: **{ref['verdict']}**")
    out += ["", "## New failure types (not seen in C1 or C2)", ""]
    for k, new in res["new_failure_types"].items():
        out.append(f"- {k}: {', '.join(new) if new else 'none'}")
    return "\n".join(out) + "\n"


def write_figure(res: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "serif", "font.size": 9})
    fig, ax = plt.subplots(figsize=(5.2, 3.6), dpi=200)
    for k, a in res["runs"].items():
        m3 = a["primary"]["overall"]["M3"]
        x = a["usage"]["per_episode"]["usd"]
        lo, hi = m3["wilson95"]
        frozen = k.startswith("C")
        ax.errorbar(
            x, m3["rate"], yerr=[[m3["rate"] - lo], [hi - m3["rate"]]], fmt="o" if frozen else "s",
            color="0.45" if frozen else "black", mfc="white" if frozen else "black",
            capsize=3, lw=0.8,
        )
        ax.annotate(f"{LABELS[k]}\n{m3['k']}/{a['primary']['overall']['n']}", (x, m3["rate"]),
                    textcoords="offset points", xytext=(6, -14), fontsize=7)
    ax.set_xscale("log")
    xs = [a["usage"]["per_episode"]["usd"] for a in res["runs"].values()]
    ax.set_xlim(min(xs) * 0.7, max(xs) * 2.5)
    ax.set_xlabel("Estimated API cost per episode (USD, log scale)")
    ax.set_ylabel("M3, justified diagnosis (rate)")
    ax.set_ylim(0, 1.05)
    ax.set_title("Strong matrix (n = 30): cost vs justified diagnosis, Wilson 95 % CI", fontsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


def analyse(runs: dict[str, Path]) -> dict:
    res = {"runs": {k: analyse_run(p) for k, p in {**FROZEN, **runs}.items()}}
    seen = failure_vocabulary(res["runs"]["C1"]) | failure_vocabulary(res["runs"]["C2"])
    res["decisions"] = {
        k: {"reference": REFERENCE[k], "verdict": decide(res["runs"][k], res["runs"][REFERENCE[k]])}
        for k in runs
    }
    res["new_failure_types"] = {
        k: sorted(failure_vocabulary(res["runs"][k]) - seen) for k in runs
    }
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", default=[], help="CONFIG=RUN_DIR")
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args(argv)
    runs = {}
    for spec in args.run:
        k, p = spec.split("=", 1)
        if k not in REFERENCE:
            raise SystemExit(f"unknown config {k}")
        runs[k] = (ROOT / p).resolve() if not Path(p).is_absolute() else Path(p)
    res = analyse(runs)
    (args.out / "analysis.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    (args.out / "analysis.md").write_text(render_md(res), encoding="utf-8")
    write_figure(res, args.out / "cost_vs_m3.png")
    print(render_md(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
