import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
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


# ---- review fixes (#31) ---------------------------------------------------------------------

def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load("gate0")
P = _load("gate0_plots")


@pytest.fixture(scope="module")
def quick_data():
    prior = G.load_prior(G.SCENARIO)
    frag, data = G.run_checks(prior, G.QUICK)
    return frag, data


@pytest.fixture
def figs(monkeypatch):
    captured = {}
    def keep(fig, out, name):
        fig.canvas.draw()
        captured[name] = fig
        return name
    monkeypatch.setattr(P, "_save", keep)
    return captured


def test_make_plots_requires_summary_sweep(tmp_path, quick_data) -> None:
    with pytest.raises(ValueError, match="summary_sweep is required"):
        P.make_plots(tmp_path, quick_data[1])


def test_intervention_sweep_matches_rows_by_d_not_order(tmp_path, quick_data, figs) -> None:
    frag, data = quick_data
    P.intervention_sweep(tmp_path, data, list(reversed(frag["sweep"])))
    ax_c = figs["intervention_sweep.png"].axes[2]
    by_d = {r["d"]: r for r in frag["sweep"]}
    ds = sorted(data["sweep"])
    auroc, bal = ax_c.get_lines()[:2]
    assert list(auroc.get_xdata()) == ds
    assert list(auroc.get_ydata()) == [by_d[d]["auroc"] for d in ds]
    assert list(bal.get_ydata()) == [by_d[d]["tau_balanced_accuracy"] for d in ds]
    a, b, _ = figs["intervention_sweep.png"].axes
    med_ma = [float(np.quantile(data["sweep"][d][G.MA]["c_over_k"], 0.5)) for d in ds]
    assert np.allclose(a.get_lines()[1].get_ydata(), med_ma)
    assert np.allclose(b.get_lines()[0].get_ydata(),
                       [np.mean(data["sweep"][d][G.BP]["useful"]) for d in ds])
    assert "Ĉ / K" in a.get_ylabel() and a.get_xscale() == "log"


def test_intervention_sweep_rejects_mismatched_grid(tmp_path, quick_data, figs) -> None:
    frag, data = quick_data
    bad = [dict(r, d=r["d"] * 3) for r in frag["sweep"]]
    with pytest.raises(ValueError, match="do not match"):
        P.intervention_sweep(tmp_path, data, bad)
    with pytest.raises(ValueError, match="do not match"):
        P.intervention_sweep(tmp_path, data, frag["sweep"][:-1])


def test_assay_response_thresholds_and_units(tmp_path, figs) -> None:
    prior = G.load_prior(G.SCENARIO)
    P.assay_response(tmp_path, prior)
    a, b = figs["assay_response.png"].axes
    assert a.get_xlabel() == "x / S" and b.get_ylabel().startswith("compression")
    assert [ln.get_ydata()[0] for ln in b.get_lines()][-1] == prior.eps_lin
    assert any("0.9187" in t.get_text() for t in a.get_legend().get_texts())


def test_latent_reveal_values_match_spec(tmp_path, figs) -> None:
    prior = G.load_prior(G.SCENARIO)
    P.latent_reveal(tmp_path, prior)
    ax = figs["latent_reveal.png"].axes[0]
    lines = {ln.get_label(): ln for ln in ax.get_lines()}
    bp_obs = lines["BIOLOGICAL_PLATEAU observed"].get_ydata()
    ma_obs = lines["MEASUREMENT_ARTIFACT observed"].get_ydata()
    assert np.max(np.abs(bp_obs - ma_obs)) < 1e-12
    assert lines["MEASUREMENT_ARTIFACT latent X(t)"].get_ydata()[-1] == pytest.approx(4.0, abs=1e-3)
    assert lines["BIOLOGICAL_PLATEAU latent X(t)"].get_ydata()[-1] == pytest.approx(1.03, abs=5e-3)
    assert ax.get_xlabel() == "time (h)" and ax.get_ylabel() == "ODeq"


def test_separability_values_and_threshold(tmp_path, quick_data, figs) -> None:
    checks = quick_data[1]["checks"]
    P.separability(tmp_path, checks)
    ax = figs["separability_before_after.png"].axes[0]
    widths = sorted(p.get_width() for p in ax.patches)
    expect = sorted([checks["G0-A"]["analytic_ceiling"], checks["G0-A"]["passive_bayes"]["balanced_accuracy"],
                     checks["G0-A"]["knn15"]["balanced_accuracy"], checks["G0-D"]["D1_undiluted_discriminability"],
                     checks["G0-D"]["D2_early_discriminability"], checks["G0-C"]["good_scientist_accuracy"]])
    assert np.allclose(widths, expect)
    assert any(list(ln.get_xdata()) == [0.65, 0.65] for ln in ax.get_lines())


def test_summary_exists_before_plotting(tmp_path, monkeypatch) -> None:
    seen = {}
    def fake(out, data, summary_sweep=None):
        seen["summary"] = (Path(out) / "summary.json").is_file()
        return []
    monkeypatch.setitem(sys.modules, "gate0_plots", types.SimpleNamespace(make_plots=fake))
    G.main(["--quick", "--out", str(tmp_path)])
    assert seen == {"summary": True}


def test_blocking_failure_with_plots_exits_nonzero(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(G, "g0c_iv_passes", lambda *a: False)
    assert G.main(["--quick", "--out", str(tmp_path)]) == 1
    s = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert s["passed"] is False and s["plots"] == EXPECTED
