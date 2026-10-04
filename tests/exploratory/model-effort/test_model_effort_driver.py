"""Model-effort driver tests use fake clients only."""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest
from anthropic.types import Message

ROOT = Path(__file__).resolve().parents[3]
DRIVER_DIR = ROOT / "experiments" / "exploratory" / "model-effort"


def _load_module(name: str, path: Path):
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


driver = _load_module("exp_model_effort_driver", DRIVER_DIR / "driver.py")


@pytest.fixture(autouse=True)
def no_network_or_api_key(monkeypatch):
    def guard(*args, **kwargs):
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def msg(*blocks, model="claude-sonnet-5-5", output_tokens=5):
    return Message.model_validate(
        {
            "id": "msg_x",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": list(blocks),
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "stop_details": None,
            "usage": {"input_tokens": 10, "output_tokens": output_tokens},
        }
    )


def tool(name, args, index=0):
    return {
        "type": "tool_use",
        "id": f"toolu_{index}",
        "name": name,
        "input": args,
    }


DIAGNOSIS = {
    "diagnosis": "BIOMASS_ABOVE_READING",
    "p_biomass_above_reading": 0.9,
    "late_biomass_estimate_od": 4.0,
    "rationale": "The diluted late measurement is above the plateau.",
}


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **params):
        self.requests.append(dict(params, messages=list(params["messages"])))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def diagnosed_responses(model="claude-sonnet-5-5", *, large_output=False):
    output_tokens = 500_000 if large_output else 5
    return [
        msg(
            tool(
                "measure_od",
                {
                    "time_h": 18,
                    "dilution_factor": 10,
                    "replicates": 3,
                },
                1,
            ),
            model=model,
            output_tokens=output_tokens,
        ),
        msg(tool("submit_diagnosis", DIAGNOSIS, 2), model=model),
    ]


def test_effort_agent_preserves_base_request_except_effort():
    baseline = driver.ClaudeAgent(object(), model="claude-sonnet-5-5")
    low = driver.EffortClaudeAgent(
        object(), model="claude-sonnet-5-5", effort="low"
    )
    without_effort = driver.EffortClaudeAgent(
        object(), model="claude-sonnet-5-5", effort=None
    )
    messages = [{"role": "user", "content": "test"}]
    baseline_params = baseline.request_params(messages)
    low_params = low.request_params(messages)
    no_effort_params = without_effort.request_params(messages)

    assert low.effort == "low"
    assert low_params["output_config"] == {"effort": "low"}
    assert without_effort.effort is None
    assert "output_config" not in no_effort_params
    assert {
        key: value for key, value in low_params.items() if key != "output_config"
    } == {
        key: value
        for key, value in baseline_params.items()
        if key != "output_config"
    }
    assert {
        key: value for key, value in no_effort_params.items() if key != "output_config"
    } == {
        key: value
        for key, value in baseline_params.items()
        if key != "output_config"
    }


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("claude-haiku-4-5-20251001", 0.00263),
        ("claude-sonnet-5-5", 0.00526),
        ("claude-opus-5-5", 0.01046),
    ],
)
def test_cost_usd_includes_input_output_and_cache_prices(model, expected):
    usage = {
        "input_tokens": 100,
        "output_tokens": 200,
        "cache_read_input_tokens": 300,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 400,
            "ephemeral_1h_input_tokens": 500,
        },
    }
    assert driver.cost_usd(usage, model) == pytest.approx(expected)


