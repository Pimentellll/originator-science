import json
import shutil
from pathlib import Path

import pytest

from mirage.agents.claude import DEFAULT_MODEL
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
    # The summary is recomputed from the episode files: removing one changes it.
    # (Editing a single score field would make the record internally inconsistent,
    # which the evaluator's record validation rejects.)
    sorted((copy / "episodes").glob("*.json"))[0].unlink()
    runner.summarize(copy)
    overall = json.loads((copy / "summary.json").read_text())["metrics"]["primary"]["overall"]
    assert overall["n"] == 9 and overall["M1"]["k"] == 9


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


# --- LLM path (DEV-013): fake client only; no network, no API key -----------------------------
class _ScriptedClient:
    """Answers every episode with: one measurement, then a diagnosis (or raises on request)."""

    def __init__(self, fail_after: int | None = None):
        self.messages, self.calls, self.fail_after = self, 0, fail_after

    def create(self, **params):
        from anthropic.types import Message
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise KeyboardInterrupt  # simulates the operator stopping a paid run
        last = params["messages"][-1]["content"]
        if isinstance(last, list):  # tool result came back -> diagnose
            block = {"type": "tool_use", "id": f"t{len(params['messages'])}", "name": "submit_diagnosis",
                     "input": {"diagnosis": "BIOMASS_ABOVE_READING", "p_biomass_above_reading": 0.9,
                               "late_biomass_estimate_od": 4.0, "rationale": "fake"}}
        else:
            block = {"type": "tool_use", "id": f"t{len(params['messages'])}", "name": "measure_od",
                     "input": {"time_h": 14.0, "dilution_factor": 10, "replicates": 2}}
        return Message.model_validate({
            "id": "m", "type": "message", "role": "assistant", "model": params["model"],
            "content": [block], "stop_reason": "tool_use", "stop_sequence": None,
            "stop_details": None, "usage": {"input_tokens": 1, "output_tokens": 1}})


def go_llm(tmp: Path, out: str, client, n: int = 4, run_id: str = "L", **kw) -> Path:
    return runner.run("claude", "t", tmp / out, matrix=small_matrix(tmp, n), run_id=run_id,
                      gate0_summary=fixture_gate0(tmp / "g0.json"), client=client,
                      reference_seeds=REFERENCE_SEEDS[:5000], **kw)


def test_llm_run_records_model_prompt_and_transcript(tmp_path) -> None:
    d = go_llm(tmp_path, "o", _ScriptedClient())
    res = runner.load_results(d)
    assert len(res) == 4
    for r in res:
        assert r.agent.kind == "llm" and r.agent.model == DEFAULT_MODEL
        assert r.agent.prompt_sha256 and r.llm_transcript and r.status == "DIAGNOSED"
    man = json.loads((d / "manifest.json").read_text())
    assert man["model"] == DEFAULT_MODEL and man["effort"] == "high"


def test_llm_run_refuses_without_key(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(runner.API_KEY_ENV, raising=False)
    with pytest.raises(ValueError, match=runner.API_KEY_ENV):
        go_llm(tmp_path, "o", None)
    assert not (tmp_path / "o").exists()


def test_llm_resume_skips_finished_and_matches_uninterrupted(tmp_path) -> None:
    full = go_llm(tmp_path, "full", _ScriptedClient(), run_id="R")
    with pytest.raises(KeyboardInterrupt):
        go_llm(tmp_path, "part", _ScriptedClient(fail_after=3), run_id="R")  # 1.5 episodes in
    part = tmp_path / "part" / "R"
    done = sorted(p.name for p in (part / "episodes").glob("*.json"))
    assert 0 < len(done) < 4 and not list(part.rglob("*.tmp"))
    c = _ScriptedClient()
    go_llm(tmp_path, "part", c, run_id="R", resume=True)
    assert c.calls == 2 * (4 - len(done))  # only the unfinished episodes were paid for
    assert strip_meta_all(part) == strip_meta_all(full)


def test_resume_refuses_changed_config(tmp_path) -> None:
    go_llm(tmp_path, "o", _ScriptedClient(), n=2, run_id="R")
    with pytest.raises(ValueError, match="manifest differs"):
        go_llm(tmp_path, "o", _ScriptedClient(), n=2, run_id="R", resume=True, model="claude-other")
    with pytest.raises(FileExistsError):
        go_llm(tmp_path, "o", _ScriptedClient(), n=2, run_id="R")


def strip_meta_all(run_dir: Path) -> list[str]:
    return [strip_meta(f) for f in sorted((run_dir / "episodes").glob("*.json"))]
