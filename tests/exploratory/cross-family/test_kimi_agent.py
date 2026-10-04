"""Y2 (Kimi K3 via Kimi Code chat completions) tests use fake clients only."""

from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import socket
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_DIR = ROOT / "experiments" / "exploratory" / "cross-family"
if "exp_cross_family_driver" in sys.modules:
    driver = sys.modules["exp_cross_family_driver"]
else:
    spec = importlib.util.spec_from_file_location(
        "exp_cross_family_driver", EXPERIMENT_DIR / "driver.py"
    )
    assert spec is not None and spec.loader is not None
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver
    spec.loader.exec_module(driver)
kimi_agent = importlib.import_module("exp_cross_family_kimi_agent")

MODEL = "k3"
DIAGNOSIS = {
    "diagnosis": "BIOMASS_ABOVE_READING",
    "p_biomass_above_reading": 0.9,
    "late_biomass_estimate_od": 4.0,
    "rationale": "The diluted late measurement is above the plateau.",
}
USAGE = {
    "prompt_tokens": 1000,
    "completion_tokens": 200,
    "cached_tokens": 600,
    "completion_tokens_details": {"reasoning_tokens": 150},
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*args, **kwargs):
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.setattr(kimi_agent.urllib.request, "urlopen", guard)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)


def chat(message, *, model=MODEL, finish="tool_calls", rid="chatcmpl-1"):
    return {
        "id": rid,
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": USAGE,
    }


def diagnose(call_id="tool_1", rid="chatcmpl-1"):
    return chat(
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "thinking",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "submit_diagnosis", "arguments": json.dumps(DIAGNOSIS)},
                }
            ],
        },
        rid=rid,
    )


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []
        self.responses = self

    def create(self, **params):
        self.requests.append(copy.deepcopy(params))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def dev_run(tmp_path, responses):
    client = FakeClient(responses)
    result_dir = driver.run_config(
        "Y2", "dev", client=client, ledger_path=tmp_path / "ledger.jsonl", out_root=tmp_path / "runs"
    )
    records = [
        driver.runner.EpisodeResult.model_validate_json(path.read_text())
        for path in sorted((result_dir / "episodes").glob("*.json"))
    ]
    return client, result_dir, records


def test_y2_is_registered_as_k3_high_on_kimi_code():
    assert driver.CONFIGS["Y2"] == ("k3", "high")
    assert driver.PROVIDERS["Y2"]["env"] == "MOONSHOT_API_KEY"
    assert kimi_agent.API_URL == "https://api.kimi.com/coding/v1/chat/completions"


def test_chat_usage_counts_cached_tokens_and_list_price():
    assert driver._usage_counts(USAGE) == {
        "input_tokens": 1000,
        "cached_input_tokens": 600,
        "output_tokens": 200,
    }
    nested = {"prompt_tokens": 10, "completion_tokens": 1, "prompt_tokens_details": {"cached_tokens": 4}}
    assert driver._usage_counts(nested)["cached_input_tokens"] == 4
    assert driver.cost_usd(USAGE, MODEL) == pytest.approx((400 * 3 + 600 * 0.3 + 200 * 15) / 1e6)


def test_request_shape_and_full_assistant_message_replay(tmp_path):
    thinking = chat(
        {"role": "assistant", "content": "Let me think.", "reasoning_content": "secret-ish"},
        finish="stop",
        rid="chatcmpl-0",
    )
    client, result_dir, records = dev_run(tmp_path, [thinking, diagnose(), diagnose("tool_2")])

    first, second = client.requests[0], client.requests[1]
    assert first["model"] == MODEL and first["reasoning_effort"] == "high"
    assert first["messages"][0]["role"] == "system"
    assert first["messages"][1]["role"] == "user"
    names = [t["function"]["name"] for t in first["tools"]]
    assert "submit_diagnosis" in names and all(t["type"] == "function" for t in first["tools"])
    # The whole assistant message, reasoning included, goes back, then the reminder.
    assert second["messages"][2] == thinking["choices"][0]["message"]
    assert second["messages"][3] == {"role": "user", "content": kimi_agent.REMINDER}

    assert len(records) == 2
    assert all(r.status == "DIAGNOSED" and r.agent.name == "kimi_chat" for r in records)
    manifest = json.loads((result_dir / "manifest.json").read_text())
    assert manifest["api"] == "kimi-code-chat-completions"
    assert manifest["endpoint"] == kimi_agent.API_URL
    assert manifest["model"] == MODEL
    assert "Y2 Kimi K3 high" in (result_dir / "results.md").read_text()
    ledger = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert len(ledger) == 3 and all(line["config"] == "Y2" for line in ledger)


