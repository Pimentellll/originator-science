import json
from pathlib import Path

from mirage.ui import api
from scripts.export_growth_static import export_growth_static

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
DEMO_RUN = "20261004-0016_claude_demo"


def test_export_growth_static_writes_all_api_files(tmp_path: Path) -> None:
    output = tmp_path / "growth-data"
    export_growth_static(RESULTS, output)

    runs = api.list_runs(RESULTS)
    assert json.loads((output / "runs.json").read_text(encoding="utf-8")) == runs
    assert DEMO_RUN in {run["run_id"] for run in runs}

    expected_files = {"runs.json", "grid-strong.json"}
    for entry in runs:
        run_id = entry["run_id"]
        run = api.get_run(RESULTS, run_id)
        expected_files.add(f"runs/{run_id}.json")
        for episode in run["episodes"]:
            expected_files.add(
                f"runs/{run_id}/episodes/{episode['episode_id']}.json"
            )

    actual_files = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files
