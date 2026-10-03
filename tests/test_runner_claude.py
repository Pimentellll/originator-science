"""Claude runner integration with a fake client only."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import anthropic
import httpx2 as httpx
import pytest
from anthropic.types import Message

from mirage.agents import claude
from mirage.biology.conditions import Condition
from mirage.config import canonical_sha256, load_prior
from mirage.evaluation import report, runner
from mirage.evaluation.metrics import EpisodeResult
from mirage.evaluation.passive import REFERENCE_SEEDS
from mirage.lab.tools import prompt_sha256

ROOT = Path(__file__).resolve().parents[1]
PRIOR = load_prior(runner.SCENARIO)
SHA = canonical_sha256(PRIOR)
MODEL = claude.DEFAULT_MODEL


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
    "rationale": "1:10 back-corrected reading exceeds the plateau.",
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


def fixture_gate0(path: Path, sha: str = SHA) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "gate0-summary-v2",
                "scenario_sha256": sha,
                "diagnostic_action_set": {
                    "scenario_sha256": sha,
                    "late_window_h": [12, 18],
                    "d_min": 1.5,
                    "d_max": 100.0,
                    "auroc_threshold": 0.95,
                    "evaluated_replicates": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def small_matrix(path: Path) -> Path:
    matrix_path = path / "matrix.json"
    episodes = [
        {"seed": 930_000, "condition": Condition.BIOLOGICAL_PLATEAU.value},
        {"seed": 930_001, "condition": Condition.MEASUREMENT_ARTIFACT.value},
    ]
    matrix_path.write_text(
        json.dumps({"matrices": {"two": {"episodes": episodes}}}),
        encoding="utf-8",
    )
    return matrix_path


def api_connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))


def diagnosed_responses():
    return [
        msg(tool("measure_od", {"time_h": 18, "dilution_factor": 10, "replicates": 3}, 1)),
        msg(tool("submit_diagnosis", DIAG, 2)),
    ]


def run_claude(tmp_path: Path, responses, run_id: str = "claude", **run_kwargs) -> Path:
    client = responses if isinstance(responses, FakeClient) else FakeClient(responses)
    return runner.run(
        "claude",
        "two",
        tmp_path / "runs",
        matrix=small_matrix(tmp_path),
        gate0_summary=fixture_gate0(tmp_path / "gate0.json"),
        run_id=run_id,
        reference_seeds=REFERENCE_SEEDS[:5000],
        client=client,
        **run_kwargs,
    )


def records(run_dir: Path) -> list[EpisodeResult]:
    return [
        EpisodeResult.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted((run_dir / "episodes").glob("*.json"))
    ]


def read_manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def test_diagnosed_claude_run_has_llm_records_and_reports(tmp_path: Path) -> None:
    run_dir = run_claude(tmp_path, diagnosed_responses() * 2)
    loaded = records(run_dir)
    assert len(loaded) == 2
    for record in loaded:
        assert record.agent.name == "claude"
        assert record.agent.kind == "llm"
        assert record.agent.model == MODEL
        assert record.agent.prompt_sha256 == prompt_sha256()
        assert record.llm_transcript
        assert record.status == "DIAGNOSED"

    manifest = read_manifest(run_dir)
    assert manifest["model"] == MODEL
    assert manifest["effort"] == "high"
    assert manifest["reruns"] == {}
    report.build_report({"claude": run_dir}, tmp_path / "report")
    markdown = (tmp_path / "report" / "results.md").read_text(encoding="utf-8")
    assert "| C1 Claude | 2 |" in markdown


def test_api_failure_reruns_episode_and_persists_first_attempt(tmp_path: Path) -> None:
    run_dir = run_claude(
        tmp_path,
        [api_connection_error(), *diagnosed_responses(), *diagnosed_responses()],
        run_id="retry",
    )
    final_records = records(run_dir)
    first = next(record for record in final_records if record.episode.seed == 930_000)
    assert first.status == "DIAGNOSED"

    attempt1_path = run_dir / "reruns" / f"{first.episode.episode_id}.attempt1.json"
    attempt1 = EpisodeResult.model_validate_json(attempt1_path.read_text(encoding="utf-8"))
    assert attempt1.status == "API_FAILURE"
    manifest = read_manifest(run_dir)
    assert manifest["reruns"] == {
        first.episode.episode_id: f"reruns/{first.episode.episode_id}.attempt1.json"
    }
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_episodes"] == 2


def test_double_api_failure_stores_one_rerun_and_final_failure(tmp_path: Path) -> None:
    run_dir = run_claude(
        tmp_path,
        [api_connection_error(), api_connection_error(), *diagnosed_responses()],
        run_id="double-failure",
    )
    final_records = records(run_dir)
    first = next(record for record in final_records if record.episode.seed == 930_000)
    assert first.status == "API_FAILURE"
    manifest = read_manifest(run_dir)
    assert len(manifest["reruns"]) == 1
    attempt1 = run_dir / manifest["reruns"][first.episode.episode_id]
    assert EpisodeResult.model_validate_json(attempt1.read_text(encoding="utf-8")).status == (
        "API_FAILURE"
    )


def test_refused_episode_is_not_rerun(tmp_path: Path) -> None:
    refusal = msg(
        {"type": "text", "text": "no"},
        stop="refusal",
        stop_details={"type": "refusal", "category": "bio"},
    )
    run_dir = run_claude(tmp_path, [refusal, *diagnosed_responses()], run_id="refused")
    first = next(record for record in records(run_dir) if record.episode.seed == 930_000)
    assert first.status == "REFUSED"
    assert read_manifest(run_dir)["reruns"] == {}
    assert not (run_dir / "reruns").exists()


def test_resume_during_rerun_uses_existing_attempt1_once(tmp_path: Path) -> None:
    run_id = "resume-rerun"
    first_client = FakeClient([api_connection_error(), RuntimeError("crash")])
    with pytest.raises(RuntimeError, match="crash"):
        run_claude(tmp_path, first_client, run_id=run_id)

    run_dir = tmp_path / "runs" / run_id
    first_attempt = next((run_dir / "reruns").glob("*.attempt1.json"))
    attempt1_bytes = first_attempt.read_bytes()
    attempt1 = EpisodeResult.model_validate_json(attempt1_bytes)
    final_episode = run_dir / "episodes" / f"{attempt1.episode.episode_id}.json"
    assert not final_episode.exists()
    original_created_at = read_manifest(run_dir)["created_at"]

    resume_client = FakeClient(diagnosed_responses() * 2)
    run_claude(tmp_path, resume_client, run_id=run_id, resume=True)

    final = EpisodeResult.model_validate_json(final_episode.read_text(encoding="utf-8"))
    assert final.status == "DIAGNOSED"
    assert first_attempt.read_bytes() == attempt1_bytes
    assert not list((run_dir / "reruns").glob("*.attempt2.json"))
    manifest = read_manifest(run_dir)
    assert manifest["reruns"] == {
        attempt1.episode.episode_id: f"reruns/{first_attempt.name}"
    }
    assert manifest["created_at"] == original_created_at
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_episodes"] == 2


def test_resume_skips_episode_with_final_api_failure(tmp_path: Path) -> None:
    run_id = "resume-final-api-failure"
    run_dir = run_claude(
        tmp_path,
        [api_connection_error(), api_connection_error(), *diagnosed_responses()],
        run_id=run_id,
    )
    first = next(record for record in records(run_dir) if record.episode.seed == 930_000)
    assert first.status == "API_FAILURE"
    attempt1 = run_dir / "reruns" / f"{first.episode.episode_id}.attempt1.json"
    assert EpisodeResult.model_validate_json(attempt1.read_text(encoding="utf-8")).status == (
        "API_FAILURE"
    )
    assert read_manifest(run_dir)["reruns"][first.episode.episode_id] == (
        f"reruns/{first.episode.episode_id}.attempt1.json"
    )

    unused_client = FakeClient([])
    run_claude(tmp_path, unused_client, run_id=run_id, resume=True)
    assert unused_client.requests == []


def test_scripted_records_and_manifest_remain_unchanged(tmp_path: Path) -> None:
    run_dir = runner.run(
        "good_scientist",
        "two",
        tmp_path / "runs",
        matrix=small_matrix(tmp_path),
        gate0_summary=fixture_gate0(tmp_path / "gate0.json"),
        run_id="scripted",
        reference_seeds=REFERENCE_SEEDS[:5000],
    )
    for record in records(run_dir):
        assert record.agent.kind == "scripted"
        assert record.llm_transcript is None
    manifest = read_manifest(run_dir)
    assert not {"reruns", "model", "effort"} & manifest.keys()
    assert set(manifest) == {
        "run_id",
        "agent",
        "matrix",
        "matrix_sha256",
        "scenario_sha256",
        "gate0_summary_sha256",
        "diagnostic_action_set",
        "prompt_version",
        "n_episodes",
        "versions",
        "created_at",
    }


def test_scripted_agent_rejects_model_in_factory_and_cli(tmp_path: Path, capsys) -> None:
    with pytest.raises(
        ValueError, match="--model is only supported with --agent claude"
    ):
        runner.make_agent("good_scientist", PRIOR, model="x")

    matrix_path = small_matrix(tmp_path)
    gate0_path = fixture_gate0(tmp_path / "gate0.json")
    rc = runner.main(
        [
            "run",
            "--agent",
            "good_scientist",
            "--matrix",
            "two",
            "--matrix-file",
            str(matrix_path),
            "--out",
            str(tmp_path / "runs"),
            "--gate0-summary",
            str(gate0_path),
            "--model",
            "x",
        ]
    )
    assert rc == 2
    assert "--model is only supported with --agent claude" in capsys.readouterr().err


def test_cli_accepts_matrix_file(tmp_path: Path, capsys) -> None:
    matrix_path = small_matrix(tmp_path)
    gate0_path = fixture_gate0(tmp_path / "gate0.json")
    out_root = tmp_path / "runs"
    rc = runner.main(
        [
            "run",
            "--agent",
            "good_scientist",
            "--matrix",
            "two",
            "--matrix-file",
            str(matrix_path),
            "--out",
            str(out_root),
            "--gate0-summary",
            str(gate0_path),
        ]
    )
    assert rc == 0
    run_dir = Path(capsys.readouterr().out.strip())
    assert run_dir.parent == out_root
    assert len(records(run_dir)) == 2


@pytest.mark.parametrize("module", ["mirage.evaluation.runner", "mirage.evaluation.report"])
def test_import_does_not_eagerly_import_anthropic(module: str) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    code = f"import {module}, sys; print('anthropic' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"
