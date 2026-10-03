"""T-012 (hidden state cannot reach the agent) and T-028 (prompt-v1 snapshot, no scaffolding)."""

import ast
import json
import re
from pathlib import Path

import pytest
from anthropic.types import Message

from mirage.agents.claude import ClaudeAgent
from mirage.agents.scripted import GoodScientist
from mirage.biology.conditions import Condition
from mirage.config import load_prior, sample_episode
from mirage.lab.environment import LabEnvironment
from mirage.lab.tools import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TOOL_DEFINITIONS,
    render_observation,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "mirage"
PRIOR = load_prior(ROOT / "experiments" / "configs" / "scenario_v1.json")
SNAPSHOT = Path(__file__).parent / "snapshots" / "prompt_v1.json"
SNAPSHOT_EPISODE = (0, Condition.BIOLOGICAL_PLATEAU)

FORBIDDEN = ("saturat", "artefact", "artifact", "linear", "plateau", "carrying capacity",
             "ceiling", "calibrat", "detector", "hidden", "ground truth", "BIOLOGICAL_PLATEAU",
             "MEASUREMENT_ARTIFACT", "kappa", "lambda")
SCAFFOLD = ("hypothes", "alternative", "competing", "explanation")
VISIBLE_BANNED = ("mirage.config", "mirage.biology", "mirage.assay", "mirage.evaluation",
                  "mirage.lab.environment")


def imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            out.add(mod)
            out |= {f"{mod}.{a.name}" for a in node.names}
    return out


def hits(text: str, terms) -> list[str]:
    low = text.lower()
    return [t for t in terms if t.lower() in low]


def visible_modules() -> list[Path]:
    return sorted((SRC / "agents").glob("*.py")) + [SRC / "lab" / "tools.py"]


# ---- T-012 (1): AST import scan -------------------------------------------------------------

@pytest.mark.parametrize("path", visible_modules(), ids=lambda p: p.name)
def test_t012_visible_modules_import_nothing_hidden(path) -> None:
    bad = [m for m in imports(path) for b in VISIBLE_BANNED if m == b or m.startswith(b + ".")]
    assert not bad, f"{path.name} imports hidden modules: {bad}"


@pytest.mark.parametrize("path", sorted((SRC / "evaluation").glob("*.py")), ids=lambda p: p.name)
def test_t012_evaluation_does_not_import_anthropic(path) -> None:
    assert not [m for m in imports(path) if m.split(".")[0] == "anthropic"]


def test_t012_scan_detects_a_violation(tmp_path) -> None:
    p = tmp_path / "leak.py"
    p.write_text("from mirage.config import EpisodeConfig\nimport mirage.assay.od_reader\n")
    found = imports(p)
    assert "mirage.config" in found and "mirage.assay.od_reader" in found


# ---- T-012 (2,3): prompt-leakage scan and whitelist ---------------------------------------

def episodes(n_per: int = 100):
    for cond in Condition:
        for seed in range(n_per):
            yield sample_episode(PRIOR, seed, cond)


def test_t012_prompt_tools_and_tool_results_leak_nothing() -> None:
    assert not hits(SYSTEM_PROMPT, FORBIDDEN)
    assert not hits(json.dumps(TOOL_DEFINITIONS), FORBIDDEN)
    for cfg in episodes():
        env = LabEnvironment(cfg)
        obs = render_observation(env.observation())
        assert not hits(obs, FORBIDDEN), cfg.episode_id
        GoodScientist().run(env.session())
        for e in env.events:
            payload = json.dumps({"result": e.result, "error": e.error})
            assert not hits(payload, FORBIDDEN), (cfg.episode_id, e.tool)


