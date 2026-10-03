# MIRAGE Benchmark Methodology

| Field | Value |
|---|---|
| Status | Methodology (3 October 2026). Items marked *current* are planned for MIRAGE-Bio v0.1; items marked *stretch* or *future* are non-blocking. |
| Role | How MIRAGE constructs ambiguity and evaluates experiments |
| Related | [MIRAGE](MIRAGE.md) · [DIFFERENTIATION](DIFFERENTIATION.md) · [MIRAGE-Bio GATE0_SPEC](mirage-bio/GATE0_SPEC.md) · [MIRAGE-Bio DESIGN §15](mirage-bio/DESIGN.md#15-evaluation) |

---

## 1. Paired worlds: controlled non-identifiability

**Plain English.** Build two (or more) hidden worlds with genuinely different causes.
Their initial observations must be so alike that even a classifier that knows how
the worlds are generated cannot reliably tell them apart. At least one available
experiment must produce clearly different outcomes in the two worlds. The benchmark
then asks whether the agent finds and runs such an experiment before it commits to
a conclusion.

**Formally.** Let $W \in \{W_1, W_2\}$ be the hidden world and $\theta$ be nuisance
parameters (instrument, inoculum, rates). The nuisance distribution is independent
of the world:

$$p(\theta \mid W_1) = p(\theta \mid W_2) = p(\theta).$$

If it were not, the nuisance would leak the label. Initial (passive) data $D_0$ are
generated as $D_0 \sim P(D_0 \mid W, \theta)$. The construction requires:

$$P(D_0 \mid W_1) \approx P(D_0 \mid W_2), \qquad P(D_0 \mid W) = \int P(D_0 \mid W, \theta)\,p(\theta)\,d\theta,$$

operationalised as: Bayes classification accuracy from $D_0$ ≤ a pre-registered
threshold. It also requires that there exists an action $a^*$ in the action space
$\mathcal A$ with outcome $Y$ such that

$$P(Y \mid W_1, a^*) \not\approx P(Y \mid W_2, a^*),$$

operationalised as: accuracy from $(D_0, Y_{a^*})$ ≥ a pre-registered threshold.

This is **controlled non-identifiability**. MIRAGE deliberately constructs situations
where passive data do not contain enough information for a justified conclusion.
That is a benchmark property, demonstrated quantitatively before any agent is
evaluated. It is not an accidental flaw.

**MIRAGE-Bio instance.**

| Element | MIRAGE-Bio v0.1 |
|---|---|
| $W_1$, $W_2$ | `BIOLOGICAL_PLATEAU`, `MEASUREMENT_ARTIFACT` |
| $\theta$ | Saturation scale $S$, growth rate $r$, inoculum $X_0$, all drawn independently of $W$ |
| $D_0$ | 19 hourly undiluted OD readings |
| $a^*$ | Late-stage aliquot, adequately diluted (e.g. 1:10) |
| Passive threshold / design-time value | ≤ 0.65 / analytic Bayes ceiling ≈ 0.58 |
| After-$a^*$ threshold / design-time value | ≥ 0.98 / ≈ 1.00 |

Details: [GATE0_SPEC](mirage-bio/GATE0_SPEC.md).

## 2. What is evaluated

| Dimension | Question | MIRAGE-Bio v0.1 | Status |
|---|---|---|---|
| Answer quality | Did the agent identify the correct hidden world? | M1 diagnosis accuracy | current |
| Evidence quality | Did it perform an experiment that distinguishes the remaining explanations? | M2 diagnostic-control rate; M3 justified accuracy (M1 ∧ M2) | current |
| Quantitative reconstruction | Did the experiment also permit an accurate estimate of the hidden quantity? | Q1 reconstruction adequacy: secondary, descriptive; not required for justification | current (secondary) |
| Experimental efficiency | How much budget did it use? | M4 experimental cost | current |
| Experiment diagnosticity | How informative was the chosen experiment compared with the alternatives? | M5 (§3) | stretch, non-blocking |
| Belief revision | Did it change its conclusion appropriately when new evidence arrived? | Probabilities are logged if the agent uses `declare_state`; not scored | future |
| Premature commitment | Did it conclude before collecting sufficient evidence? | Reported descriptively as correct-but-unjustified episodes (M1 ∧ ¬M2); no separate metric | future |
| Claim/evidence alignment | Is the claimed strength bounded by the evidence? | Evidence-maturity ladder ([MIRAGE §6](MIRAGE.md#6-evidence-maturity-project-philosophy-not-mvp-scoring)) | future |

MIRAGE-Bio v0.1 ships with M1–M4. M5 and everything below it in the table must not
block development.

## 3. Experiment diagnosticity

Because the evaluator knows the generative model, it can estimate how discriminative
any experiment $a$ is between the candidate worlds. A general diagnosticity function
$D(a)$ measures how separated the predicted outcome distributions
$P(Y \mid W_i, a)$ are.

| Option | Definition | Trade-off |
|---|---|---|
| Jensen–Shannon divergence | $\mathrm{JS}(P(Y\mid W_1,a)\,\Vert\,P(Y\mid W_2,a))$ | Symmetric and bounded; needs density estimates |
| Expected information gain | $I(W; Y \mid a, D_0)$ (Lindley, 1956) | Principled; needs a posterior over worlds and nuisance; heavier to compute |
| Outcome-classification AUROC | AUROC of discriminating $W_1$ from $W_2$ using the single outcome $Y$ | Simple, interpretable (0.5 = useless, 1 = decisive); easy to reproduce |

**Recommended for MIRAGE-Bio v0.1 (M5, stretch): matched-twin single-outcome AUROC.**

1. For the episode's world $W$, construct its **matched twin** $W'$ in the other
   condition. $W'$ has the same $r$, $X_0$ and $K$-quantile, with $S'$ solved in
   closed form so that both worlds have the same apparent plateau $K'$. The two
   worlds then produce identical noise-free passive data, so $W'$ is exactly the
   competing explanation the agent faces.
2. For the agent's measurement $a = (t, d, m)$, compute the noise-free readings
   $\mu_W, \mu_{W'}$ and noise SDs $\sigma_W, \sigma_{W'}$. Then

   $$D(a) = \Phi\!\left(\frac{\lvert \mu_W - \mu_{W'}\rvert}{\sqrt{(\sigma_W^2 + \sigma_{W'}^2)/m}}\right).$$

   This is a closed form. It needs no sampling.

Design-time values for the demo pair ([reference output](../experiments/reference/design_validation_output.txt)):

| Measurement | $D(a)$ |
|---|---|
| Undiluted re-measurement | 0.50 |
| Diluted, $t \le 4$ h | 0.50 |
| Diluted, $t = 6$ h | 0.80 |
| Any late dilution $d \ge 2$ | 1.00 |

**Selection efficiency** (Phase 2): $E(a) = D(a) / \max_{a' \in \mathcal A} D(a')$.
For an AUROC-based $D$, the chance-corrected form
$(D(a) - 0.5)/(\max D - 0.5)$ is preferable.

**Honest limitation.** In a two-world problem with a decisive experiment, every
diagnosticity measure saturates. In MIRAGE-Bio, M5 separates *non-diagnostic* choices
(≈ 0.5) from *diagnostic* ones (≈ 1). It does not rank good experiments against each
other.

**Diagnostic sufficiency vs quantitative reconstruction.** MIRAGE credits evidence
that makes the explanations distinguishable.
- **M2** counts an action as diagnostic if Gate 0 has demonstrated that actions of
  its class discriminate the worlds. In MIRAGE-Bio v0.1 this is a frozen
  classification of late dilution factors (GATE0_SPEC G0-H); it needs no M5
  machinery at scoring time.
- **M5** grades diagnosticity more finely (stretch).
- **Q1** separately records whether the measurement also permits accurate
  reconstruction of the latent quantity. Q1 is useful scientific information but is
  not required for a justified diagnosis.

| Late measurement | Diagnostic separation (M2) | Accurate biomass reconstruction (Q1) |
|---|---|---|
| 1:2 dilution | **Yes** ($D = 1.0$; AUROC 1.00) | **No** (≈ 50 % of true biomass in `MEASUREMENT_ARTIFACT`) |
| 1:10 dilution | **Yes** | **Yes** |

Gate 0 additionally reports **prior-level** diagnosticity: the AUROC of the dilution
ratio statistic across the dilution sweep ([GATE0_SPEC §3](mirage-bio/GATE0_SPEC.md#3-required-gate-0-outputs)).

## 4. Why correct answers are insufficient

In a balanced two-world benchmark:

- **Lucky guess:** a coin flip scores ≈ 50 % accuracy with no evidence.
- **Scripted bias:** a fixed rule, such as "dense cultures are always saturated, so
  answer `GROWTH_CONTINUED`", scores 50 % overall and 100 % on one world. Reported
  per world, it can look impressive.
- **Passive inference** can reach the passive ceiling (≈ 0.58 in MIRAGE-Bio) without
  any experiment.

Therefore

```text
correct conclusion
without diagnostic evidence
```

is not equivalent to

```text
correct conclusion
supported by evidence acquired during the episode
```

Justified accuracy (M3) counts only the second. Correct-but-unjustified episodes are
reported separately.

## 5. Counterfactual evaluation advantage

Because MIRAGE controls the worlds, the evaluator can ask of any action the agent
took: *what would this same experiment have produced in each competing world?* That
allows direct, per-episode evaluation of experiment quality, independent of whether
the agent happened to reach the right answer.

- In MIRAGE-Bio the matched twin (§3) is computed analytically.
- The demo pair is such a twin pair: identical passive readings, with true biomass
  1.03 vs 4.0.
- Real-world or dataset-backed evaluations cannot normally do this, because the
  counterfactual world is never observed.

## 6. Generalisation (methodology only)

A new MIRAGE environment would need, at minimum:

1. two or more fully specified hidden worlds with different causal explanations;
2. nuisance parameters drawn independently of the world;
3. demonstrated passive ambiguity against a strong model-aware classifier;
4. at least one feasible diagnostic action, with demonstrated separation;
5. evidence that trivial or inadequate actions are not diagnostic;
6. deterministic ground truth and hidden-state isolation;
7. a Gate-0-style validation before any agent is evaluated, with parameters frozen
   before agent runs.

This describes how the method transfers. **No other environment is planned or
implemented.** No generic environment interface is part of the MIRAGE-Bio
implementation.

### Reference

Lindley, D. V. (1956). On a measure of the information provided by an experiment.
*Annals of Mathematical Statistics*, 27(4), 986–1005.
