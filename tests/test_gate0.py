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


# ---- review fixes (#30) ---------------------------------------------------------------------

def _patched_prior(monkeypatch, **update):
    prior = load_prior(G.SCENARIO).model_copy(update=update)
    monkeypatch.setattr(G, "load_prior", lambda *_a, **_k: prior)
    return prior


def test_g0b_compression_failure_still_writes_summary(tmp_path, monkeypatch) -> None:
    # BP carrying capacity pushed above x_lin: a genuine G0-B compression failure.
    _patched_prior(monkeypatch, kappa_uniform=(1.5, 1.6))
    rc = G.main(["--quick", "--no-plots", "--out", str(tmp_path)])
    s = json.loads((tmp_path / "summary.json").read_text())
    assert s["checks"]["G0-B"]["max_compression"] > 0.05
    assert s["checks"]["G0-B"]["passed"] is False and s["passed"] is False and rc != 0


def test_every_check_passed_is_python_bool(quick) -> None:
    s = quick[1]
    for name, c in s["checks"].items():
        assert type(c["passed"]) is bool, name
        for v in c.get("variants", []):
            assert type(v["passed"]) is bool, (name, v.get("name"))
    assert type(s["checks"]["G0-D"]["D3"]["passed"]) is bool


def test_stability_fails_without_environment(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "mirage.lab.environment", None)
    ok, detail = G._within_episode_stable(load_prior(G.SCENARIO), 4)
    assert ok is False and "unavailable" in detail


def test_stability_fails_when_requests_rejected(monkeypatch) -> None:
    from mirage.lab import environment as E
    real = E.LabEnvironment.call
    def reject_half(self, tool, args):
        return real(self, tool, dict(args, replicates=9) if self.turn % 2 else args)
    monkeypatch.setattr(E.LabEnvironment, "call", reject_half)
    ok, detail = G._within_episode_stable(load_prior(G.SCENARIO), 4)
    assert ok is False and "accepted" in detail


def test_stability_passes_with_six_accepted_requests() -> None:
    ok, detail = G._within_episode_stable(load_prior(G.SCENARIO), 4)
    assert ok is True, detail


def test_full_mode_fails_when_plotting_unavailable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(G, "FULL", dict(G.QUICK))
    monkeypatch.setitem(sys.modules, "gate0_plots", None)
    rc = G.main(["--out", str(tmp_path)])
    assert (tmp_path / "summary.json").exists() and rc != 0


def test_quick_mode_may_skip_plots(tmp_path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "gate0_plots", None)
    monkeypatch.setattr(G, "g0c_iv_passes", lambda *a: True)
    rc = G.main(["--quick", "--out", str(tmp_path)])
    s = json.loads((tmp_path / "summary.json").read_text())
    assert rc == (0 if s["passed"] else 1)


@pytest.mark.parametrize("cond", ["BIOLOGICAL_PLATEAU", "MEASUREMENT_ARTIFACT"])
def test_passive_noise_and_rounding_match_environment(cond) -> None:
    from mirage.lab.environment import LabEnvironment
    seeds = list(range(30))
    w = G.worlds(PRIOR, seeds, G.Condition(cond))
    for i, seed in enumerate(seeds):
        env = LabEnvironment(sample_episode(PRIOR, seed, cond))
        lib = [m.mean_reading for m in env.passive]
        assert w["passive"][i].tolist() == lib  # exact: same stream [seed,1], same round_4
        assert all(round(v, 4) == v for v in w["passive"][i])
        assert w["p_hat"][i] == pytest.approx(np.mean(lib[15:19]), abs=1e-15)


@pytest.mark.parametrize("t,d,reps", [(18, 10.0, 3), (13, 2.5, 2), (3, 10.0, 1), (18, 1.0, 3)])
def test_measurement_stream_and_reconstruction_match_environment(t, d, reps) -> None:
    """Fails if the reference measurement stream moves off [seed, 2, 0]."""
    from mirage.lab.environment import LabEnvironment
    seeds = list(range(30))
    for cond in ("BIOLOGICAL_PLATEAU", "MEASUREMENT_ARTIFACT"):
        w = G.worlds(PRIOR, seeds, G.Condition(cond))
        m = G.measure(w, PRIOR, t, d, reps)
        for i, seed in enumerate(seeds):
            env = LabEnvironment(sample_episode(PRIOR, seed, cond))
            res = env.session().call("measure_od", {"time_h": t, "dilution_factor": d,
                                                   "replicates": reps})
            ys = res.result["readings"]
            y = G.noisy(m["mu"][i:i+1, None], w["z_meas"][i:i+1, :reps], PRIOR)[0]
            assert y.tolist() == ys
            assert m["c_hat"][i] == pytest.approx(d * np.mean(ys), rel=1e-14)
            acc = env.accepted[0]
            assert m["presented"][i] == pytest.approx(acc.presented_biomass_odeq, rel=1e-14)
            assert m["mu"][i] == pytest.approx(acc.noise_free_reading, rel=1e-14)


def test_useful_region_boundaries_use_library_x_lin_and_loq() -> None:
    from mirage.assay.od_reader import x_lin
    w = {k: np.array([v]) for k, v in dict(k=4.0, r=0.75, x0=0.01, s=1.0).items()}
    w["z_meas"] = np.zeros((1, 3)); w["p_hat"] = np.array([1.0])
    xl = x_lin(s_odeq=1.0, n=PRIOR.n, eps_lin=PRIOR.eps_lin)
    x18 = float(G.latent([18.0], w["k"], w["r"], w["x0"], PRIOR.nu)[0, 0])
    just_in, just_out = x18 / (xl * (1 - 1e-9)), x18 / (xl * (1 + 1e-9))
    assert G.measure(w, PRIOR, 18, just_in, 1)["useful"][0]
    assert not G.measure(w, PRIOR, 18, just_out, 1)["useful"][0]
    # Lower bound: noise-free reading must be >= y_LoQ = 0.03.
    lo = G.measure(w, PRIOR, 18, 100.0, 1)
    assert lo["useful"][0] == (lo["mu"][0] >= 0.03)
    assert G.measure(w, PRIOR, 18, 10.0, 3)["c_hat"][0] == pytest.approx(10 * G.noisy(
        G.resp(np.array(x18 / 10), np.array(1.0), PRIOR.n), np.zeros(1), PRIOR)[0])
