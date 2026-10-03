import ast
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from mirage.biology.conditions import Condition
from mirage.config import canonical_sha256, load_prior
from mirage.demo import replay
from mirage.evaluation import runner
from mirage.evaluation.metrics import EpisodeResult

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sample_episode_llm.json"
PRIOR = load_prior(runner.SCENARIO)
SCENARIO_SHA = canonical_sha256(PRIOR)


def fixture_gate0(path: Path, sha: str = SCENARIO_SHA) -> Path:
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
        json.dumps({"matrices": {"gs_replay": {"episodes": episodes}}}),
        encoding="utf-8",
    )
    return matrix_path


@pytest.fixture(autouse=True)
def no_network_or_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny_network(*args, **kwargs):
        raise AssertionError("network access is disabled in replay tests")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_replay_sections_reveal_and_figure(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    figure = tmp_path / "replay.png"
    assert replay.main([str(FIXTURE), "--pace", "0", "--figure", str(figure)]) == 0
    output = capsys.readouterr().out
    section_positions = [output.index(header) for header in replay.SECTIONS]
    assert section_positions == sorted(section_positions)

    section_three = output[section_positions[2] : section_positions[3]]
    assert section_three.index("turn=1") < section_three.index("REJECTED")
    assert "no charge" in section_three

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["episode"]["condition"] in output[section_positions[4] :]
    assert f"{fixture['episode']['growth']['k_odeq']:.4f}" in output[section_positions[4] :]
    assert f"{fixture['episode']['assay']['s_odeq']:.4f}" in output[section_positions[4] :]
    accepted = next(
        event
        for event in fixture["events"]
        if event["tool"] == "measure_od" and event["ok"]
    )
    expected_back_corrected = (
        accepted["result"]["mean_reading"] * accepted["result"]["dilution_factor"]
    )
    assert f"{expected_back_corrected:.4f}" in output[section_positions[4] :]

    assert figure.is_file()
    image = figure.read_bytes()
    assert len(image) > 0
    assert image.startswith(b"\x89PNG\r\n\x1a\n")


def test_latent_curve_matches_recorded_biomass() -> None:
    record = replay.load_record(FIXTURE)
    latent = float(replay.latent_curve(record.episode, 18.0))
    assert latent == pytest.approx(record.audit[0].latent_biomass_odeq, rel=1e-9)
    assert latent == pytest.approx(4.104, abs=5e-4)


def test_replay_imports_do_not_use_anthropic() -> None:
    for module_path in (
        REPO_ROOT / "src" / "mirage" / "demo" / "replay.py",
        REPO_ROOT / "src" / "mirage" / "demo" / "__init__.py",
    ):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("anthropic") for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("anthropic")

    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            "import mirage.demo.replay, sys; print('anthropic' in sys.modules)",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert imported.stdout.strip() == "False"


def test_pace_sleeps_only_when_positive(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    calls: list[float] = []
    monkeypatch.setattr(replay.time, "sleep", calls.append)

    assert replay.main([str(FIXTURE), "--pace", "0"]) == 0
    capsys.readouterr()
    assert calls == []

    assert replay.main([str(FIXTURE), "--pace", "0.5"]) == 0
    capsys.readouterr()
    assert len(calls) >= 5
    assert all(pace == 0.5 for pace in calls)


def test_invalid_record_raises_validation_error(tmp_path: Path) -> None:
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    del record["status"]
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ValidationError):
        replay.load_record(invalid_path)


def test_declare_state_notes_are_replayed(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record["events"].insert(
        1,
        {
            "index": 1,
            "turn": 2,
            "tool": "declare_state",
            "arguments": {"notes": "An explicit replay note.", "p_growth_continued": 0.7},
            "ok": True,
            "result": {"status": "recorded"},
            "error": None,
        },
    )
    for index, event in enumerate(record["events"]):
        event["index"] = index
        event["turn"] = index + 1
    record_path = tmp_path / "with-declare-state.json"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    EpisodeResult.model_validate_json(record_path.read_text(encoding="utf-8"))

    assert replay.main([str(record_path), "--pace", "0"]) == 0
    output = capsys.readouterr().out
    section_two = output[
        output.index(replay.SECTIONS[1]) : output.index(replay.SECTIONS[2])
    ]
    assert "An explicit replay note." in section_two


def test_module_cli_smoke() -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mirage.demo.replay",
            str(FIXTURE),
            "--pace",
            "0",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_good_scientist_records_replay_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_dir = runner.run(
        "good_scientist",
        "gs_replay",
        tmp_path / "runs",
        matrix=small_matrix(tmp_path),
        gate0_summary=fixture_gate0(tmp_path / "gate0.json"),
        run_id="gs",
    )
    episode_files = sorted((run_dir / "episodes").glob("*.json"))
    assert len(episode_files) == 2

    for episode_path in episode_files:
        record = EpisodeResult.model_validate_json(
            episode_path.read_text(encoding="utf-8")
        )
        figure = tmp_path / f"{record.episode.episode_id}.png"
        assert replay.main(
            [str(episode_path), "--pace", "0", "--figure", str(figure)]
        ) == 0
        output = capsys.readouterr().out
        section_positions = [output.index(header) for header in replay.SECTIONS]
        assert section_positions == sorted(section_positions)
        assert "REJECTED" not in output
        assert f"condition={record.episode.condition.value}" in output
        assert figure.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

        measurement_index = next(
            index
            for index, event in enumerate(record.events)
            if event.tool == "measure_od" and event.ok
        )
        latent = float(
            replay.latent_curve(
                record.episode,
                record.events[measurement_index].arguments["time_h"],
            )
        )
        assert latent == pytest.approx(
            record.audit[0].latent_biomass_odeq, rel=1e-9
        )
