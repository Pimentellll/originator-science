"""Summarize saved cost-sensitivity records without re-scoring them."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cost_driver import BUDGET_UNITS, HERE, PRICES, RUNS

from mirage.evaluation import runner
from mirage.evaluation.metrics import PRIMARY_STATUSES, EpisodeResult, wilson

REFERENCE_RUN = runner.ROOT / "experiments" / "results" / "20261004-0049_claude_strong"


def _metric(k: int, n: int) -> dict[str, Any]:
    return {
        "k": k,
        "n": n,
        "rate": k / n if n else None,
        "wilson95": list(wilson(k, n)) if n else None,
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _split(records: list[EpisodeResult]) -> dict[str, dict[str, Any]]:
    out = {}
    for key, control in (("control", True), ("no_control", False)):
        group = [r for r in records if r.scores.diagnostic_control is control]
        diagnosed = [r for r in group if r.diagnosis is not None]
        confidences = [
            max(
                r.diagnosis.p_biomass_above_reading,
                1 - r.diagnosis.p_biomass_above_reading,
            )
            for r in diagnosed
        ]
        briers = [r.scores.brier for r in diagnosed if r.scores.brier is not None]
        out[key] = {
            "n": len(group),
            "mean_confidence": _mean(confidences),
            "mean_brier": _mean(briers),
            "correct_k": sum(r.scores.correct for r in group),
        }
    return out


def _row(
    label: str,
    unit_price: int,
    records: list[EpisodeResult],
    manifest: dict[str, Any],
    summary_path: Path,
) -> dict[str, Any]:
    primary = [r for r in records if r.status in PRIMARY_STATUSES]
    n = len(primary)
    counts = {
        "M1": sum(r.scores.correct for r in primary),
        "M2": sum(r.scores.diagnostic_control for r in primary),
        "M3": sum(r.scores.justified for r in primary),
    }
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for key, value in counts.items():
        assert value == summary["metrics"]["primary"]["overall"].get(key, {}).get("k", 0)
    briers = [r.scores.brier for r in primary if r.scores.brier is not None]
    replicates_mean = _mean([float(r.scores.cost_units) for r in primary])
    return {
        "arm": label,
        "run_id": manifest["run_id"],
        "agent": manifest["agent"],
        "unit_price": unit_price,
        "replicates_affordable": BUDGET_UNITS // unit_price,
        "n": n,
        "M1": _metric(counts["M1"], n),
        "M2": _metric(counts["M2"], n),
        "M3": _metric(counts["M3"], n),
        "lucky": _metric(
            sum(r.scores.correct and not r.scores.diagnostic_control for r in primary),
            n,
        ),
        "replicates_mean": replicates_mean,
        "priced_units_mean": (
            unit_price * replicates_mean if replicates_mean is not None else None
        ),
        "q1_k": sum(r.scores.reconstruction_adequate for r in primary),
        "brier_mean": _mean(briers),
        "status_counts": {
            status: sum(r.status == status for r in records)
            for status in ("DIAGNOSED", "NO_DIAGNOSIS", "API_FAILURE", "REFUSED")
        },
        "budget_rejections": sum(
            event.tool == "measure_od"
            and not event.ok
            and event.error is not None
            and "exceeds remaining budget" in event.error
            for record in records
            for event in record.events
        ),
        "split": _split(primary),
    }


def _load_arm(run_dir: Path, label: str, unit_price: int) -> tuple[dict, list[EpisodeResult]]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    records = runner.load_results(run_dir)
    return (
        _row(label, unit_price, records, manifest, run_dir / "summary.json"),
        records,
    )


def _format_metric(metric: dict[str, Any]) -> str:
    n = metric["n"]
    if n == 0:
        return "0/0 [n/a]"
    low, high = metric["wilson95"]
    return f"{metric['k']}/{n} [{low:.2f}, {high:.2f}]"


def _format_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _render_markdown(rows: list[dict[str, Any]]) -> str:
    headers = (
        "Arm",
        "price",
        "reps affordable",
        "n",
        "M1",
        "M2",
        "M3",
        "lucky (M1∧¬M2)",
        "reps mean",
        "units mean",
        "mean Brier",
        "conf (control / no control)",
    )
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        split = row["split"]
        confidence = (
            f"{_format_optional(split['control']['mean_confidence'])} / "
            f"{_format_optional(split['no_control']['mean_confidence'])}"
        )
        cells = (
            row["arm"],
            f"{row['unit_price']}×",
            str(row["replicates_affordable"]),
            str(row["n"]),
            _format_metric(row["M1"]),
            _format_metric(row["M2"]),
            _format_metric(row["M3"]),
            _format_metric(row["lucky"]),
            _format_optional(row["replicates_mean"]),
            _format_optional(row["priced_units_mean"]),
            _format_optional(row["brier_mean"]),
            confidence,
        )
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _group_claude(
    arms: list[tuple[dict[str, Any], list[EpisodeResult]]],
) -> dict[int, list[EpisodeResult]]:
    grouped: dict[int, list[EpisodeResult]] = {price: [] for price in PRICES}
    for row, records in arms:
        if row["agent"] == "claude":
            grouped.setdefault(row["unit_price"], []).extend(
                record for record in records if record.status in PRIMARY_STATUSES
            )
    return grouped


def _plot(
    rows: list[dict[str, Any]],
    arms: list[tuple[dict[str, Any], list[EpisodeResult]]],
    pooled_claude: dict[int, list[EpisodeResult]],
    out_path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "serif", "figure.facecolor": "white"})
    figure, axis = plt.subplots(figsize=(8, 5), facecolor="white")
    axis.set_facecolor("white")
    x_values = {price: index for index, price in enumerate(PRICES)}
    labels = [f"{price}× ({BUDGET_UNITS // price} reps)" for price in PRICES]

    claude_rows = [row for row in rows if row["agent"] == "claude"]
    m2_x = []
    m2_y = []
    for price in PRICES:
        records = pooled_claude.get(price, [])
        if not records:
            continue
        n = len(records)
        k = sum(record.scores.diagnostic_control for record in records)
        metric = _metric(k, n)
        lo, hi = metric["wilson95"]
        x = x_values[price]
        rate = metric["rate"]
        m2_x.append(x)
        m2_y.append(rate)
        axis.errorbar(
            x,
            rate,
            yerr=[[max(0.0, rate - lo)], [max(0.0, hi - rate)]],
            fmt="o",
            color="black",
            capsize=3,
            label="Claude M2" if not m2_x[:-1] else None,
        )
        m3 = sum(record.scores.justified for record in records) / n
        axis.plot(
            x,
            m3,
            marker="s",
            linestyle="none",
            color="grey",
            label="Claude M3" if x == m2_x[0] else None,
        )
        lucky_k = sum(
            record.scores.correct and not record.scores.diagnostic_control
            for record in records
        )
        lucky = lucky_k / n
        lucky_lo, lucky_hi = wilson(lucky_k, n)
        axis.errorbar(
            x,
            lucky,
            yerr=[
                [max(0.0, lucky - lucky_lo)],
                [max(0.0, lucky_hi - lucky)],
            ],
            fmt="^",
            markerfacecolor="none",
            markeredgecolor="black",
            ecolor="black",
            capsize=3,
            label="Lucky correct" if x == m2_x[0] else None,
        )
    if m2_x:
        axis.plot(m2_x, m2_y, color="black")

    script_x = []
    script_y = []
    for price in PRICES:
        group = [
            record
            for row, records in arms
            if row["agent"] == "good_scientist_priced" and row["unit_price"] == price
            for record in records
            if record.status in PRIMARY_STATUSES
        ]
        if group:
            script_x.append(x_values[price])
            script_y.append(
                sum(record.scores.diagnostic_control for record in group) / len(group)
            )
    if script_x:
        axis.plot(
            script_x,
            script_y,
            linestyle="--",
            color="grey",
            label="PricedGoodScientist M2",
        )

    reference = next(
        (row for row in rows if row["arm"] == "C2 reference (frozen runner, 1x)"),
        None,
    )
    if reference is not None and reference["n"]:
        metric = reference["M2"]
        lo, hi = metric["wilson95"]
        rate = metric["rate"]
        axis.errorbar(
            x_values[PRICES[0]],
            rate,
            yerr=[[max(0.0, rate - lo)], [max(0.0, hi - rate)]],
            fmt="*",
            color="black",
            capsize=3,
            markersize=12,
            label="C2 reference",
        )
    axis.set_xticks(range(len(PRICES)), labels)
    axis.set_ylim(0, 1.05)
    axis.set_ylabel("rate (Wilson 95% CI)")
    title = "Measurement-price sensitivity"
    if not claude_rows:
        title += " — no Claude runs (API key unavailable)"
    axis.set_title(title)
    axis.legend()
    figure.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, facecolor="white")
    plt.close(figure)


def analyze(runs: Path = RUNS, out: Path = HERE) -> dict[str, Any]:
    arms: list[tuple[dict[str, Any], list[EpisodeResult]]] = []
    if runs.exists():
        for run_dir in sorted(runs.iterdir()):
            if not run_dir.is_dir() or run_dir.name == "dev-dryrun":
                continue
            manifest_path = run_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if "unit_price" not in manifest:
                continue
            label = manifest["run_id"]
            arms.append(_load_arm(run_dir, label, manifest["unit_price"]))

    reference, reference_records = _load_arm(
        REFERENCE_RUN,
        "C2 reference (frozen runner, 1x)",
        1,
    )
    reference["agent"] = "claude_c2_reference"
    arms_for_plot = [*arms, (reference, reference_records)]
    rows = [row for row, _ in arms] + [reference]
    pooled = _group_claude(arms)
    pooled_split = _split(
        [record for group in pooled.values() for record in group]
    )
    result = {"rows": rows, "pooled_claude_split": pooled_split}
    out.mkdir(parents=True, exist_ok=True)
    (out / "analysis.json").write_text(
        json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out / "analysis.md").write_text(_render_markdown(rows), encoding="utf-8")
    _plot(rows, arms_for_plot, pooled, out / "price_vs_control.png")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analyze")
    parser.add_argument("--runs", type=Path, default=RUNS)
    parser.add_argument("--out", type=Path, default=HERE)
    args = parser.parse_args(argv)
    analyze(args.runs, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
