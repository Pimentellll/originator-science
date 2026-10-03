# MIRAGE-Bio — Analysis

| Field | Value |
|---|---|
| Status | Accepted for MVP (3 October 2026) |
| Role | Authoritative requirements: **what** is built and **why** |
| Project | MIRAGE-Bio is the first environment of [MIRAGE](../MIRAGE.md). Methodology: [BENCHMARK_METHODOLOGY](../BENCHMARK_METHODOLOGY.md) |
| Related | [DESIGN](DESIGN.md) (how) · [GATE0_SPEC](GATE0_SPEC.md) (scientific validation) · [DEVELOPMENT_PLAN](DEVELOPMENT_PLAN.md) (when) · [TEST_PLAN](TEST_PLAN.md) (verification) · [EXPERIMENT_PLAN](EXPERIMENT_PLAN.md) (measurement) · [RISKS](RISKS.md) · [ADRs](ADR/) |

Normative language: **must** = required for the MVP; **should** = expected unless a
documented reason prevents it; **may** = optional.

---

## 1. Purpose

This document is the authoritative statement of requirements for MIRAGE-Bio. It
specifies the scientific question, the scope boundary, the scientific model at the
level of assumptions, and the functional, non-functional and scientific-validity
requirements that the implementation must satisfy. Implementation detail (equations
in code form, schemas, module boundaries) lives in [DESIGN.md](DESIGN.md).

When this document and any other project document conflict, this document wins on
*what* and *why*. DESIGN wins on *how*, and GATE0_SPEC wins on how the
scientific-validity requirements are demonstrated. Conflicts must be fixed, not
tolerated. Project-level concepts (paired worlds, justified accuracy, diagnosticity)
are defined in [MIRAGE](../MIRAGE.md) and
[BENCHMARK_METHODOLOGY](../BENCHMARK_METHODOLOGY.md).

## 2. Problem context

### 2.1 Autonomous scientists

AI agents are increasingly used to propose, run and interpret experiments in closed
loops (AI-scientist systems, self-driving laboratories). Evaluations of such agents
usually ask whether they reach a correct answer or optimise an objective. They rarely
ask whether an agent notices that its evidence **cannot** distinguish between
competing explanations, and whether it then chooses the experiment that can.

### 2.2 Measurement-mediated observation

An agent never observes biological state directly. It observes instrument readings:
the output of a measurement process applied to that state. Every biological
inference therefore depends, explicitly or not, on a model of the instrument.
When the instrument's response changes character (for example, stops being
proportional), the same readings can be produced by different biological states.

### 2.3 OD600-like measurements

Optical density at 600 nm (OD600) is the routine proxy for microbial culture
density. Facts relied on by this project (see §10 for labels):

- OD600 measures attenuation of light, dominated by scattering, through a cell
  suspension. It is a proxy for biomass, not a count of viable cells (A-001).
- At sufficiently high density the reading becomes sublinear in density (A-002).
- The density at which this happens depends on instrument, optical path length,
  wavelength, organism and medium; there is no universal threshold (A-003).
- Dense samples are measured by diluting into the proportional range and
  multiplying by the dilution factor ("back-correction") (A-004).

### 2.4 How measurement response confounds biological interpretation

A flattening of OD readings late in a batch culture can mean that biomass stopped
increasing (stationary phase), or that biomass kept increasing while the instrument
stopped responding proportionally. From the readings alone these two explanations
can be indistinguishable. A standard control separates them: dilute a late-stage
aliquot into the proportional range, read it, and back-correct. If the
back-corrected value agrees with the apparent plateau, the plateau is real; if it is
much larger, the plateau was produced by the measurement.

## 3. Problem statement

There is no small, controlled, fully auditable environment in which:

1. passive observation **quantitatively** underdetermines the explanation;
2. a specific, feasible control experiment resolves it;
3. ground truth is known exactly; and
4. scoring is deterministic and free of LLM judgement.

Without such an environment, claims that an AI scientist "recognises ambiguity" or
"chooses good controls" cannot be tested cleanly. MIRAGE-Bio provides one such
environment for one scenario.

## 4. Scientific question

> When an apparent biological effect is equally consistent with true biology and
> measurement artefact, can an autonomous scientist recognise the ambiguity and
> choose the control experiment that makes the explanations distinguishable?

Demo framing: *Did the cells stop growing, or did the instrument stop seeing them?*

## 5. Project thesis

MIRAGE-Bio is a controlled virtual microbiology laboratory in which an AI scientist
sees a growth curve that rises and apparently plateaus. In one hidden condition the
culture genuinely stops growing within the instrument's trustworthy range; in the
other it keeps growing far beyond that range and the instrument's nonlinear response
hides the growth. The passive data are constructed to be quantitatively ambiguous:
a classifier with full knowledge of the simulator, using passive data only,
stays close to chance. One adequately diluted late-stage measurement makes the two
explanations clearly separable. Because ground truth is held by the simulator and
scoring is deterministic, the environment measures whether an agent **acts** to
resolve ambiguity, not whether it can recite a fact about OD600.

