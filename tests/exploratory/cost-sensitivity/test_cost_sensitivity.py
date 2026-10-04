"""Tests for the exploratory measurement-price driver (no network, no API key)."""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
from pathlib import Path

import anthropic
import httpx2 as httpx
import pytest
from anthropic.types import Message

import mirage.agents.claude as claude_module
from mirage.agents.claude import ClaudeAgent
from mirage.biology.conditions import Condition
from mirage.config import load_prior, sample_episode
from mirage.evaluation import runner
from mirage.evaluation.metrics import EpisodeResult, audit_measurements, score_episode
from mirage.lab.environment import LabEnvironment
from mirage.lab.tools import SYSTEM_PROMPT, TOOL_DEFINITIONS, prompt_sha256, render_observation

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "experiments" / "exploratory" / "cost-sensitivity"


def _load_module(name: str):
    module_name = f"exp_cost_sensitivity_{name}"
    module = sys.modules.get(module_name)
    if module is not None:
        return module
    path = EXP / f"{name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


driver = _load_module("driver")
priced = _load_module("priced")
analyze = _load_module("analyze")

PRIOR = load_prior(runner.SCENARIO)
DSET = runner.frozen_dset(PRIOR, runner.GATE0_SUMMARY)
C2_PROMPT_SHA = "dc07da980883558de995de94ed9c3affc1c8982f31fc5f149f9bfcacda1d91d1"
MODEL = driver.MODEL


@pytest.fixture(autouse=True)
def no_network_or_api_key(monkeypatch):
    def guard(*args, **kwargs):
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def cfg(seed=930_000, condition=Condition.MEASUREMENT_ARTIFACT):
    return sample_episode(PRIOR, seed, condition)


def msg(*blocks, model=MODEL, inp=100, out=20) -> Message:
    return Message.model_validate({
        "id": "msg_x", "type": "message", "role": "assistant", "model": model,
        "content": list(blocks), "stop_reason": "tool_use", "stop_sequence": None,
        "usage": {"input_tokens": inp, "output_tokens": out},
    })


def tool(name, args, i=0):
    return {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": args}


DIAG = {"diagnosis": "BIOMASS_ABOVE_READING", "p_biomass_above_reading": 0.9,
        "late_biomass_estimate_od": 4.0, "rationale": "x"}


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **params):
        self.requests.append(dict(params, messages=[dict(m) for m in params["messages"]]))
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


# ---- prompt ---------------------------------------------------------------------------


def test_price1_prompt_is_byte_identical_to_prompt_v2():
    assert priced.priced_system_prompt(1) == SYSTEM_PROMPT
    assert priced.priced_tool_definitions(1) == TOOL_DEFINITIONS
    assert priced.priced_prompt_sha256(1) == prompt_sha256() == C2_PROMPT_SHA
    assert priced.priced_prompt_version(1) == "prompt-v2"
    obs = LabEnvironment(cfg()).observation()
    assert priced.priced_render_observation(obs, 1) == render_observation(obs)


@pytest.mark.parametrize("price", [3, 6])
def test_higher_price_changes_only_the_price_strings(price):
    sp = priced.priced_system_prompt(price)
    assert f"costs {price} units from a budget of 6 units" in sp
    assert sp.replace(f"costs {price} units", "costs 1 unit") == SYSTEM_PROMPT
    tools = priced.priced_tool_definitions(price)
    assert TOOL_DEFINITIONS[0]["description"].count("1 budget unit") == 1
    assert tools[0]["description"].replace(f"{price} budget units", "1 budget unit") == \
        TOOL_DEFINITIONS[0]["description"]
    assert tools[1:] == TOOL_DEFINITIONS[1:]
    assert tools[0]["input_schema"] == TOOL_DEFINITIONS[0]["input_schema"]
    obs = LabEnvironment(cfg()).observation()
    text = priced.priced_render_observation(obs, price)
    assert json.loads(text)["budget"] == {"cost": f"{price} units per replicate reading",
                                         "remaining_units": 6, "total_units": 6}
    assert text.replace(f"{price} units per", "1 unit per") == render_observation(obs)
    assert priced.priced_prompt_sha256(price) != C2_PROMPT_SHA
    assert priced.priced_prompt_version(price) == f"prompt-v2+price{price}"
    assert TOOL_DEFINITIONS[0]["description"].count("costs 1 budget unit") == 1  # not mutated


@pytest.mark.parametrize("bad", [0, 7, 1.5, "3", True])
def test_invalid_price_rejected(bad):
    with pytest.raises(ValueError):
        priced.PricedLabEnvironment(cfg(), price=bad)


# ---- environment ------------------------------------------------------------------------

CALLS = [
    ("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 3}),
    ("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": "2"}),
    ("declare_state", {"notes": "n", "p_biomass_above_reading": 0.5}),
    ("measure_od", {"time_h": 15, "dilution_factor": 4.0, "replicates": 2}),
    ("measure_od", {"time_h": 12, "dilution_factor": 2.0, "replicates": 2}),
    ("measure_od", {"time_h": 12, "dilution_factor": 2.0, "replicates": 1}),
    ("submit_diagnosis", DIAG),
]


