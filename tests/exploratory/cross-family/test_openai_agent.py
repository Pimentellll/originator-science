"""OpenAI Responses adapter tests use fake clients only."""

from __future__ import annotations

import copy
import hashlib
import importlib
import io
import json
import platform
import socket
import sys
from pathlib import Path
from urllib import error as urllib_error

import pytest

from mirage.agents.claude import REMINDER
from mirage.biology.conditions import Condition
from mirage.config import load_prior, sample_episode
from mirage.evaluation import runner
from mirage.lab.environment import LabEnvironment
from mirage.lab.tools import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
    prompt_sha256,
    render_observation,
)

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_DIR = ROOT / "experiments" / "exploratory" / "cross-family"
OPENAI_AGENT_MODULE = "exp_cross_family_openai_agent"
openai_agent = sys.modules.get(OPENAI_AGENT_MODULE)
if openai_agent is None:
    spec = importlib.util.spec_from_file_location(
        OPENAI_AGENT_MODULE, EXPERIMENT_DIR / "openai_agent.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("cannot load cross-family OpenAI agent")
    openai_agent = importlib.util.module_from_spec(spec)
    sys.modules[OPENAI_AGENT_MODULE] = openai_agent
    spec.loader.exec_module(openai_agent)

MODEL = "gpt-6-luna"
PRIOR = load_prior(runner.SCENARIO)
DIAGNOSIS = {
    "diagnosis": "BIOMASS_ABOVE_READING",
    "p_biomass_above_reading": 0.9,
    "late_biomass_estimate_od": 4.0,
    "rationale": "The diluted late measurement is above the plateau.",
}


@pytest.fixture(autouse=True)
def no_network_or_api_key(monkeypatch):
    def guard(*args, **kwargs):
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.setattr(openai_agent.urllib.request, "urlopen", guard)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def function_call(name, arguments, call_id="call_1", item_id="fc_1"):
    return {
        "type": "function_call",
        "id": item_id,
        "call_id": call_id,
        "name": name,
        "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
    }


def response(*output, model=MODEL, status="completed", response_id="resp_1"):
    return {
        "id": response_id,
        "object": "response",
        "model": model,
        "status": status,
        "output": list(output),
        "usage": {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens": 30,
        },
    }


class FakeResponses:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def create(self, **params):
        self.requests.append(copy.deepcopy(params))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


def episode():
    return LabEnvironment(
        sample_episode(PRIOR, 3, Condition.MEASUREMENT_ARTIFACT)
    )


def play(responses, *, model=MODEL, max_turns=12):
    env = episode()
    client = FakeClient(responses)
    agent = openai_agent.OpenAIResponsesAgent(
        client, model=model, effort="high", max_turns=max_turns
    )
    agent.run(env.session())
    if not env.finished:
        env.finish(agent.outcome or "NO_DIAGNOSIS")
    return env, client, agent


def test_agent_identity_and_responses_request():
    env = episode()
    initial_observation = env.session().observation()
    client = FakeClient(
        [response(function_call("submit_diagnosis", DIAGNOSIS))]
    )
    agent = openai_agent.OpenAIResponsesAgent(
        client, model=MODEL, effort="high"
    )
    agent.run(env.session())

    request = client.responses.requests[0]
    expected_tools = [
        {
            "type": "function",
            "name": definition["name"],
            "description": definition["description"],
            "parameters": definition["input_schema"],
            "strict": True,
        }
        for definition in TOOL_DEFINITIONS
    ]
    expected_hash = hashlib.sha256(
        json.dumps(expected_tools, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    assert agent.kind == "llm"
    assert agent.name == "openai_responses"
    assert agent.model == MODEL
    assert agent.effort == "high"
    assert agent.max_turns == 12
    assert agent.prompt_version == PROMPT_VERSION
    assert agent.prompt_sha256 == prompt_sha256()
    assert agent.sdk_version == f"urllib/{platform.python_version()}"
    assert agent.tools_sha256 == expected_hash
    assert request["model"] == MODEL
    assert request["instructions"] == SYSTEM_PROMPT
    assert request["input"] == [
        {
            "role": "user",
            "content": render_observation(initial_observation),
        }
    ]
    assert request["tools"] == expected_tools
    assert all(tool["strict"] is True for tool in request["tools"])
    assert all(
        tool["parameters"] == definition["input_schema"]
        for tool, definition in zip(request["tools"], TOOL_DEFINITIONS)
    )
    assert request["tool_choice"] == "auto"
    assert request["parallel_tool_calls"] is False
    assert request["reasoning"] == {"effort": "high"}
    assert request["max_output_tokens"] == 16_000
    assert request["store"] is False
    assert request["include"] == ["reasoning.encrypted_content"]
    assistant_entry = agent.transcript[1]
    assert assistant_entry["kind"] == "assistant"
    assert assistant_entry["request"] == {
        key: value
        for key, value in request.items()
        if key not in {"input", "instructions", "tools"}
    }
    assert assistant_entry["response"]["id"] == "resp_1"
    assert assistant_entry["response_id"] == "resp_1"


def test_reasoning_and_function_call_items_are_replayed_unchanged():
    reasoning = {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [],
        "encrypted_content": "opaque-test-value",
    }
    first_call = function_call(
        "measure_od",
        {"time_h": 18, "dilution_factor": 10, "replicates": 1},
        call_id="call_measure",
        item_id="fc_measure",
    )
    env, client, agent = play(
        [
            response(reasoning, first_call, response_id="resp_first"),
            response(
                function_call(
                    "submit_diagnosis",
                    DIAGNOSIS,
                    call_id="call_diagnosis",
                    item_id="fc_diagnosis",
                ),
                response_id="resp_second",
            ),
        ]
    )

    assert env.status == "DIAGNOSED"
    second_input = client.responses.requests[1]["input"]
    assert second_input[1] == reasoning
    assert second_input[2] == first_call
    assert second_input[3]["type"] == "function_call_output"
    assert second_input[3]["call_id"] == "call_measure"
    tool_result = json.loads(second_input[3]["output"])
    assert tool_result["mean_reading"] > 0
    assert list(tool_result) == sorted(tool_result)
    assert client.responses.requests[0]["input"][0]["content"] == render_observation(
        episode().session().observation()
    )
    assert agent.transcript[1]["response_id"] == "resp_first"
    assert agent.transcript[1]["response"]["output"] == [reasoning, first_call]


def test_multiple_function_calls_run_in_order_until_session_finishes():
    calls = [
        function_call(
            "measure_od",
            {"time_h": 18, "dilution_factor": 10, "replicates": 1},
            call_id="call_measure",
        ),
        function_call(
            "submit_diagnosis", DIAGNOSIS, call_id="call_diagnosis"
        ),
        function_call(
            "measure_od",
            {"time_h": 12, "dilution_factor": 10, "replicates": 1},
            call_id="call_after_finish",
        ),
    ]
    env, client, _ = play([response(*calls)])

    assert env.status == "DIAGNOSED"
    assert [event.tool for event in env.events] == [
        "measure_od",
        "submit_diagnosis",
    ]
    assert len(client.responses.requests) == 1


def test_no_function_call_adds_reminder():
    env, client, agent = play(
        [
            response(
                {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": "I am considering the data."}
                ]}
            ),
            response(function_call("submit_diagnosis", DIAGNOSIS)),
        ]
    )

    assert env.status == "DIAGNOSED"
    assert client.responses.requests[1]["input"][-1] == {
        "role": "user",
        "content": REMINDER,
    }
    assert any(
        entry.get("reminder") and entry["content"] == REMINDER
        for entry in agent.transcript
    )


def test_incomplete_response_with_tool_call_adds_reminder():
    env, client, _ = play(
        [
            response(
                function_call(
                    "measure_od",
                    {"time_h": 18, "dilution_factor": 10, "replicates": 1},
                ),
                status="incomplete",
            ),
            response(function_call("submit_diagnosis", DIAGNOSIS)),
        ]
    )

    assert env.status == "DIAGNOSED"
    assert client.responses.requests[1]["input"][-1] == {
        "role": "user",
        "content": REMINDER,
    }


def test_refusal_maps_to_refused():
    env, client, agent = play(
        [
            response(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "refusal", "refusal": "I cannot help."}],
                }
            )
        ]
    )

    assert env.status == "REFUSED"
    assert agent.outcome == "REFUSED"
    assert len(client.responses.requests) == 1
    assert agent.transcript[-1]["kind"] == "end"