## 6. Objectives

### 6.1 Primary objectives

| ID | Objective |
|---|---|
| OBJ-1 | Build a virtual laboratory in which passive OD readings are quantitatively ambiguous between `BIOLOGICAL_PLATEAU` and `MEASUREMENT_ARTIFACT`, and an adequate late-stage dilution separates them. |
| OBJ-2 | Measure whether one autonomous AI scientist chooses a diagnostic control (an experiment that distinguishes the competing explanations) and reaches a correct, justified diagnosis. |
| OBJ-3 | Compare that agent with the strongest implemented passive baseline (read against the analytic passive ceiling) and a scripted good-scientist baseline (evidence that the task is solvable within budget). |
| OBJ-4 | Deliver an offline demo that replays saved evidence. |

### 6.2 Secondary objectives

| ID | Objective |
|---|---|
| OBJ-5 | Record the agent's stated beliefs so that calibration can be reported (optional metric). |
| OBJ-6 | Record experimental cost and rounds to diagnosis. |
| OBJ-7 | Produce episode records that are self-contained and re-scorable. |

### 6.3 Explicit non-objectives

- A realistic digital twin of *E. coli* or of any real plate reader.
- Determining the true linear range of any real instrument.
- Benchmarking many models or vendors.
- Proposing a new agent method; the novelty is the evaluation design.
- Producing biological discoveries.
- A general autonomous-science benchmark.
- Optimising the agent prompt to maximise score.

## 7. Scope

### 7.1 In scope (MVP)

| Element | Count |
|---|---|
| Virtual biological world | 1 |
| Bacterial-growth abstraction | 1 (Richards / generalised logistic) |
| OD600-like assay | 1 |
| Hidden conditions | 2: `BIOLOGICAL_PLATEAU`, `MEASUREMENT_ARTIFACT` |
| Active intervention | 1: aliquot dilution + remeasurement |
| AI-scientist adapter | 1 (Claude, Anthropic API) |
| Scripted baselines | 2: `GoodScientist`, `PassiveBayes` |
| Deterministic evaluator | 1 |
| Experiment runner | 1 |
| Offline demo replay | 1 |
| Evaluation episodes per agent configuration | 10 (minimum) to 30 (target) |

### 7.2 Out of scope

