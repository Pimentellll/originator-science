"""Cross-family driver tests use fake Responses API clients only."""

from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest

from mirage.biology.conditions import Condition

ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_DIR = ROOT / "experiments" / "exploratory" / "cross-family"
spec = importlib.util.spec_from_file_location(
    "exp_cross_family_driver", EXPERIMENT_DIR / "driver.py"
)
if spec is None or spec.loader is None:
    raise ImportError("cannot load cross-family driver")
driver = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = driver
spec.loader.exec_module(driver)
openai_agent = importlib.import_module("exp_cross_family_openai_agent")

MODEL = "gpt-6-luna"
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


def function_call(name, arguments, call_id="call_1"):
    return {
        "type": "function_call",
        "id": "fc_1",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(arguments),
    }


def diagnosed_response(response_id="resp_1"):
    return {
        "id": response_id,
        "model": MODEL,
        "status": "completed",
        "output": [function_call("submit_diagnosis", DIAGNOSIS)],
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


def test_y1_dev_matrix_has_registered_development_seeds():
    episodes = driver.runner.load_matrix(driver.DEV_MATRIX, "dev")

    assert episodes == [
        (0, Condition.BIOLOGICAL_PLATEAU),
        (1, Condition.MEASUREMENT_ARTIFACT),
    ]
    assert driver.CONFIGS["Y1"] == ("gpt-6-luna", "high")
    assert driver.SPEND_CAP_USD == 2.00
    assert driver.STRONG_MATRIX == ROOT / "experiments" / "configs" / "eval_matrix_v1.json"


def test_cost_arithmetic_includes_cached_input_and_output():
    usage = {
        "input_tokens": 100,
        "input_tokens_details": {"cached_tokens": 40},
        "output_tokens": 20,
    }

    assert driver.cost_usd(usage, MODEL) == pytest.approx(0.0000164)


def test_metered_client_writes_usage_and_ledger(tmp_path):
    client = FakeClient([diagnosed_response()])
    metered = driver.MeteredClient(
        client,
        run_dir=tmp_path / "run",
        ledger_path=tmp_path / "ledger.jsonl",
        run_id="run-1",
        config="Y1",
        matrix="dev",
    )
    metered.responses.create(model=MODEL)

    usage = json.loads((tmp_path / "run" / "usage.jsonl").read_text().splitlines()[0])
    ledger = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])
    assert usage["input_tokens"] == 100
    assert usage["cached_input_tokens"] == 20
    assert usage["output_tokens"] == 30
    assert usage["cost_usd"] == pytest.approx(
        driver.cost_usd(diagnosed_response()["usage"], MODEL)
    )
    assert ledger["run_id"] == "run-1"
    assert ledger["config"] == "Y1"
    assert ledger["matrix"] == "dev"
    assert ledger["model"] == MODEL
    assert ledger["cost_usd"] == usage["cost_usd"]
    assert driver._ledger_total(tmp_path / "ledger.jsonl") == pytest.approx(
        usage["cost_usd"]
    )


def test_spend_guard_stops_before_an_over_cap_request(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(json.dumps({"cost_usd": 1.999}) + "\n", encoding="utf-8")
    client = FakeClient([])
    metered = driver.MeteredClient(
        client,
        run_dir=tmp_path / "run",
        ledger_path=ledger_path,
        run_id="guarded",
        config="Y1",
        matrix="dev",
    )

    with pytest.raises(driver.SpendCapReached, match="spend cap"):
        metered.responses.create(model=MODEL)

    assert client.responses.requests == []


def test_fake_dev_run_summarizes_and_builds_report_with_openai_agent(tmp_path):
    client = FakeClient([diagnosed_response("resp_0"), diagnosed_response("resp_1")])
    result_dir = driver.run_config(
        "Y1",
        "dev",
        client=client,
        ledger_path=tmp_path / "ledger.jsonl",
        out_root=tmp_path / "runs",
    )

    manifest = json.loads((result_dir / "manifest.json").read_text())
    records = [
        driver.runner.EpisodeResult.model_validate_json(path.read_text())
        for path in sorted((result_dir / "episodes").glob("*.json"))
    ]
    summary = json.loads((result_dir / "summary.json").read_text())

    assert manifest["model"] == MODEL
    assert manifest["effort"] == "high"
    assert manifest["api"] == "openai-responses"
    expected_tools_hash = hashlib.sha256(
        json.dumps(
            client.responses.requests[0]["tools"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert manifest["tools_sha256"] == expected_tools_hash
    assert len(records) == 2
    assert all(record.agent.name == "openai_responses" for record in records)
    assert all(record.agent.model == MODEL for record in records)
    assert all(record.status == "DIAGNOSED" and record.scores is not None for record in records)
    assert summary["n_episodes"] == 2
    assert (result_dir / "results.md").exists()
    assert (result_dir / "results.png").exists()
    assert "Y1 GPT-6 Luna high" in (result_dir / "results.md").read_text()


def test_api_failure_is_rerun_once_by_runner(tmp_path):
    client = FakeClient(
        [
            openai_agent.OpenAIAPIError("HTTP 503"),
            diagnosed_response("resp_retry"),
            diagnosed_response("resp_second_episode"),
        ]
    )
    result_dir = driver.run_config(
        "Y1",
        "dev",
        client=client,
        ledger_path=tmp_path / "ledger.jsonl",
        out_root=tmp_path / "runs",
    )
    manifest = json.loads((result_dir / "manifest.json").read_text())
    episode_paths = sorted((result_dir / "episodes").glob("*.json"))
    records = [
        driver.runner.EpisodeResult.model_validate_json(path.read_text())
        for path in episode_paths
    ]
    first_episode_id = records[0].episode.episode_id
    attempt1 = driver.runner.EpisodeResult.model_validate_json(
        (result_dir / "reruns" / f"{first_episode_id}.attempt1.json").read_text()
    )

    assert len(client.responses.requests) == 3
    assert manifest["reruns"] == {
        first_episode_id: f"reruns/{first_episode_id}.attempt1.json"
    }
    assert attempt1.status == "API_FAILURE"
    assert all(record.status == "DIAGNOSED" for record in records)


def test_cli_run_and_spend_commands(tmp_path, monkeypatch, capsys):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        json.dumps({"config": "Y1", "matrix": "dev", "cost_usd": 0.25}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(driver, "DEFAULT_LEDGER", ledger_path)
    calls = []

    def fake_run_config(config, matrix, *, resume_run_id=None):
        calls.append((config, matrix, resume_run_id))
        return tmp_path / "run-dir"

    monkeypatch.setattr(driver, "run_config", fake_run_config)

    assert driver.main(
        ["run", "--config", "Y1", "--matrix", "dev", "--resume", "run-1"]
    ) == 0
    assert calls == [("Y1", "dev", "run-1")]
    assert "run-dir" in capsys.readouterr().out
    assert driver.main(["spend"]) == 0
    assert "Total: $0.250000" in capsys.readouterr().out
