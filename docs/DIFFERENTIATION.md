# MIRAGE — Differentiation and Novelty Boundary

| Field | Value |
|---|---|
| Status | Positioning (3 October 2026) |
| Role | What the contribution is, what makes it distinctive, and what we do **not** claim |
| Related | [MIRAGE](MIRAGE.md) · [BENCHMARK_METHODOLOGY](BENCHMARK_METHODOLOGY.md) |

---

> **The benchmark does not ask whether the AI knows the answer. It places the AI in a
> situation where the answer is deliberately unknowable from current evidence, and
> asks whether the AI knows what experiment would make it knowable.**

## 1. A crowded space

Autonomous scientific agents, AI-scientist pipelines, self-driving laboratories,
experiment-selection and Bayesian experimental-design methods, causal-discovery
environments and agent benchmarks already exist. None of the following is new, and
MIRAGE does not present them as new:

- hypothesis generation by language models;
- tool-using or experiment-running agents;
- scientific simulation;
- active learning and optimal experimental design;
- reasoning about measurement error and instrument nonlinearity.

The repository contains no systematic literature comparison. The positioning below
is therefore stated as a design focus, not as a competitive claim.

## 2. Differentiation thesis

MIRAGE focuses specifically on **epistemic disambiguation under observational
equivalence**. It constructs controlled scientific worlds that initially support
multiple explanations, then evaluates whether the agent selects evidence that
actually separates those explanations.

The contribution is the combination of:

- deliberately paired ambiguous worlds, with ambiguity demonstrated quantitatively;
- explicit hidden scientific ground truth;
- active experiment selection under a budget;
- counterfactual experiment scoring (the same experiment evaluated in each
  competing world);
- evidence-aware evaluation: justified accuracy rather than answer accuracy alone;
- eventually, claim/evidence maturity boundaries ([MIRAGE §6](MIRAGE.md#6-evidence-maturity-project-philosophy-not-mvp-scoring)).

## 3. What would make MIRAGE generic

MIRAGE loses its identity if it is pitched as:

- "an AI research agent";
- "an automated hypothesis generator";
- "an agent that runs experiments";
- "a false-positive checker";
- "a generic science workflow engine".

These describe the **thing being evaluated**, or adjacent tools. They do not describe
MIRAGE.

## 4. Creative edge

The user-facing insight is the inversion in the quote at the top. Most evaluations
reward knowing the answer. MIRAGE makes the answer unknowable from the current
evidence, by construction and with proof, and rewards knowing how to make it
knowable.

The MIRAGE-Bio demo shows this in one picture: two identical OD curves; underneath,
one culture stopped and the other kept growing to 4×. One late, diluted measurement
reveals which is which.

## 5. Technical edge

| Element | What it provides |
|---|---|
| Controlled non-identifiability | Passive ambiguity is a measured property (analytic Bayes ceiling plus strong classifiers), not an impression ([BENCHMARK_METHODOLOGY §1](BENCHMARK_METHODOLOGY.md#1-paired-worlds-controlled-non-identifiability)) |
| Counterfactual worlds | Each experiment can be evaluated in the competing world (matched twin) |
| Experiment diagnosticity | Experiment quality is scored separately from answer correctness (M5, stretch) |
| Deterministic evaluator | No LLM judge; every number recomputable from saved records |
| Active evidence acquisition | Only evidence the agent chose and obtained counts toward justification |
| Claim/evidence alignment | Conclusions should not exceed the evidence: M3 now, maturity ladder later |

## 6. MIRAGE-Bio as the proof of concept

During a hackathon, one environment with a proven construction is worth more than
six shallow ones.

- MIRAGE-Bio comes with an analytic ambiguity argument (exact passive-family
  equivalence), quantitative Gate 0 criteria, robustness checks, baselines that
  bracket performance, and hidden-state isolation tests.
- Shallow environments without such validation could be solved by surface cues or
  passive guessing, and would weaken every claim.
- Breadth is explicitly future work ([MIRAGE §9](MIRAGE.md#9-future-research-directions-not-development-tasks)).

## 7. Novelty boundary

MIRAGE does **not** claim to have invented:

- active experimentation or optimal experimental design;
- causal reasoning or causal discovery;
- measurement-error or assay-nonlinearity analysis;
- scientific agents, AI scientists or self-driving labs.

The contribution is a **benchmark and evaluation construction, and a systems
combination**: paired observationally equivalent worlds, hidden ground truth, active
evidence acquisition and evidence-aware deterministic scoring, demonstrated in one
carefully validated environment.

Wording rules:
- Never say "first".
- Make no comparative claims about other systems unless evidence is committed to the
  repository.
- Results apply only to MIRAGE-Bio `scenario-v1` and the agent configurations
  actually run.
