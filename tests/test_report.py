from __future__ import annotations

import ast
import json
import os
import socket
import statistics
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from mirage.biology.conditions import Condition
from mirage.config import canonical_sha256, load_prior
from mirage.evaluation import metrics, runner
from mirage.evaluation.metrics import EpisodeResult, PRIMARY_STATUSES
from mirage.evaluation.passive import REFERENCE_SEEDS
import mirage.evaluation.report as report

ROOT = Path(__file__).resolve().parents[1]
PRIOR = load_prior(runner.SCENARIO)
SCENARIO_SHA = canonical_sha256(PRIOR)


@pytest.fixture(scope="session", autouse=True)
def offline() -> Iterator[None]:
    def blocked(*args, **kwargs):
        raise AssertionError("network access is disabled in report tests")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(socket.socket, "connect", blocked)
        monkeypatch.setattr(socket.socket, "connect_ex", blocked)
        monkeypatch.setattr(socket, "create_connection", blocked)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        yield


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


def small_matrix(path: Path, n: int = 10) -> Path:
    episodes = [
        {
            "seed": seed,
            "condition": (
                Condition.BIOLOGICAL_PLATEAU.value
                if index % 2 == 0
                else Condition.MEASUREMENT_ARTIFACT.value
            ),
        }
        for index, seed in enumerate(range(900_000, 900_000 + n))
    ]
    matrix_path = path / "matrix.json"
    matrix_path.write_text(
        json.dumps({"matrices": {"report_test": {"episodes": episodes}}}),
        encoding="utf-8",
    )
    return matrix_path


