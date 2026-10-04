"""Tests for the model-effort analysis script (reads frozen records only; no network)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
ANALYZE_PATH = ROOT / "experiments" / "exploratory" / "model-effort" / "analyze.py"
ANALYZE_MODULE = "exp_model_effort_analyze"
analyze = sys.modules.get(ANALYZE_MODULE)
if analyze is None:
    spec = importlib.util.spec_from_file_location(ANALYZE_MODULE, ANALYZE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {ANALYZE_PATH}")
    analyze = importlib.util.module_from_spec(spec)
    sys.modules[ANALYZE_MODULE] = analyze
    spec.loader.exec_module(analyze)


def _ep(status="DIAGNOSED", correct=True, control=True):
    return SimpleNamespace(
        status=status, scores=SimpleNamespace(correct=correct, diagnostic_control=control)
    )


@pytest.mark.parametrize(
    ("episode", "expected"),
    [
        (_ep(), "justified"),
        (_ep(control=False), "correct_without_control"),
        (_ep(correct=False), "wrong_after_control"),
        (_ep(correct=False, control=False), "wrong_without_control"),
        (_ep(status="NO_DIAGNOSIS", correct=False, control=False), "NO_DIAGNOSIS"),
        (_ep(status="API_FAILURE", correct=False, control=False), "API_FAILURE"),
        (_ep(status="REFUSED", correct=False, control=False), "REFUSED"),
    ],
)
def test_classify_is_exhaustive_and_exclusive(episode, expected):
    assert analyze.classify(episode) == expected
    assert expected in analyze.CLASSES


def _m3(k, lo, hi):
    return {"primary": {"overall": {"M3": {"k": k, "wilson95": [lo, hi]}}}}


def test_decision_rule_boundaries():
    ref = _m3(29, 0.833, 0.994)  # 29/30
    assert analyze.decide(_m3(20, 0.488, 0.808), ref) == "detectable drop"
    assert analyze.decide(_m3(26, 0.703, 0.947), ref) == "lower, worth following up"
    assert analyze.decide(_m3(27, 0.744, 0.965), ref) == "no detectable difference at n = 30"
    assert analyze.decide(_m3(30, 0.886, 1.0), ref) == "no detectable difference at n = 30"


def test_call_cost_uses_registered_prices():
    line = {"model": "claude-haiku-4-5-20251001", "input_tokens": 1_000_000,
            "output_tokens": 1_000_000, "cache_write": 0, "cache_read": 0}
    assert analyze.call_cost(line) == pytest.approx(6.0)
    line["model"] = "claude-opus-5-5"
    assert analyze.call_cost(line) == pytest.approx(24.0)


def test_analyse_on_frozen_record_as_variant(tmp_path):
    """Feeding frozen C2 as a variant reproduces C2 and finds no new failure types."""
    res = analyze.analyse({"X2": analyze.FROZEN["C2"]})
    c2 = res["runs"]["C2"]
    assert c2["primary"]["overall"]["M3"]["k"] == 29
    assert c2["episodes"]["s500028-BP"]["class"] == "wrong_after_control"
    assert res["decisions"]["X2"] == {
        "reference": "C2", "verdict": "no detectable difference at n = 30"
    }
    assert res["new_failure_types"]["X2"] == []
    assert all(e["q1"] for e in c2["episodes"].values())  # C2 Q1 is 30/30
    md = analyze.render_md(res)
    assert "s500028-BP" in md and "| X2 |" in md
    analyze.write_figure(res, tmp_path / "fig.png")
    assert (tmp_path / "fig.png").stat().st_size > 0