Second organism; second assay; fluorescence; sequencing; microscopy; real wet-lab
integration; real biological datasets; multiple sensor-fault types; multi-agent
debate; retrieval-augmented generation; agent frameworks; fine-tuning; web platform
or UI; a general autonomous-science benchmark; more than 30 evaluation episodes per
configuration before the MVP is complete; multiple vendors before the baseline works;
a second scientific domain. Phase-2 ideas are listed, and fenced off, in
[DEVELOPMENT_PLAN §9](DEVELOPMENT_PLAN.md#9-expansion-plan).

## 8. Stakeholders

| Stakeholder | Interest | What they need from MIRAGE-Bio |
|---|---|---|
| Hackathon judges | Scientific soundness, clarity, working system | A clear question, honest claims, a live or replayed demo, reproducible numbers |
| Project team | Shipping by Sunday 4 October 2026, 14:45 BST | Unambiguous specification, small task list, stop rules |
| Autonomous-science researchers | Evaluation methodology for experimental choice | Transparent environment design, deterministic scoring, saved transcripts |
| Future self-driving-lab researchers | Instrument-aware agents | A worked example of measurement-confounded inference and its control |

## 9. Scientific model

The model has two strictly separated layers. Equations and parameter values are in
[DESIGN §5–§8](DESIGN.md#5-mathematical-design).

### 9.1 Latent biology (hidden)

The culture's biomass $X(t)$ is expressed in **OD-equivalent units (ODeq)**: the
reading a perfectly linear reference instrument would give. Biomass follows a
Richards (generalised logistic) curve with growth rate $r$, inoculum $X_0$,
carrying capacity $K$ and transition sharpness $\nu = 8$, which gives a near-exponential
phase followed by a fairly abrupt entry into stationary phase (A-005, A-006).

The two hidden conditions differ **only** in $K$:

| Condition | Carrying capacity | Meaning |
|---|---|---|
| `BIOLOGICAL_PLATEAU` | $K = \kappa S$, $\kappa \in [0.80, 0.90]$ | The culture stops growing inside the instrument's useful range. |
| `MEASUREMENT_ARTIFACT` | $K = \lambda S$, $\lambda \in [3, 5]$ | The culture keeps growing to 3–5× the instrument's saturation scale. |

### 9.2 Measurement (the only thing the agent sees)

A reading is $y = f(X/d) + \varepsilon$, where $d \ge 1$ is the dilution factor, $f$ is
a smooth saturating response that is approximately the identity at low density and
approaches a ceiling near the saturation scale $S$, and $\varepsilon$ is Gaussian
noise (A-008, A-010). $S$ is a property of the instrument, varies between episodes,
is drawn independently of the condition, and is not disclosed to the agent (A-003,
A-009).

### 9.3 Why passive data are ambiguous

Because the growth sharpness equals the assay sharpness (A-017), the observed passive
curve in **both** conditions is exactly a Richards curve. It differs between conditions
only in its apparent plateau level $K'$. With $S$ unknown and variable, $K'$ carries
little information about the condition. A classifier with full knowledge of the
simulator therefore has a hard ceiling on passive accuracy. The analytic Bayes ceiling
is estimated at ≈ 0.58 ([GATE0_SPEC §5](GATE0_SPEC.md#5-passive-baseline-strength)). If $S$ were fixed and known, the conditions would be
perfectly separable by plateau level ([ADR-007](ADR/ADR-007-matched-sharpness-unknown-saturation.md)).

### 9.4 Why dilution resolves it

Diluting a late-stage aliquot by an adequate factor (1:10 is adequate for every
scenario in the frozen distribution) brings the presented biomass into the
proportional range. The back-corrected estimate $d \cdot y$ then recovers $X$ to within
5 % plus noise. Distinguishing the explanations needs less than that: any late
dilution that Gate 0 classifies as diagnostic separates them, even when it is too
weak to reconstruct the biomass accurately (§14, Q1).

| | Passive apparent plateau | Back-corrected late biomass (adequate dilution) | Ratio |
|---|---|---|---|
| `BIOLOGICAL_PLATEAU` | $\approx K$ (compression 1.9–4.4 %) | $\approx K$ | 1.02–1.05 (noise-free) |
| `MEASUREMENT_ARTIFACT` | $\approx S$ | $\approx \lambda S$ | ≈ 3–5 |

### 9.5 Correction of the earlier causal-design flaw

An earlier draft placed Condition A's carrying capacity far beyond the assay's useful
range while using a strongly saturating response in both conditions. Condition A was
therefore also heavily distorted by the measurement, so dilution would have revealed
"hidden" biomass in both conditions and the causal contrast was muddled. That
parameterisation (including any `S·tanh(X/S)` response with $K_A = 2$) is withdrawn.
The corrected design requires:

- **Passive observation.** `BIOLOGICAL_PLATEAU`: true biomass ≈ observed plateau.
  `MEASUREMENT_ARTIFACT`: true biomass ≫ observed plateau.
- **After adequate dilution.** `BIOLOGICAL_PLATEAU`: corrected estimate ≈ the
  passive plateau. `MEASUREMENT_ARTIFACT`: corrected estimate ≈ 3–5× the passive
  plateau.

These properties are enforced by SVR-001 to SVR-003 and SVR-007 (§13) and verified at
Gate 0.

A second finding from design verification: with plain logistic growth ($\nu = 1$), a
trustworthy Condition A cannot be made passively ambiguous. Logistic deceleration
begins at $K/2$, while a saturating assay produces an abrupt corner. A model-free
classifier separates the two at ≈ 0.82–0.90 accuracy across design-time runs. This is
why the growth abstraction is Richards with $\nu = 8$
([ADR-007](ADR/ADR-007-matched-sharpness-unknown-saturation.md)).

### 9.6 Benchmark-construction statement

MIRAGE-Bio intentionally constructs two hidden worlds whose passive observations are
difficult to distinguish. This is an **adversarial identifiability benchmark**. It is
not a claim that these exact parameter combinations are representative of typical
microbial cultures or instruments. Condition A's placement near the top of the
useful range, and the matched growth and assay sharpness, are deliberate and
disclosed (A-017, A-018,
[ADR-007](ADR/ADR-007-matched-sharpness-unknown-saturation.md)). Gate 0 checks that
the construction holds over a neighbourhood of parameters, not at one point
([GATE0_SPEC](GATE0_SPEC.md), G0-G).

### 9.7 Ecological realism versus benchmark validity

The environment is **valid as a benchmark** if:

- it models a scientifically plausible measurement pathology qualitatively
  (A-002 to A-004);
- its causal structure is coherent;
- the ambiguity is demonstrated quantitatively;
- the intervention resolves the ambiguity;
- claims remain limited to the controlled environment (§18).

It need not reproduce the full ecology or physiology of a real organism, or the
optics of a real plate reader. Realism criticism is answered by these validity
conditions, not by adding biological detail.

## 10. Scientific assumptions

Labels: **FACT**: supported by microbiology or assay practice. **MODEL ASSUMPTION**:
a chosen abstraction or value. **SIMPLIFICATION**: a real effect deliberately
omitted. **DESIGN DECISION**: a choice made to create a valid evaluation, with no
claim about nature.

| ID | Statement | Label |
|---|---|---|
| A-001 | OD600 is a light-attenuation (mainly scattering) proxy for culture density; it is not a viable-cell count. | FACT |
| A-002 | OD readings become sublinear in cell density at sufficiently high density. | FACT |
| A-003 | The onset of nonlinearity depends on instrument, path length, wavelength, organism and medium. No universal OD threshold exists, so the proportional range must be established empirically. | FACT |
| A-004 | Diluting a dense sample into the proportional range and multiplying by the dilution factor is standard practice for estimating dense-culture density. | FACT |
| A-005 | Batch cultures limited by a single nutrient can enter stationary phase fairly abruptly on exhaustion. Richer media support higher final densities. (Qualitative.) | FACT |
| A-006 | Latent biomass follows a Richards curve, $dX/dt = rX[1-(X/K)^\nu]$, with $\nu = 8$ in both conditions. Logistic growth is the special case $\nu = 1$. | MODEL ASSUMPTION |
| A-007 | Biomass is expressed in ODeq, the reading of a perfectly linear reference instrument. | MODEL ASSUMPTION |
| A-008 | The assay transfer function is $f(x) = x\,[1+(x/S)^n]^{-1/n}$ with $n = 8$. This is not a calibrated model of any real instrument. | MODEL ASSUMPTION |
| A-009 | The instrument saturation scale $S$ is unknown to the agent and varies across episodes ($\log S$ uniform on $[\log 0.5, \log 2.0]$ ODeq), independently of the condition. It is sampled once at episode creation and is fixed for every measurement in that episode. | MODEL ASSUMPTION |
| A-010 | Measurement noise is Gaussian, independent between readings, with $\sigma(y) = 0.003 + 0.02\,y$. Readings are reported to 4 decimal places and are not clipped at zero. | MODEL ASSUMPTION |
| A-011 | Growth parameters: $r \sim U[0.6, 0.9]\ \mathrm{h^{-1}}$, $\log X_0 \sim U[\log 0.005, \log 0.02]$ ODeq. | MODEL ASSUMPTION |
| A-012 | Dilution is exact (no pipetting error) and the diluent contributes no signal. | SIMPLIFICATION |
| A-013 | Aliquots were retained hourly from 0 to 18 h and are identical to the culture state at the time of withdrawal. Withdrawal does not perturb the culture, and diluted aliquots do not regrow before reading. | SIMPLIFICATION |
| A-014 | No lag phase, death phase, settling, clumping, morphology or cell-size change, evaporation, or medium background. | SIMPLIFICATION |
| A-015 | One culture per episode. Variability between episodes comes only from the sampled parameters. | SIMPLIFICATION |
| A-016 | The conditions differ only in $K$ ($K = \kappa S$ vs $K = \lambda S$). All other parameters share distributions. | DESIGN DECISION |
| A-017 | Growth sharpness $\nu$ equals assay sharpness $n$, so both conditions yield passive curves in the same parametric family. | DESIGN DECISION |
| A-018 | `BIOLOGICAL_PLATEAU` places $K$ at $0.80$–$0.90\,S$: inside the useful region but near its top. This is a scenario-selection choice that creates genuine ambiguity, not a claim that real cultures plateau near instrument limits. | DESIGN DECISION |
| A-019 | The **useful region** of the assay is defined as compression $1 - f(x)/x \le 5\%$ (i.e. $x \le 0.9187\,S$), together with a noise-free reading of at least $10\,\sigma_{\text{abs}}$. In `scenario-v1` that bound is 0.03, where the per-replicate relative SD is 12 %. Both are benchmark design thresholds derived from the simulator's response and noise model, not instrument facts. The useful region defines **quantitative reconstruction adequacy** (Q1). It is **not** required for a diagnostic control (M2). | DESIGN DECISION |
| A-020 | The simulator configuration is the authoritative ground truth ([ADR-003](ADR/ADR-003-hidden-ground-truth.md)). | DESIGN DECISION |
| A-021 | The late-stage diagnostic window is the fixed clock-time interval $t \in [12, 18]$ h, defined on visible time only. It does not depend on hidden state. In every `scenario-v1` episode, the apparent plateau begins at least 2 h before 12 h. | DESIGN DECISION |
| A-022 | A late, diluted measurement counts as **diagnostic** (M2) if its dilution factor lies in the **diagnostic dilution set** $D_{\text{diag}} = [d_{\min}, d_{\max}]$. Gate 0 freezes this set (G0-H) as the dilution factors whose single-measurement discriminability between the two conditions (AUROC of the ratio statistic over the scenario prior) is ≥ 0.95, under the least favourable setting (single replicate, worst time in the window). The classification depends only on the visible action, never on the episode's hidden state. | DESIGN DECISION |

## 11. Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | **Growth simulation.** The system must compute latent biomass $X(t)$ in closed form for a given growth configuration, deterministically. |
| FR-002 | **`BIOLOGICAL_PLATEAU` condition.** The scenario generator must set $K = \kappa S$ with $\kappa$ drawn from $[0.80, 0.90]$. |
| FR-003 | **`MEASUREMENT_ARTIFACT` condition.** The scenario generator must set $K = \lambda S$ with $\lambda$ drawn from $[3.0, 5.0]$. |
| FR-004 | **Shared nuisance parameters.** $S$, $r$ and $X_0$ must be drawn from condition-independent distributions before any condition-specific draw, so that the same seed yields the same $S$, $r$, $X_0$ in either condition. |
| FR-005 | **Assay measurement.** For presented biomass $x$, the assay must return $f(x)$ plus noise as defined in A-008/A-010, one reading per replicate, rounded to 4 decimal places. |
| FR-006 | **Passive history.** At episode start the agent must receive 19 undiluted single readings at $t = 0, 1, \dots, 18$ h, free of charge. |
| FR-007 | **Aliquot dilution.** The agent must be able to request a reading of an aliquot from any whole hour $t \in \{0, \dots, 18\}$ diluted by $d \in [1, 100]$. Presented biomass is $X(t)/d$; the culture is unaffected. |
| FR-008 | **Finite budget.** Each episode must have a budget of 6 replicate-readings. Each accepted replicate costs 1. Requests exceeding the remaining budget must be rejected without charge. |
| FR-009 | **Request validation.** Invalid requests (time outside the grid, $d$ outside $[1, 100]$, replicates outside 1–3, malformed input) must be rejected with an error message and no charge. |
| FR-010 | **Agent interaction.** Agents must interact only through three tools: `measure_od`, `declare_state` and `submit_diagnosis`. An episode must end after at most 12 agent turns. |
| FR-011 | **Diagnosis submission.** `submit_diagnosis` must accept a label (`GROWTH_STOPPED` or `GROWTH_CONTINUED`), a probability that growth continued, an optional late-biomass estimate and a rationale, and must end the episode. |
| FR-012 | **Belief declaration (optional).** `declare_state` must record free-text notes and a probability at no budget cost. Its use is optional and never required by the scored prompt. |
| FR-013 | **Deterministic scoring.** The evaluator must compute per-episode scores and M1–M4 from the saved episode record and hidden configuration only, without any LLM. |
| FR-014 | **Episode persistence.** Every episode, including failed ones, must be saved as one self-contained JSON record (configuration, configuration hash, passive data, all events, diagnosis, audit, scores, software versions, and the LLM transcript where applicable). |
| FR-015 | **Experiment runner.** The runner must execute a given agent over a given episode matrix and write records plus a summary. The summary must be recomputable from records alone. |
| FR-016 | **Offline replay.** A saved episode must be replayable step by step with no network access and no API key. |
| FR-017 | **Gate 0.** A script must evaluate every check in [GATE0_SPEC §4](GATE0_SPEC.md#4-quantitative-acceptance-criteria), emit every output in [GATE0_SPEC §3](GATE0_SPEC.md#3-required-gate-0-outputs) (including `summary.json`), and record the hash of the frozen scenario configuration. |
| FR-018 | **Baselines.** `GoodScientist` and `PassiveBayes` must run through the same runner and evaluator as the AI scientist. |
| FR-019 | **Minimal scored prompt.** The scored prompt must state the task, tools and budget only. It must not instruct the agent to enumerate competing hypotheses or explanations, must not require `declare_state`, and must not name the hidden conditions or hint at the intended control (§11.1). |

### 11.1 Minimal prompt policy

Requiring the agent to "first state alternative hypotheses" would scaffold exactly the
capability being evaluated: recognising that alternatives exist. The scored prompt
therefore does not ask for hypotheses. `declare_state` remains available, optional and
logged when used, which is useful for the demo. The agent must decide for itself
whether alternatives need consideration. Agent-facing diagnosis labels are
`GROWTH_STOPPED` and `GROWTH_CONTINUED`. The internal names `BIOLOGICAL_PLATEAU` and
`MEASUREMENT_ARTIFACT` never appear on any agent-visible surface.

## 12. Non-functional requirements

| ID | Requirement | Acceptance |
|---|---|---|
| NFR-001 | **Deterministic and reproducible.** Same configuration, seed and agent actions must give identical results. | Two runs of a scripted agent produce byte-identical records, excluding the `run_meta` block (T-017). |
| NFR-002 | **Auditable.** Every reported number must be recomputable from committed records by one command. | `summarize` reproduces committed `summary.json` exactly (T-023). |
| NFR-003 | **Simple.** No agent framework, no database, no service. Runtime dependencies are limited to `numpy`, `matplotlib`, `pydantic`, `anthropic`; `pytest` for development. | Dependency review at MS6. |
| NFR-004 | **Local-first.** Everything runs on a laptop. The only network use is the Anthropic API during live agent runs. | Gate 0, baselines, tests and replay run offline. |
| NFR-005 | **Isolated hidden state.** The agent must have no code path or prompt content that exposes hidden configuration. | T-012 (import scan, prompt-leakage scan). |
| NFR-006 | **Offline demo.** The demo must run without network or API key. | T-018; rehearsal with Wi-Fi disabled. |
| NFR-007 | **Low runtime cost.** Simulating plus scoring 1,000 scripted episodes takes < 60 s. Gate 0 takes < 5 min. A 30-episode LLM matrix is expected to cost ≈ $5–15 (to be measured). | Timed in MS1/MS3. |
| NFR-008 | **Pinned environment.** Python ≥ 3.11. Dependency versions pinned in `pyproject.toml`. Versions recorded in every record. | Record inspection. |
| NFR-009 | **Fail loudly.** Invalid configurations, schema violations and inconsistent state must raise, never be silently coerced. | Unit tests on validators. |

## 13. Scientific-validity requirements

These requirements protect the causal contrast. They are verified before LLM
integration by Gate 0 and by tests in [TEST_PLAN](TEST_PLAN.md). The criteria below are
summaries. The authoritative criteria, threshold types (benchmark design threshold vs
simulator choice) and outputs are in [GATE0_SPEC §4](GATE0_SPEC.md#4-quantitative-acceptance-criteria).
The thresholds are fixed now and must not be relaxed after seeing results.

| ID | Requirement | Quantitative acceptance criterion | Verified by |
|---|---|---|---|
| SVR-001 | **Passive ambiguity.** Passive trajectories from the two conditions must not be reliably separable. | (i) Analytic Bayes ceiling (accuracy given the exact apparent plateau $K'$, noise-free) ≤ 0.65. (ii) `PassiveBayes`, the strongest implemented passive baseline: balanced accuracy ≤ 0.65 on 1,000 held-out episodes per condition. (iii) 15-nearest-neighbour classifier on log-transformed full trajectories (1,000 train + 1,000 test per condition) ≤ 0.65. Design-time reference: 0.58 / 0.57 / 0.55. | G0-A, T-008 |
| SVR-002 | **Diagnostic separability.** An adequate late-stage dilution must yield strongly different corrected estimates. | Reference protocol ($t = 18$ h, $d = 10$, 3 replicates): ≥ 99 % of `MEASUREMENT_ARTIFACT` episodes have $R = \hat C/\hat P \ge 2.5$, and `GoodScientist` accuracy ≥ 0.98 over 1,000 episodes per condition. | G0-C, T-010, T-015 |
| SVR-003 | **Biological-condition trustworthiness.** `BIOLOGICAL_PLATEAU` must not rely on assay saturation. | (i) Noise-free compression at $K$ ≤ 5 % in 100 % of sampled scenarios. (ii) Reference protocol: ≥ 95 % of episodes have $\lvert R - 1\rvert \le 0.15$ and $\lvert \hat C/K - 1\rvert \le 0.15$. | G0-B, T-004, T-009 |
| SVR-004 | **Hidden-state isolation.** No hidden quantity (condition, $K$, $\kappa$, $\lambda$, $S$, $r$, $X_0$, noise-free values, seed) may reach the agent, and no prompt or tool description may contain forbidden terms. | Import scan and prompt-leakage scan pass. | T-012 |
| SVR-005 | **No LLM in the evaluation path.** | Evaluator and runner `summarize` import no LLM client. | T-012, code review |
| SVR-006 | **Same assay model in both conditions; stable instrument.** Same function, $n$, noise model and resolution. $S$ is drawn from the same distribution independently of the condition ($P(S \mid H_A) = P(S \mid H_B)$), is sampled once per episode, and never changes within an episode. | Same seed gives identical $S$, $r$, $X_0$ under both conditions. KS statistic of $\log S$ between conditions ≤ 0.03. $S$ is constant across all measurements of an episode. A single assay code path is used. | G0-F, T-024, T-025, T-026 |
| SVR-007 | **Diagnostic measurement must be late-stage and informative.** An early sample with a naturally low reading is not a diagnostic control. The late-stage criterion must not depend on hidden state. | A measurement counts only if it comes from the fixed window $t \in [12, 18]$ h (A-021). Window validity: in 100 % of scenarios, $t_{95} + 2\text{ h} \le 12$ h; in 100 % of `MEASUREMENT_ARTIFACT` scenarios, $X(12\text{ h}) \ge 2.5\,K'$. | G0-C, T-005, T-021, T-027 |
| SVR-008 | **A 1:2 dilution is insufficient for accurate latent-biomass reconstruction, even though it may still be diagnostically discriminating** (desirable, non-blocking). Its diagnostic status is decided like any other dilution, by the frozen diagnostic set (SVR-011); design-time AUROC is 1.00. | With $d = 2$ in `MEASUREMENT_ARTIFACT`, ≥ 95 % of episodes present biomass outside the useful region and have $\hat C/K \le 0.75$. | G0-D (D3) |
| SVR-009 | **Undiluted and early interventions are non-diagnostic.** Undiluted late re-measurement and early diluted samples must not discriminate the conditions beyond passive level. | Discriminability $\max(\text{AUROC}, 1-\text{AUROC})$ of the ratio statistic ≤ 0.65 for $(t = 18, d = 1)$ and $(t = 3, d = 10)$. | G0-D (D1, D2) |
| SVR-010 | **Robustness** (non-blocking). The construction must hold in a neighbourhood of `scenario-v1`, not at a single point. | GATE0_SPEC G0-G perturbations keep passive ambiguity, Condition-A trustworthiness and diagnostic separation, or the boundary is documented. | G0-G |
| SVR-011 | **Frozen diagnostic action set.** M2 must be operationalised from Gate 0, not from LLM judgement or from biomass-reconstruction accuracy. | Gate 0 freezes $D_{\text{diag}}$ (A-022). It must be a contiguous interval on the evaluation grid that contains $d = 10$ and excludes $d = 1$, recorded in `summary.json` under the scenario hash. | G0-H, T-032 |

## 14. Metrics

Metrics are computed per episode and aggregated per agent configuration, overall and
per condition. Exact computations are in [DESIGN §15](DESIGN.md#15-evaluation).

Two properties of a measurement are kept separate:

- **Diagnostic sufficiency (M2):** does the experiment provide evidence that
  distinguishes `GROWTH_STOPPED` from `GROWTH_CONTINUED`?
- **Quantitative reconstruction quality (Q1):** does it place the presented sample
  inside the assay's useful region, so that back-correction gives an accurate
  estimate of the latent biomass?

Reconstruction is scientifically useful, but a diagnosis is justified without it
whenever the experiment already distinguishes the competing worlds.

A measurement is a **diagnostic control** if and only if all of the following hold:

1. it was accepted by the environment;
2. it was obtained before the diagnosis;
3. it is late-stage: the aliquot comes from the fixed visible window $t \in [12, 18]$ h
   (A-021);
4. it is diluted: $d > 1$;
5. its dilution factor lies in the Gate-0-frozen diagnostic set
   $D_{\text{diag}} = [d_{\min}, d_{\max}]$ (A-022, SVR-011).

There is **no** useful-region requirement for M2. The classification depends only on
the visible action $(t, d)$ and the frozen Gate 0 result. It never depends on an LLM,
on the agent's interpretation, or on the episode's hidden state, so the same action
counts identically in both conditions.

A measurement is **reconstruction-adequate** (Q1) if it satisfies clauses 1–4 above
**and** lies in the useful region (A-019): presented biomass $X(t)/d \le 0.9187\,S$
and noise-free reading $\ge 10\,\sigma_{\text{abs}} = 0.03$.

Key example (design-time reference, GATE0_SPEC §6):

| Late measurement | Diagnostic separation (M2) | Accurate biomass reconstruction (Q1) |
|---|---|---|
| 1:2 dilution | **Yes** (AUROC 1.00) | **No** (`MEASUREMENT_ARTIFACT` recovers ≈ 50 % of true biomass) |
| 1:10 dilution | **Yes** (AUROC 1.00) | **Yes** (within ≈ 7 % in both conditions) |
| Undiluted | No (AUROC 0.50; not diluted) | No |

| ID | Metric | Definition |
|---|---|---|
| M1 | Diagnosis accuracy | Fraction of episodes whose submitted label maps to the true condition. A missing diagnosis counts as incorrect. |
| M2 | Diagnostic-control rate | Fraction of episodes in which the agent performed, before diagnosis, at least one diagnostic control: an accepted, late, diluted measurement whose dilution factor Gate 0 demonstrated to be diagnostically discriminating ($d \in D_{\text{diag}}$). |
| M3 | Justified accuracy | Fraction of episodes that are both correct (M1) and contain a diagnostic control (M2). |
| M4 | Experimental cost | Mean replicate-readings consumed per episode (report median and maximum too). |
| M5 (stretch, non-blocking) | Experiment diagnosticity / selection efficiency | How informative the chosen experiment was compared with the alternatives: matched-twin single-outcome AUROC $D(a)$ ([BENCHMARK_METHODOLOGY §3](../BENCHMARK_METHODOLOGY.md#3-experiment-diagnosticity)). The MVP ships without it. |
| Q1 (secondary, descriptive) | Quantitative reconstruction adequacy | Fraction of episodes with at least one reconstruction-adequate measurement. Reported per condition; not part of M3 and not a headline metric. |
| O1 (optional) | Belief calibration | Brier score of the final `p_growth_continued`. |
| O2 (optional) | Rounds to diagnosis | Number of `measure_od` calls before diagnosis. |

Label mapping: `GROWTH_STOPPED` ↔ `BIOLOGICAL_PLATEAU`; `GROWTH_CONTINUED` ↔
`MEASUREMENT_ARTIFACT`. The agent never sees the condition names
([DESIGN §9](DESIGN.md#9-agent-tool-api)).

## 15. Experiment requirements

| ID | Requirement |
|---|---|
| ER-001 | Evaluation matrices must be balanced across the two conditions and interleaved so that any prefix of a run is approximately balanced. |
| ER-002 | Evaluation seeds must be fixed in advance in a committed matrix file and kept disjoint from development seeds. Prompt development must use development seeds only. |
| ER-003 | Baselines must be run on the same evaluation episodes as the AI scientist, and additionally on 1,000 episodes per condition for precise reference values. |
| ER-004 | Every episode must be saved, including failures. API failures and refusals are reported separately from agent errors. |
| ER-005 | The scenario configuration hash and the prompt version must be recorded in every record. Changing either after the evaluation freeze invalidates comparability. |
| ER-006 | Results must be reported as exact counts with Wilson 95 % intervals, overall and per condition ([EXPERIMENT_PLAN](EXPERIMENT_PLAN.md)). |
| ER-007 | Once Gate 0 freezes the scenario parameters, agent outcomes must never be used to change them. If the benchmark proves easy or hard for the agent, that is reported, not tuned away. |

## 16. Demo requirements

| ID | Requirement |
|---|---|
| DR-001 | The demo must be an offline replay of saved episode records ([ADR-006](ADR/ADR-006-offline-demo-replay.md)). |
| DR-002 | It must show, in order: the passive data; the agent's declared state, if it used `declare_state`; the experiment chosen; the new evidence; the diagnosis; the ground-truth reveal and score. |
| DR-003 | It must include one `BIOLOGICAL_PLATEAU` and one `MEASUREMENT_ARTIFACT` episode, ideally the matched demo pair whose passive curves are identical. |
| DR-004 | It must fit in ≤ 3 minutes. |
| DR-005 | Every number shown must come from a saved record or the committed results summary. |
| DR-006 | It must show the results table comparing the AI scientist with both baselines. |

## 17. Success criteria

### 17.1 Gate 0 success (blocking; no LLM work is merged before it)

Every blocking criterion in [GATE0_SPEC §4](GATE0_SPEC.md#4-quantitative-acceptance-criteria)
passes (G0-A, G0-B, G0-C, G0-D1/D2, G0-E, G0-F, G0-H). Non-blocking G0-D3 and G0-G
are reported. The diagnostic set $D_{\text{diag}}$ is frozen with the scenario hash. Every output in [GATE0_SPEC §3](GATE0_SPEC.md#3-required-gate-0-outputs)
and the frozen `scenario_v1.json` are committed.

### 17.2 MVP success

- Gate 0 passed.
- `GoodScientist`: M3 ≥ 0.95. `PassiveBayes`: M1 ≤ 0.65, M2 = 0.
- The Claude adapter completes at least 10 evaluation episodes (5 per condition)
  with complete records.
- Evaluator and summary are deterministic and recomputable from records.
- The offline replay works for one episode per condition.

### 17.3 Strong hackathon success

- 30 Claude evaluation episodes (15 per condition) with M1–M4, Wilson intervals and
  per-condition breakdown, compared with both baselines.
- A demo replay of the matched pair, with interpretation consistent with
  [EXPERIMENT_PLAN §9](EXPERIMENT_PLAN.md#9-interpretation-matrix).
- Clear limitations stated.

### 17.4 Failure-to-ship conditions

Any one of the following means LLM results must **not** be presented as findings:

- Gate 0 not passed with the pre-registered thresholds.
- A hidden-state leak is found and the affected episodes cannot be excluded and re-run.
- Any LLM call in the scoring path.
- Reported numbers that cannot be regenerated from committed records.

If Gate 0 passes but the LLM integration does not work by the evaluation freeze, the
submission falls back to: Gate 0 evidence, both baselines, and the offline replay of
scripted episodes, with the AI-scientist result explicitly marked as not obtained.

## 18. Scientific communication constraints

The team must not claim, in the repository, slides or verbal pitch:

- that simulated outcomes are biological discoveries or say anything about real
  organisms;
- any universal OD threshold for nonlinearity (A-003 says none exists; the
  simulator's $S$ values are model choices);
- that the model represents comprehensive bacterial physiology or any real
  instrument;
- generalisation from this one scenario to "AI scientists" in general, to other
  assays, or to real laboratories;
- method novelty for the agent. Any novelty is in the evaluation and system design;
- that LLM behaviour is reproducible by seed. LLM runs are reproducible only through
  saved transcripts;
- that `PassiveBayes` or any implemented classifier is optimal. The analytic ceiling
  is the bound;
- that over-dilution has a discrimination optimum (a U-shaped curve) unless Gate 0
  demonstrates one. The design-time reference shows that over-dilution costs
  precision and reconstruction adequacy (Q1), not discriminability.

Allowed and forbidden claims about experimental results are listed in
[EXPERIMENT_PLAN §10](EXPERIMENT_PLAN.md#10-claims).
