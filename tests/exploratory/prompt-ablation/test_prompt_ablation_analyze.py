"""Tests for experiments/exploratory/prompt-ablation/analyze.py (read-only analysis)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
C2 = ROOT / "experiments" / "results" / "20261004-0049_claude_strong"
_spec = importlib.util.spec_from_file_location(
    "prompt_ablation_analyze", ROOT / "experiments" / "exploratory" / "prompt-ablation" / "analyze.py")
analyze = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analyze)


def test_cid_hit_terms_and_strict_mode():
    assert analyze.cid_hit("Reader SATURATION near 0.76", strict=False)
    assert analyze.cid_hit("diluted readings are in the linear range", strict=True)
    assert analyze.cid_hit("the reader responded proportionally", strict=False)
    assert not analyze.cid_hit("the reader responded proportionally", strict=True)
    assert analyze.cid_hit("proportional, and it was under-read", strict=True)
    assert not analyze.cid_hit("growth stopped; stationary phase plateau", strict=False)


def test_visible_text_excludes_thinking_and_includes_notes_and_rationale():
    episode = {
        "llm_transcript": [
            {"kind": "user", "content": "saturation in the user turn is not agent text"},
            {"kind": "assistant", "response": {"content": [
                {"type": "thinking", "thinking": "ceiling"},
                {"type": "text", "text": "plan A"},
                {"type": "tool_use", "name": "declare_state", "input": {"notes": "note B"}},
                {"type": "tool_use", "name": "measure_od", "input": {"time_h": 18}},
            ]}},
        ],
        "diagnosis": {"rationale": "rationale C"},
    }
    assert analyze.visible_text(episode) == ["plan A", "note B", "rationale C"]


def test_analyze_run_reproduces_frozen_c2_summary(tmp_path):
    before = {p: p.read_bytes() for p in C2.rglob("*") if p.is_file()}
    r = analyze.analyze_run(C2)
    summary = json.loads((C2 / "summary.json").read_text(encoding="utf-8"))
    assert r["metrics"] == summary["metrics"]
    assert r["prompt_version"] == "prompt-v2" and r["model"] == "claude-sonnet-5-5"
    assert r["cid"]["overall"]["any"]["n"] == 30
    assert r["cid"]["MEASUREMENT_ARTIFACT"]["strict"]["n"] == 15
    assert analyze.main(["--arm", f"C2={C2}", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "comparison.png").stat().st_size > 0
    assert "| C2 | all | 29/30 [0.83, 0.99] | 30/30 [0.89, 1.00] |" in (
        tmp_path / "comparison.md").read_text(encoding="utf-8")
    assert before == {p: p.read_bytes() for p in C2.rglob("*") if p.is_file()}