def test_tool_results_are_sent_as_tool_messages():
    class Session:
        finished = False

        def observation(self):
            raise NotImplementedError

        def call(self, tool, args):
            self.finished = True
            return type("R", (), {"ok": True, "result": {"accepted": True}, "error": None})()

    agent = kimi_agent.KimiChatAgent(FakeClient([diagnose("tool_9")]), model=MODEL, effort="high")
    agent_render = kimi_agent.render_observation
    kimi_agent.render_observation = lambda obs: "start"
    try:
        Session.observation = lambda self: None
        agent.run(Session())
    finally:
        kimi_agent.render_observation = agent_render
    tool_msg = agent.transcript[-1]["content"][0]
    assert tool_msg == {"role": "tool", "tool_call_id": "tool_9", "content": json.dumps({"accepted": True})}


@pytest.mark.parametrize(
    ("response", "outcome"),
    [
        (chat({"role": "assistant", "content": "x"}, model="kimi-for-coding"), "API_FAILURE"),
        (chat({"role": "assistant", "content": ""}, finish="content_filter"), "REFUSED"),
        ({"id": "x", "model": MODEL, "choices": []}, "API_FAILURE"),
        (kimi_agent.KimiAPIError("HTTP 500 from Kimi API"), "API_FAILURE"),
    ],
)
def test_failures_map_to_outcomes(response, outcome):
    class Session:
        finished = False

        def observation(self):
            return None

    agent = kimi_agent.KimiChatAgent(FakeClient([response]), model=MODEL, effort="high")
    original = kimi_agent.render_observation
    kimi_agent.render_observation = lambda obs: "start"
    try:
        agent.run(Session())
    finally:
        kimi_agent.render_observation = original
    assert agent.outcome == outcome


def test_client_sends_bearer_and_genuine_user_agent(monkeypatch):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode()

    def urlopen(request, timeout):
        seen["auth"] = request.get_header("Authorization")
        seen["ua"] = request.get_header("User-agent")
        seen["url"] = request.full_url
        return Response()

    monkeypatch.setenv("MOONSHOT_API_KEY", "  sk-test  ")
    monkeypatch.setattr(kimi_agent.urllib.request, "urlopen", urlopen)
    assert kimi_agent.KimiChatClient().create(model=MODEL) == {"ok": True}
    assert seen == {
        "auth": "Bearer sk-test",
        "ua": kimi_agent.USER_AGENT,
        "url": kimi_agent.API_URL,
    }


def test_client_without_key_raises_and_http_errors_retry(monkeypatch):
    with pytest.raises(kimi_agent.KimiAPIError, match="not set"):
        kimi_agent.KimiChatClient().create(model=MODEL)
    calls = []

    def urlopen(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 429, "rate", {}, None)

    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test")
    monkeypatch.setattr(kimi_agent.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(kimi_agent.time, "sleep", lambda s: None)
    with pytest.raises(kimi_agent.KimiAPIError, match="HTTP 429"):
        kimi_agent.KimiChatClient().create(model=MODEL)
    assert len(calls) == kimi_agent.RETRIES + 1


def test_driver_refuses_y2_without_key(tmp_path):
    with pytest.raises(ValueError, match="MOONSHOT_API_KEY"):
        driver.run_config("Y2", "dev", ledger_path=tmp_path / "l.jsonl", out_root=tmp_path / "r")
