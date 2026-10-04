"""Calibration analysis of the committed strong-matrix records (exploratory; REGISTRATION.md).

Reads experiments/results/ only; writes results.json and figures into this directory.
    PYTHONPATH=src .venv/bin/python experiments/exploratory/calibration/analysis.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import calib

from mirage.assay.od_reader import response
from mirage.biology.growth import richards
from mirage.evaluation.metrics import EpisodeResult, wilson

RESULTS = ROOT / "experiments" / "results"
SCENARIO = ROOT / "experiments" / "configs" / "scenario_v1.json"
GATE0 = RESULTS / "gate0" / "summary.json"
RUNS = {
    "C1 Opus": "20261003-2323_claude_strong",
    "C2 Sonnet": "20261004-0049_claude_strong",
    "GoodScientist": "20261003-2333_good_scientist_strong",
    "PassiveBayes": "20261003-2333_passive_bayes_strong",
}
CASE = "s500028-BP"
TAU = 1.5
NOISE_DRAWS = 200_000
NOISE_SEED = 28
PAIRS = [("C1 Opus", "C2 Sonnet"), ("C1 Opus", "GoodScientist"), ("C2 Sonnet", "GoodScientist"),
         ("C1 Opus", "PassiveBayes"), ("C2 Sonnet", "PassiveBayes"),
         ("GoodScientist", "PassiveBayes")]
METRICS = ("brier", "log_loss", "ece", "rel", "res", "unc", "residual")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_run(run: str) -> tuple[list[EpisodeResult], list[Path]]:
    files = sorted((RESULTS / run / "episodes").glob("*.json"), key=lambda f: int(f.stem[1:7]))
    return [EpisodeResult.model_validate_json(f.read_text(encoding="utf-8")) for f in files], files


def reads_of(r: EpisodeResult) -> list[tuple[int, float, float]]:
    """(time_h, dilution, reading) per replicate of every accepted measure_od."""
    out = []
    for e in r.events:
        if e.tool == "measure_od" and e.ok:
            for y in e.result["readings"]:
                out.append((int(e.result["time_h"]), float(e.result["dilution_factor"]), float(y)))
    return out


def passive_of(r: EpisodeResult) -> dict[int, float]:
    return {m.time_h: m.mean_reading for m in r.passive}


def point_metrics(p: np.ndarray, y: np.ndarray, edges=calib.BIN_EDGES) -> dict[str, float]:
    m = calib.murphy(p, y, edges)
    ll, _ = calib.log_loss(p, y)
    return {**m, "log_loss": ll, "ece": calib.ece(p, y)}


def main() -> None:
    prior = json.loads(SCENARIO.read_text(encoding="utf-8"))
    gate0 = json.loads(GATE0.read_text(encoding="utf-8"))
    inputs = {str(SCENARIO.relative_to(ROOT)): sha256(SCENARIO), str(GATE0.relative_to(ROOT)): sha256(GATE0)}
    recs: dict[str, list[EpisodeResult]] = {}
    for name, run in RUNS.items():
        rs, files = load_run(run)
        recs[name] = rs
        for f in [*files, RESULTS / run / "summary.json", RESULTS / run / "manifest.json"]:
            inputs[str(f.relative_to(ROOT))] = sha256(f)
    ids = [r.episode.episode_id for r in recs["C1 Opus"]]
    for name, rs in recs.items():
        assert [r.episode.episode_id for r in rs] == ids, name
        assert all(r.status == "DIAGNOSED" for r in rs), name
    cond = np.array([r.episode.condition.value[:1] + ("P" if r.episode.condition.value[0] == "B" else "A")
                     for r in recs["C1 Opus"]])  # "BP" / "MA"
    y = (cond == "MA").astype(float)
    P = {n: np.array([r.diagnosis.p_biomass_above_reading for r in rs]) for n, rs in recs.items()}
    correct = {n: np.array([r.scores.correct for r in rs]) for n, rs in recs.items()}

    out: dict = {"inputs_sha256": inputs, "episode_ids": ids, "condition": cond.tolist(),
                 "registration": "REGISTRATION.md", "agents": {}}

    # consistency with the frozen summaries (assert, never replace)
    for name, run in RUNS.items():
        summ = json.loads((RESULTS / run / "summary.json").read_text(encoding="utf-8"))
        o1 = summ["metrics"]["primary"]["overall"]["O1"]
        frozen = np.array([r.scores.brier for r in recs[name]])
        assert math.isclose(frozen.mean(), o1, abs_tol=1e-12), name
        assert np.allclose(frozen, (P[name] - y) ** 2, atol=1e-12), name
        assert summ["metrics"]["primary"]["overall"]["M1"]["k"] == int(correct[name].sum())

    idx = calib.stratified_indices(cond)
    boot: dict[str, dict[str, np.ndarray]] = {}
    for name, run_id in RUNS.items():
        p = P[name]
        pt = point_metrics(p, y)
        exact = calib.murphy(p, y, None)
        _, clipped = calib.log_loss(p, y)
        bs = {k: np.empty(len(idx)) for k in (*METRICS, "rel_exact", "res_exact", "residual_exact")}
        for b, ix in enumerate(idx):
            m = point_metrics(p[ix], y[ix])
            for k in METRICS:
                bs[k][b] = m[k]
            me = calib.murphy(p[ix], y[ix], None)
            bs["rel_exact"][b], bs["res_exact"][b], bs["residual_exact"][b] = me["rel"], me["res"], me["residual"]
        boot[name] = bs
        by_cond = {}
        for c in ("BP", "MA"):
            mask = cond == c
            pc, yc = p[mask], y[mask]
            ll = -(yc * np.log(np.clip(pc, calib.LOG_LOSS_EPS, 1 - calib.LOG_LOSS_EPS))
                   + (1 - yc) * np.log(1 - np.clip(pc, calib.LOG_LOSS_EPS, 1 - calib.LOG_LOSS_EPS)))
            sel = [ix[cond[ix] == c] for ix in idx]
            pcb = np.array([p[s] for s in sel])
            ycb = np.array([y[s] for s in sel])
            llb = -(ycb * np.log(np.clip(pcb, 1e-6, 1 - 1e-6)) + (1 - ycb) * np.log(1 - np.clip(pcb, 1e-6, 1 - 1e-6)))
            by_cond[c] = {
                "n": int(mask.sum()), "k_correct": int(correct[name][mask].sum()),
                "mean_p": float(pc.mean()), "mean_p_ci": calib.percentile_ci(pcb.mean(axis=1)),
                "brier": float(((pc - yc) ** 2).mean()), "brier_ci": calib.percentile_ci(((pcb - ycb) ** 2).mean(axis=1)),
                "log_loss": float(ll.mean()), "log_loss_ci": calib.percentile_ci(llb.mean(axis=1)),
                "citl": float((pc - yc).mean()), "citl_ci": calib.percentile_ci((pcb - ycb).mean(axis=1)),
                "p_min": float(pc.min()), "p_max": float(pc.max()),
            }
            lo, hi = by_cond[c]["citl_ci"]
            by_cond[c]["D2_biased"] = bool(lo > 0 or hi < 0)
        k = int(correct[name].sum())
        out["agents"][name] = {
            "run_id": run_id, "n": len(p), "M1_k": k, "M1_wilson95": list(wilson(k, len(p))),
            "point": pt, "ci": {m: calib.percentile_ci(bs[m]) for m in bs},
            "murphy_exact": exact, "log_loss_clipped": clipped,
            "reliability": calib.reliability_table(p, y),
            "reliability_wilson95": [list(wilson(row["k"], row["n"])) for row in calib.reliability_table(p, y)],
            "distinct_p": sorted(set(p.round(6).tolist())),
            "by_condition": by_cond,
        }
    out["paired_differences"] = {}
    for a, b in PAIRS:
        d = {}
        for m in ("brier", "log_loss", "ece", "rel", "res"):
            diff = out["agents"][a]["point"][m] - out["agents"][b]["point"][m]
            ci = calib.percentile_ci(boot[a][m] - boot[b][m])
            d[m] = {"diff": diff, "ci": ci, "D1_differs": bool(ci[0] > 0 or ci[1] < 0)}
        out["paired_differences"][f"{a} - {b}"] = d

    # reference posterior and ratios, every episode and agent (REGISTRATION §6)
    ref = {}
    for i, eid in enumerate(ids):
        r0 = recs["PassiveBayes"][i]
        passive_obs = [(m.time_h, m.dilution_factor, yy) for m in r0.passive for yy in m.readings]
        g, a = r0.episode.growth, r0.episode.assay
        k_true = g.k_odeq
        f_k = float(response(k_true, s_odeq=a.s_odeq, n=a.n))
        row = {"condition": cond[i], "k_ratio": r0.episode.k_ratio, "noise_free_gap": k_true / f_k - 1,
               "pb_p": float(P["PassiveBayes"][i]),
               "passive_only_posterior": calib.late_posterior(passive_obs, prior)["p_ma"],
               "plateau_mean_15_18": float(np.mean([passive_of(r0)[t] for t in calib.PLATEAU_TIMES_H]))}
        for name in ("C1 Opus", "C2 Sonnet", "GoodScientist"):
            r = recs[name][i]
            rd = reads_of(r)
            assert passive_of(r) == passive_of(r0)
            lp = calib.late_posterior(passive_obs + rd, prior)
            row[name] = {"p": float(P[name][i]), "correct": bool(correct[name][i]),
                         "ratio": calib.corrected_plateau_ratio(passive_of(r), rd),
                         "posterior_p_ma": lp["p_ma"], "posterior_log10_odds": lp["log10_odds_ma"],
                         "agent_reads_dropped_lt14h": lp["n_dropped"] - sum(1 for t, _, _ in passive_obs if t < 14),
                         "estimate_od": r.diagnosis.late_biomass_estimate_od}
        ref[eid] = row
    out["per_episode"] = ref
    pb = np.array([ref[e]["pb_p"] for e in ids])
    po = np.array([ref[e]["passive_only_posterior"] for e in ids])
    out["passive_check"] = {"max_abs_diff_pb_vs_passive_only_posterior": float(np.abs(pb - po).max()),
                            "same_label": int(np.sum((pb > 0.5) == (po > 0.5)))}

    # s500028-BP case study
    ci_ = ids.index(CASE)
    r_case = recs["C1 Opus"][ci_]
    g, a = r_case.episode.growth, r_case.episode.assay
    latent = {t: float(richards(t, **g.model_dump())) for t in range(19)}
    bp = [e for e in ids if ref[e]["condition"] == "BP"]
    case = {"episode": r_case.episode.model_dump(mode="json"),
            "passive": [[m.time_h, m.mean_reading] for m in r_case.passive],
            "noise_free_reading_18h": float(response(latent[18], s_odeq=a.s_odeq, n=a.n)),
            "latent_18h": latent[18], "agents": {}}
    for key in ("noise_free_gap", "k_ratio"):
        vals = sorted(((ref[e][key], e) for e in bp), reverse=True)
        case[f"rank_{key}_among_BP"] = [e for _, e in vals].index(CASE) + 1
    for name in ("C1 Opus", "C2 Sonnet", "GoodScientist"):
        r = recs[name][ci_]
        reqs = [(int(e.arguments["time_h"]), float(e.arguments["dilution_factor"]), int(e.arguments["replicates"]),
                 e.result["readings"]) for e in r.events if e.tool == "measure_od" and e.ok]
        late = [(t, d, n) for t, d, n, _ in reqs if 12 <= t <= 18 and d > 1]
        sims = calib.simulate_ratio(latent, late, s_odeq=a.s_odeq, n=a.n, sigma_abs=a.sigma_abs,
                                    sigma_rel=a.sigma_rel, draws=NOISE_DRAWS, seed=NOISE_SEED)
        obs_ratio = ref[CASE][name]["ratio"]
        p_case = ref[CASE][name]["posterior_p_ma"]
        others = sorted(ref[e][name]["ratio"] for e in bp if e != CASE)
        reasonable = (p_case >= 0.2) or (obs_ratio >= TAU) or (float(np.mean(sims >= TAU)) >= 0.05)
        not_reasonable = p_case < 0.01 and obs_ratio < TAU
        case["agents"][name] = {
            "requests": [{"time_h": t, "dilution": d, "replicates": n, "readings": rd,
                          "corrected": [d * v for v in rd],
                          "noise_free_reading": nf,
                          "z": [(v - nf) / (a.sigma_abs + a.sigma_rel * nf) for v in rd]}
                         for t, d, n, rd in reqs
                         for nf in [float(response(latent[t] / d, s_odeq=a.s_odeq, n=a.n))]],
            "brier_share_of_mean": float(r.scores.brier / len(ids) / np.mean([x.scores.brier for x in recs[name]])),
            "diagnosis": r.diagnosis.diagnosis, "p": r.diagnosis.p_biomass_above_reading,
            "estimate_od": r.diagnosis.late_biomass_estimate_od, "rationale": r.diagnosis.rationale,
            "visible_text_blocks": [c.get("text") for m in (r.llm_transcript or []) if m.get("kind") == "assistant"
                                    for c in m["response"]["content"] if c["type"] == "text"],
            "thinking_blocks_nonempty": sum(1 for m in (r.llm_transcript or []) if m.get("kind") == "assistant"
                                            for c in m["response"]["content"]
                                            if c["type"] == "thinking" and c.get("thinking")),
            "ratio": obs_ratio, "log_ratio_over_tau": math.log(obs_ratio / TAU),
            "noise_free_ratio_same_design": float(
                np.mean([d * float(response(latent[t] / d, s_odeq=a.s_odeq, n=a.n)) for t, d, n in late for _ in range(n)])
                / np.mean([float(response(latent[t], s_odeq=a.s_odeq, n=a.n)) for t in calib.PLATEAU_TIMES_H])),
            "p_noise_ratio_ge_observed": float(np.mean(sims >= obs_ratio)),
            "p_noise_ratio_ge_tau": float(np.mean(sims >= TAU)),
            "sim_ratio_q": [float(q) for q in np.quantile(sims, [0.025, 0.5, 0.975])],
            "posterior_p_ma": p_case, "posterior_log10_odds": ref[CASE][name]["posterior_log10_odds"],
            "other_BP_ratio_range": [others[0], others[-1]],
            "rank_ratio_among_BP": sorted((ref[e][name]["ratio"] for e in bp), reverse=True).index(obs_ratio) + 1,
            "D3": "reasonable" if reasonable else ("not_reasonable" if not_reasonable else "borderline"),
        }
    first = {n: case["agents"][n]["requests"][0]["readings"][:2] for n in case["agents"]}
    case["first_request_readings_identical"] = len({tuple(v) for v in first.values()}) == 1
    case["literal_claim_true"] = case["latent_18h"] > case["noise_free_reading_18h"]
    out["case_study"] = case

    # PassiveBayes "lucky" analysis (REGISTRATION §7)
    p, cor = P["PassiveBayes"], correct["PassiveBayes"]
    conf = np.maximum(p, 1 - p)
    k = int(cor.sum())
    au_b = np.array([calib.auroc(conf[ix], cor[ix]) for ix in idx])
    out["passive_bayes"] = {
        "k_correct": k, "n": len(p), "wilson95": list(wilson(k, len(p))),
        "conf_correct": {"mean": float(conf[cor].mean()), "median": float(np.median(conf[cor])),
                         "min": float(conf[cor].min()), "max": float(conf[cor].max()),
                         "n_conf_lt_0_55": int(np.sum(conf[cor] < 0.55))},
        "conf_wrong": {"mean": float(conf[~cor].mean()), "median": float(np.median(conf[~cor])),
                       "min": float(conf[~cor].min()), "max": float(conf[~cor].max()),
                       "n_conf_lt_0_55": int(np.sum(conf[~cor] < 0.55))},
        "n_conf_ge_0_75": int(np.sum(conf >= 0.75)), "n_conf_ge_0_75_correct": int(np.sum(cor[conf >= 0.75])),
        "auroc": calib.auroc(conf, cor), "auroc_ci": calib.percentile_ci(au_b),
        "auroc_boot_nan": int(np.isnan(au_b).sum()),
        "expected_correct_own_probs": float(conf.sum()),
        "p_ge_observed_own_probs": calib.poisson_binomial_sf(conf, k),
        "gate0_G0A": gate0["checks"]["G0-A"]["passive_bayes"],
    }
    ci = out["passive_bayes"]["auroc_ci"]
    out["passive_bayes"]["D4_informative"] = bool(ci[0] > 0.5 or ci[1] < 0.5)
    out["gate0"] = {"G0B_max_compression": gate0["checks"]["G0-B"]["max_compression"],
                    "diagnostic_dilution": gate0["diagnostic_dilution"]}

    (HERE / "inputs.json").write_text(json.dumps(inputs, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (HERE / "results.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", HERE / "results.json")


if __name__ == "__main__":
    main()
