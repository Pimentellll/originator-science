"""T-022: Claude adapter loop with a mocked client. No network, no API key."""

import json
import socket
from pathlib import Path

import anthropic
import httpx2 as httpx  # the HTTP library the anthropic SDK uses
import pytest
from anthropic.types import Message

from mirage.agents import claude
from mirage.agents.claude import REMINDER, TOOL_CHOICE, ClaudeAgent
from mirage.biology.conditions import Condition
from mirage.config import load_prior, sample_episode
from mirage.lab.environment import LabEnvironment

PRIOR = load_prior(Path(__file__).resolve().parents[1] / "experiments" / "configs" / "scenario_v1.json")
MODEL = claude.DEFAULT_MODEL


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*a, **k):
        raise AssertionError("network access attempted in a test")
    monkeypatch.setattr(socket.socket, "connect", guard)


def msg(*blocks, stop="tool_use", model=MODEL, stop_details=None) -> Message:
    return Message.model_validate({
        "id": "msg_x", "type": "message", "role": "assistant", "model": model,
        "content": list(blocks), "stop_reason": stop, "stop_sequence": None,
        "stop_details": stop_details, "usage": {"input_tokens": 10, "output_tokens": 5}})


def tool(name, args, i=0):
    return {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": args}


DIAG = {
    "diagnosis": "BIOMASS_ABOVE_READING",
    "p_biomass_above_reading": 0.9,
    "late_biomass_estimate_od": 4.0,
    "rationale": "1:10 back-corrected reading exceeds the plateau.",
}


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **params):
        self.requests.append(params)
        # Snapshot so later appends do not rewrite what this request saw.
        self.requests[-1] = dict(params, messages=list(params["messages"]))
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def episode():
    return LabEnvironment(sample_episode(PRIOR, 3, Condition.MEASUREMENT_ARTIFACT))


def play(responses, **kw):
    env, client = episode(), FakeClient(responses)
    agent = ClaudeAgent(client, **kw)
    agent.run(env.session())
    if not env.finished:  # finish() raises on a final episode (PR #36); a diagnosis already ended it
        env.finish(agent.outcome or "NO_DIAGNOSIS")  # what the runner does
    return env, client, agent


def check_request_settings(client):
    for p in client.requests:
        assert p["tool_choice"] == TOOL_CHOICE == {"type": "auto", "disable_parallel_tool_use": True}
        assert p["output_config"] == {"effort": "high"}
        assert p["model"] == MODEL and p["max_tokens"] == 16_000
        assert not {"temperature", "top_p", "top_k", "thinking"} & set(p)


def test_case1_full_loop_diagnosed():
    r1 = msg({"type": "text", "text": "Noting state."}, tool("declare_state", {"notes": "n", "p_biomass_above_reading": 0.5}, 1))
    r2 = msg(tool("measure_od", {"time_h": 18, "dilution_factor": 10, "replicates": 3}, 2))
    r3 = msg(tool("submit_diagnosis", DIAG, 3))
    env, client, agent = play([r1, r2, r3])
    assert env.status == "DIAGNOSED" and agent.outcome is None
    assert [e.tool for e in env.events] == ["declare_state", "measure_od", "submit_diagnosis"]
    check_request_settings(client)
    first = client.requests[0]["messages"]
    assert len(first) == 1 and json.loads(first[0]["content"])["budget"]["total_units"] == 6
    second = client.requests[1]["messages"]
    assert second[1] == {"role": "assistant", "content": r1.content}
    assert second[1]["content"] is r1.content  # appended unchanged
    tr = second[2]["content"]
    assert tr[0]["tool_use_id"] == "toolu_1" and tr[0]["is_error"] is False
    third = client.requests[2]["messages"]
    m = json.loads(third[4]["content"][0]["content"])
    assert m["time_h"] == 18 and len(m["readings"]) == 3 and m["budget_remaining"] == 3
    assert m == env.events[1].result
    kinds = [t["kind"] for t in agent.transcript]
    assert kinds == ["user", "assistant", "user", "assistant", "user", "assistant", "user"]
    assert agent.transcript[1]["response"]["model"] == MODEL


def test_case2_end_turn_reminder_counts_as_turn():
    env, client, agent = play([msg({"type": "text", "text": "Thinking."}, stop="end_turn"),
                               msg(tool("submit_diagnosis", DIAG))])
    assert env.status == "DIAGNOSED"
    reminders = [m for m in client.requests[1]["messages"] if m["content"] == REMINDER]
    assert len(reminders) == 1 and sum(t.get("reminder", False) for t in agent.transcript) == 1
    # The reminder consumed a turn: with max_turns=1 the agent stops after it.
    env, client, agent = play([msg({"type": "text", "text": "x"}, stop="end_turn")], max_turns=1)
    assert len(client.requests) == 1 and env.status == "NO_DIAGNOSIS"


def test_case3_refusal():
    env, _, agent = play([msg({"type": "text", "text": "no"}, stop="refusal",
                              stop_details={"type": "refusal", "category": "bio"})])
    assert env.status == "REFUSED" and agent.reason == "bio"
    assert agent.transcript[-1]["outcome"] == "REFUSED"


def test_case4_connection_error_is_api_failure():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    env, client, agent = play([anthropic.APIConnectionError(request=req)] * 3)
    assert env.status == "API_FAILURE" and len(client.requests) == 1
    assert "APIConnectionError" in agent.reason and env.events == []


def test_case4_client_retry_configuration(monkeypatch):
    seen = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: seen.update(kw) or "client")
    assert claude.make_client() == "client"
    assert seen == {"max_retries": 4, "timeout": 120.0}


def test_case5_twelve_invalid_calls_no_diagnosis():
    bad = [msg(tool("measure_od", {"time_h": 99, "dilution_factor": 1, "replicates": 1}, i))
           for i in range(13)]
    env, client, agent = play(bad)
    assert env.status == "NO_DIAGNOSIS" and len(client.requests) == 12 and env.turn == 12
    assert all(not e.ok for e in env.events) and env.budget_remaining == 6
    last = client.requests[-1]["messages"][-1]["content"][0]
    assert last["is_error"] is True and "error" in json.loads(last["content"])


def test_case6_model_mismatch_aborts():
    env, client, agent = play([msg(tool("submit_diagnosis", DIAG), model="claude-other")])
    assert env.status == "API_FAILURE" and "claude-other" in agent.reason
    assert env.events == [] and len(client.requests) == 1


def test_records_identity_fields():
    agent = ClaudeAgent(FakeClient([]))
    assert agent.prompt_version == "prompt-v2" and len(agent.prompt_sha256) == 64
    assert agent.sdk_version == anthropic.__version__ and agent.model == MODEL
