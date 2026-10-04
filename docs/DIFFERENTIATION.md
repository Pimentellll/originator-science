# MIRAGE: differentiation and novelty boundary

| Field | Value |
|---|---|
| Role | What the contribution is, and what is **not** claimed |
| Related | [MIRAGE](MIRAGE.md) · [Baseline V1 analysis](evaluation/BASELINE_V1.md) |

## 1. A crowded space

Autonomous scientific agents, AI-scientist pipelines, self-driving laboratories, Bayesian experimental design,
active learning and agent benchmarks already exist. MIRAGE does not present any of the following as new:

- hypothesis generation by language models;
- tool-using or experiment-running agents;
- scientific simulation;
- Bayesian optimal experimental design, expected information gain, or particle filtering / SMC;
- reinforcement learning for sequential decisions.

The repository contains **no systematic literature comparison**. What follows is a statement of design focus, not a
competitive claim.

## 2. Design focus

MIRAGE focuses on one question that most evaluations skip: *did the evidence the agent gathered justify the
decision it made?* The combination it provides is:

- a factorised, partially observed binder-rescue world with **compound failures** and a three-level failure
  hierarchy (molecule / experiment / biological model);
- **resource-constrained** experiment selection with **path dependence** (an SPR reading on an aggregated sample
  damages the instrument);
- a **hard trust boundary**: policies, the belief engine, the API, the UI and replay never see truth; a separate
  privileged evaluator does;
- an evaluator that scores **correct and justified separately**, and a documented set of reward-hacking probes;
- seeded, replayable episodes with a model-free replay;
- honest baselines, including a published result where the information-gain policy did **not** win.

## 3. What Baseline V1 changes about the story

It would be easy to pitch "information-gain planning rescues binders". The first published result does not support
that: FixedPipeline (74% justified) beat GreedyEIG (64% justified) on the identical 250 worlds. The contribution is a
benchmark that can say so, and that exposed why (see [BASELINE_V1](evaluation/BASELINE_V1.md)). Whether a long-horizon
planner helps under scarcity is the question the preregistered V2 poses; it has **not been answered**.

## 4. What is not claimed

- No wet-lab, structural, sequence-level or therapeutic claim, and no validated EGFR model.
- No claim that Lookahead or PPO outperform anything: neither has been evaluated.
- No claim that the particle posterior is converged (the B4A gate is unmet).
- No generality beyond this environment, these scenario semantics and these evaluator thresholds. Thresholds and the agent
  prior are versioned benchmark-engineering parameters, not biological facts.
- Never "first". No comparative claims about other systems unless evidence is committed to the repository.

## 5. The growth benchmark

MIRAGE-Bio v0.1 (the OD600 growth-plateau environment) is retained as the project's first environment. Its Gate 0
validation and 30-episode Claude run are real, committed, and scoped to that environment only
([mirage-bio/](mirage-bio/README.md)). They do not support any claim about binder rescue.
