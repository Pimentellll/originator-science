import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from mirage.assay.od_reader import k_prime, response, t_q
from mirage.biology.growth import richards
from mirage.config import load_prior, sample_episode

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gate0.py"
PRIOR = load_prior(ROOT / "experiments" / "configs" / "scenario_v1.json")


def load_gate0():
    spec = importlib.util.spec_from_file_location("gate0_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = load_gate0()


@pytest.fixture(scope="module")
def quick(tmp_path_factory):
    out = tmp_path_factory.mktemp("gate0")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--quick", "--no-plots", "--out", str(out)],
                          capture_output=True, text=True, timeout=300)
    return proc, json.loads((out / "summary.json").read_text(encoding="utf-8"))


def test_matplotlib_not_imported_by_gate0_module() -> None:
    code = (f"import importlib.util, sys; s = importlib.util.spec_from_file_location('g', {str(SCRIPT)!r});"
            "m = importlib.util.module_from_spec(s); s.loader.exec_module(m);"
            "print('matplotlib' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


@pytest.mark.parametrize("cond", ["BIOLOGICAL_PLATEAU", "MEASUREMENT_ARTIFACT"])
def test_vectorised_worlds_match_library(cond) -> None:
    seeds = list(range(50))
    w = G.worlds(PRIOR, seeds, G.Condition(cond))
    for i, seed in enumerate(seeds):
        e = sample_episode(PRIOR, seed, cond)
        g, a = e.growth, e.assay
        assert w["s"][i] == pytest.approx(a.s_odeq, rel=1e-14)
        assert w["k"][i] == pytest.approx(g.k_odeq, rel=1e-14)
        x = richards(np.arange(19), **g.model_dump())
        assert np.allclose(G.latent(np.arange(19), w["k"][i:i+1], w["r"][i:i+1], w["x0"][i:i+1],
                                    PRIOR.nu)[0], x, rtol=1e-13, atol=0)
        assert G.resp(x, a.s_odeq, a.n) == pytest.approx(response(x, s_odeq=a.s_odeq, n=a.n), rel=1e-14)
        assert G.kprime(g.k_odeq, a.s_odeq, a.n) == pytest.approx(
            k_prime(k_odeq=g.k_odeq, s_odeq=a.s_odeq, n=a.n), rel=1e-14)
        t95 = t_q(0.95, k_odeq=g.k_odeq, s_odeq=a.s_odeq, r_per_h=g.r_per_h, x0_odeq=g.x0_odeq,
                  n=a.n, nu=g.nu)
        assert G.t95_plus_2(PRIOR, {k: v[i:i+1] for k, v in w.items()})[0] == pytest.approx(t95 + 2)


def test_auroc_ks_wilson() -> None:
    assert G.auroc(np.array([0.0, 1.0]), np.array([2.0, 3.0])) == 1.0
    assert G.auroc(np.array([1.0, 1.0]), np.array([1.0, 1.0])) == 0.5
    assert G.auroc(np.array([0.0, 2.0]), np.array([1.0, 3.0])) == 0.75
    assert G.ks_statistic(np.arange(10.0), np.arange(10.0)) == 0.0
    assert G.ks_statistic(np.arange(10.0), np.arange(10.0) + 100) == 1.0
    lo, hi = G.wilson(8, 10)
    assert (round(lo, 4), round(hi, 4)) == (0.4902, 0.9433)


def test_g0c_iv_rule_as_written() -> None:
    assert G.g0c_iv_passes(12.0, 2.5)
    assert not G.g0c_iv_passes(12.127, 3.0)  # the scenario-v1 support corner (PR #3)
    assert not G.g0c_iv_passes(11.9, 2.49)


def test_diagnostic_action_set_rules() -> None:
    ok, bad = 0.99, 0.5
    assert G.diagnostic_action_set([bad, bad, ok, ok, ok, ok, ok, ok, ok, ok]) == (1.5, 100.0, True)
    assert G.diagnostic_action_set([bad, ok, bad, ok, ok, ok, ok, ok, ok, ok]) == (None, None, False)
    assert G.diagnostic_action_set([ok] * 6 + [bad] + [ok] * 3) == (None, None, False)  # no 10


def test_t029_summary_integrity(quick) -> None:
    proc, s = quick
    assert s["mode"] == "quick"
    for key in ("schema_version", "passed", "scenario_version", "scenario_sha256", "source_commit",
                "source_dirty", "parameters", "nuisance_distributions", "seeds", "checks",
                "passive_baseline", "diagnostic_dilution", "diagnostic_action_set",
                "good_scientist", "sweep", "plots", "versions", "runtime_s"):
        assert key in s, key
    assert s["schema_version"] == "gate0-summary-v2"
    assert set(s["checks"]) == {"G0-A", "G0-B", "G0-C", "G0-D", "G0-E", "G0-F", "G0-G", "G0-H"}
    for name, c in s["checks"].items():
        assert {"blocking", "passed", "threshold_type"} <= set(c), name
        assert "threshold" in c or "thresholds" in c or name == "G0-G", name
    assert s["checks"]["G0-G"]["blocking"] is False
    assert s["checks"]["G0-D"]["D3"]["blocking"] is False
    blocking = [c["passed"] for c in s["checks"].values() if c["blocking"]]
    assert s["passed"] == all(blocking)
    assert (proc.returncode == 0) == s["passed"]
    assert s["diagnostic_action_set"]["scenario_sha256"] == s["scenario_sha256"]
    assert [row["d"] for row in s["sweep"]] == [1, 2, 5, 10, 20, 50, 100]
    assert s["seeds"]["passive_reference"] == [1000000, 1199999]
    assert s["plots"] == []  # --no-plots


def test_nonzero_exit_on_blocking_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(G, "g0c_iv_passes", lambda *a: False)
    assert G.main(["--quick", "--no-plots", "--out", str(tmp_path)]) == 1
    s = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert s["passed"] is False and s["checks"]["G0-C"]["passed"] is False
