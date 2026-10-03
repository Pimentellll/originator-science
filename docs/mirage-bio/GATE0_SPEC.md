# MIRAGE-Bio — Gate 0 Scientific Validation

| Field | Value |
|---|---|
| Status | Specification (3 October 2026). **Gate 0 has not been executed in the repository.** |
| Authority | The **single authoritative** Gate 0 specification. ANALYSIS §13 states the requirements (SVRs); this document states how they are demonstrated and what passes. DESIGN §17 points here. |
| Implementation | `scripts/gate0.py` (planned, DEV-006) |
| Design-time reference | [`experiments/reference/design_validation.py`](../../experiments/reference/design_validation.py) and its [saved output](../../experiments/reference/design_validation_output.txt). These are not the production Gate 0 and not evidence that it has passed. |

**No LLM integration is merged until every blocking criterion in §4 passes and the §3
outputs are committed.**

---

## 1. Purpose

Gate 0 is the scientific foundation of MIRAGE-Bio. It must demonstrate, using
repository code, that:

1. passive evidence is insufficient to identify the hidden condition;
2. `BIOLOGICAL_PLATEAU` is a genuine biological plateau, not severe assay saturation;
3. `MEASUREMENT_ARTIFACT` hides substantial continued growth;
4. an adequate late-stage dilution separates the two worlds;
5. inadequate interventions (undiluted re-measurement, early samples) do not solve
   the benchmark;
6. the result is not an artefact of one pathological parameter point.

## 2. Generative process

```text
episode seed ──► scenario stream [seed, 0]
                       │
   condition-independent nuisance (drawn FIRST):  S, r, X0, u
                       │
hidden condition H ────┤
 (from the matrix)     ├── condition-dependent:  K = κ(u)·S   if H = BIOLOGICAL_PLATEAU
                       │                         K = λ(u)·S   if H = MEASUREMENT_ARTIFACT
                       ▼
            latent state X(t)   (Richards, ν = 8)
                       │   aliquot at t, dilute by d
                       ▼
            assay model  y = f(X(t)/d; S, n = 8) + ε     (noise stream [seed, 1] or [seed, 2, i])
                       │
                       ▼
            passive observations (t = 0..18 h)  ──►  agent
```

| Parameter | Value / distribution | Scope | Condition-independent | Agent-visible | Evaluator-visible |
|---|---|---|---|---|---|
| Hidden condition $H$ | `BIOLOGICAL_PLATEAU` / `MEASUREMENT_ARTIFACT`, balanced by the matrix | per episode | — (it is the label) | no | yes |
| Growth sharpness $\nu$ | 8 | global fixed | yes | no | yes |
| Assay sharpness $n$ | 8 | global fixed | yes | no | yes |
| Noise $\sigma_{\text{abs}}, \sigma_{\text{rel}}$ | 0.003, 0.02 | global fixed | yes | no (only through readings) | yes |
| Reading resolution | 0.0001 | global fixed | yes | implicitly (4-dp readings) | yes |
| Saturation scale $S$ | $\log S \sim U[\log 0.5, \log 2.0]$ ODeq. Sampled **once** at episode creation and fixed for every measurement in the episode. | per-episode nuisance | **yes**: $P(S \mid H_A) = P(S \mid H_B)$ by construction | no | yes |
| Growth rate $r$ | $U[0.6, 0.9]$ h⁻¹ | per-episode nuisance | yes | no | yes |
| Inoculum $X_0$ | $\log X_0 \sim U[\log 0.005, \log 0.02]$ ODeq | per-episode nuisance | yes | no (the $t = 0$ reading approximates it) | yes |
| $K$-quantile $u$ | $U(0, 1)$ | per-episode nuisance | yes | no | yes |
| $\kappa$ | $0.80 + 0.10\,u$ | condition-dependent (`BIOLOGICAL_PLATEAU`) | no | no | yes |
| $\lambda$ | $3 + 2u$ | condition-dependent (`MEASUREMENT_ARTIFACT`) | no | no | yes |
| Carrying capacity $K$ | $\kappa S$ or $\lambda S$ | condition-dependent | no | no | yes |
| Passive schedule | $t = 0, 1, \dots, 18$ h; $d = 1$; 1 replicate | global fixed | yes | yes | yes |
| Budget, dilution range, replicates, turns | 6; $[1, 100]$; 1–3; 12 | global fixed | yes | yes | yes |
| Useful-region bounds | compression ≤ 5 %; noise-free reading ≥ $10\,\sigma_{\text{abs}} = 0.03$ | global fixed (benchmark threshold) | yes | no | yes |
| Late diagnostic window | $t \in [12, 18]$ h (clock time) | global fixed (benchmark threshold) | yes | not disclosed, but defined only on visible clock time | yes |
| Seed and noise draws | per episode / per reading | — | yes | readings only | yes |

