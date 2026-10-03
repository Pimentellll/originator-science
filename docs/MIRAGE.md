# MIRAGE — Epistemic Stress Testing for Autonomous Scientists

| Field | Value |
|---|---|
| Status | Project framing (3 October 2026). Conceptual, not an implementation plan. |
| Scope | What MIRAGE is and is not. The only implemented environment is [MIRAGE-Bio](mirage-bio/ANALYSIS.md), and that is not yet built. |
| Related | [BENCHMARK_METHODOLOGY](BENCHMARK_METHODOLOGY.md) · [DIFFERENTIATION](DIFFERENTIATION.md) · [docs index](README.md) |

---

## 1. What MIRAGE is

MIRAGE is a controlled evaluation system for testing whether autonomous scientific
agents recognise when current observations are insufficient to support a
scientific conclusion, and whether they select experiments that resolve the
underlying ambiguity.

**Invariant.** An agent does not receive credit merely for reaching the correct
conclusion. MIRAGE evaluates whether the agent acquired evidence that actually
justified that conclusion.

The benchmark does not ask whether an AI scientist knows the answer. It places the
scientist in a situation where the answer is deliberately unknowable from current
evidence, and asks whether it knows what experiment would make the answer knowable.

## 2. The problem

Autonomous research systems can generate hypotheses, call scientific tools and
produce conclusions. Whether they reach a correct answer is not the hard question.
The hard question is whether they know:

- when the current evidence is insufficient;
- which alternative explanations remain;
- what evidence would distinguish them;
- whether the experiment they ran was actually diagnostic;
- what strength of conclusion the evidence supports.

A correct answer reached without discriminating evidence is a lucky or prior-driven
guess, and it will not transfer to situations where the prior is wrong. MIRAGE
separates the two.

## 3. The MIRAGE scientific loop

```text
Initial observation
        ↓
Multiple plausible explanations remain
        ↓
Agent recognises / fails to recognise ambiguity
        ↓
Agent chooses an experiment
        ↓
Experimental environment executes it
        ↓
New evidence
        ↓
Agent updates or fails to update
        ↓
Evidence-bounded conclusion
        ↓
Deterministic MIRAGE evaluation
```

**Central question.** When current evidence cannot identify the cause of an
observation, does the autonomous scientist choose an experiment that makes the
competing explanations distinguishable?

This is more precise than "can the agent do science?" and more substantive than
"can the agent detect false positives?"

Conceptual architecture. This describes roles, not code: there is no generic adapter
layer in the implementation.

```text
Scientific Agent
      │  experiment specification
      ▼
Experimental Environment      (hidden world + measurement process)
      │  evidence
      ▼
Scientific update             (agent-side)
      │  conclusion + full action log
      ▼
MIRAGE Evaluator              (knows the hidden world; deterministic; no LLM)
```

## 4. Evaluation philosophy

| Concept | Meaning in MIRAGE |
|---|---|
| **Observational ambiguity** | The initial observations are about equally probable under two or more distinct hidden worlds. A model-aware classifier cannot reliably tell them apart from the initial data. |
| **Competing causal worlds** | Hidden generative processes with different causal explanations of the same observation (e.g. "biology stopped" vs "the instrument stopped responding"). They are fully specified and known to the evaluator. |
| **Active disambiguation** | The agent acquires new evidence by choosing an intervention or measurement. Passive re-observation does not count. |
| **Diagnostic experiment** | An experiment whose outcome distribution differs substantially between the competing worlds. Diagnosticity is a property of the experiment and the worlds, judged by the evaluator, not by the agent's narrative. |
| **Evidence-bounded conclusion** | A conclusion whose strength does not exceed what the acquired evidence supports. |
| **Deterministic ground truth** | The hidden world is fixed by a frozen, hashed configuration and a seed. Scoring is a pure function of the hidden world and the action log. |

## 5. Experimental environments

An environment supplies hidden worlds, an observation process and an action space.
Conceptually it could be backed by any of the following. Only the first is used, and
only in MIRAGE-Bio.

| Backing | Examples | Status |
|---|---|---|
| Simulation-backed | Deterministic Python, numerical or GPU simulation of a scientific process plus its measurement | **MIRAGE-Bio v0.1 uses only this**, as a controlled computational environment |
| Model-backed | Protein or structure models, scientific ML surrogates | Conceptual only |
| Dataset-backed | Existing measurements, perturbation datasets, held-out data queried as "experiments" | Conceptual only |
| Physical laboratory | Instrumented wet-lab execution | Future possibility only. Out of scope. |

## 6. Evidence maturity (project philosophy, not MVP scoring)

| Level | Evidential status |
|---|---|
| E0 | Hypothesis or idea |
| E1 | Computational support |
| E2 | Independent in-silico replication |
| E3 | Direct experimental evidence |
| E4 | Independent experimental replication |

A MIRAGE-compatible scientific agent should not represent a claim as having stronger
evidential status than the experiments supporting it. This ladder is a guiding
principle and a possible future evaluation axis. It is **not** a requirement or
metric of MIRAGE-Bio v0.1.

## 7. First environment — MIRAGE-Bio

MIRAGE-Bio is a virtual microbiology laboratory. An agent sees an OD600-like growth
curve that rises and flattens. In the hidden world `BIOLOGICAL_PLATEAU` the culture
truly stops growing inside the instrument's useful range. In `MEASUREMENT_ARTIFACT`
it keeps growing to 3–5× beyond the instrument's saturation scale, and the nonlinear
reader hides the growth. The two worlds are constructed so that their passive curves
belong to the same parametric family. With the instrument's saturation scale unknown,
the design-time analytic passive ceiling is ≈ 0.58.

The agent can request diluted remeasurements of retained aliquots on a budget of six
readings, then answers `GROWTH_STOPPED` or `GROWTH_CONTINUED`. A late, adequately
diluted measurement separates the worlds. A deterministic evaluator scores accuracy,
whether a diagnostic control (an experiment that distinguishes the worlds) was
obtained, justified accuracy and cost.

Requirements: [mirage-bio/ANALYSIS.md](mirage-bio/ANALYSIS.md).
Scientific validation: [mirage-bio/GATE0_SPEC.md](mirage-bio/GATE0_SPEC.md).

## 8. What MIRAGE is not

- Not a generic autonomous researcher or "AI scientist".
- Not an LLM orchestration or agent framework.
- Not a wet-lab robotics platform.
- Not a false-positive checker.
- Not a hypothesis generator.
- Not a universal science platform or general workflow engine.
- Not a source of biological (or other scientific) discoveries. Its worlds are
  controlled constructions.

## 9. Future research directions (not development tasks)

Possible future environments that share the construction "observationally similar
worlds plus a diagnostic action":

- other assay artefacts;
- numerical artefacts (discretisation, convergence, precision);
- scoring-function artefacts (proxy metrics diverging from the target property);
- confounded datasets;
- multi-assay disagreement;
- incomplete hypothesis classes (the true world is outside the agent's initial list).

None of these is planned work. The binding rule is: **do not expand the
implementation until MIRAGE-Bio works end to end.**
