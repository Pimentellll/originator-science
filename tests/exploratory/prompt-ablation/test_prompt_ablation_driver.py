"""Driver accounting and end-to-end tests using only a fake Messages API client."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from anthropic.types import Message

from mirage.lab.tools import TOOL_DEFINITIONS

ROOT = Path(__file__).resolve().parents[3]
DRIVER_PATH = (
    ROOT / "experiments" / "exploratory" / "prompt-ablation" / "driver.py"
)
spec = importlib.util.spec_from_file_location("prompt_ablation_driver_test", DRIVER_PATH)
assert spec is not None and spec.loader is not None
driver = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = driver
spec.loader.exec_module(driver)


def msg(*blocks, usage=None, model=driver.MODEL):
    return Message.model_validate(
        {
            "id": "msg_prompt_ablation",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": list(blocks),
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": usage or {"input_tokens": 100, "output_tokens": 20},
        }
    )


def tool(name, args, index=0):
    return {
        "type": "tool_use",
        "id": f"toolu_prompt_ablation_{index}",
        "name": name,
        "input": args,
    }


DIAGNOSIS = {
    "diagnosis": "BIOMASS_AS_READ",
    "p_biomass_above_reading": 0.1,
    "late_biomass_estimate_od": None,
    "rationale": "The available readings are consistent with the stated level.",
}


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **params):
        self.requests.append(dict(params))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_variant_agent_replaces_only_the_system_prompt() -> None:
    from mirage.agents.claude import ClaudeAgent

    messages = [{"role": "user", "content": "hello"}]
    base = ClaudeAgent(object(), model=driver.MODEL).request_params(messages)
    variant = driver.VariantClaudeAgent(
        object(), model=driver.MODEL, prompt_version="prompt-v2-noceiling"
    ).request_params(messages)
    assert variant["system"] == driver.PROMPTS["prompt-v2-noceiling"]
    assert {key: value for key, value in variant.items() if key != "system"} == {
        key: value for key, value in base.items() if key != "system"
    }
    assert variant["tools"] == TOOL_DEFINITIONS


def test_cost_usd_handles_cache_breakdown_and_legacy_fallback() -> None:
    usage = {
        "input_tokens": 100_000,
        "output_tokens": 20_000,
        "cache_read_input_tokens": 10_000,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 5_000,
            "ephemeral_1h_input_tokens": 2_000,
        },
    }
    assert driver.cost_usd(usage, driver.MODEL) == pytest.approx(0.4225)
    legacy = {
        "input_tokens": 100_000,
        "output_tokens": 20_000,
        "cache_read_input_tokens": 10_000,
        "cache_creation_input_tokens": 7_000,
    }
    assert driver.cost_usd(legacy, driver.MODEL) == pytest.approx(0.4195)


def test_metered_client_records_usage_and_ledger_lines(tmp_path: Path) -> None:
    usage = {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_input_tokens": 10,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 5,
            "ephemeral_1h_input_tokens": 2,
        },
    }
    fake = FakeClient([msg(tool("submit_diagnosis", DIAGNOSIS), usage=usage)])
    run_dir = tmp_path / "run"
    ledger_path = tmp_path / "spend_ledger.jsonl"
    metered = driver.MeteredClient(
        fake,
        run_dir=run_dir,
        ledger_path=ledger_path,
        run_id="fake-run",
        arm="prompt-v2-noceiling",
        matrix="dev",
    )
    response = metered.messages.create(model=driver.MODEL)
    assert response.model == driver.MODEL
    assert len(fake.requests) == 1

    usage_line = json.loads((run_dir / "usage.jsonl").read_text(encoding="utf-8"))
    assert set(usage_line) == {
        "model",
        "stop_reason",
        "input_tokens",
        "output_tokens",
        "cache_read",
        "cache_write",
        "s",
    }
    assert usage_line == {
        "model": driver.MODEL,
        "stop_reason": "tool_use",
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read": 10,
        "cache_write": 7,
        "s": usage_line["s"],
    }
    assert isinstance(usage_line["s"], float)

    ledger_line = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger_line["run_id"] == "fake-run"
    assert ledger_line["arm"] == "prompt-v2-noceiling"
    assert ledger_line["matrix"] == "dev"
    assert ledger_line["model"] == driver.MODEL
    assert ledger_line["input_tokens"] == 100
    assert ledger_line["output_tokens"] == 20
    assert ledger_line["cache_read_input_tokens"] == 10
    assert ledger_line["cache_creation_ephemeral_5m_input_tokens"] == 5
    assert ledger_line["cache_creation_ephemeral_1h_input_tokens"] == 2
    assert ledger_line["cost_usd"] == pytest.approx(driver.cost_usd(usage, driver.MODEL))
    assert ledger_line["utc"].endswith("+00:00")


def test_spend_guard_refuses_before_call_when_ledger_is_near_cap(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text('{"cost_usd":0.01}\n', encoding="utf-8")
    fake = FakeClient([msg(tool("submit_diagnosis", DIAGNOSIS))])
    metered = driver.MeteredClient(
        fake,
        run_dir=tmp_path / "run",
        ledger_path=ledger_path,
        run_id="guarded",
        arm="prompt-v2-noceiling",
        matrix="dev",
        cap=0.2,
    )
    with pytest.raises(driver.SpendCapReached, match="spend cap"):
        metered.messages.create(model=driver.MODEL)
    assert fake.requests == []
    assert not (tmp_path / "run" / "usage.jsonl").exists()


def test_inner_client_exception_is_reraised_without_logging(tmp_path: Path) -> None:
    failure = RuntimeError("fake failure")
    fake = FakeClient([failure])
    run_dir = tmp_path / "run"
    ledger_path = tmp_path / "ledger.jsonl"
    metered = driver.MeteredClient(
        fake,
        run_dir=run_dir,
        ledger_path=ledger_path,
        run_id="failed",
        arm="prompt-v2-noceiling",
        matrix="dev",
    )
    with pytest.raises(RuntimeError, match="fake failure"):
        metered.messages.create(model=driver.MODEL)
    assert not (run_dir / "usage.jsonl").exists()
    assert not ledger_path.exists()


def test_dev_run_arm_writes_variant_records_summary_and_report(tmp_path: Path) -> None:
    responses = [
        msg(tool("submit_diagnosis", DIAGNOSIS, index))
        for index in range(4)
    ]
    fake = FakeClient(responses)
    ledger_path = tmp_path / "ledger.jsonl"
    run_dir = driver.run_arm(
        "prompt-v2-noceiling",
        "dev",
        out_root=tmp_path / "runs",
        run_id="test-noceiling-dev",
        client=fake,
        ledger_path=ledger_path,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["prompt_version"] == "prompt-v2-noceiling"
    assert manifest["prompt_sha256"] == driver.variant_sha256(
        driver.PROMPTS["prompt-v2-noceiling"]
    )
    assert manifest["model"] == "claude-sonnet-5-5"

    episode_files = sorted((run_dir / "episodes").glob("*.json"))
    assert len(episode_files) == 4
    episodes = [json.loads(path.read_text(encoding="utf-8")) for path in episode_files]
    assert all(
        episode["agent"]["prompt_version"] == "prompt-v2-noceiling"
        for episode in episodes
    )
    assert (run_dir / "summary.json").is_file()
    assert len((run_dir / "usage.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    assert len(ledger_path.read_text(encoding="utf-8").splitlines()) == 4
    assert (run_dir / "results.md").is_file()
    assert (run_dir / "results.png").is_file()
    markdown = (run_dir / "results.md").read_text(encoding="utf-8")
    assert "| Sonnet 5.5 prompt-v2-noceiling | 4 |" in markdown
    assert "C1 Claude" not in markdown
    assert "C2 Claude Sonnet 5.5" not in markdown
    assert "B1 GoodScientist" not in markdown
    assert "B2 PassiveBayes" not in markdown
    assert len(fake.requests) == 4


def test_missing_key_rejects_run_before_creating_client(monkeypatch) -> None:
    called = False

    def unexpected_client():
        nonlocal called
        called = True
        raise AssertionError("client factory should not be called")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(driver, "make_client", unexpected_client)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is not set"):
        driver.run_arm("prompt-v2-minimal", "dev")
    assert not called


def test_cli_missing_key_and_spend_cap_exit_two(monkeypatch, capsys) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert driver.main(
        ["run", "--prompt", "prompt-v2-minimal", "--matrix", "dev"]
    ) == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err

    def capped(*args, **kwargs):
        raise driver.SpendCapReached("spend cap reached")

    monkeypatch.setattr(driver, "run_arm", capped)
    assert driver.main(
        ["run", "--prompt", "prompt-v2-minimal", "--matrix", "dev"]
    ) == 2
    assert "spend cap reached" in capsys.readouterr().err


def test_spend_command_prints_total_and_per_run_subtotals(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        '{"run_id":"run-a","cost_usd":0.25}\n'
        '{"run_id":"run-a","cost_usd":0.5}\n'
        '{"run_id":"run-b","cost_usd":1.0}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(driver, "DEFAULT_LEDGER", ledger_path)
    assert driver.main(["spend"]) == 0
    output = capsys.readouterr().out
    assert "Total: $1.750000" in output
    assert "run-a: $0.750000" in output
    assert "run-b: $1.000000" in output
