"""Tests for the exploratory prompt-ablation driver (fake client only; no network)."""

from __future__ import annotations

import json
import re
import socket
import sys
from pathlib import Path

import anthropic
import httpx2 as httpx
import pytest
from anthropic.types import Message

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT / "experiments" / "exploratory" / "prompt-ablation"
sys.path.insert(0, str(EXP))

import analyze  # noqa: E402
import driver  # noqa: E402
import variants  # noqa: E402
from mirage.agents import claude as claude_mod  # noqa: E402
from mirage.agents.claude import ClaudeAgent  # noqa: E402
from mirage.config import load_prior, sample_episode  # noqa: E402
from mirage.evaluation import runner  # noqa: E402
from mirage.lab import tools as frozen  # noqa: E402
from mirage.lab.environment import LabEnvironment  # noqa: E402

MODEL = "claude-sonnet-5-5"
DEV = EXP / "dev_matrix.json"


@pytest.fixture(autouse=True)
def no_network_or_api_key(monkeypatch):
    def guard(*args, **kwargs):
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def msg(*blocks, model=MODEL, stop="tool_use", tokens=(1000, 100)) -> Message:
    return Message.model_validate({
        "id": "msg_x", "type": "message", "role": "assistant", "model": model,
        "content": list(blocks), "stop_reason": stop, "stop_sequence": None,
        "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
    })


def tool(name, args, i=0):
    return {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": args}


DIAG = {"diagnosis": "BIOMASS_ABOVE_READING", "p_biomass_above_reading": 0.9,
        "late_biomass_estimate_od": 4.0, "rationale": "Diluted reading suggests saturation."}


def script():
    return [msg({"type": "text", "text": "Plateau may be a ceiling."},
                tool("measure_od", {"time_h": 18, "dilution_factor": 10.0, "replicates": 1})),
            msg(tool("submit_diagnosis", DIAG, 1))]


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **params):
        self.requests.append(dict(params, messages=list(params["messages"])))
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def env_session(seed=1, condition="MEASUREMENT_ARTIFACT"):
    prior = load_prior(runner.SCENARIO)
    return LabEnvironment(sample_episode(prior, seed, condition))


# --- variants ---------------------------------------------------------------------------

def test_identity_variant_hashes_to_frozen_prompt_v2():
    assert variants.PROMPT_V2.sha256() == frozen.prompt_sha256()
    assert variants.PROMPT_V2.version == "prompt-v2"


def test_noceiling_changes_only_the_system_prompt_words_undiluted():
    v = variants.PROMPT_V2_NOCEILING
    assert v.tools == frozen.TOOL_DEFINITIONS
    assert v.assay == variants.ASSAY_V2
    assert "undiluted" not in v.system
    assert frozen.SYSTEM_PROMPT.replace("undiluted ", "") == v.system
    assert v.sha256() != frozen.prompt_sha256()


def test_tool_schemas_identical_across_variants():
    skeleton = variants.schema_skeleton(frozen.TOOL_DEFINITIONS)
    for v in variants.VARIANTS.values():
        assert variants.schema_skeleton(v.tools) == skeleton
        assert [t["name"] for t in v.tools] == list(frozen.TOOL_NAMES)


def test_frozen_tool_definitions_not_mutated_by_building_variants():
    assert frozen.prompt_sha256() == "dc07da980883558de995de94ed9c3affc1c8982f31fc5f149f9bfcacda1d91d1"


CUE = re.compile(r"undilut|saturat|ceiling|linear|proportional|correction|evidence|plate reader",
                 re.IGNORECASE)


def test_minimal_has_no_registered_cue_words_outside_tool_affordance():
    v = variants.PROMPT_V2_MINIMAL
    assert not CUE.search(v.system)
    assert not CUE.search(v.assay)
    descs = json.dumps(variants.schema_skeleton(v.tools))  # schema without descriptions
    assert not CUE.search(descs)
    for t in v.tools:
        texts = [t["description"]] + [p["description"]
                                      for p in t["input_schema"]["properties"].values()]
        for text in texts:
            hits = set(m.lower() for m in CUE.findall(text))
            # The measure_od description keeps its frozen first sentence (registration §3).
            assert hits <= {"plate reader"}, (t["name"], text)


def test_sub_refuses_when_frozen_text_is_missing():
    with pytest.raises(ValueError):
        variants._sub("abc", "zzz", "y")


# --- agent ------------------------------------------------------------------------------

def test_identity_variant_agent_sends_byte_identical_requests_to_frozen_agent():
    a, b = FakeClient(script()), FakeClient(script())
    ClaudeAgent(a, model=MODEL).run(env_session().session())
    agent = driver.VariantClaudeAgent(variants.PROMPT_V2, b, model=MODEL)
    agent.run(env_session().session())
    assert json.dumps(a.requests, default=str) == json.dumps(b.requests, default=str)
    assert agent.prompt_sha256 == frozen.prompt_sha256()


def test_noceiling_agent_swaps_system_only():
    c = FakeClient(script())
    driver.VariantClaudeAgent(variants.PROMPT_V2_NOCEILING, c, model=MODEL).run(
        env_session().session())
    first = c.requests[0]
    assert first["system"] == variants.PROMPT_V2_NOCEILING.system
    assert first["tools"] == frozen.TOOL_DEFINITIONS
    assert first["messages"][0]["content"] == frozen.render_observation(
        env_session().session().observation())