def test_t012_observation_key_whitelist() -> None:
    obs = json.loads(render_observation(LabEnvironment(sample_episode(PRIOR, 1, Condition.MEASUREMENT_ARTIFACT)).observation()))
    assert set(obs) == {"budget", "experiment", "limits", "passive_readings"}
    assert set(obs["budget"]) == {"cost", "remaining_units", "total_units"}
    assert set(obs["experiment"]) == {"assay", "culture", "retained_aliquots_h"}
    assert set(obs["limits"]) == {"dilution_factor", "max_turns", "replicates", "time_h"}
    assert len(obs["passive_readings"]) == 19
    assert all(set(r) == {"dilution_factor", "reading", "time_h"} for r in obs["passive_readings"])


def test_t012_observation_depends_only_on_readings() -> None:
    ca = sample_episode(PRIOR, 7, Condition.BIOLOGICAL_PLATEAU)
    cb = sample_episode(PRIOR, 8, Condition.MEASUREMENT_ARTIFACT)
    a, b = LabEnvironment(ca), LabEnvironment(cb)
    b.passive = a.passive  # same readings, different hidden configuration
    assert render_observation(a.observation()) == render_observation(b.observation())
    assert ca != cb


# ---- T-012 (4): payload scan with the mocked Anthropic client ------------------------------

class CapturingClient:
    def __init__(self) -> None:
        self.payloads: list[str] = []
        self.messages = self
        self._n = 0

    def create(self, **params):
        self.payloads.append(json.dumps(params, default=lambda o: o.model_dump(), sort_keys=True))
        self._n += 1
        if self._n == 1:
            block = {"type": "tool_use", "id": "t1", "name": "measure_od",
                     "input": {"time_h": 18, "dilution_factor": 10, "replicates": 3}}
        else:
            block = {"type": "tool_use", "id": "t2", "name": "submit_diagnosis",
                     "input": {"diagnosis": "GROWTH_STOPPED", "p_growth_continued": 0.2,
                               "late_biomass_estimate_od": None, "rationale": "r"}}
        return Message.model_validate({
            "id": "m", "type": "message", "role": "assistant", "model": params["model"],
            "content": [block], "stop_reason": "tool_use", "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1}})


def test_t012_request_payloads_leak_nothing() -> None:
    for cfg in episodes(10):
        client = CapturingClient()
        ClaudeAgent(client).run(LabEnvironment(cfg).session())
        assert len(client.payloads) == 2
        secrets = {f"{cfg.growth.k_odeq:.6g}", f"{cfg.assay.s_odeq:.6g}"}
        for p in client.payloads:
            assert not hits(p, FORBIDDEN), cfg.episode_id
            assert not [s for s in secrets if re.search(rf"(?<![\d.]){re.escape(s)}(?!\d)", p)]


# ---- T-028: snapshot and no scaffolding ---------------------------------------------------

def rendered_surfaces() -> dict[str, str]:
    seed, cond = SNAPSHOT_EPISODE
    first = render_observation(LabEnvironment(sample_episode(PRIOR, seed, cond)).observation())
    return {"prompt_version": PROMPT_VERSION, "system_prompt": SYSTEM_PROMPT,
            "initial_user_message": first,
            "tool_definitions": json.dumps(TOOL_DEFINITIONS, sort_keys=True, ensure_ascii=False)}


def test_t028_prompt_matches_committed_snapshot() -> None:
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert rendered_surfaces() == snap, (
        "prompt surface changed: bump PROMPT_VERSION and update the snapshot with science-lead approval")


def test_t028_no_scaffolding() -> None:
    s = rendered_surfaces()
    for key in ("system_prompt", "initial_user_message"):
        assert not hits(s[key], SCAFFOLD), key
        assert "declare_state" not in s[key], key
    by_name = {d["name"]: d for d in TOOL_DEFINITIONS}
    assert "optional" in by_name["declare_state"]["description"].lower()
    for d in TOOL_DEFINITIONS:
        assert not hits(json.dumps(d), FORBIDDEN), d["name"]


def test_terms_scan_is_case_insensitive() -> None:
    assert hits("The detector SATURATES", FORBIDDEN) == ["saturat", "detector"]
    assert hits("an Alternative", SCAFFOLD) == ["alternative"]
