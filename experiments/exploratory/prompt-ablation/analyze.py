"""Comparison tables, transcript cue analysis, excerpts, word diffs and figure (REGISTRATION §5).

Reads committed records only (frozen C2 is read, never rescored). Metrics come from each
run's ``summary.json`` written by the frozen ``runner.summarize``; nothing is hand-typed.

Usage (repo root, PYTHONPATH=src):
  .venv/bin/python experiments/exploratory/prompt-ablation/analyze.py \
      --run experiments/exploratory/prompt-ablation/runs/<X1_RUN_ID> \
      [--run experiments/exploratory/prompt-ablation/runs/<X2_RUN_ID>] \
      --out experiments/exploratory/prompt-ablation/analysis
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from mirage.evaluation import runner  # noqa: E402
from mirage.lab import tools as frozen  # noqa: E402

import driver  # noqa: E402
import variants  # noqa: E402

# Registered regex (REGISTRATION §5), case-insensitive.
CEILING_RE = re.compile(
    r"saturat|ceiling|linear range|linearity|non-?linear|proportional|compress|dynamic range"
    r"|upper limit|detection limit|beer.?lambert|under-?(?:read|report|estimat)",
    re.IGNORECASE,
)
D_DIAG_MIN, LATE_LO, LATE_HI = 1.1, 12, 18


def _blocks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return entry.get("response", {}).get("content", []) or []


def visible_texts(transcript: list[dict[str, Any]]) -> list[tuple[int, bool, str]]:
    """(turn, before_first_measure_result, text) for text blocks, declare_state notes and the
    submit_diagnosis rationale. Thinking is redacted by the API and is not included."""
    out: list[tuple[int, bool, str]] = []
    seen_measure = False
    for entry in transcript:
        if entry.get("kind") != "assistant":
            continue
        before = not seen_measure
        for b in _blocks(entry):
            if b.get("type") == "text" and b.get("text"):
                out.append((entry["turn"], before, b["text"]))
            elif b.get("type") == "tool_use":
                args = b.get("input") or {}
                if b.get("name") == "declare_state" and args.get("notes"):
                    out.append((entry["turn"], before, str(args["notes"])))
                elif b.get("name") == "submit_diagnosis" and args.get("rationale"):
                    out.append((entry["turn"], before, str(args["rationale"])))
                elif b.get("name") == "measure_od":
                    seen_measure = True  # its result arrives after this turn
    return out


def episode_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((run_dir / "episodes").glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        texts = visible_texts(rec.get("llm_transcript") or [])
        measures = [e for e in rec["events"] if e["tool"] == "measure_od" and e["ok"]]
        first = measures[0]["arguments"] if measures else None
        diag = rec.get("diagnosis") or {}
        rows.append({
            "episode_id": rec["episode"]["episode_id"],
            "seed": rec["episode"]["seed"],
            "condition": rec["episode"]["condition"],
            "status": rec["status"],
            "correct": rec["scores"]["correct"],
            "control": rec["scores"]["diagnostic_control"],
            "justified": rec["scores"]["justified"],
            "cost_units": rec["scores"]["cost_units"],
            "brier": rec["scores"]["brier"],
            "ceiling_named": any(CEILING_RE.search(t) for _, _, t in texts),
            "ceiling_named_before_evidence": any(CEILING_RE.search(t)
                                                 for _, before, t in texts if before),
            "first_measure": first,
            "first_measure_diagnostic": bool(
                first and LATE_LO <= first["time_h"] <= LATE_HI
                and float(first["dilution_factor"]) >= D_DIAG_MIN),
            "rationale": diag.get("rationale"),
            "diagnosis": diag.get("diagnosis"),
            "p": diag.get("p_biomass_above_reading"),
        })
    rows.sort(key=lambda r: r["seed"])
    return rows


def word_diff(old: str, new: str) -> str:
    """Word-level diff: unchanged words plain, removed [-...-], added {+...+}."""
    a, b = old.split(), new.split()
    out: list[str] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            out.extend(a[i1:i2])
        else:
            if i2 > i1:
                out.append("[-" + " ".join(a[i1:i2]) + "-]")
            if j2 > j1:
                out.append("{+" + " ".join(b[j1:j2]) + "+}")
    return " ".join(out)


def wilson(k: int, n: int) -> tuple[float, float]:
    from mirage.evaluation.metrics import wilson as _w  # frozen implementation
    return tuple(_w(k, n))  # type: ignore[return-value]


def _cell(block: dict[str, Any], name: str) -> str:
    m, n = block[name], block["n"]
    lo, hi = m["wilson95"]
    return f"{m['k']}/{n} [{lo:.2f}, {hi:.2f}]"


def _label(run_dir: Path) -> str:
    man = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    return man["prompt_version"]


def metric_table(runs: list[tuple[str, Path]]) -> str:
    lines = []
    for block_name, title in (("overall", "Overall"), ("BIOLOGICAL_PLATEAU", "BIOLOGICAL_PLATEAU"),
                              ("MEASUREMENT_ARTIFACT", "MEASUREMENT_ARTIFACT")):
        lines += [f"**{title}**", "",
                  "| Configuration | n | M1 correct | M2 control | M3 justified | M4 mean (median, max) | Q1 | Brier (O1) | API_FAILURE / REFUSED |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for label, run_dir in runs:
            s = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))["metrics"]
            b = s["primary"][block_name]
            sc = s["status_counts"]
            m4 = b["M4"]
            q1 = round(b["Q1"] * b["n"])
            lines.append(
                f"| {label} | {b['n']} | {_cell(b, 'M1')} | {_cell(b, 'M2')} | {_cell(b, 'M3')} "
                f"| {m4['mean']:.2f} ({m4['median']:g}, {m4['max']}) | {q1}/{b['n']} "
                f"| {'n/a' if b['O1'] is None else format(b['O1'], '.3f')} | {sc['API_FAILURE']} / {sc['REFUSED']} |")
        lines.append("")
    return "\n".join(lines)


def cue_table(runs: list[tuple[str, Path]]) -> str:
    lines = ["| Configuration | n | Ceiling named (visible text) | Ceiling named before first measurement | First measurement late + diluted (D_diag) |",
             "| --- | --- | --- | --- | --- |"]
    for label, run_dir in runs:
        rows = episode_rows(run_dir)
        n = len(rows)
        cells = []
        for key in ("ceiling_named", "ceiling_named_before_evidence", "first_measure_diagnostic"):
            k = sum(r[key] for r in rows)
            lo, hi = wilson(k, n)
            cells.append(f"{k}/{n} [{lo:.2f}, {hi:.2f}]")
        lines.append(f"| {label} | {n} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def excerpts(label: str, run_dir: Path, max_chars: int = 420) -> list[str]:
    """Registered rule: first BP and first MA episode (seed order), plus first M2 = 0."""
    rows = episode_rows(run_dir)
    picks: list[dict[str, Any]] = []
    for cond in ("BIOLOGICAL_PLATEAU", "MEASUREMENT_ARTIFACT"):
        picks += [r for r in rows if r["condition"] == cond][:1]
    picks += [r for r in rows if not r["control"]][:1]
    out = []
    for r in picks:
        text = (r["rationale"] or "(no rationale)").replace("\n", " ")
        if len(text) > max_chars:
            text = text[:max_chars].rsplit(" ", 1)[0] + " …"
        out.append(f"- **{label}, {r['episode_id']}** (diagnosis {r['diagnosis']}, p = {r['p']}, "
                   f"correct = {r['correct']}, control = {r['control']}): \"{text}\"")
    return out


def prompt_diffs() -> str:
    v2 = variants.PROMPT_V2
    parts = []
    for v in (variants.PROMPT_V2_NOCEILING, variants.PROMPT_V2_MINIMAL):
        parts += [f"#### {v.version} vs prompt-v2", "", f"System prompt:", "", "```text",
                  word_diff(v2.system, v.system), "```", ""]
        changed = []
        for t_old, t_new in zip(v2.tools, v.tools):
            pairs = [(t_old["name"], t_old["description"], t_new["description"])]
            for p, spec in t_old["input_schema"]["properties"].items():
                pairs.append((f"{t_old['name']}.{p}", spec["description"],
                              t_new["input_schema"]["properties"][p]["description"]))
            changed += [(where, o, n) for where, o, n in pairs if o != n]
        if v.assay != v2.assay:
            changed.append(("observation experiment.assay", v2.assay, v.assay))
        if not changed:
            parts += ["Tool definitions and observation: byte-identical to prompt-v2.", ""]
        else:
            parts += ["Tool descriptions and observation:", ""]
            for where, o, n in changed:
                parts += [f"- `{where}`:", "", "  ```text", "  " + word_diff(o, n), "  ```", ""]
    return "\n".join(parts)


def write_figure(runs: list[tuple[str, Path]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = ("M1", "M2", "M3")
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [3, 1.3]})
    width = 0.8 / max(1, len(runs))
    colors = ("#888888", "#F58518", "#4C78A8", "#54A24B")
    for i, (label, run_dir) in enumerate(runs):
        b = json.loads((run_dir / "summary.json").read_text())["metrics"]["primary"]["overall"]
        rates = [b[m]["rate"] for m in names]
        lo = [b[m]["rate"] - b[m]["wilson95"][0] for m in names]
        hi = [b[m]["wilson95"][1] - b[m]["rate"] for m in names]
        xs = [j + (i - (len(runs) - 1) / 2) * width for j in range(len(names))]
        ax.bar(xs, rates, width, yerr=[[max(0, v) for v in lo], [max(0, v) for v in hi]],
               capsize=3, color=colors[i % len(colors)], label=f"{label} (n={b['n']})")
        ax2.bar([i], [b["M4"]["mean"]], 0.6, color=colors[i % len(colors)])
    ax.axhline(0.65, color="k", lw=0.8, ls=":", label="0.65 (H2 threshold)")
    ax.set_xticks(range(len(names)), ["M1 correct", "M2 control", "M3 justified"])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("rate (Wilson 95 % CI)")
    ax.set_title("Sonnet 5.5, effort high, strong matrix (30 episodes)")
    ax.legend(fontsize=8, loc="lower left")
    ax2.set_xticks(range(len(runs)), [r[0] for r in runs], rotation=20, fontsize=8)
    ax2.set_ylabel("M4 mean units (of 6)")
    ax2.set_ylim(0, 6)
    ax2.set_title("Cost")
    fig.tight_layout()
    fig.savefig(path, dpi=120, metadata={"Software": None})
    plt.close(fig)


def build(run_dirs: list[Path], out: Path) -> Path:
    runs = [("prompt-v2 (frozen C2)", driver.FROZEN_C2)] + [(_label(d), d) for d in run_dirs]
    out.mkdir(parents=True, exist_ok=True)
    md = ["# Prompt-ablation comparison (generated by analyze.py)", "",
          "Sources: " + ", ".join(f"`{label}` = `{d.relative_to(runner.ROOT)}`" for label, d in runs),
          "", "## Evaluator metrics (primary denominator)", "", metric_table(runs),
          "## Transcript cue analysis (registered regex, visible text only)", "", cue_table(runs),
          "## Excerpts (registered selection rule)", ""]
    for label, d in runs[1:]:
        md += excerpts(label, d)
    md += ["", "## Word-level prompt diffs", "", prompt_diffs()]
    per_episode = {label: episode_rows(d) for label, d in runs}
    (out / "comparison.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (out / "episodes.json").write_text(json.dumps(per_episode, indent=1, sort_keys=True) + "\n",
                                       encoding="utf-8")
    write_figure(runs, out / "comparison.png")
    return out / "comparison.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="prompt-ablation-analyze")
    ap.add_argument("--run", type=Path, action="append", default=[])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    print(build([p.resolve() for p in args.run], args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