**Independence by construction.**
- $S, r, X_0, u$ are drawn from the scenario stream **before** the condition is read.
  The same seed therefore yields identical nuisance values under either condition
  (T-024).
- Over independent seeds, the distribution of $S$ is identical by condition (T-025;
  G0-F).
- $S$ never changes within an episode (T-026; G0-F).

## 3. Required Gate 0 outputs

All are written to `experiments/results/gate0/` and committed:

```text
experiments/results/gate0/
├── assay_response.png
├── passive_overlap.png
├── latent_reveal.png
├── intervention_sweep.png
├── separability_before_after.png
├── robustness_map.png            # non-blocking (strongly recommended)
└── summary.json
```

| File | Content | Purpose |
|---|---|---|
| `assay_response.png` | $f(x)$ against $x/S$, with the identity line. Shade: the useful region ($x \le 0.9187\,S$, compression ≤ 5 %); the `BIOLOGICAL_PLATEAU` late-stage band ($K \in [0.80, 0.90]\,S$); the `MEASUREMENT_ARTIFACT` latent band ($K \in [3, 5]\,S$). Mark the readings those bands produce. Secondary panel: compression $1 - f(x)/x$. | Show visually that Condition A sits in the low-compression region (1.9–4.4 %) and is not secretly saturated, while Condition B's latent biomass maps onto the flat top. |
| `passive_overlap.png` | 40 noisy passive trajectories per condition (different seeds) overlaid in two colours, plus each condition's pointwise 5–95 % band. Second panel: histogram of the late passive mean (13–18 h) by condition. | Show that the worlds look alike before intervention. |
| `latent_reveal.png` | Matched demo pair (`demo_pair.json`): both observed curves (solid; identical to 3 × 10⁻¹⁶) and both latent curves $X(t)$ (dashed). `BIOLOGICAL_PLATEAU` plateaus at 1.03; `MEASUREMENT_ARTIFACT` reaches 4.0. Mark the late window and the 1:10 corrected values. | The conceptual heart of the benchmark; reused in the demo. |
| `intervention_sweep.png` | Dilution grid $d \in \{1, 2, 5, 10, 20, 50, 100\}$ at $t = 18$ h with 3 replicates, using the same 500 worlds per condition at every $d$. Panels: (a) $\hat C/K$ median and 95 % band by condition; (b) fraction of M2-valid measurements by condition; (c) discriminability: AUROC of $R = \hat C/\hat P$ and balanced accuracy of the $\tau = 1.5$ rule; (d, optional) matched-twin diagnosticity $D(a)$ ([BENCHMARK_METHODOLOGY §3](../BENCHMARK_METHODOLOGY.md#3-experiment-diagnosticity)). | Show what too little, adequate and too much dilution each do, honestly (§6). |
| `separability_before_after.png` | Balanced accuracy, with Wilson 95 % intervals where applicable. *Passive only:* analytic Bayes ceiling, `PassiveBayes`, 15-NN. *After one experiment:* undiluted late re-measurement; early diluted sample ($t = 3$ h, $d = 10$); adequate late dilution (reference protocol, $\tau$ rule). AUROC is shown alongside. | Quantify "passive evidence only" against "after a diagnostic experiment", and show that inadequate experiments add nothing. |
| `robustness_map.png` | Grid with rows = one-at-a-time perturbations and columns = blocking properties (passive 15-NN accuracy; maximum BP compression; `GoodScientist` accuracy). Each cell shows the value, coloured pass/fail. | Show that the benchmark occupies a region of parameter space, not one point. |
| `summary.json` | §7 | Machine-readable evidence |

Perturbations for `robustness_map.png`:

| Parameter | Perturbations |
|---|---|
| $\nu$ (with $n = 8$) | 6, 7, 9, 10 |
| $n$ (with $\nu = 8$) | 7, 10 |
| Noise | ×0.5, ×2 |
| $r$ range | ×0.8, ×1.2 |
| $X_0$ range | ÷2, ×2 |
| $S$ range | [0.6, 1.5], [0.4, 2.5] |

## 4. Quantitative acceptance criteria

Threshold types:
- **BDT**: benchmark design threshold. Chosen to define a valid benchmark; not a
  fact about nature.
- **SIM**: simulator choice.
- **FACT**: empirical or scientific fact.

No criterion here is a FACT. Biological facts used by the design (ANALYSIS §10,
A-001 to A-005) are qualitative.

| ID | Property (SVR) | Criterion | Type | Blocking | Design-time reference |
|---|---|---|---|---|---|
| **G0-A** | Passive ambiguity (SVR-001) | Each of the following has balanced accuracy ≤ 0.65: (i) analytic Bayes ceiling; (ii) `PassiveBayes` on 1,000 test episodes per condition; (iii) 15-NN on log full trajectories (1,000 train + 1,000 test per condition) | BDT | yes | 0.577 / 0.574 / 0.552 |
| **G0-B** | Condition A trustworthy (SVR-003) | (i) Noise-free compression at $K$ ≤ 5 % in 100 % of 10,000 BP scenarios. (ii) Reference protocol on 1,000 BP episodes: ≥ 95 % with $\lvert R - 1\rvert \le 0.15$ and ≥ 95 % with $\lvert \hat C/K - 1\rvert \le 0.15$ | BDT (5 % is SIM-defined) | yes | max 4.38 %; 99.7 %; $\hat C/K$ 95 % = [0.93, 1.07] |
| **G0-C** | Diagnostic separation and late-window validity (SVR-002, SVR-007) | (i) ≥ 99 % of 1,000 MA episodes have $R \ge 2.5$. (ii) `GoodScientist` accuracy ≥ 0.98 over 1,000 per condition. (iii) ≥ 95 % of MA have $\lvert\hat C/K - 1\rvert \le 0.15$. (iv) Over 10,000 scenarios per condition: $t_{95} + 2\text{ h} \le 12$ h in 100 %, and in MA $X(12\text{ h})/K' \ge 2.5$ in 100 % | BDT | yes | 100 %; 1.000; MA 95 % = [0.97, 1.03]; max $t_{95}+2$ = 11.92 h; min ratio 2.995 |
| **G0-D** | Inadequate interventions (SVR-008, SVR-009) | **D1** (blocking): undiluted late re-measurement ($t = 18$, $d = 1$, 3 reps), with discriminability $\max(\text{AUROC}, 1 - \text{AUROC})$ of $R$ ≤ 0.65. **D2** (blocking): early diluted sample ($t = 3$, $d = 10$, 3 reps), same criterion. **D3** (non-blocking, reported): with $d = 2$ in MA, ≥ 95 % present biomass outside the useful region and have $\hat C/K \le 0.75$. Its discriminability is reported without a threshold. | BDT | D1, D2 yes; D3 no | D1 0.503; D2 0.581; D3 100 % outside, 97.5th percentile of $\hat C/K$ = 0.65 (AUROC 1.00, see §6) |
| **G0-E** | Passive-family equivalence (implementation integrity) | Max relative deviation between $f(X(t))$ and Richards$(K', y_0, r, \nu)$ ≤ 10⁻⁹ over 1,000 scenarios per condition, $t = 0..18$ h in steps of 0.25 h | SIM | yes | 3.0 × 10⁻¹⁶ |
| **G0-F** | Nuisance independence and instrument stability (SVR-006) | (i) The same seed gives identical $S, r, X_0, u$ under both conditions (seeds 0–9,999). (ii) Two-sample KS statistic of $\log S$ between conditions on independent seeds (10,000 each) ≤ 0.03. (iii) $S$ is unchanged across all measurements in 100 simulated episodes with 6 requests each. | SIM | yes | by construction |
| **G0-G** | Robustness (SVR-010) | For each §3 perturbation: 15-NN passive accuracy ≤ 0.65, `GoodScientist` accuracy ≥ 0.98, and maximum BP compression ≤ 5 %, or else the failure is reported as a documented boundary | BDT | **no** | All perturbations pass except $n = 7$ (compression 5.4 %), a documented boundary |

Not computed by Gate 0 but required before MS1: hidden-state isolation (SVR-004) and
no LLM in evaluation (SVR-005), both via T-012.

## 5. Passive-baseline strength

| Classifier | What it is | Correct wording |
|---|---|---|
| Analytic Bayes ceiling | Oracle calculation from the generative model. By passive-family equivalence (DESIGN §5.4), the noise-free passive likelihood ratio depends only on $K'$. The ceiling is $\tfrac12 + \tfrac12\,\mathrm{TV}$ between the two $\log K'$ distributions, from ≥ 200,000 draws per condition (200-bin histogram; this slightly overestimates, i.e. is conservative). | "Analytic Bayes ceiling (noise-free, under the `scenario-v1` prior)" |
| `PassiveBayes` | Plug-in likelihood ratio on the late passive mean, with class-conditional densities from 200,000 simulated episodes per condition | "Strongest implemented passive baseline". Never "optimal" or "best possible". |
| 15-NN | Model-free, on log full trajectories | "Model-free full-trajectory check" |
| Monte Carlo marginal-likelihood classifier on full trajectories | Optional; not required | Only if implemented and converged |

No implemented classifier may be called optimal. The bound is the analytic ceiling.

## 6. Intervention diagnosticity: what the sweep shows (design-time reference)

| $d$ | BP $\hat C/K$ (95 %) | MA $\hat C/K$ (95 %) | M2-valid BP / MA | AUROC($R$) | $\tau$-rule balanced accuracy |
|---|---|---|---|---|---|
| 1 | 0.97 [0.94, 1.00] | 0.25 [0.20, 0.33] | 0 / 0 | 0.51 | 0.50 |
| 2 | 1.00 [0.97, 1.03] | 0.50 [0.40, 0.65] | 1.00 / 0 | 1.00 | 1.00 |
| 5 | 1.00 [0.95, 1.04] | 0.98 [0.92, 1.02] | 1.00 / 0.82 | 1.00 | 1.00 |
| 10 | 1.00 [0.93, 1.07] | 1.00 [0.97, 1.03] | 1.00 / 1.00 | 1.00 | 1.00 |
| 20 | 1.00 [0.88, 1.12] | 1.00 [0.96, 1.04] | 0.74 / 1.00 | 1.00 | 1.00 |
| 50 | 1.00 [0.75, 1.27] | 1.00 [0.93, 1.08] | 0.09 / 1.00 | 1.00 | 0.999 |
| 100 | 1.01 [0.50, 1.46] | 1.00 [0.87, 1.13] | 0 / 0.69 | 1.00 | 0.986 |

What this shows, stated honestly:

- **Too little dilution** cannot reconstruct the hidden biomass: at $d = 2$, MA
  recovers only ≈ 50 %, and the measurement is not M2-valid. It **does** still
  discriminate the conditions, through the dilution-proportionality ratio
  (AUROC 1.00). The benchmark therefore separates "detected nonlinearity" (diagnostic;
  M5) from "quantitatively valid control" (M2).
- **Adequate dilution** ($d = 10$; universal window $[5.44, 13.3]$) reconstructs both
  worlds within ≈ 7 % and discriminates perfectly.
- **Too much dilution** degrades precision ($d = 100$: BP 95 % band ±50 %) and fails
  the useful-region lower bound. Discrimination barely degrades (balanced accuracy
  0.99). **No U-shaped discrimination optimum is claimed.** The cost of over-dilution
  in this simulator is precision and validity, not discriminability.

Matched-twin diagnosticity $D(a)$ is cheap (closed form). It may be overlaid on
panel (d). A formal information-theoretic score (M5 / selection efficiency) is
post-MVP.

## 7. Machine-readable result (`summary.json`)

```json
{
  "schema_version": "gate0-summary-v2",
  "passed": false,
  "scenario_version": "scenario-v1",
  "scenario_sha256": "<sha256 of canonical scenario_v1.json>",
  "source_commit": "<git rev-parse HEAD or null>",
  "source_dirty": true,
  "parameters": {"nu": 8, "n": 8, "sigma_abs": 0.003, "sigma_rel": 0.02, "resolution": 0.0001,
                 "eps_lin": 0.05, "lower_useful_bound": 0.03, "late_window_h": [12, 18],
                 "passive_times_h": "0..18", "budget_units": 6, "dilution_range": [1, 100]},
  "nuisance_distributions": {"S": "loguniform(0.5, 2.0)", "r": "uniform(0.6, 0.9)",
                             "X0": "loguniform(0.005, 0.02)", "u": "uniform(0, 1)",
                             "kappa": "0.80 + 0.10*u", "lambda": "3 + 2*u"},
  "seeds": {"test": [900000, 900999], "knn_train": [901000, 901999], "scans": [902000, 911999],
            "sweep": [900000, 900499], "robustness": [920000, 929999], "passive_reference": [1000000, 1199999]},
  "checks": {
    "G0-A": {"blocking": true, "passed": false, "threshold": 0.65, "threshold_type": "BDT",
             "analytic_ceiling": null, "passive_bayes": {"balanced_accuracy": null, "wilson95": null, "n_per_condition": 1000},
             "knn15": {"balanced_accuracy": null, "wilson95": null, "n_per_condition": 1000}},
    "G0-B": {"blocking": true, "passed": false, "max_compression": null, "frac_R_within_0_15": null, "frac_C_over_K_within_0_15": null},
    "G0-C": {"blocking": true, "passed": false, "frac_MA_R_ge_2_5": null, "good_scientist_accuracy": null,
             "frac_MA_C_over_K_within_0_15": null, "max_t95_plus_2_h": null, "min_MA_X12_over_Kprime": null},
    "G0-D": {"blocking": true, "passed": false, "D1_undiluted_discriminability": null, "D2_early_discriminability": null,
             "D3": {"blocking": false, "frac_outside_useful_region": null, "p95_C_over_K": null, "auroc": null}},
    "G0-E": {"blocking": true, "passed": false, "max_relative_deviation": null},
    "G0-F": {"blocking": true, "passed": false, "same_seed_identical": null, "ks_logS": null, "within_episode_stable": null},
    "G0-G": {"blocking": false, "passed": null, "variants": []}
  },
  "passive_baseline": {"name": "PassiveBayes", "balanced_accuracy": null},
  "diagnostic_dilution": {"t_h": 18, "d": 10, "replicates": 3, "R_BP_p99": null, "R_MA_p1": null},
  "good_scientist": {"accuracy": null, "valid_control_rate": null},
  "sweep": [{"d": 1, "auroc": null, "tau_balanced_accuracy": null, "valid_BP": null, "valid_MA": null}],
  "plots": ["assay_response.png", "passive_overlap.png", "latent_reveal.png", "intervention_sweep.png",
            "separability_before_after.png", "robustness_map.png"],
  "versions": {"python": null, "numpy": null, "matplotlib": null, "mirage": null},
  "runtime_s": null
}
```

`passed` is the logical AND of the `passed` flags of every **blocking** check. Every
SVR verified by Gate 0 (SVR-001, -002, -003, -006, -007, -008, -009, -010) has an
entry.

## 8. Freeze rule and failure handling

**Freeze.** When Gate 0 passes:
- `experiments/configs/scenario_v1.json` is frozen. Its canonical SHA-256 is recorded
  in `summary.json`.
- The runner refuses to run if the hashes differ (T-031).
- Any change to a scientific parameter requires a new scenario version, a full Gate 0
  re-run, and regenerated plots and `summary.json` committed with the change.
- Gate 0 parameters must never be changed in response to agent results
  ([EXPERIMENT_PLAN §1.1](EXPERIMENT_PLAN.md#11-two-separate-phases)).

**If Gate 0 fails.**
1. Assume an implementation bug first. Compare against the design-time reference
   output.
2. The only pre-approved parameter change is widening $S$ to $[0.4, 2.5]$
   (design-time ceiling 0.56), as `scenario-v1.1`.
3. Any other change needs science-lead sign-off, an update to this document, and a
   full re-run.
4. Thresholds in §4 are never relaxed.

## 9. Sizes, seeds and runtime

- **Sizes:** as in §4. The sweep uses 500 paired worlds per condition. Robustness
  uses 300 per condition per perturbation.
- **Seed blocks:** as in `summary.json` above. All are inside the `gate0` and
  `passive_reference` blocks of DESIGN §18.
- **Runtime:** < 5 min with vectorised numpy.
- **Quick mode:** `scripts/gate0.py --quick` runs at reduced sizes for tests (T-030).
  It writes the same files but must never be used to claim a pass.
