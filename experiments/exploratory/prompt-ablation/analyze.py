"""Compare prompt-ablation arms with frozen C2: evaluator metrics, ceiling identification (C-id),
transcript excerpts and a figure. Reads run directories only; writes only to --out.

    PYTHONPATH=src .venv/bin/python experiments/exploratory/prompt-ablation/analyze.py \
        --arm "C2 prompt-v2=experiments/results/20261004-0049_claude_strong" \
        --arm "A1 prompt-v2-noceiling=experiments/exploratory/prompt-ablation/runs/<RUN_ID>" \
        --out experiments/exploratory/prompt-ablation/analysis
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from mirage.evaluation.metrics import wilson

# Pre-registered in REGISTRATION.md §5; do not edit.
CID_PATTERN = re.compile(
    r"saturat|ceiling|linear(ity| range| regime| response)?|non-?linear|nonproportional"
    r"|non-proportional|proportional|dynamic range|upper limit|detection limit|detector limit"
    r"|compress|out of range|beer.?lambert|underestimat|under-?report|under-?read",
    re.IGNORECASE,
)
PROPORTIONAL = re.compile(r"nonproportional|non-proportional|proportional", re.IGNORECASE)
METRICS = ("M1", "M2", "M3")


def visible_text(episode: dict[str, Any]) -> list[str]:
    """Rationale, assistant text blocks and declare_state notes (thinking excluded)."""
    parts: list[str] = []
    for entry in episode.get("llm_transcript") or []:
        if entry.get("kind") != "assistant":
            continue
        for block in entry["response"]["content"]:
            if block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
            elif block.get("type") == "tool_use" and block.get("name") == "declare_state":
                notes = (block.get("input") or {}).get("notes")
                if notes:
                    parts.append(notes)
    diagnosis = episode.get("diagnosis")
    if diagnosis and diagnosis.get("rationale"):
        parts.append(diagnosis["rationale"])
    return parts


def cid_hit(text: str, *, strict: bool) -> bool:
    """strict=True ignores matches that are only 'proportional' terms (may echo tool text T4)."""
    for m in CID_PATTERN.finditer(text):
        if not (strict and PROPORTIONAL.fullmatch(m.group(0))):
            return True
    return False


def load_episodes(run_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((run_dir / "episodes").glob("*.json"))]


def kn(k: int, n: int) -> dict[str, Any]:
    lo, hi = wilson(k, n) if n else (0.0, 1.0)
    return {"k": k, "n": n, "wilson95": [lo, hi]}


def analyze_run(run_dir: Path) -> dict[str, Any]:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    episodes = load_episodes(run_dir)
    cid: dict[str, Any] = {}
    for group in ("overall", "BIOLOGICAL_PLATEAU", "MEASUREMENT_ARTIFACT"):
        eps = [e for e in episodes if e["status"] == "DIAGNOSED"
               and (group == "overall" or e["episode"]["condition"] == group)]
        texts = ["\n".join(visible_text(e)) for e in eps]
        cid[group] = {
            "any": kn(sum(cid_hit(t, strict=False) for t in texts), len(texts)),
            "strict": kn(sum(cid_hit(t, strict=True) for t in texts), len(texts)),
        }
    return {
        "run_id": manifest["run_id"], "model": manifest.get("model"),
        "prompt_version": manifest.get("prompt_version"),
        "prompt_sha256": manifest.get("prompt_sha256"),
        "episode_ids": summary["episode_ids"], "metrics": summary["metrics"], "cid": cid,
    }


def fmt_kn(d: dict[str, Any]) -> str:
    lo, hi = d["wilson95"]
    return f"{d['k']}/{d['n']} [{lo:.2f}, {hi:.2f}]"


def table(results: dict[str, dict[str, Any]]) -> str:
    head = ("| Arm | group | M1 | M2 | M3 | M4 mean (median, max) | Q1 | mean Brier "
            "| C-id | C-id strict | status |")
    lines = [head, "| " + " | ".join(["---"] * 11) + " |"]
    for label, r in results.items():
        status = ", ".join(f"{k} {v}" for k, v in r["metrics"]["status_counts"].items() if v)
        for group in ("overall", "BIOLOGICAL_PLATEAU", "MEASUREMENT_ARTIFACT"):
            m = r["metrics"]["primary"][group]
            n = m["n"]
            cells = [fmt_kn({"k": m[k]["k"], "n": n, "wilson95": m[k]["wilson95"]})
                     for k in METRICS]
            m4 = m["M4"]
            brier = "n/a" if m["O1"] is None else f"{m['O1']:.3f}"
            q1 = "n/a" if m["Q1"] is None else f"{round(m['Q1'] * n)}/{n}"
            lines.append(
                f"| {label} | {'BP' if group == 'BIOLOGICAL_PLATEAU' else 'MA' if group == 'MEASUREMENT_ARTIFACT' else 'all'} | "
                + " | ".join(cells)
                + f" | {m4['mean']:.2f} ({m4['median']:g}, {m4['max']}) | {q1} | {brier} | "
                + f"{fmt_kn(r['cid'][group]['any'])} | {fmt_kn(r['cid'][group]['strict'])} | "
                + f"{status if group == 'overall' else ''} |"
            )
    return "\n".join(lines) + "\n"


def figure(results: dict[str, dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = ["M1", "M2", "M3", "C-id (MA, strict)"]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    width = 0.8 / max(len(results), 1)
    for i, (label, r) in enumerate(results.items()):
        m = r["metrics"]["primary"]["overall"]
        cells = [(m[k]["k"], m["n"], m[k]["wilson95"]) for k in METRICS]
        c = r["cid"]["MEASUREMENT_ARTIFACT"]["strict"]
        cells.append((c["k"], c["n"], c["wilson95"]))
        xs = [j + (i - (len(results) - 1) / 2) * width for j in range(len(names))]
        rates = [k / n if n else 0.0 for k, n, _ in cells]
        err = [[max(0.0, r_ - ci[0]) for r_, (_, _, ci) in zip(rates, cells)],
               [max(0.0, ci[1] - r_) for r_, (_, _, ci) in zip(rates, cells)]]
        ax.bar(xs, rates, width, yerr=err, capsize=3, label=label)
    ax.set_xticks(range(len(names)), names)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("rate (Wilson 95% CI)")
    ax.set_title("Claude Sonnet 5.5, strong matrix (n = 30; C-id over MA, n = 15)")
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, metadata={"Software": None})
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="append", required=True, help="LABEL=RUN_DIR")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    results = {}
    for spec in args.arm:
        label, _, path = spec.partition("=")
        results[label] = analyze_run(Path(path))
    ids = {tuple(r["episode_ids"]) for r in results.values()}
    if len(ids) != 1:
        raise SystemExit("arms do not cover the same episodes")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "comparison.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out / "comparison.md").write_text(table(results), encoding="utf-8")
    figure(results, args.out / "comparison.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