def test_minimal_agent_replaces_assay_only_and_restores_renderer():
    c = FakeClient(script())
    driver.VariantClaudeAgent(variants.PROMPT_V2_MINIMAL, c, model=MODEL).run(
        env_session().session())
    assert claude_mod.render_observation is frozen.render_observation
    sent = json.loads(c.requests[0]["messages"][0]["content"])
    ref = json.loads(frozen.render_observation(env_session().session().observation()))
    assert sent["experiment"]["assay"] == variants.MINIMAL_ASSAY
    ref["experiment"]["assay"] = variants.MINIMAL_ASSAY
    assert sent == ref
    assert c.requests[0]["tools"] == variants.PROMPT_V2_MINIMAL.tools


def test_renderer_restored_after_exception():
    class Boom(FakeClient):
        def create(self, **params):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        driver.VariantClaudeAgent(variants.PROMPT_V2_MINIMAL, Boom([]), model=MODEL).run(
            env_session().session())
    assert claude_mod.render_observation is frozen.render_observation


# --- cost and run loop ------------------------------------------------------------------

def test_call_cost_uses_registered_sonnet_pricing():
    assert driver.call_cost(MODEL, 1_000_000, 0) == pytest.approx(2.0)
    assert driver.call_cost(MODEL, 0, 1_000_000) == pytest.approx(10.0)
    assert driver.call_cost(MODEL, 303_000, 30_000) == pytest.approx(0.906)


def _ledger(tmp_path, stop=4.5):
    return driver.Ledger(root=tmp_path / "empty", stop_usd=stop)


def test_run_variant_end_to_end_with_fake_client(tmp_path):
    client = FakeClient(script() + script())
    run_dir = driver.run_variant("prompt-v2-noceiling", "dev2", tmp_path, matrix_file=DEV,
                                 client=client, run_id="t", ledger=_ledger(tmp_path))
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["prompt_version"] == "prompt-v2-noceiling"
    assert manifest["model"] == MODEL and manifest["effort"] == "high"
    assert manifest["exploratory"] is True and manifest["reruns"] == {}
    assert sorted(p.name for p in (run_dir / "episodes").glob("*.json")) == [
        "s0-BP.json", "s1-MA.json"]
    usage = (run_dir / "usage.jsonl").read_text().splitlines()
    assert len(usage) == 4
    assert driver.spent_usd(run_dir) == pytest.approx(4 * driver.call_cost(MODEL, 1000, 100))
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["n_episodes"] == 2
    rec = json.loads((run_dir / "episodes" / "s1-MA.json").read_text())
    assert rec["agent"]["prompt_version"] == "prompt-v2-noceiling"
    assert rec["scores"]["diagnostic_control"] is True


def test_run_variant_stops_before_exceeding_cap(tmp_path):
    run_dir = driver.run_variant("prompt-v2-minimal", "dev2", tmp_path, matrix_file=DEV,
                                 client=FakeClient([]), run_id="t",
                                 ledger=_ledger(tmp_path, stop=0.10))
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert "stopped_early" in manifest
    assert not any((run_dir / "episodes").glob("*.json"))


def test_run_variant_reruns_api_failure_once_and_keeps_both(tmp_path):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.APIConnectionError(request=req)
    client = FakeClient([err] + script() + script())
    run_dir = driver.run_variant("prompt-v2-noceiling", "dev2", tmp_path, matrix_file=DEV,
                                 client=client, run_id="t", ledger=_ledger(tmp_path))
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["reruns"] == {"s0-BP": "reruns/s0-BP.attempt1.json"}
    first = json.loads((run_dir / "reruns" / "s0-BP.attempt1.json").read_text())
    assert first["status"] == "API_FAILURE"
    final = json.loads((run_dir / "episodes" / "s0-BP.json").read_text())
    assert final["status"] == "DIAGNOSED"


def test_run_variant_refuses_unknown_model_and_existing_dir(tmp_path):
    with pytest.raises(ValueError):
        driver.run_variant("prompt-v2-noceiling", "dev2", tmp_path, matrix_file=DEV,
                           client=FakeClient([]), model="claude-opus-5-5")
    (tmp_path / "t").mkdir()
    with pytest.raises(FileExistsError):
        driver.run_variant("prompt-v2-noceiling", "dev2", tmp_path, matrix_file=DEV,
                           client=FakeClient([]), run_id="t", ledger=_ledger(tmp_path))


def test_metered_client_blocks_calls_after_stop(tmp_path):
    ledger = _ledger(tmp_path, stop=0.0)
    mc = driver.MeteredClient(FakeClient(script()), tmp_path / "u.jsonl", ledger)
    with pytest.raises(driver.BudgetExceeded):
        mc.create(model=MODEL)


# --- analysis ---------------------------------------------------------------------------

def test_ceiling_regex_matches_registered_terms():
    for text in ("reader saturation", "a CEILING", "linear range", "nonlinear", "non-linear",
                 "responded proportionally", "compressed", "dynamic range", "under-reading",
                 "underestimates"):
        assert analyze.CEILING_RE.search(text), text
    assert not analyze.CEILING_RE.search("the culture reached stationary phase")


def test_episode_cue_analysis_on_fake_run(tmp_path):
    client = FakeClient(script() + script())
    run_dir = driver.run_variant("prompt-v2-noceiling", "dev2", tmp_path, matrix_file=DEV,
                                 client=client, run_id="t", ledger=_ledger(tmp_path))
    rows = analyze.episode_rows(run_dir)
    assert len(rows) == 2
    for row in rows:
        assert row["ceiling_named"] is True
        assert row["ceiling_named_before_evidence"] is True  # text block before measure_od
        assert row["first_measure_diagnostic"] is True


def test_word_diff_marks_removed_words():
    d = analyze.word_diff("a b undiluted c", "a b c")
    assert "[-undiluted-]" in d and "{+" not in d
