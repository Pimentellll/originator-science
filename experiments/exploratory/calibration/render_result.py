"""Write RESULT.md from results.json (no number in RESULT.md is typed by hand).

    PYTHONPATH=src .venv/bin/python experiments/exploratory/calibration/render_result.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENTS = ["C1 Opus", "C2 Sonnet", "GoodScientist", "PassiveBayes"]
CLAUDE = ["C1 Opus", "C2 Sonnet"]
CASE = "s500028-BP"
TWIN = "s500000-BP"


def iv(ci: list[float], f: str = ".3f") -> str:
    return f"[{ci[0]:{f}}, {ci[1]:{f}}]"


def est(v: float, ci: list[float], f: str = ".3f") -> str:
    return f"{v:{f}} {iv(ci, f)}"


def main() -> None:
    d = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    A, cs, pe, pb = d["agents"], d["case_study"], d["per_episode"], d["passive_bayes"]
    g0 = d["gate0"]["diagnostic_dilution"]
    bp = [e for e in d["episode_ids"] if pe[e]["condition"] == "BP"]
    ca = cs["agents"]
    gaps = sorted(pe[e]["noise_free_gap"] for e in bp)
    pd = d["paired_differences"]
    oc = pd["C1 Opus - C2 Sonnet"]
    bp_other = {n: [pe[e][n]["p"] for e in bp if e != CASE] for n in CLAUDE}
    und18 = dict(map(tuple, cs["passive"]))[18]
    seen = {n: ca[n]["estimate_od"] / und18 - 1 for n in CLAUDE}
    z10 = ", ".join(f"{z:+.2f}" for z in ca["C1 Opus"]["requests"][0]["z"])
    rel_sd = {r["dilution"]: (0.003 + 0.02 * r["noise_free_reading"]) / r["noise_free_reading"]
              for n in CLAUDE for r in ca[n]["requests"] if r["time_h"] == 18}
    z40 = max(z for r in ca["C2 Sonnet"]["requests"] if r["dilution"] == 40 for z in r["z"])
    z14 = next(r["z"][0] for r in ca["C1 Opus"]["requests"] if r["time_h"] == 14)
    max_lo = max(ca[n]["posterior_log10_odds"] for n in ca)
    L: list[str] = []
    w = L.append

    w("# Result: calibration of stated probabilities, and the shared s500028-BP miss\n")
    w("**Exploratory, not confirmatory.** Analysis of committed strong-matrix records only "
      "(seeds 500000–500029, 15 BP + 15 MA); no API calls, nothing rescored. Registered in "
      "[`REGISTRATION.md`](REGISTRATION.md) before any statistic was computed; deviations are listed there.\n")
    w("## Headline\n")
    w(f"Both Claude models are sharp but lean toward MA on plateau cultures. Resolution is at or near its "
      f"ceiling (binned RES {A['C1 Opus']['point']['res']:.3f} Opus, {A['C2 Sonnet']['point']['res']:.3f} "
      f"Sonnet; UNC = 0.25). On the 15 BP cultures their mean stated P(above reading) is "
      f"{est(A['C1 Opus']['by_condition']['BP']['mean_p'], A['C1 Opus']['by_condition']['BP']['mean_p_ci'])} (Opus) and "
      f"{est(A['C2 Sonnet']['by_condition']['BP']['mean_p'], A['C2 Sonnet']['by_condition']['BP']['mean_p_ci'])} (Sonnet), "
      f"against 0 observed; on MA they are slightly under-confident "
      f"({A['C1 Opus']['by_condition']['MA']['mean_p']:.3f}, {A['C2 Sonnet']['by_condition']['MA']['mean_p']:.3f}). "
      f"The single s500028-BP miss accounts for {ca['C1 Opus']['brier_share_of_mean']:.0%} (Opus) and "
      f"{ca['C2 Sonnet']['brier_share_of_mean']:.0%} (Sonnet) of their mean Brier. Opus and Sonnet show no "
      f"detectable difference in Brier ({est(oc['brier']['diff'], oc['brier']['ci'])}) or log loss at n = 30. "
      f"PassiveBayes is calibrated (ECE {A['PassiveBayes']['point']['ece']:.3f}) but has little resolution "
      f"(RES {est(A['PassiveBayes']['point']['res'], A['PassiveBayes']['ci']['res'])}), and its confidence carries "
      f"no detectable information about which answers are right (AUROC {est(pb['auroc'], pb['auroc_ci'], '.2f')}). "
      f"On s500028-BP, by the registered rule D3, the miss is **not a reasonable condition call under measurement noise**. "
      f"Given each model's own readings, the simulator's posterior gives log10 odds for MA of "
      f"{ca['C1 Opus']['posterior_log10_odds']:.0f} (Opus) and {ca['C2 Sonnet']['posterior_log10_odds']:.0f} (Sonnet). "
      f"Their corrected/plateau ratios ({ca['C1 Opus']['ratio']:.3f}, {ca['C2 Sonnet']['ratio']:.3f}) sit far below "
      f"τ = 1.5 and below the Gate 0 BP 99th percentile ({g0['R_BP_p99']:.3f}). But the readings themselves were "
      f"ordinary: a ratio at least this high arises from noise alone in {ca['C1 Opus']['p_noise_ratio_ge_observed']:.0%} / "
      f"{ca['C2 Sonnet']['p_noise_ratio_ge_observed']:.0%} of simulations of this culture. And the literal claim both "
      f"models made, that biomass is higher than the undiluted reading, is **true** (latent K "
      f"{cs['latent_18h']:.3f} vs noise-free reading {cs['noise_free_reading_18h']:.3f}). The best explanation is that "
      f"s500028 has the largest hidden under-read of the 15 plateau cultures "
      f"({pe[CASE]['noise_free_gap']:.2%}, effectively tied with {TWIN} at {pe[TWIN]['noise_free_gap']:.2%}). An "
      f"ordinary upward noise draw then made that real gap look like {seen['C1 Opus']:.0%} (Opus) and "
      f"{seen['C2 Sonnet']:.0%} (Sonnet) against the 18 h undiluted reading, and the models answered the literal "
      f"question without any materiality threshold, reading replicate scatter at high dilution as signal.\n")

    w("## Main table\n")
    w("Point estimate with stratified-bootstrap 95% interval (B = 10,000; 15 BP + 15 MA per resample). "
      "M1 is k/30 with the Wilson 95% interval. REL/RES use the registered bins [0, .1, .3, .7, .9, 1]; "
      "UNC = 0.250 for every agent; Brier ≈ REL − RES + UNC + residual (within-bin term).\n")
    w("| Agent | M1 correct | Brier | REL | RES | residual | Log loss | ECE |")
    w("|---|---|---|---|---|---|---|---|")
    for n in AGENTS:
        a = A[n]
        p, c = a["point"], a["ci"]
        w(f"| {n} | {a['M1_k']}/30 {iv(a['M1_wilson95'], '.2f')} | {est(p['brier'], c['brier'])} | "
          f"{est(p['rel'], c['rel'])} | {est(p['res'], c['res'])} | {p['residual']:+.4f} | "
          f"{est(p['log_loss'], c['log_loss'])} | {est(p['ece'], c['ece'])} |")
    w("")
    w("Mean Brier equals each run's committed `summary.json` O1 to 1e-12 (asserted). No forecast was clipped "
      "for log loss. GoodScientist's intervals have zero width because it always states 0.01 or 0.99 and is always right.\n")
    w("![Reliability diagrams](fig1_reliability.png)\n")
    w("![Brier decomposition, log loss and ECE](fig2_decomposition.png)\n")

    w("### Paired differences (rule D1: differ only if the paired 95% interval excludes 0)\n")
    w("| Pair | Δ Brier | Δ log loss | Δ REL | Δ RES | Δ ECE |")
    w("|---|---|---|---|---|---|")
    for k, v in pd.items():
        cells = [f"{est(v[m]['diff'], v[m]['ci'])}{' *' if v[m]['D1_differs'] else ''}"
                 for m in ("brier", "log_loss", "rel", "res", "ece")]
        w(f"| {k} | " + " | ".join(cells) + " |")
    w("\n`*` = interval excludes 0. Opus vs Sonnet differ on REL and ECE only. That difference is fragile: it "
      "comes from which bin the single miss falls in (Opus's 0.8 sits alone in the [0.7, 0.9) bin, while Sonnet's "
      "0.9 is pooled into the top bin with 15 correct MA calls). Brier and log loss, which do not bin, show no "
      "detectable difference.\n")

    w("## Calibration by hidden condition (rule D2)\n")
    w("Calibration-in-the-large = mean(p − y). It is positive when the agent leans toward MA.\n")
    w("| Agent | Condition | k correct | mean p | p range | Brier | log loss | mean(p − y) | D2 |")
    w("|---|---|---|---|---|---|---|---|---|")
    for n in AGENTS:
        for c in ("BP", "MA"):
            r = A[n]["by_condition"][c]
            lab = ("biased toward MA" if r["citl"] > 0 else "biased toward BP") if r["D2_biased"] else "no detectable bias"
            w(f"| {n} | {c} | {r['k_correct']}/15 | {est(r['mean_p'], r['mean_p_ci'])} | {r['p_min']:.3g}–{r['p_max']:.3g} | "
              f"{est(r['brier'], r['brier_ci'], '.4f')} | {est(r['log_loss'], r['log_loss_ci'])} | "
              f"{est(r['citl'], r['citl_ci'])} | {lab} |")
    w(f"\nEvery agent is \"biased\" by D2 in both conditions. For GoodScientist that is trivial (fixed 0.01/0.99, "
      f"so the interval has zero width). For Claude the BP lean is not only the miss. Descriptively (not "
      f"registered), the other 14 BP forecasts range {min(bp_other['C1 Opus']):.2f}–{max(bp_other['C1 Opus']):.2f} (Opus, "
      f"mean {sum(bp_other['C1 Opus']) / 14:.3f}) and {min(bp_other['C2 Sonnet']):.2f}–{max(bp_other['C2 Sonnet']):.2f} "
      f"(Sonnet, mean {sum(bp_other['C2 Sonnet']) / 14:.3f}), against a reference posterior that is essentially 0 for "
      f"every BP episode. The models hedge on plateau cultures and not on artefact cultures. PassiveBayes's lean "
      f"toward 0.5 in both conditions is what passive-only data supports (Gate 0 G0-A balanced accuracy "
      f"{pb['gate0_G0A']['balanced_accuracy']:.3f} on 1,000/condition).\n")
    w("![Mean stated probability by hidden condition](fig3_by_condition.png)\n")

    w("## Case study: s500028-BP\n")
    ep = cs["episode"]
    w(f"**Hidden culture** (read from the record, used only for diagnostics): BP, K = {cs['latent_18h']:.4f} ODeq, "
      f"S = {ep['assay']['s_odeq']:.4f}, K/S = {pe[CASE]['k_ratio']:.3f}. The reader saturates below S too, so the "
      f"noise-free undiluted reading is f(K) = {cs['noise_free_reading_18h']:.4f}. Biomass really is "
      f"{pe[CASE]['noise_free_gap']:.2%} above the reading. That is the largest gap of the 15 BP cultures "
      f"(range {gaps[0]:.2%}–{gaps[-1]:.2%}; rank {cs['rank_noise_free_gap_among_BP']}/15), with {TWIN} at "
      f"{pe[TWIN]['noise_free_gap']:.2%}. Both models called {TWIN} correctly (p = {pe[TWIN]['C1 Opus']['p']}, "
      f"{pe[TWIN]['C2 Sonnet']['p']}; ratios {pe[TWIN]['C1 Opus']['ratio']:.3f}, {pe[TWIN]['C2 Sonnet']['ratio']:.3f}). "
      f"The distance from the boundary is therefore the same in the two episodes; what differs is the noise draw.\n")
    pas = cs["passive"]
    w(f"**Passive data.** The 19 hourly readings rise to {pas[7][1]:.3f} at 7 h and stay flat after that "
      f"(7–18 h range {min(v for t, v in pas if t >= 7):.4f}–{max(v for t, v in pas if t >= 7):.4f}; mean at 15–18 h "
      f"{pe[CASE]['plateau_mean_15_18']:.4f}). PassiveBayes's committed p = {pe[CASE]['pb_p']:.3f}, so the passive data "
      f"cannot tell the conditions apart.\n")
    w("**Dilution readings.** Here z is the deviation from the noise-free reading of the true culture, in units of "
      "the assay noise SD (σ = 0.003 + 0.02·f). It is descriptive and was added after registration.\n")
    w("| Agent | t (h) | dilution | readings | d × reading | noise-free reading | z |")
    w("|---|---|---|---|---|---|---|")
    for n in ("C1 Opus", "C2 Sonnet", "GoodScientist"):
        for r in ca[n]["requests"]:
            w(f"| {n} | {r['time_h']} | {r['dilution']:g}× | {', '.join(f'{v:.4f}' for v in r['readings'])} | "
              f"{', '.join(f'{v:.3f}' for v in r['corrected'])} | {r['noise_free_reading']:.4f} | "
              f"{', '.join(f'{z:+.2f}' for z in r['z'])} |")
    assert cs["first_request_readings_identical"]
    w(f"\nThe first two 1:10 reads at 18 h are identical for all three agents, because the simulator's sample "
      f"noise is seeded per episode. GoodScientist took a third replicate (z = {ca['GoodScientist']['requests'][0]['z'][2]:+.2f}) "
      f"and applied its fixed rule (ratio {ca['GoodScientist']['ratio']:.3f} < τ = 1.5 → BP, p = 0.01). Opus and Sonnet "
      f"saw the same two upward reads (z = {z10}). They then added high-dilution reads whose relative noise is "
      f"large (σ/f = {rel_sd[20.0]:.1%} at 20×, {rel_sd[40.0]:.1%} at 40×, vs {rel_sd[10.0]:.1%} at 10×), and treated "
      f"the scatter as a signal.\n")
    w("| Agent | p | own ratio R | rank of R among 15 BP | other-BP R range | log(R/τ) | P_noise(R ≥ observed) | "
      "P_noise(R ≥ τ) | reference P(MA \\| own data) | D3 |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for n in ("C1 Opus", "C2 Sonnet", "GoodScientist"):
        a = ca[n]
        w(f"| {n} | {a['p']} | {a['ratio']:.3f} | {a['rank_ratio_among_BP']} | {a['other_BP_ratio_range'][0]:.3f}–"
          f"{a['other_BP_ratio_range'][1]:.3f} | {a['log_ratio_over_tau']:.3f} | {a['p_noise_ratio_ge_observed']:.3f} | "
          f"{a['p_noise_ratio_ge_tau']:.3f} | 10^{a['posterior_log10_odds']:.0f} odds | "
          f"{a['D3'].replace('_', ' ') if a['diagnosis'] != 'BIOMASS_AS_READ' else 'n/a (correct call)'} |")
    w(f"\nR is the mean of d × reading over the agent's late (12–18 h) diluted reads, divided by the mean passive "
      f"reading at 15–18 h. The noise probabilities come from 200,000 simulations of the true culture under each agent's "
      f"own measurement design, with passive reads redrawn. Under that design the noise-free R is "
      f"{ca['C1 Opus']['noise_free_ratio_same_design']:.3f}, and the 95% noise range is "
      f"{iv(ca['C1 Opus']['sim_ratio_q'][::2])} (Opus) and {iv(ca['C2 Sonnet']['sim_ratio_q'][::2])} (Sonnet). "
      f"The reference posterior is the exact grid posterior from the scenario-v1 generative model, using every reading "
      f"at t ≥ 14 h. Population reference from Gate 0: R_BP_p99 = {g0['R_BP_p99']:.3f}, R_MA_p1 = {g0['R_MA_p1']:.3f}.\n")
    w("![s500028-BP case study](fig4_s500028.png)\n")
    w("**What the models wrote** (final `submit_diagnosis` rationale, verbatim). The transcripts contain no visible "
      "assistant text outside tool calls. Their thinking blocks are signed and empty, so no reasoning beyond this "
      "can be quoted or inferred.\n")
    for n in CLAUDE:
        a = ca[n]
        w(f"*{n}* — `{a['diagnosis']}`, p = {a['p']}, estimate {a['estimate_od']} OD:\n")
        w("> " + a["rationale"] + "\n")
    w(f"**Assessment.** Under D3, neither model's call is a reasonable *condition* call. Its own data put P(MA) at "
      f"effectively 0, its R is far below τ, and noise never pushes R to τ for this culture. Each model also made a "
      f"specific error. Opus concluded that biomass \"kept rising to about 1.47 by 18 h\" from a single 14 h read "
      f"(z = {z14:+.2f}) and the upward 18 h reads, although latent biomass is flat at K (to within 2.1e-4, relative) from 14 h onward in "
      f"scenario-v1. Sonnet read 1.40 → 1.47 → 1.52 across "
      f"4×/10×/40× as non-proportionality, but the noise-free corrected value is {cs['latent_18h']:.3f} at every one of "
      f"those dilutions, and the 40× reads are at most z = {z40:+.2f}. Both answers are nevertheless true as *literal* statements "
      f"(biomass is {pe[CASE]['noise_free_gap']:.1%} above the reading). As OPEN_RULINGS §H already records, prompt-v2 asks "
      f"\"higher\" with no materiality threshold. This analysis does not rescore the episode (it stays correct = false). "
      f"Whether a later prompt should say \"substantially higher\" is a science-lead question, unchanged by this result.\n")

    w("## PassiveBayes: the 20 correct answers vs the 10 wrong ones\n")
    cc, cw = pb["conf_correct"], pb["conf_wrong"]
    w("| | n | mean confidence | median | range | n with confidence < 0.55 |")
    w("|---|---|---|---|---|---|")
    w(f"| correct | {pb['k_correct']} | {cc['mean']:.3f} | {cc['median']:.3f} | {cc['min']:.3f}–{cc['max']:.3f} | {cc['n_conf_lt_0_55']} |")
    w(f"| wrong | {pb['n'] - pb['k_correct']} | {cw['mean']:.3f} | {cw['median']:.3f} | {cw['min']:.3f}–{cw['max']:.3f} | {cw['n_conf_lt_0_55']} |")
    w(f"\nConfidence = max(p, 1 − p). {cc['n_conf_lt_0_55']} of the 20 correct answers were made at confidence below "
      f"0.55: these are the \"lucky\" ones, essentially coin flips. The remaining correct answers come from "
      f"{pb['n_conf_ge_0_75']} episodes with confidence ≥ 0.75 (all {pb['n_conf_ge_0_75_correct']} correct), whose "
      f"passive history happened to be informative. AUROC of confidence for correct vs wrong is "
      f"{est(pb['auroc'], pb['auroc_ci'], '.2f')}, so by D4 there is no detectable information at n = 30. Under its own "
      f"probabilities PassiveBayes expected {pb['expected_correct_own_probs']:.1f} correct; P(≥ {pb['k_correct']}) = "
      f"{pb['p_ge_observed_own_probs']:.2f}. So 20/30 {iv(pb['wilson95'], '.2f')} is consistent with its own calibration "
      f"and with Gate 0 G0-A {pb['gate0_G0A']['balanced_accuracy']:.3f} {iv(pb['gate0_G0A']['wilson95'], '.3f')}.\n")
    w("![PassiveBayes confidence](fig5_passive_bayes.png)\n")

    pc = d["passive_check"]
    w("## Limitations\n")
    w("- n = 30, with one record per (seed, agent). There are no significance claims; the intervals are wide, and binned "
      "REL/ECE depend on a single episode's bin placement.\n")
    w("- The results hold for scenario-v1, prompt-v2 and the strong matrix only. They are not compared with any model "
      "not run on this matrix.\n")
    w("- The Claude probabilities are coarse (a handful of distinct values), so the exact Murphy sensitivity is degenerate "
      "(REL = Brier, RES = UNC); see Deviations.\n")
    w(f"- The late-data reference posterior uses only readings at t ≥ 14 h. As a check, its passive-only version differs "
      f"from PassiveBayes's committed p by up to {pc['max_abs_diff_pb_vs_passive_only_posterior']:.3f}, and agrees in "
      f"label on {pc['same_label']}/30 episodes. PassiveBayes uses the whole curve, and most disagreements are at "
      f"p ≈ 0.5. The case-study conclusion does not depend on this: the late-data log10 odds are at most "
      f"{max_lo:.0f} for every agent.\n")
    w("- Thinking blocks are empty in the records, so the models' reasons are known only from their rationale text.\n")
    w("- The diagnostic quantities (hidden K, S, noise-free gap) come from the record's hidden config. No agent sees them.\n")
    w("## Spend\n")
    w("**$0.00.** No Anthropic API call was made, and no episode was run (dev or matrix). There is therefore no new "
      "`usage.jsonl`. The committed per-run `summary.json` / `results.md` under `experiments/results/<run>/` are the "
      "per-run summaries; their SHA-256 values are in `inputs.json`.\n")
    w("## Files\n")
    w("`REGISTRATION.md` (pre-registration + deviations) · `calib.py` (statistics) · `analysis.py` (loads records → "
      "`results.json`, `inputs.json`) · `figures.py` · `render_result.py` (→ this file) · tests in "
      "`tests/exploratory/calibration/`.\n")
    w("## Reproduce\n")
    w("```bash\n./mirage setup\n"
      "PYTHONPATH=src .venv/bin/python experiments/exploratory/calibration/analysis.py      # ~90 s\n"
      "PYTHONPATH=src .venv/bin/python experiments/exploratory/calibration/figures.py\n"
      "PYTHONPATH=src .venv/bin/python experiments/exploratory/calibration/render_result.py\n"
      "PYTHONPATH=src .venv/bin/python -m pytest tests/exploratory/calibration -q\n"
      "./mirage test --quick\n```\n")
    assert not any(math.isnan(x) for x in [pb["auroc"]])
    (HERE / "RESULT.md").write_text("\n".join(L), encoding="utf-8")
    print("wrote", HERE / "RESULT.md")


if __name__ == "__main__":
    main()
