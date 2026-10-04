import json
import socket
import sys
from pathlib import Path

import anthropic
import httpx2 as httpx
import pytest
from anthropic.types import Message

ROOT = Path(__file__).resolve().parents[3]
DRIVER_DIR = ROOT / "experiments" / "exploratory" / "cost-sensitivity"
sys.path.insert(0, str(DRIVER_DIR))

import analyze
import cost_driver

from mirage.agents import claude as claude_module
from mirage.agents.claude import ClaudeAgent
from mirage.agents.scripted import GoodScientist
from mirage.biology.conditions import Condition
from mirage.config import load_prior, sample_episode
from mirage.evaluation import runner
from mirage.evaluation.metrics import EpisodeResult
from mirage.lab.environment import LabEnvironment
from mirage.lab.tools import (
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
    prompt_sha256,
    render_observation,
)

MODEL = cost_driver.MODEL
PRIOR = load_prior(runner.SCENARIO)


@pytest.fixture(autouse=True)
def no_network_or_api_key(monkeypatch):
    def guard(*args, **kwargs):
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def msg(*blocks, stop="tool_use", model=MODEL, stop_details=None) -> Message:
    return Message.model_validate(
        {
            "id": "msg_x",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": list(blocks),
            "stop_reason": stop,
            "stop_sequence": None,
            "stop_details": stop_details,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    )


def tool(name, args, i=0):
    return {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": args}


DIAG = {
    "diagnosis": "BIOMASS_ABOVE_READING",
    "p_biomass_above_reading": 0.9,
    "late_biomass_estimate_od": 4.0,
    "rationale": "The corrected late reading exceeds the plateau.",
}


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **params):
        self.requests.append(dict(params, messages=list(params["messages"])))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def fixture_matrix(path: Path, episodes=None) -> Path:
    matrix_path = path / "matrix.json"
    if episodes is None:
        episodes = [
            {"seed": 930_000, "condition": Condition.BIOLOGICAL_PLATEAU.value},
            {"seed": 930_001, "condition": Condition.MEASUREMENT_ARTIFACT.value},
        ]
    matrix_path.write_text(
        json.dumps({"matrices": {"two": {"episodes": episodes}}}),
        encoding="utf-8",
    )
    return matrix_path


def episode_config(seed: int, condition: Condition):
    return sample_episode(PRIOR, seed, condition)


def responses_for(conditions):
    responses = []
    for index, condition in enumerate(conditions):
        diagnosis = dict(DIAG)
        if condition is Condition.BIOLOGICAL_PLATEAU:
            diagnosis |= {
                "diagnosis": "BIOMASS_AS_READ",
                "p_biomass_above_reading": 0.1,
            }
        responses.extend(
            [
                msg(
                    tool(
                        "measure_od",
                        {
                            "time_h": 18,
                            "dilution_factor": 10,
                            "replicates": 1,
                        },
                        2 * index,
                    )
                ),
                msg(tool("submit_diagnosis", diagnosis, 2 * index + 1)),
            ]
        )
    return responses


def test_price_one_is_frozen_identity():
    cfg = episode_config(500_000, Condition.BIOLOGICAL_PLATEAU)
    obs = LabEnvironment(cfg).observation()
    assert cost_driver.priced_system_prompt(1) == SYSTEM_PROMPT
    assert cost_driver.priced_tools(1) == TOOL_DEFINITIONS
    assert cost_driver.priced_prompt_sha256(1) == (
        "dc07da980883558de995de94ed9c3affc1c8982f31fc5f149f9bfcacda1d91d1"
    )
    assert cost_driver.priced_prompt_sha256(1) == prompt_sha256()
    assert cost_driver.prompt_version(1) == "prompt-v2"
    assert cost_driver.render_priced_observation(obs, 1) == render_observation(obs)
    for invalid in (True, False, 0, -1, 1.0):
        with pytest.raises(ValueError):
            cost_driver.prompt_version(invalid)


@pytest.mark.parametrize("price", [3, 6])
def test_priced_prompt_strings_change_only_cost_labels(price):
    priced_system = cost_driver.priced_system_prompt(price)
    old_system = "each replicate reading\ncosts 1 unit from a budget of 6 units"
    new_system = f"each replicate reading\ncosts {price} units from a budget of 6 units"
    assert new_system in priced_system
    assert priced_system.replace(new_system, old_system) == SYSTEM_PROMPT

    frozen_tools = json.loads(json.dumps(TOOL_DEFINITIONS))
    priced = cost_driver.priced_tools(price)
    priced_measure = next(t for t in priced if t["name"] == "measure_od")
    old_text = "and costs 1 budget unit."
    new_text = f"and costs {price} budget units."
    assert new_text in priced_measure["description"]
    priced_measure["description"] = priced_measure["description"].replace(new_text, old_text)
    assert priced == frozen_tools

    cfg = episode_config(500_000, Condition.BIOLOGICAL_PLATEAU)
    obs = LabEnvironment(cfg).observation()
    frozen_obs = json.loads(render_observation(obs))
    priced_obs = json.loads(cost_driver.render_priced_observation(obs, price))
    assert priced_obs["budget"]["cost"] == f"{price} units per replicate reading"
    del frozen_obs["budget"]["cost"]
    del priced_obs["budget"]["cost"]
    assert priced_obs == frozen_obs


def test_price_one_environment_is_bit_identical():
    script = [
        ("declare_state", {"notes": "state", "p_biomass_above_reading": 0.5}),
        ("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 3}),
        ("measure_od", {"time_h": 15, "dilution_factor": 1.0, "replicates": 2}),
        ("measure_od", {"time_h": 14, "dilution_factor": 2.0, "replicates": 2}),
        ("measure_od", {"time_h": "invalid", "dilution_factor": 1.0, "replicates": 1}),
        ("measure_od", {"time_h": 12, "dilution_factor": 1.0, "replicates": 1}),
        ("submit_diagnosis", DIAG),
    ]
    cases = (
        (500_000, Condition.BIOLOGICAL_PLATEAU),
        (500_001, Condition.MEASUREMENT_ARTIFACT),
        (7, Condition.BIOLOGICAL_PLATEAU),
    )
    for seed, condition in cases:
        config = episode_config(seed, condition)
        frozen = LabEnvironment(config)
        priced = cost_driver.PricedLabEnvironment(config, unit_price=1)
        frozen_budgets = []
        priced_budgets = []
        for name, args in script:
            frozen.call(name, args)
            priced.call(name, args)
            frozen_budgets.append(frozen.budget_remaining)
            priced_budgets.append(priced.budget_remaining)
        assert [e.model_dump() for e in priced.events] == [
            e.model_dump() for e in frozen.events
        ]
        assert [m.model_dump() for m in priced.passive] == [
            m.model_dump() for m in frozen.passive
        ]
        assert priced_budgets == frozen_budgets


def test_prices_three_and_six_enforce_budget_and_turn_errors():
    cfg = episode_config(500_000, Condition.BIOLOGICAL_PLATEAU)
    env3 = cost_driver.PricedLabEnvironment(cfg, unit_price=3)
    assert env3.call(
        "measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 1}
    ).ok
    assert env3.budget_remaining == 3
    rejected = env3.call(
        "measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 2}
    )
    assert not rejected.ok
    assert "6 units" in rejected.error and "3 units" in rejected.error
    assert env3.turn == 2
    assert env3.call(
        "measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 1}
    ).ok
    assert env3.budget_remaining == 0

    env6 = cost_driver.PricedLabEnvironment(cfg, unit_price=6)
    assert not env6.call(
        "measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 2}
    ).ok
    assert env6.call(
        "measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 1}
    ).ok
    assert env6.budget_remaining == 0
    assert not env6.call(
        "measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 1}
    ).ok


def test_priced_good_scientist_records_and_price_one_events():
    dset = runner.frozen_dset(PRIOR, runner.GATE0_SUMMARY)
    for seed, condition in (
        (500_001, Condition.MEASUREMENT_ARTIFACT),
        (500_000, Condition.BIOLOGICAL_PLATEAU),
    ):
        cfg = episode_config(seed, condition)
        result = cost_driver.run_priced_episode(
            cfg, cost_driver.PricedGoodScientist(6), dset, {"run_id": "test"}, 6
        )
        EpisodeResult.model_validate(result.model_dump())
        assert result.scores.diagnostic_control
        assert result.scores.cost_units == 1
        assert result.scores.correct

    cfg = episode_config(500_001, Condition.MEASUREMENT_ARTIFACT)
    frozen = runner.run_episode(cfg, GoodScientist(), dset, {"run_id": "same"})
    priced = cost_driver.run_priced_episode(
        cfg, cost_driver.PricedGoodScientist(1), dset, {"run_id": "same"}, 1
    )
    assert [event.model_dump() for event in priced.events] == [
        event.model_dump() for event in frozen.events
    ]


def test_priced_claude_reuses_loop_and_restores_observation_renderer():
    original = claude_module.render_observation
    cfg = episode_config(500_001, Condition.MEASUREMENT_ARTIFACT)
    client1 = FakeClient(responses_for([Condition.MEASUREMENT_ARTIFACT]))
    agent1 = cost_driver.PricedClaudeAgent(client1, unit_price=1)
    agent1.run(cost_driver.PricedLabEnvironment(cfg, unit_price=1).session())
    reference_params = ClaudeAgent(FakeClient([]), model=MODEL).request_params(
        client1.requests[0]["messages"]
    )
    assert client1.requests[0] == reference_params
    assert client1.requests[0]["messages"][0]["content"] == render_observation(
        cost_driver.PricedLabEnvironment(cfg, unit_price=1).observation()
    )
    assert claude_module.render_observation is original

    client6 = FakeClient(responses_for([Condition.MEASUREMENT_ARTIFACT]))
    agent6 = cost_driver.PricedClaudeAgent(client6, unit_price=6)
    agent6.run(cost_driver.PricedLabEnvironment(cfg, unit_price=6).session())
    assert "costs 6 units from a budget of 6 units" in client6.requests[0]["system"]
    first = json.loads(client6.requests[0]["messages"][0]["content"])
    assert first["budget"]["cost"] == "6 units per replicate reading"
    assert claude_module.render_observation is original

    failing = FakeClient([RuntimeError("fake failure")])
    with pytest.raises(RuntimeError, match="fake failure"):
        cost_driver.PricedClaudeAgent(failing, unit_price=6).run(
            cost_driver.PricedLabEnvironment(cfg, unit_price=6).session()
        )
    assert claude_module.render_observation is original


def test_run_arm_fake_claude_usage_summary_report_and_manifest(tmp_path: Path):
    matrix_file = fixture_matrix(tmp_path)
    conditions = [
        Condition.BIOLOGICAL_PLATEAU,
        Condition.MEASUREMENT_ARTIFACT,
    ]
    client = FakeClient(responses_for(conditions))
    run_dir = cost_driver.run_arm(
        "claude",
        3,
        "two",
        tmp_path / "runs",
        matrix_file=matrix_file,
        run_id="claude-three",
        client=client,
        spend_root=tmp_path / "spend",
    )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["agent"] == "claude"
    assert manifest["unit_price"] == 3
    assert manifest["budget_units"] == 6
    assert manifest["driver"] == (
        "experiments/exploratory/cost-sensitivity/cost_driver.py"
    )
    assert manifest["model"] == MODEL
    assert manifest["effort"] == "high"
    assert manifest["prompt_version"] == "prompt-v2-price3x"
    assert manifest["prompt_sha256"] == cost_driver.priced_prompt_sha256(3)
    assert manifest["pricing_usd_per_mtok"] == cost_driver.PRICING_USD_PER_MTOK
    usage_lines = (run_dir / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(usage_lines) == len(client.requests)
    expected_keys = {
        "model",
        "stop_reason",
        "input_tokens",
        "output_tokens",
        "cache_read",
        "cache_write",
        "s",
    }
    assert all(set(json.loads(line)) == expected_keys for line in usage_lines)
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "results.md").exists()


def test_run_arm_spend_cap_and_api_failure_rerun(tmp_path: Path):
    matrix_file = fixture_matrix(tmp_path)
    spend_root = tmp_path / "prior-spend"
    spend_root.mkdir()
    usage_path = spend_root / "prior" / "usage.jsonl"
    usage_path.parent.mkdir()
    usage_path.write_text(
        json.dumps(
            {
                "model": MODEL,
                "stop_reason": "end_turn",
                "input_tokens": 2_450_000,
                "output_tokens": 0,
                "cache_read": 0,
                "cache_write": 0,
                "s": 1.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stopped = cost_driver.run_arm(
        "claude",
        3,
        "two",
        tmp_path / "capped",
        matrix_file=matrix_file,
        run_id="stopped",
        client=FakeClient([]),
        spend_root=spend_root,
    )
    stopped_manifest = json.loads(
        (stopped / "manifest.json").read_text(encoding="utf-8")
    )
    assert stopped_manifest["stopped_early"]["reason"] == "spend cap"
    assert stopped_manifest["stopped_early"]["completed_episodes"] == 0
    assert not list((stopped / "episodes").glob("*.json"))

    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    client = FakeClient(
        [
            error,
            *responses_for(
                [Condition.BIOLOGICAL_PLATEAU, Condition.MEASUREMENT_ARTIFACT]
            ),
        ]
    )
    rerun_dir = cost_driver.run_arm(
        "claude",
        3,
        "two",
        tmp_path / "reruns",
        matrix_file=matrix_file,
        run_id="rerun",
        client=client,
        spend_root=tmp_path / "empty-spend",
    )
    manifest = json.loads((rerun_dir / "manifest.json").read_text(encoding="utf-8"))
    first_episode = episode_config(
        930_000, Condition.BIOLOGICAL_PLATEAU
    ).episode_id
    assert (rerun_dir / "reruns" / f"{first_episode}.attempt1.json").exists()
    assert manifest["reruns"][first_episode] == (
        f"reruns/{first_episode}.attempt1.json"
    )


def test_claude_run_refuses_missing_key_and_client(tmp_path: Path):
    matrix_file = fixture_matrix(tmp_path)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is not set"):
        cost_driver.run_arm(
            "claude",
            1,
            "two",
            tmp_path / "runs",
            matrix_file=matrix_file,
            run_id="no-key",
        )


def test_spend_usd_counts_usage_tokens(tmp_path: Path):
    usage = tmp_path / "one" / "usage.jsonl"
    usage.parent.mkdir()
    usage.write_text(
        json.dumps(
            {
                "input_tokens": 1_000_000,
                "output_tokens": 100_000,
                "cache_write": 0,
                "cache_read": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert cost_driver.spend_usd(tmp_path) == pytest.approx(3.0)


def test_analyze_scripted_arms_matches_manual_recount(tmp_path: Path):
    matrix_file = fixture_matrix(tmp_path)
    runs = tmp_path / "runs"
    dirs = []
    for price in (1, 6):
        dirs.append(
            cost_driver.run_arm(
                "good_scientist",
                price,
                "two",
                runs,
                matrix_file=matrix_file,
                run_id=f"scripted-{price}",
            )
        )
    result = analyze.analyze(runs, tmp_path / "analysis")
    assert (tmp_path / "analysis" / "analysis.json").exists()
    assert (tmp_path / "analysis" / "analysis.md").exists()
    assert (tmp_path / "analysis" / "price_vs_control.png").exists()

    for run_dir in dirs:
        records = runner.load_results(run_dir)
        primary = [r for r in records if r.status in ("DIAGNOSED", "NO_DIAGNOSIS")]
        row = next(row for row in result["rows"] if row["run_id"] == run_dir.name)
        assert row["n"] == len(primary)
        assert row["M1"]["k"] == sum(r.scores.correct for r in primary)
        assert row["M2"]["k"] == sum(r.scores.diagnostic_control for r in primary)
        assert row["M3"]["k"] == sum(r.scores.justified for r in primary)
        assert row["lucky"]["k"] == sum(
            r.scores.correct and not r.scores.diagnostic_control for r in primary
        )
        assert row["split"]["control"]["correct_k"] == sum(
            r.scores.correct for r in primary if r.scores.diagnostic_control
        )
        assert row["split"]["no_control"]["correct_k"] == sum(
            r.scores.correct for r in primary if not r.scores.diagnostic_control
        )
    assert result["pooled_claude_split"]["control"]["n"] == 0