def make_run(path: Path, agent: str, run_id: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    matrix_path = small_matrix(path)
    return runner.run(
        agent,
        "report_test",
        path / "runs",
        matrix=matrix_path,
        gate0_summary=fixture_gate0(path / "gate0.json"),
        run_id=run_id,
        reference_seeds=REFERENCE_SEEDS[:5000],
    )


@pytest.fixture(scope="module")
def real_runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("report-runs")
    return {
        "good_scientist": make_run(base / "gs", "good_scientist", "gs-report-test"),
        "passive_bayes": make_run(base / "pb", "passive_bayes", "pb-report-test"),
    }


def _format_row(
    label: str,
    records: list[EpisodeResult],
    condition: Condition | None = None,
    *,
    intention_to_treat: bool = False,
) -> str:
    selected = [
        record
        for record in records
        if (intention_to_treat or record.status in PRIMARY_STATUSES)
        and (condition is None or record.episode.condition is condition)
    ]
    n = len(selected)
    cells = [label, str(n)]
    if n == 0:
        cells.extend(["n/a (n=0)"] * 4)
    else:
        for attribute in ("correct", "diagnostic_control", "justified"):
            k = sum(
                getattr(record.scores, attribute)
                and (
                    not intention_to_treat
                    or record.status in PRIMARY_STATUSES
                )
                for record in selected
            )
            lo, hi = metrics.wilson(k, n)
            cells.append(f"{k}/{n} [{lo:.2f}, {hi:.2f}]")
        costs = [record.scores.cost_units for record in selected]
        cells.append(
            f"{statistics.mean(costs):.2f} "
            f"(median {statistics.median(costs):g}, max {max(costs)})"
        )
    counts = {
        status: sum(record.status == status for record in records)
        for status in ("API_FAILURE", "REFUSED")
    }
    cells.append(
        f"API_FAILURE {counts['API_FAILURE']}, REFUSED {counts['REFUSED']}"
    )
    return "| " + " | ".join(cells) + " |"


def _section(markdown: str, heading: str) -> str:
    start = markdown.index(heading)
    markers = ["\n## "] if heading.startswith("## ") else ["\n### ", "\n## "]
    endings = [
        position
        for marker in markers
        if (position := markdown.find(marker, start + len(heading))) >= 0
    ]
    end = min(endings) if endings else -1
    return markdown[start : end if end >= 0 else len(markdown)]


def test_report_writes_markdown_and_png(real_runs: dict[str, Path], tmp_path: Path) -> None:
    out = tmp_path / "report"
    assert report.main(
        [
            "--out",
            str(out),
            "--good-scientist",
            str(real_runs["good_scientist"]),
            "--passive-bayes",
            str(real_runs["passive_bayes"]),
        ]
    ) == 0
    markdown = (out / "results.md").read_text(encoding="utf-8")
    image = out / "results.png"
    assert image.is_file() and image.stat().st_size > 0
    assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    for key, label in (
        ("good_scientist", "B1 GoodScientist"),
        ("passive_bayes", "B2 PassiveBayes"),
    ):
        records = runner.load_results(real_runs[key])
        for heading, condition in (
            ("Overall", None),
            ("BIOLOGICAL_PLATEAU", Condition.BIOLOGICAL_PLATEAU),
            ("MEASUREMENT_ARTIFACT", Condition.MEASUREMENT_ARTIFACT),
        ):
            section = _section(markdown, f"### {heading}")
            assert _format_row(label, records, condition) in section


def test_not_run_rows_are_explicit_and_never_blank(
    real_runs: dict[str, Path], tmp_path: Path
) -> None:
    out = tmp_path / "not-run"
    assert report.main(
        ["--out", str(out), "--good-scientist", str(real_runs["good_scientist"])]
    ) == 0
    markdown = (out / "results.md").read_text(encoding="utf-8")
    claude_rows = [
        line for line in markdown.splitlines() if line.startswith("| C1 Claude |")
    ]
    assert len(claude_rows) == 5
    for row in claude_rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert cells[0] == "C1 Claude"
        assert cells[1:] and all(cell == "not run" for cell in cells[1:])
    assert "0/0" not in markdown
    assert "||" not in markdown
    assert "|  |" not in markdown


def _make_claude_run(source: Path, destination: Path) -> tuple[Path, list[EpisodeResult]]:
    episode_dir = destination / "episodes"
    episode_dir.mkdir(parents=True)
    source_records = runner.load_results(source)
    records = []
    for index, original in enumerate(source_records):
        raw = original.model_dump(mode="json")
        raw["agent"].update(
            {
                "name": "claude",
                "kind": "llm",
                "model": "claude-test",
                "effort": "high",
                "prompt_version": "test-prompt-v1",
                "prompt_sha256": None,
                "sdk_version": None,
            }
        )
        if index in (0, 1):
            raw["events"] = [
                event for event in raw["events"] if event["tool"] != "submit_diagnosis"
            ]
            raw["status"] = "API_FAILURE" if index == 0 else "REFUSED"
            raw["diagnosis"] = None
            raw["scores"].update(
                {"correct": False, "justified": False, "brier": None}
            )
        record = EpisodeResult.model_validate(raw)
        records.append(record)
        (episode_dir / f"{record.episode.episode_id}.json").write_text(
            json.dumps(record.model_dump(mode="json"), sort_keys=True),
            encoding="utf-8",
        )
    source_manifest = json.loads(
        (source / "manifest.json").read_text(encoding="utf-8")
    )
    manifest = {
        **source_manifest,
        "run_id": "claude-synthetic",
        "agent": "claude",
        "n_episodes": len(records),
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )
    return destination, records


def test_itt_includes_synthetic_claude_failures(
    real_runs: dict[str, Path], tmp_path: Path
) -> None:
    claude_dir, records = _make_claude_run(
        real_runs["good_scientist"], tmp_path / "claude-run"
    )
    out = tmp_path / "claude-report"
    assert report.main(
        ["--out", str(out), "--claude", str(claude_dir)]
    ) == 0
    markdown = (out / "results.md").read_text(encoding="utf-8")
    status_section = _section(markdown, "## Status breakdown")
    expected_status = (
        "| C1 Claude | "
        + " | ".join(
            str(sum(record.status == status for record in records))
            for status in (
                "DIAGNOSED",
                "NO_DIAGNOSIS",
                "API_FAILURE",
                "REFUSED",
            )
        )
        + f" | {len(records)} |"
    )
    assert expected_status in status_section
    assert (
        "No API_FAILURE or REFUSED episodes, so intention-to-treat equals primary."
        not in markdown
    )
    itt_section = _section(markdown, "## Intention-to-treat")
    assert "### Overall" in itt_section
    assert _format_row(
        "C1 Claude", records, intention_to_treat=True
    ) in _section(itt_section, "### Overall")


def test_report_reuses_metrics_wilson(
    real_runs: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    records = runner.load_results(real_runs["good_scientist"])
    manifest = json.loads(
        (real_runs["good_scientist"] / "manifest.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(metrics, "wilson", lambda _k, _n: (0.123, 0.456))
    markdown = report.render_markdown({"good_scientist": (records, manifest)})
    assert "[0.12, 0.46]" in markdown


def test_markdown_is_deterministic(real_runs: dict[str, Path], tmp_path: Path) -> None:
    run_dirs = {
        "good_scientist": real_runs["good_scientist"],
        "passive_bayes": real_runs["passive_bayes"],
    }
    first, _ = report.build_report(run_dirs, tmp_path / "first")
    second, _ = report.build_report(run_dirs, tmp_path / "second")
    assert first.read_bytes() == second.read_bytes()


def test_mismatched_agent_returns_two(
    real_runs: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert report.main(
        [
            "--out",
            str(tmp_path / "mismatch"),
            "--passive-bayes",
            str(real_runs["good_scientist"]),
        ]
    ) == 2
    assert "report:" in capsys.readouterr().err


def test_empty_run_directory_counts_as_not_run(tmp_path: Path) -> None:
    empty = tmp_path / "empty" / "episodes"
    empty.mkdir(parents=True)
    markdown_path, _ = report.build_report(
        {"claude": empty.parent}, tmp_path / "empty-report"
    )
    markdown = markdown_path.read_text(encoding="utf-8")
    assert (
        "| C1 Claude | not run | not run | not run | not run | not run | not run |"
        in markdown
    )


def test_report_imports_are_offline_only() -> None:
    path = ROOT / "src" / "mirage" / "evaluation" / "report.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    assert not any(
        name == "anthropic"
        or name.startswith("anthropic.")
        or name == "mirage.agents.claude"
        or name.startswith("mirage.agents.claude.")
        for name in imported
    )


def test_module_cli_smoke(real_runs: dict[str, Path], tmp_path: Path) -> None:
    out = tmp_path / "subprocess-report"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), env.get("PYTHONPATH", "")]
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mirage.evaluation.report",
            "--out",
            str(out),
            "--good-scientist",
            str(real_runs["good_scientist"]),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    assert (out / "results.md").is_file()
    assert (out / "results.png").is_file()
