import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gate0.py"
EXPECTED = ["assay_response.png", "passive_overlap.png", "latent_reveal.png",
            "intervention_sweep.png", "separability_before_after.png", "robustness_map.png"]


def test_quick_run_writes_all_plots_after_summary(tmp_path) -> None:
    proc = subprocess.run([sys.executable, str(SCRIPT), "--quick", "--out", str(tmp_path)],
                          capture_output=True, text=True, timeout=300)
    s = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert s["mode"] == "quick"
    assert s["plots"] == EXPECTED
    for name in EXPECTED:
        f = tmp_path / name
        assert f.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", name
        assert f.stat().st_size > 10_000, name
    assert (proc.returncode == 0) == s["passed"]


def test_plot_module_matches_gate0_plot_list() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import gate0
    finally:
        sys.path.pop(0)
    assert gate0.PLOTS == EXPECTED