def test_model_mismatch_fails_but_dated_snapshot_is_accepted():
    env, _, agent = play(
        [response(function_call("submit_diagnosis", DIAGNOSIS), model="gpt-6-other")]
    )
    assert env.status == "API_FAILURE"
    assert agent.outcome == "API_FAILURE"
    assert "gpt-6-other" in agent.reason

    env, _, agent = play(
        [
            response(
                function_call("submit_diagnosis", DIAGNOSIS),
                model="gpt-6-luna-2026-10-04",
            )
        ]
    )
    assert env.status == "DIAGNOSED"
    assert agent.outcome is None


def test_unparsable_arguments_are_sent_as_empty_object_and_logged():
    bad_arguments = "{not-json"
    env, _, agent = play(
        [
            response(function_call("measure_od", bad_arguments)),
            response(function_call("submit_diagnosis", DIAGNOSIS)),
        ]
    )

    assert env.status == "DIAGNOSED"
    assert env.events[0].arguments == {}
    assert env.events[0].ok is False
    assert agent.transcript[1]["response"]["output"][0]["arguments"] == bad_arguments


def test_openai_api_error_maps_to_api_failure():
    env, _, agent = play([openai_agent.OpenAIAPIError("HTTP 503")])

    assert env.status == "API_FAILURE"
    assert agent.outcome == "API_FAILURE"
    assert "OpenAIAPIError" in agent.reason


class FakeHTTPResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.data


def test_urllib_client_posts_json_with_server_side_bearer_header(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-secret")
    payload = {"id": "resp_http", "model": MODEL, "output": []}
    requests = []

    def fake_urlopen(request, *, timeout):
        requests.append((request, timeout))
        return FakeHTTPResponse(json.dumps(payload).encode())

    monkeypatch.setattr(openai_agent.urllib.request, "urlopen", fake_urlopen)
    client = openai_agent.OpenAIResponsesClient()
    params = {"model": MODEL, "input": [], "store": False}

    assert client.responses.create(**params) == payload
    request, timeout = requests[0]
    assert request.full_url == openai_agent.API_URL
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer test-key-not-a-secret"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == params
    assert timeout == 120


@pytest.mark.parametrize(
    "failure",
    [
        lambda: urllib_error.HTTPError(
            openai_agent.API_URL, 429, "rate limited", None, io.BytesIO(b"")
        ),
        lambda: urllib_error.HTTPError(
            openai_agent.API_URL, 503, "unavailable", None, io.BytesIO(b"")
        ),
        lambda: urllib_error.URLError("connection failed"),
    ],
)
def test_http_failures_retry_four_times_then_raise(monkeypatch, failure):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-secret")
    calls = []
    sleeps = []

    def fake_urlopen(request, *, timeout):
        calls.append(request)
        raise failure()

    monkeypatch.setattr(openai_agent.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(openai_agent.time, "sleep", sleeps.append)
    client = openai_agent.OpenAIResponsesClient()

    with pytest.raises(openai_agent.OpenAIAPIError) as exc_info:
        client.responses.create(model=MODEL)

    assert len(calls) == 5
    assert sleeps == [1, 2, 4, 8]
    assert "test-key-not-a-secret" not in str(exc_info.value)


def test_exhausted_http_retries_map_to_api_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-secret")
    calls = []

    def fake_urlopen(request, *, timeout):
        calls.append(request)
        raise urllib_error.HTTPError(
            openai_agent.API_URL, 503, "unavailable", None, io.BytesIO(b"")
        )

    monkeypatch.setattr(openai_agent.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(openai_agent.time, "sleep", lambda _: None)
    env = episode()
    agent = openai_agent.OpenAIResponsesAgent(
        openai_agent.OpenAIResponsesClient(), model=MODEL, effort="high"
    )
    agent.run(env.session())

    assert len(calls) == 5
    assert agent.outcome == "API_FAILURE"
    assert agent.transcript[-1]["kind"] == "end"
