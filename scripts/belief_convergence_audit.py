"""Posterior convergence audit (B4A): fixed public traces x particle counts x particle-RNG seeds.

    PYTHONPATH=src:tests python scripts/belief_convergence_audit.py \
        --out docs/validation/convergence_audit.json [--counts 256 512 1024 2048 4096] [--seeds 16]

For every trace prefix, particle count and configuration it records the eight failure marginals,
mechanism entropy, ESS / resampling / unique-particle / max-weight diagnostics and the posterior
predictive log likelihood, then evaluates the gate in docs/validation/POSTERIOR_CONVERGENCE_GATE.md.
Configurations: 'legacy' (one-shot reweight + resample-move, tempering=False) and 'tempered'
(adaptive tempering, the production engine). Exact importance-sampling references are computed for
the early prefixes where their effective sample size permits.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from v1_config_support import MODEL_V1, PRIOR_V1, SCHEMA_V1, load_traces, replay

from mirage.belief import FAILURE_FIELDS

TOL_MARGINAL = 0.05
TOL_SEED_SD = 0.05
TOL_JSD = 0.02
CONFIGS = {"legacy": dict(tempering=False), "tempered": dict()}


def run_one(args):
    key, trace, n, seed, cfg = args
    from v1_config_support import fresh_belief
    from mirage.belief import DegenerateBeliefError

    t0 = time.perf_counter()
    b = fresh_belief(n, seed, **CONFIGS[cfg])
    rows, log_pred = [], 0.0
    for action, obs in trace:
        try:
            info = b.observe(MODEL_V1, action, obs)
            log_pred += info.log_evidence
            ess_w, resampled, stages, wmax = info.ess_weighted, info.resampled, info.stages, info.max_weight
        except DegenerateBeliefError:
            ess_w = resampled = stages = wmax = None
        rows.append(
            dict(
                marg=[b.failure_probabilities()[f] for f in FAILURE_FIELDS],
                entropy=b.mechanism_entropy(),
                pattern=b.pattern_distribution().tolist(),
                ess_weighted_frac=None if ess_w is None else ess_w / n,
                resampled=resampled,
                stages=stages,
                max_weight=wmax,
                unique_frac=len({tuple(r) for r in b.particles}) / n,
                log_predictive=log_pred,
            )
        )
    s = b.summary()
    return key, n, seed, cfg, rows, dict(means=s.continuous_means, variances=s.continuous_variances), time.perf_counter() - t0


def jsd(p, q):
    p, q = np.asarray(p) + 1e-300, np.asarray(q) + 1e-300
    m = 0.5 * (p + q)
    return float(0.5 * np.sum(p * np.log(p / m)) + 0.5 * np.sum(q * np.log(q / m)))


def exact_reference(trace, k, draws, seed=0):
    rng = np.random.default_rng(seed)
    z = PRIOR_V1.sample(rng, draws)
    ll = np.zeros(draws)
    for action, obs in trace[:k]:
        ll += MODEL_V1.log_likelihood(obs, z, action)
    w = np.exp(ll - ll.max())
    ess = float(w.sum() ** 2 / np.sum(w**2))
    ind = SCHEMA_V1.failure_indicators(z)
    return ((w[:, None] * ind).sum(0) / w.sum()).tolist(), ess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", type=int, nargs="+", default=[256, 512, 1024, 2048, 4096])
    ap.add_argument("--seeds", type=int, default=16)
    ap.add_argument("--configs", nargs="+", default=["legacy", "tempered"])
    ap.add_argument("--out", default="docs/validation/convergence_audit.json")
    ap.add_argument("--exact-draws", type=int, default=1_500_000)
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    traces = load_traces()
    jobs = [(k, tr, n, s, c) for c in args.configs for n in args.counts for k, tr in traces.items() for s in range(args.seeds)]
    t0 = time.time()
    with ProcessPoolExecutor(args.workers) as ex:
        results = list(ex.map(run_one, jobs, chunksize=4))
    print(f"replays: {len(results)} in {time.time() - t0:.0f}s", flush=True)

    # exact references for early prefixes
    exact = {}
    for key, tr in traces.items():
        for k in range(1, min(3, len(tr)) + 1):
            marg, ess = exact_reference(tr, k, args.exact_draws)
            if ess >= 300:
                exact[f"{key}|{k}"] = dict(marginals=marg, ess=ess)
    print(f"exact references: {len(exact)}", flush=True)

    cell = {}
    for key, n, seed, cfg, rows, final, secs in results:
        cell.setdefault((cfg, n, key), []).append((rows, secs))

    def stack(cfg, n, key, k, field):
        return np.array([rows[k][field] for rows, _ in cell[(cfg, n, key)]], dtype=float)

    report = {"gate": dict(marginal=TOL_MARGINAL, seed_sd=TOL_SEED_SD, jsd=TOL_JSD), "seeds": args.seeds, "configs": {}}
    for cfg in args.configs:
        per_n = {}
        for n in args.counts:
            ref_n = 4 * n if 4 * n in args.counts else None
            worst_sd = worst_diff = worst_jsd = worst_exact = 0.0
            fails, total, worst_case = 0, 0, None
            ess_min, uniq, resamples, wmax, secs_all = [], [], [], [], []
            for key, tr in traces.items():
                for rows, secs in cell[(cfg, n, key)]:
                    secs_all.append(secs)
                for k in range(len(tr)):
                    m = stack(cfg, n, key, k, "marg")
                    sd = m.std(axis=0).max()
                    ok = sd <= TOL_SEED_SD
                    diff = jsd_v = None
                    if ref_n:
                        mr = stack(cfg, ref_n, key, k, "marg")
                        diff = float(np.abs(m.mean(0) - mr.mean(0)).max())
                        pn = np.mean([r[k]["pattern"] for r, _ in cell[(cfg, n, key)]], axis=0)
                        pr = np.mean([r[k]["pattern"] for r, _ in cell[(cfg, ref_n, key)]], axis=0)
                        jsd_v = jsd(pn, pr)
                        ok = ok and diff <= TOL_MARGINAL and jsd_v <= TOL_JSD
                        worst_diff, worst_jsd = max(worst_diff, diff), max(worst_jsd, jsd_v)
                    ex = exact.get(f"{key}|{k + 1}")
                    if ex:
                        e = float(np.abs(m.mean(0) - np.array(ex["marginals"])).max())
                        ok = ok and e <= TOL_MARGINAL
                        worst_exact = max(worst_exact, e)
                    total += 1
                    fails += (not ok)
                    if sd > worst_sd:
                        worst_sd, worst_case = float(sd), f"{key} k={k + 1}"
                    worst_sd = max(worst_sd, sd)
                    for field, acc in (("ess_weighted_frac", ess_min), ("unique_frac", uniq), ("max_weight", wmax)):
                        v = [r[k][field] for r, _ in cell[(cfg, n, key)] if r[k][field] is not None]
                        if v:
                            acc.append(float(np.mean(v)))
                    resamples.append(float(np.mean([r[k]["resampled"] or 0 for r, _ in cell[(cfg, n, key)]])))
            per_n[n] = dict(
                prefixes=total, prefixes_failing_gate=fails, worst_seed_sd=worst_sd, worst_case=worst_case,
                worst_mean_diff_vs_4N=worst_diff if ref_n else None, worst_jsd_vs_4N=worst_jsd if ref_n else None,
                worst_diff_vs_exact=worst_exact, min_mean_ess_weighted_frac=float(min(ess_min)),
                mean_unique_frac_after_update=float(np.mean(uniq)), mean_max_weight=float(np.mean(wmax)),
                mean_resample_rate=float(np.mean(resamples)), mean_replay_seconds=float(np.mean(secs_all)),
                gate_pass=(fails == 0),
            )
        report["configs"][cfg] = per_n
    report["exact_references"] = {k: dict(ess=v["ess"]) for k, v in exact.items()}
    # invalid_biological_model focus: marginals by N at the final prefix for the V1 greedy episode
    focus = {}
    for cfg in args.configs:
        for n in args.counts:
            key = "invalid_biological_model-50000-greedy_eig"
            for k in range(len(traces[key])):
                m = stack(cfg, n, key, k, "marg")
                focus.setdefault(cfg, {}).setdefault(str(k + 1), {})[str(n)] = dict(
                    mean=dict(zip(FAILURE_FIELDS, m.mean(0).round(4).tolist())),
                    sd=dict(zip(FAILURE_FIELDS, m.std(0).round(4).tolist())),
                    entropy_mean=float(stack(cfg, n, key, k, "entropy").mean()),
                    log_predictive_mean=float(stack(cfg, n, key, k, "log_predictive").mean()),
                    log_predictive_sd=float(stack(cfg, n, key, k, "log_predictive").std()),
                )
    report["focus_invalid_biological_model"] = focus
    json.dump(report, open(args.out, "w"), indent=1)
    print(json.dumps({c: {n: {k: v for k, v in d.items() if k in ("prefixes_failing_gate", "worst_seed_sd", "worst_mean_diff_vs_4N", "worst_jsd_vs_4N", "gate_pass", "mean_replay_seconds")} for n, d in r.items()} for c, r in report["configs"].items()}, indent=1))


if __name__ == "__main__":
    main()
