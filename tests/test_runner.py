import json
import shutil
from pathlib import Path

import pytest

from mirage.config import canonical_sha256, load_prior
from mirage.evaluation import runner
from mirage.evaluation.metrics import EpisodeResult, audit_measurements, score_episode
from mirage.evaluation.passive import REFERENCE_SEEDS

ROOT = Path(__file__).resolve().parents[1]
PRIOR = load_prior(runner.SCENARIO)
SHA = canonical_sha256(PRIOR)


def fixture_gate0(path: Path, sha: str = SHA) -> Path:
    """FIXTURE Gate 0 summary (T-032 D_diag [1.5, 100]); the real one does not exist yet."""
    path.write_text(json.dumps({
        "schema_version": "gate0-summary-v2", "scenario_sha256": sha,
        "diagnostic_action_set": {"scenario_sha256": sha, "late_window_h": [12, 18], "d_min": 1.5,
                                  "d_max": 100.0, "auroc_threshold": 0.95,
                                  "evaluated_replicates": 1}}), encoding="utf-8")
    return path


def small_matrix(tmp: Path, n: int = 10) -> Path:
    eps = [{"seed": s, "condition": "BIOLOGICAL_PLATEAU" if i % 2 == 0 else "MEASUREMENT_ARTIFACT"}
           for i, s in enumerate(range(900_000, 900_000 + n))]
    p = tmp / "matrix.json"
    p.write_text(json.dumps({"matrices": {"t": {"episodes": eps}}}), encoding="utf-8")
    return p


def go(tmp: Path, out: str, n: int = 20, agent: str = "good_scientist", run_id: str = "r") -> Path:
    return runner.run(agent, "t", tmp / out, matrix=small_matrix(tmp, n),
                      gate0_summary=fixture_gate0(tmp / "g0.json"), run_id=run_id,
                      reference_seeds=REFERENCE_SEEDS[:5000])


def strip_meta(path: Path) -> str:
    d = json.loads(path.read_text(encoding="utf-8"))
    d.pop("run_meta")
    return json.dumps(d, sort_keys=True)


def test_t017_reproducible_records(tmp_path) -> None:
    a, b = go(tmp_path, "a"), go(tmp_path, "b")
    fa = sorted((a / "episodes").glob("*.json"))
    fb = sorted((b / "episodes").glob("*.json"))
    assert [f.name for f in fa] == [f.name for f in fb] and len(fa) == 20
    for x, y in zip(fa, fb):
        assert strip_meta(x) == strip_meta(y)
        r = EpisodeResult.model_validate_json(x.read_text(encoding="utf-8"))
        dset = runner.frozen_dset(PRIOR, tmp_path / "g0.json")
        audit = audit_measurements(r.episode, r.events, dset)
        assert audit == r.audit
        assert score_episode(r.episode, r.events, r.diagnosis, audit) == r.scores
    assert (a / "summary.json").read_bytes() == (b / "summary.json").read_bytes()


def test_t023_summarize_is_recomputed_from_episodes(tmp_path) -> None:
    a = go(tmp_path, "a", n=10)
    committed = (a / "summary.json").read_bytes()
    copy = tmp_path / "copy"
    shutil.copytree(a, copy)
    (copy / "summary.json").unlink()
    runner.summarize(copy)
    runner.summarize(a)
    assert (copy / "summary.json").read_bytes() == committed == (a / "summary.json").read_bytes()
    s = json.loads(committed)
    m1 = s["metrics"]["primary"]["overall"]["M1"]
    assert m1["k"] == 10 and m1["wilson95"][0] == pytest.approx(0.7225, abs=1e-4)
    assert s["metrics"]["primary"]["BIOLOGICAL_PLATEAU"]["n"] == 5
    # Tampering with an episode file changes the recomputed summary.
    f = sorted((copy / "episodes").glob("*.json"))[0]
    d = json.loads(f.read_text(encoding="utf-8"))
    d["scores"]["correct"] = False
    f.write_text(json.dumps(d), encoding="utf-8")
    runner.summarize(copy)
    assert json.loads((copy / "summary.json").read_text())["metrics"]["primary"]["overall"]["M1"]["k"] == 9


def test_t031_changed_config_refuses_to_start(tmp_path) -> None:
    raw = json.loads(runner.SCENARIO.read_text(encoding="utf-8"))
    changed = dict(raw, kappa_uniform=[0.80, 0.91])
    p = tmp_path / "scenario_changed.json"
    p.write_text(json.dumps(changed), encoding="utf-8")
    assert canonical_sha256(load_prior(p)) != SHA
    with pytest.raises(ValueError, match="hash mismatch"):
        runner.run("good_scientist", "t", tmp_path / "o", scenario=p, matrix=small_matrix(tmp_path),
                   gate0_summary=fixture_gate0(tmp_path / "g0.json"), run_id="x")
    assert not (tmp_path / "o" / "x").exists()
    reformatted = tmp_path / "scenario_ws.json"
    reformatted.write_text(json.dumps(dict(reversed(list(raw.items()))), indent=7), encoding="utf-8")
    assert canonical_sha256(load_prior(reformatted)) == SHA


def test_real_gate0_summary_hash_check() -> None:
    if not runner.GATE0_SUMMARY.exists():
        pytest.skip("experiments/results/gate0/summary.json does not exist yet (Gate 0 not run)")
    runner.frozen_dset(PRIOR, runner.GATE0_SUMMARY)


def test_missing_gate0_summary_refuses(tmp_path, capsys) -> None:
    rc = runner.main(["run", "--agent", "good_scientist", "--matrix", "minimal", "--out",
                      str(tmp_path), "--gate0-summary", str(tmp_path / "nope.json")])
    assert rc == 2 and "Gate 0 must pass" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_never_overwrites_and_atomic(tmp_path) -> None:
    go(tmp_path, "a", n=2)
    with pytest.raises(FileExistsError):
        go(tmp_path, "a", n=2)
    assert not list((tmp_path / "a").rglob("*.tmp"))


def test_passive_bayes_run_has_no_measurements(tmp_path) -> None:
    d = go(tmp_path, "p", n=10, agent="passive_bayes")
    s = json.loads((d / "summary.json").read_text())["metrics"]["primary"]["overall"]
    assert s["M2"]["k"] == 0 and s["M4"]["max"] == 0


def test_eval_matrix_v1() -> None:
    mini = runner.load_matrix(runner.MATRIX, "minimal")
    strong = runner.load_matrix(runner.MATRIX, "strong")
    ref = runner.load_matrix(runner.MATRIX, "baseline_reference")
    assert [s for s, _ in strong] == list(range(500_000, 500_030))
    assert strong[:10] == mini
    for m, half in ((mini, 5), (strong, 15)):
        assert sum(c.value == "BIOLOGICAL_PLATEAU" for _, c in m) == half
    assert len(ref) == 2000 and {s for s, _ in ref} == set(range(900_000, 901_000))
    assert not {s for s, _ in strong} & set(range(0, 10_000))  # dev block disjoint (ER-002)