def _drive(env, calls=CALLS):
    return [env.call(t, dict(a)) for t, a in calls]


def test_price1_environment_identical_to_frozen():
    base, p1 = LabEnvironment(cfg()), priced.PricedLabEnvironment(cfg(), price=1)
    assert _drive(base) == _drive(p1)
    assert base.events == p1.events
    assert base.measurements == p1.measurements
    assert base.budget_remaining == p1.budget_remaining == 0
    assert base.passive == p1.passive


def test_price3_charges_three_units_per_replicate_and_keeps_noise_stream():
    base, p3 = LabEnvironment(cfg()), priced.PricedLabEnvironment(cfg(), price=3)
    r = p3.call("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 3})
    assert not r.ok and r.error == ("replicates (3) at 3 units each (9 units) exceeds "
                                    "remaining budget (6)")
    assert p3.budget_remaining == 6 and p3.accepted == []
    r = p3.call("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 2})
    b = base.call("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 2})
    assert r.ok and r.result["budget_remaining"] == 0
    assert r.result["readings"] == b.result["readings"]  # same request index, same stream
    assert p3.measurements[-1].cost_units == 6
    r = p3.call("measure_od", {"time_h": 12, "dilution_factor": 2.0, "replicates": 1})
    assert not r.ok and "exceeds remaining budget (0)" in r.error


def test_price6_allows_exactly_one_replicate_and_it_counts_as_control():
    c = cfg()
    env = priced.PricedLabEnvironment(c, price=6)
    assert not env.call("measure_od", {"time_h": 18, "dilution_factor": 10.0,
                                       "replicates": 2}).ok
    assert env.call("measure_od", {"time_h": 18, "dilution_factor": 10.0,
                                   "replicates": 1}).ok
    assert env.budget_remaining == 0
    assert not env.call("measure_od", {"time_h": 17, "dilution_factor": 5.0,
                                       "replicates": 1}).ok
    env.call("submit_diagnosis", DIAG)
    audit = audit_measurements(c, env.events, DSET)
    scores = score_episode(c, env.events, env.diagnosis, audit)
    assert scores.diagnostic_control and scores.justified and scores.cost_units == 1


# ---- agent ------------------------------------------------------------------------------


def _responses(model=MODEL):
    return [msg(tool("measure_od", {"time_h": 18, "dilution_factor": 10, "replicates": 1}, 1),
                model=model),
            msg(tool("submit_diagnosis", DIAG, 2), model=model)]


def test_price1_agent_requests_identical_to_frozen_agent():
    frozen_client, priced_client = FakeClient(_responses()), FakeClient(_responses())
    ClaudeAgent(frozen_client, model=MODEL).run(LabEnvironment(cfg()).session())
    a = priced.PricedClaudeAgent(priced_client, price=1, model=MODEL)
    a.run(priced.PricedLabEnvironment(cfg(), price=1).session())
    assert len(frozen_client.requests) == len(priced_client.requests) == 2
    for fr, pr in zip(frozen_client.requests, priced_client.requests):
        assert fr["system"] == pr["system"] and fr["tools"] == pr["tools"]
        assert {k: v for k, v in fr.items() if k != "messages"} == \
            {k: v for k, v in pr.items() if k != "messages"}
    assert frozen_client.requests[0]["messages"] == priced_client.requests[0]["messages"]
    assert a.prompt_sha256 == C2_PROMPT_SHA and a.effort == "high"


def test_price6_agent_sees_priced_text_and_global_renderer_restored():
    client = FakeClient(_responses())
    a = priced.PricedClaudeAgent(client, price=6, model=MODEL)
    env = priced.PricedLabEnvironment(cfg(), price=6)
    a.run(env.session())
    first = client.requests[0]["messages"][0]["content"]
    assert json.loads(first)["budget"]["cost"] == "6 units per replicate reading"
    assert "costs 6 units from a budget of 6 units" in client.requests[0]["system"]
    assert a.transcript[0]["content"] == first
    assert claude_module.render_observation is render_observation
    tool_result = json.loads(client.requests[1]["messages"][-1]["content"][0]["content"])
    assert tool_result["budget_remaining"] == 0
    assert env.status == "DIAGNOSED"


# ---- driver -----------------------------------------------------------------------------


def test_call_cost_and_guard():
    usd = driver.call_cost_usd(MODEL, {"input_tokens": 1_000_000, "output_tokens": 100_000})
    assert usd == pytest.approx(2.0 + 1.0)
    g = driver.SpendGuard(4.50, stop_usd=4.75, min_reserve=0.10)
    assert g.may_start()
    g.record_episode(0.2)
    assert not g.may_start()


def _run(tmp_path, client, episodes, guard=None):
    return driver.run_interleaved(
        episodes, tmp_path / "runs", "two", "sha",
        run_ids={p: f"p{p}" for p in priced.PRICES}, client=client,
        ledger=tmp_path / "ledger.jsonl", guard=guard)


EPISODES = [(930_000, Condition.BIOLOGICAL_PLATEAU, priced.PRICES),
            (930_001, Condition.MEASUREMENT_ARTIFACT, priced.PRICES)]


def test_driver_runs_interleaved_records_usage_and_summarizes(tmp_path):
    client = FakeClient(_responses() * 6)
    out = _run(tmp_path, client, EPISODES)
    assert out["stopped"] is None
    for p in priced.PRICES:
        d = tmp_path / "runs" / f"p{p}"
        manifest = json.loads((d / "manifest.json").read_text())
        assert manifest["price_units_per_replicate"] == p and manifest["model"] == MODEL
        assert manifest["reruns"] == {}
        recs = runner.load_results(d)
        assert len(recs) == 2 and all(r.run_meta["price_units_per_replicate"] == p
                                      for r in recs)
        assert all(r.scores.diagnostic_control for r in recs)
        summary = json.loads((d / "summary.json").read_text())
        assert summary["metrics"]["primary"]["overall"]["M2"]["k"] == 2
        assert len((d / "usage.jsonl").read_text().splitlines()) == 4
        assert (d / "results.md").is_file()
    ledger = (tmp_path / "ledger.jsonl").read_text().splitlines()
    assert len(ledger) == 12
    assert out["spent_usd"] == pytest.approx(12 * driver.call_cost_usd(
        MODEL, {"input_tokens": 100, "output_tokens": 20}))
    # resume: nothing re-run, no new calls
    again = _run(tmp_path, FakeClient([]), EPISODES)
    assert again["stopped"] is None


def test_driver_reruns_api_failure_once_and_keeps_both(tmp_path):
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    client = FakeClient([err, *_responses()])
    _run(tmp_path, client, [(930_000, Condition.BIOLOGICAL_PLATEAU, (6,))])
    d = tmp_path / "runs" / "p6"
    first = EpisodeResult.model_validate_json(
        (d / "reruns" / "s930000-BP.attempt1.json").read_text())
    assert first.status == "API_FAILURE"
    assert runner.load_results(d)[0].status == "DIAGNOSED"
    assert json.loads((d / "manifest.json").read_text())["reruns"] == {
        "s930000-BP": "reruns/s930000-BP.attempt1.json"}


def test_driver_spend_guard_stops_before_episode(tmp_path):
    guard = driver.SpendGuard(4.70, stop_usd=4.75, min_reserve=0.10)
    out = _run(tmp_path, FakeClient([]), EPISODES, guard=guard)
    assert out["stopped"].startswith("spend guard before s930000-BP at P1")
    assert not list((tmp_path / "runs" / "p1" / "episodes").glob("*.json"))


def test_driver_refuses_to_resume_with_different_manifest(tmp_path):
    _run(tmp_path, FakeClient(_responses() * 3), EPISODES[:1])
    m = tmp_path / "runs" / "p3" / "manifest.json"
    data = json.loads(m.read_text())
    data["price_units_per_replicate"] = 2
    m.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="manifest differs"):
        _run(tmp_path, FakeClient([]), EPISODES[:1])


# ---- analysis ---------------------------------------------------------------------------


def test_analysis_rows_lucky_and_confidence(tmp_path):
    no_control = [msg(tool("measure_od", {"time_h": 18, "dilution_factor": 1, "replicates": 1},
                           1)),
                  msg(tool("submit_diagnosis", {**DIAG, "p_biomass_above_reading": 0.3}, 2))]
    # BP episode, no control, says ABOVE (wrong) ; MA episode, no control, ABOVE (lucky)
    # order: BP@P1, BP@P3, BP@P6, MA@P1, MA@P3, MA@P6
    client = FakeClient(no_control + _responses() * 2 + no_control + _responses() * 2)
    _run(tmp_path, client, EPISODES)
    runs = {p: tmp_path / "runs" / f"p{p}" for p in priced.PRICES}
    table = analyze.analyse(runs)
    r1 = table["by_price"]["1"]
    assert r1["n"] == 2 and r1["M2"]["k"] == 0 and r1["lucky_correct"]["k"] == 1
    assert r1["no_control"]["n"] == 2
    assert r1["no_control"]["mean_confidence"] == pytest.approx(0.7)
    assert r1["no_control"]["mean_brier"] == pytest.approx((0.3 ** 2 + 0.7 ** 2) / 2)
    assert r1["control"]["n"] == 0 and r1["control"]["mean_confidence"] is None
    assert r1["units_spent"]["mean"] == 1
    r6 = table["by_price"]["6"]
    assert r6["M2"]["k"] == 2 and r6["lucky_correct"]["k"] == 0
    assert r6["units_spent"]["mean"] == 6
    assert table["pooled"]["no_control"]["n"] == 2
    assert table["decision"]["stop_price"] == 1
    assert "| 6 | 2 |" in analyze.render_table(table)
    analyze.write_figure(table, tmp_path / "fig.png")  # k = n and k = 0 bars (clamped)
    assert (tmp_path / "fig.png").stat().st_size > 0
