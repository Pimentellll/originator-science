"""BASELINE V1 export: read-only, self-consistent, no placeholders in numeric tables."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from mirage.evaluation.campaign.aggregate import EvaluationStore
from mirage.evaluation.campaign.baseline_export import (
    ExportMismatch,
    _json_values_equal,
    export_baseline,
)
from mirage.evaluation.campaign.binder_benchmark import (
    BenchmarkConfig,
    export_showcase_replays,
    result_document,
    run_binder_benchmark,
)
from mirage.evaluation.campaign.harness import SeedSplit
from mirage.provenance import PublicRecordStore

SPLIT = SeedSplit(development=(1, 2), held_out=(70000, 70001, 70002))
SMALL = BenchmarkConfig(n_particles=64, eig_samples=8, max_steps=20)
SEEDS = {"development": SPLIT.development, "held_out": SPLIT.held_out}
ROOT = Path(__file__).resolve().parents[2]


def test_json_summary_comparison_tolerates_only_tiny_float_differences():
    assert _json_values_equal({"rate": 0.25}, {"rate": 0.25 + 5e-13})
    assert not _json_values_equal({"rate": 0.25}, {"rate": 0.25 + 1e-6})
    assert not _json_values_equal({"rates": [0.25, 0.5]}, {"rates": [0.25]})
    assert not _json_values_equal({"flag": True}, {"flag": 1})


@pytest.fixture(scope="module")
def finished(tmp_path_factory):
    results = tmp_path_factory.mktemp("results")
    root = results / "binder_campaign"
    run = run_binder_benchmark(
        benchmark_id="tiny", split=SPLIT, split_name="held_out", per_archetype=2, config=SMALL, code_version="abc1234",
        record_store=PublicRecordStore(root / "public"), evaluation_store=EvaluationStore(root / "privileged"),
    )
    replays, seed = export_showcase_replays(run, root / "showcase")
    doc = result_document(run, SMALL, replay_paths=replays)
    doc["run"] = {"episodes": len(run.evaluations), "wall_seconds": 1.0, "showcase_seed": seed}
    (results / "binder_campaign_benchmark.json").write_text(json.dumps(doc))
    return results, run


def test_export_writes_every_artifact_and_a_complete_manifest(finished, tmp_path):
    results, run = finished
    before = (results / "binder_campaign_benchmark.json").read_bytes()
    written = export_baseline(results_dir=results, out_dir=tmp_path / "v1", seed_split=SEEDS, reserved_train_seeds=(100_000, 199_999))
    assert {"aggregate", "world_digests", "by_archetype", "by_regime", "paired_differences", "seed_manifest", "evaluations", "manifest", "markdown"} <= set(written)
    manifest = json.loads(written["manifest"].read_text())
    for key in ("label", "git_sha", "evaluator", "environment", "episode_count", "run_completed_at_utc", "exported_at_utc", "policies"):
        assert key in manifest
    assert manifest["label"] == "BASELINE V1" and manifest["git_sha"] == "abc1234"
    assert manifest["episode_count"] == len(run.evaluations) == 30
    assert set(manifest["policies"]) == {"random", "fixed_pipeline", "greedy_eig"}
    assert manifest["evaluator"]["version"] == "campaign-eval/1"
    assert (results / "binder_campaign_benchmark.json").read_bytes() == before  # raw run untouched
    assert len(written["evaluations"].read_text().splitlines()) == 30


def test_seed_manifest_is_exact_and_disjoint(finished, tmp_path):
    results, _ = finished
    written = export_baseline(results_dir=results, out_dir=tmp_path / "v1", seed_split=SEEDS, reserved_train_seeds=(100_000, 199_999))
    seeds = json.loads(written["seed_manifest"].read_text())
    assert seeds["development"] == [1, 2] and seeds["held_out"] == [70000, 70001, 70002]
    assert seeds["held_out_used"] == [70000, 70001] and seeds["held_out_unused_reserve"] == [70002]
    assert not set(seeds["development"]) & set(seeds["held_out"])


def test_no_unavailable_policy_appears_in_numeric_outputs(finished, tmp_path):
    results, _ = finished
    written = export_baseline(results_dir=results, out_dir=tmp_path / "v1", seed_split=SEEDS, reserved_train_seeds=(100_000, 199_999))
    for name in ("aggregate", "by_archetype", "by_regime", "paired_differences", "markdown"):
        text = written[name].read_text().lower()
        assert "lookahead" not in text and not re.search(r"\bppo\b", text), name


def test_per_regime_and_paired_outputs_have_the_expected_shape(finished, tmp_path):
    results, _ = finished
    written = export_baseline(results_dir=results, out_dir=tmp_path / "v1", seed_split=SEEDS, reserved_train_seeds=(100_000, 199_999))
    regimes = json.loads(written["by_regime"].read_text())["policies"]["greedy_eig"]
    assert set(regimes) == {"myopic", "path_dependent", "invalid", "adversarial"}
    paired = json.loads(written["paired_differences"].read_text())["comparisons"]
    assert len(paired) == 3
    justified = next(d for d in paired[0]["diffs"] if d["metric"] == "justified")
    assert {"mean_diff", "lo", "hi", "n"} <= set(justified) and justified["n"] == 10


def test_export_refuses_when_aggregate_does_not_match_episodes(finished, tmp_path):
    results, _ = finished
    doc = json.loads((results / "binder_campaign_benchmark.json").read_text())
    doc["summary"]["policies"]["random"]["overall"]["correct"]["k"] += 1
    tampered = tmp_path / "t"
    (tampered).mkdir()
    (tampered / "binder_campaign_benchmark.json").write_text(json.dumps(doc))
    (tampered / "binder_campaign").symlink_to(results / "binder_campaign")
    with pytest.raises(ExportMismatch):
        export_baseline(results_dir=tampered, out_dir=tmp_path / "o", seed_split=SEEDS, reserved_train_seeds=(100_000, 199_999))


def test_export_refuses_overlapping_or_foreign_seeds(finished, tmp_path):
    results, _ = finished
    with pytest.raises(ExportMismatch):
        export_baseline(results_dir=results, out_dir=tmp_path / "a", seed_split={"development": [1, 70000], "held_out": [70000, 70001, 70002]}, reserved_train_seeds=(100_000, 199_999))
    with pytest.raises(ExportMismatch):
        export_baseline(results_dir=results, out_dir=tmp_path / "b", seed_split={"development": [1], "held_out": [70000]}, reserved_train_seeds=(100_000, 199_999))
    with pytest.raises(ExportMismatch):
        export_baseline(results_dir=results, out_dir=tmp_path / "c", seed_split=SEEDS, reserved_train_seeds=(60_000, 80_000))


def test_export_refuses_nonempty_output_directory(finished, tmp_path):
    results, _ = finished
    out = tmp_path / "existing"
    out.mkdir()
    marker = out / "preserve.txt"
    marker.write_text("keep")

    with pytest.raises(ExportMismatch, match="output directory already exists and is not empty"):
        export_baseline(results_dir=results, out_dir=out, seed_split=SEEDS, reserved_train_seeds=(100_000, 199_999))

    assert marker.read_text() == "keep"


def test_export_cli_requires_output_directory():
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_baseline_v1.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "the following arguments are required: --out" in result.stderr


def test_world_digests_are_exported_for_every_baseline_world(finished, tmp_path):
    results, run = finished
    written = export_baseline(results_dir=results, out_dir=tmp_path / "v1", seed_split=SEEDS, reserved_train_seeds=(100_000, 199_999))
    exported = json.loads(written["world_digests"].read_text())["digests"]
    assert exported == run.manifest.world_digests and len(exported) == 10