def test_metered_client_logs_usage_and_ledger_and_guards_cap(tmp_path):
    model = "claude-sonnet-5-5"
    response = msg(tool("submit_diagnosis", DIAGNOSIS), model=model)
    client = FakeClient([response])
    metered = driver.MeteredClient(
        client,
        run_dir=tmp_path / "run",
        ledger_path=tmp_path / "ledger.jsonl",
        run_id="run-1",
        config="X2",
        matrix="dev",
    )
    metered.create(model=model, messages=[])

    usage_lines = (tmp_path / "run" / "usage.jsonl").read_text().splitlines()
    ledger_lines = (tmp_path / "ledger.jsonl").read_text().splitlines()
    usage_record = json.loads(usage_lines[0])
    ledger_record = json.loads(ledger_lines[0])
    assert set(usage_record) == {
        "model",
        "stop_reason",
        "input_tokens",
        "output_tokens",
        "cache_read",
        "cache_write",
        "s",
    }
    assert len(usage_lines) == len(ledger_lines) == 1
    assert ledger_record["run_id"] == "run-1"
    assert ledger_record["config"] == "X2"
    assert ledger_record["matrix"] == "dev"
    assert ledger_record["model"] == model
    assert ledger_record["input_tokens"] == 10
    assert ledger_record["output_tokens"] == 5
    assert ledger_record["cost_usd"] == pytest.approx(0.00007)

    expensive_ledger = tmp_path / "expensive.jsonl"
    expensive_ledger.write_text(
        json.dumps({"cost_usd": 4.9}) + "\n",
        encoding="utf-8",
    )
    unused_client = FakeClient([])
    guarded = driver.MeteredClient(
        unused_client,
        run_dir=tmp_path / "guarded",
        ledger_path=expensive_ledger,
        run_id="run-2",
        config="X2",
        matrix="dev",
    )
    with pytest.raises(driver.SpendCapReached):
        guarded.create(model=model, messages=[])
    assert unused_client.requests == []


def test_inner_error_is_not_logged(tmp_path):
    client = FakeClient([RuntimeError("failed")])
    metered = driver.MeteredClient(
        client,
        run_dir=tmp_path / "run",
        ledger_path=tmp_path / "ledger.jsonl",
        run_id="run-1",
        config="X2",
        matrix="dev",
    )
    with pytest.raises(RuntimeError, match="failed"):
        metered.create(model="claude-sonnet-5-5", messages=[])
    assert not (tmp_path / "run" / "usage.jsonl").exists()
    assert not (tmp_path / "ledger.jsonl").exists()


@pytest.mark.parametrize(
    ("config_id", "no_effort", "model", "effort", "has_output_config"),
    [
        ("X2", False, "claude-sonnet-5-5", "low", True),
        ("X1", True, "claude-haiku-4-5-20251001", None, False),
    ],
)
def test_dev_matrix_run_writes_manifest_episodes_summary_reports_and_usage(
    tmp_path,
    config_id,
    no_effort,
    model,
    effort,
    has_output_config,
):
    client = FakeClient(diagnosed_responses(model) * 2)
    run_dir = driver.run_config(
        config_id,
        "dev",
        no_effort=no_effort,
        client=client,
        ledger_path=tmp_path / f"{config_id}-ledger.jsonl",
        out_root=tmp_path / f"{config_id}-runs",
    )

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["model"] == model
    assert manifest["effort"] == effort
    assert run_dir.name.endswith(f"_{config_id}-noeffort" if no_effort else f"_{config_id}")
    assert len(list((run_dir / "episodes").glob("*.json"))) == 2
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "results.md").exists()
    assert (run_dir / "results.png").exists()
    usage_lines = (run_dir / "usage.jsonl").read_text().splitlines()
    assert len(usage_lines) == len(client.requests)
    assert len(usage_lines) == 4
    assert all(("output_config" in request) is has_output_config for request in client.requests)
    if has_output_config:
        assert all(request["output_config"] == {"effort": "low"} for request in client.requests)


def test_x3_gate_and_no_effort_restriction(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(json.dumps({"cost_usd": 2.11}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="requires at least"):
        driver.run_config(
            "X3",
            "dev",
            client=FakeClient([]),
            ledger_path=ledger_path,
            out_root=tmp_path / "runs",
        )
    with pytest.raises(ValueError, match="only allowed for X1"):
        driver.run_config(
            "X2",
            "dev",
            no_effort=True,
            client=FakeClient([]),
            ledger_path=tmp_path / "other-ledger.jsonl",
            out_root=tmp_path / "runs",
        )


def test_spend_cap_during_run_keeps_completed_episode(tmp_path):
    model = "claude-sonnet-5-5"
    client = FakeClient(
        [
            *diagnosed_responses(model),
            *diagnosed_responses(model, large_output=True)[:1],
        ]
    )
    with pytest.raises(driver.SpendCapReached):
        driver.run_config(
            "X2",
            "dev",
            client=client,
            ledger_path=tmp_path / "ledger.jsonl",
            out_root=tmp_path / "runs",
        )

    run_dir = next((tmp_path / "runs").iterdir())
    assert len(list((run_dir / "episodes").glob("*.json"))) == 1
    assert (run_dir / "episodes").is_dir()
    assert len((run_dir / "usage.jsonl").read_text().splitlines()) == 3
