"""Read-only export of a finished benchmark run into the BASELINE V1 artifact set.

Nothing is re-simulated or re-scored with a different result: the per-episode privileged
evaluations written by the run are loaded, the aggregate is rebuilt from them and must equal
the aggregate the run itself wrote (otherwise the export refuses), and the derived files are
written beside the untouched raw outputs.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mirage.evaluation.campaign.aggregate import build_benchmark_summary
from mirage.evaluation.campaign.config import EvaluatorConfig
from mirage.evaluation.campaign.evaluator import CampaignEvaluation

LABEL = "BASELINE V1"
BASELINE_POLICIES = ("random", "fixed_pipeline", "greedy_eig")
POLICY_IMPLEMENTATIONS = {
    "random": "mirage.policies.RandomPolicy",
    "fixed_pipeline": "mirage.policies.FixedPipelinePolicy",
    "greedy_eig": "mirage.policies.GreedyEIGPolicy",
}
# Rates shown in the headline table: (title, GroupSummary field)
HEADLINE_RATES = (
    ("correct", "correct"),
    ("justified", "justified"),
    ("correct-but-unjustified", "lucky_correct"),
    ("justified abstention", "justified_abstention"),
    ("localisation acc.", "localisation_accuracy"),
)
HEADLINE_MEANS = (
    ("budget", "mean_budget_spent"),
    ("sample", "mean_sample_used"),
    ("time", "mean_time_elapsed"),
    ("experiments", "mean_experiments"),
)


class ExportMismatch(RuntimeError):
    """The rebuilt aggregate disagrees with the aggregate the run wrote."""


def _json_values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left == right
    if isinstance(left, float) or isinstance(right, float):
        return (
            type(left) is float
            and type(right) is float
            and math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and left.keys() == right.keys()
            and all(_json_values_equal(left[key], right[key]) for key in left)
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_json_values_equal(a, b) for a, b in zip(left, right))
        )
    return type(left) is type(right) and left == right


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dump(path: Path, obj: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    return path


def load_evaluations(privileged_dir: Path) -> list[CampaignEvaluation]:
    files = sorted((privileged_dir / "episodes").glob("*.json"))
    return [CampaignEvaluation.model_validate_json(f.read_text()) for f in files]


def _pct(rate: dict[str, Any]) -> str:
    if rate["rate"] is None:
        return "n/a"
    return f"{100 * rate['rate']:.0f}% [{100 * rate['lo']:.0f}-{100 * rate['hi']:.0f}] ({rate['k']}/{rate['n']})"


def _num(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def headline_markdown(summary: dict[str, Any]) -> str:
    """Tables generated purely from the summary numbers."""
    lines = [f"# {LABEL}: headline results (held-out worlds; 95% Wilson intervals)", ""]
    for scope, key in (("Overall", None), ("Per regime", "by_regime"), ("Per archetype", "by_archetype")):
        groups = ["all"] if key is None else sorted(next(iter(summary["policies"].values()))[key])
        lines += [f"## {scope}", ""]
        for group in groups:
            if key is not None:
                lines += [f"### {group}", ""]
            header = ["policy", "n"] + [t for t, _ in HEADLINE_RATES] + [t for t, _ in HEADLINE_MEANS]
            lines += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            for policy, body in sorted(summary["policies"].items()):
                g = body["overall"] if key is None else body[key][group]
                cells = [policy, str(g["n_episodes"])]
                cells += [_pct(g[f]) for _, f in HEADLINE_RATES]
                cells += [_num(g[f]) for _, f in HEADLINE_MEANS]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
    return "\n".join(lines) + "\n"


def export_baseline(
    *,
    results_dir: Path,
    out_dir: Path,
    seed_split: dict[str, Sequence[int]],
    reserved_train_seeds: tuple[int, int],
    evaluator_config: EvaluatorConfig | None = None,
) -> dict[str, Path]:
    """Write the BASELINE V1 artifact set to ``out_dir``. Returns name -> path."""
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise ExportMismatch(f"output directory already exists and is not empty: {out_dir}")

    main = results_dir / "binder_campaign_benchmark.json"
    doc = json.loads(main.read_text())
    root = results_dir / "binder_campaign"
    evaluations = load_evaluations(root / "privileged")
    manifest = doc["manifest"]
    if len(evaluations) != doc["run"]["episodes"]:
        raise ExportMismatch(f"{len(evaluations)} stored evaluations, run reports {doc['run']['episodes']}")

    rebuilt = json.loads(build_benchmark_summary(manifest["benchmark_id"], evaluations).model_dump_json())
    if not _json_values_equal(rebuilt, doc["summary"]):
        raise ExportMismatch("aggregate rebuilt from per-episode evaluations differs from the run's aggregate")

    policies = sorted(doc["summary"]["policies"])
    if tuple(policies) != tuple(sorted(BASELINE_POLICIES)):
        raise ExportMismatch(f"unexpected policy set {policies}")

    held_out = list(seed_split["held_out"])
    used = sorted({e.seed for e in evaluations})
    if used != sorted(manifest["seeds"]) or any(s not in held_out for s in used):
        raise ExportMismatch("evaluated seeds are not exactly the manifest's held-out seeds")
    if set(seed_split["development"]) & set(held_out):
        raise ExportMismatch("development and held-out seeds overlap")
    lo, hi = reserved_train_seeds
    if any(lo <= s <= hi for s in (*seed_split["development"], *held_out)):
        raise ExportMismatch("reserved training range overlaps development/held-out seeds")

    summary = doc["summary"]
    written: dict[str, Path] = {}
    written["aggregate"] = _dump(out_dir / "aggregate.json", {
        "label": LABEL, "benchmark_id": manifest["benchmark_id"], "evaluator_version": summary["evaluator_version"],
        "seeds": summary["seeds"],
        "policies": {p: body["overall"] for p, body in summary["policies"].items()},
    })
    written["by_archetype"] = _dump(out_dir / "by_archetype.json", {
        "label": LABEL, "policies": {p: body["by_archetype"] for p, body in summary["policies"].items()}})
    written["by_regime"] = _dump(out_dir / "by_regime.json", {
        "label": LABEL,
        "regimes": "myopic=instability; path_dependent=aggregation_kinetic_defect; invalid=broken_assay+invalid_biological_model; adversarial=misleading_proxy_trap",
        "policies": {p: body["by_regime"] for p, body in summary["policies"].items()}})
    written["by_scenario_class"] = _dump(out_dir / "by_scenario_class.json", {
        "label": LABEL, "policies": {p: body["by_scenario_class"] for p, body in summary["policies"].items()}})
    written["paired_differences"] = _dump(out_dir / "paired_differences.json", {
        "label": LABEL,
        "definition": "mean(A - B) over identical (archetype, seed) worlds; seeded percentile bootstrap, 2000 resamples, 95% interval",
        "comparisons": doc["paired_comparisons"]})

    seed_manifest = {
        "label": LABEL,
        "development": list(seed_split["development"]),
        "held_out": held_out,
        "held_out_used_per_archetype": len(used),
        "held_out_used": used,
        "held_out_unused_reserve": [s for s in held_out if s not in used],
        "train_reserved_range_inclusive": list(reserved_train_seeds),
        "notes": [
            "Baseline policies (Random, FixedPipeline, GreedyEIG) do not train; no training seeds were used.",
            "The train range is reserved for learned policies (PPO) and is disjoint from development and held-out.",
            "Only held-out seeds are reported. Later policies must be evaluated on held_out_used for every archetype.",
        ],
    }
    written["seed_manifest"] = _dump(out_dir / "seed_manifest.json", seed_manifest)

    # Strong world identity for appended policies. The run predates the digest field, so the
    # digests are recomputed from seeds alone (environment reset only; no policy is re-run).
    from mirage.evaluation.campaign.harness import Archetype
    from mirage.evaluation.campaign.privileged_binder import world_digests

    digests = world_digests([Archetype(a) for a in manifest["archetypes"]], used)
    written["world_digests"] = _dump(out_dir / "world_digests.json", {
        "label": LABEL,
        "environment": manifest["scenario_version"],
        "definition": "sha256 of the root BinderHypothesis of each seeded world; appended runs must reproduce these exactly",
        "public_initial_state_fingerprints_identical_across_seeds": len(set(manifest["world_fingerprints"].values())) == 1,
        "digests": digests,
    })

    eval_path = out_dir / "evaluations.jsonl"
    eval_path.write_text("".join(e.model_dump_json() + "\n" for e in sorted(evaluations, key=lambda e: e.episode_id)))
    written["evaluations"] = eval_path

    completed = dt.datetime.fromtimestamp(main.stat().st_mtime, tz=dt.timezone.utc).isoformat()
    cfg = evaluator_config or EvaluatorConfig()
    written["markdown"] = out_dir / "RESULTS.md"
    written["markdown"].write_text(headline_markdown(summary))

    meta = {
        "label": LABEL,
        "benchmark_id": manifest["benchmark_id"],
        "policies": {
            p: {"implementation": POLICY_IMPLEMENTATIONS[p], "config": manifest["policies"][p],
                "code_version": manifest["code_version"]}
            for p in policies
        },
        "git_sha": manifest["code_version"],
        "evaluator": {"version": manifest["evaluator_version"], "config": json.loads(cfg.model_dump_json()),
                      "label_rules": doc["label_rules"]},
        "environment": {"id": manifest["environment_id"], "scenario_version": manifest["scenario_version"],
                        "split": manifest["split"], "max_steps": manifest["max_steps"]},
        "belief": doc["belief"],
        "episode_count": len(evaluations),
        "worlds": len(manifest["world_fingerprints"]),
        "archetypes": manifest["archetypes"],
        "worlds_per_archetype": len(used),
        "run_completed_at_utc": completed,
        "exported_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "run_wall_seconds": doc["run"]["wall_seconds"],
        "incidents": doc["incident_counts"],
        "incident_total": len(manifest["incidents"]),
        "raw": {"public_traces": str(root / "public"), "privileged_evaluations": str(root / "privileged"),
                "showcase_replays": str(root / "showcase"), "run_document": str(main)},
        "files": {name: {"path": str(path), "sha256": _sha256(path)} for name, path in sorted(written.items())},
        "run_document_sha256": _sha256(main),
    }
    written["manifest"] = _dump(out_dir / "MANIFEST.json", meta)
    return written
