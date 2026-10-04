import pytest

gym = pytest.importorskip("gymnasium")

from mirage.rl.report import main as report_main
from mirage.rl.train import main as train_main


def test_train_refuses_nonempty_output_directory(tmp_path, capsys):
    out = tmp_path / "existing"
    out.mkdir()
    (out / "train_log.jsonl").write_text("{}\n")

    with pytest.raises(SystemExit) as exc:
        train_main(["--out", str(out)])

    assert exc.value.code == 2
    assert "--out already exists and is not empty" in capsys.readouterr().err


def test_heldout_report_refuses_to_overwrite_existing_report(tmp_path, capsys):
    run = tmp_path / "run"
    run.mkdir()
    report = run / "report_heldout_training_utility.json"
    report.write_text('{"frozen": true}')

    with pytest.raises(SystemExit) as exc:
        report_main(["--run", str(run)])

    assert exc.value.code == 2
    assert "held-out report already exists and will not be overwritten" in capsys.readouterr().err
