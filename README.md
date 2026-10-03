# MIRAGE

**A stress-testing environment for autonomous scientists. It asks whether they know
when evidence is insufficient, and what experiment would make the answer
knowable.**

MIRAGE is a controlled evaluation system for testing whether autonomous scientific
agents recognise when current observations are insufficient to support a scientific
conclusion, and whether they select experiments that resolve the underlying
ambiguity. An agent gets no credit merely for reaching the correct conclusion.
MIRAGE evaluates whether the agent acquired evidence that actually justified it.
Built for the Originator track at the London AI x Science Hackathon.

## The idea

Construct hidden scientific worlds that are observationally hard to distinguish,
let the agent choose experiments, and score the quality of the evidence it acquires
as well as its final answer.

```text
Initial observation ─► multiple explanations remain ─► agent chooses an experiment
   ─► environment executes it ─► new evidence ─► agent updates (or not)
   ─► evidence-bounded conclusion ─► deterministic MIRAGE evaluation
```

> The benchmark does not ask whether an AI scientist knows the answer. It places the
> scientist in a situation where the answer is deliberately unknowable from current
> evidence, and asks whether it knows what experiment would make it knowable.

## MIRAGE-Bio, the first environment

**Is late biomass at the level the undiluted readings indicate, or higher?**

An AI agent receives an OD600-like bacterial growth curve that rises and flattens.
- In the hidden world `BIOLOGICAL_PLATEAU`, the culture genuinely stops growing
  inside the reader's useful range.
- In `MEASUREMENT_ARTIFACT`, it keeps growing 3–5× beyond that range, and the
  reader's nonlinear response hides the growth.

The passive curves are constructed to be quantitatively ambiguous. The agent can
request diluted remeasurements of retained aliquots on a budget of six readings, then
answers `BIOMASS_AS_READ` if late biomass is at the level the undiluted readings
indicate, or `BIOMASS_ABOVE_READING` if it is higher.

```text
   HIDDEN (simulator)                        │  VISIBLE (agent)
                                             │
   growth model ──► latent biomass X(t)      │
                        │ aliquot at t,      │
                        │ dilute by d        │
                        ▼                    │
   OD assay  y = f(X(t)/d) + noise ──────────┼──► readings ──► AI scientist
                                             │                    │
                                             │   ◄── experiment (t, d, replicates)
                                             │   ◄── diagnosis
   deterministic evaluator ◄─────────────────┼── events + diagnosis
        │                                    │
        ▼                                    │
   episode record (JSON) ──► offline demo replay
```

The MVP: one apparent growth plateau, two hidden causes, one controlled experimental
environment, active evidence acquisition, deterministic ground truth.
- **Agents:** a Claude adapter plus two scripted baselines, `GoodScientist` and
  `PassiveBayes`.
- **Metrics:** M1 accuracy, M2 diagnostic-control rate, M3 justified accuracy,
  M4 cost. M5 diagnosticity is a stretch metric. Quantitative reconstruction
  adequacy (Q1) is reported separately.
- **Scale:** 10–30 evaluation episodes, and an offline replay demo.

## Why the benchmark is different

MIRAGE focuses on constructing intentionally ambiguous scientific worlds and scoring
the evidence-selection process, not only the final answer.
- Passive ambiguity is a measured property, checked by an analytic Bayes ceiling and
  strong classifiers.
- Each experiment can be evaluated against the competing world.
- Correct-but-unjustified answers are reported separately from justified ones.

The [differentiation document](docs/DIFFERENTIATION.md) sets out what is, and is not,
claimed.

## Current status

```text
General MIRAGE methodology      Documented
MIRAGE-Bio design               Documented (v0.1 specification)
Design-time numerical reference Committed (experiments/reference/); not Gate 0
Gate 0                          Passed and frozen (experiments/results/gate0/), under
                                provisional rulings (docs/mirage-bio/OPEN_RULINGS.md §F)
Virtual lab                     Implemented (growth, assay, environment, frozen tool interface)
Evaluator                       Implemented (M1–M4, Q1, O1, O2, Wilson intervals, ITT)
Scripted baselines              Implemented (GoodScientist, PassiveBayes)
Claude adapter                  Implemented; mock-tested, then run live (C1)
Runner, report, replay          Implemented (record-only, offline)
Evaluation runs (Claude)        Done: 30 episodes, strong matrix, prompt-v2
```

C1 results (`claude-opus-5-5`, strong matrix, seeds 500,000–500,029) are in
[`experiments/results/20261003-2323_claude_strong/`](experiments/results/20261003-2323_claude_strong/):
`results.md` (generated, with both baselines), `summary.json`, the episode records, replays and an
[interpretation note](experiments/results/20261003-2323_claude_strong/INTERPRETATION.md). The rulings
behind them are provisional (docs/mirage-bio/OPEN_RULINGS.md §F–§H). The Gate 0 artefacts validate
the benchmark itself; they are not an agent result.

## Quickstart

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). Nothing below calls a
model or the network.

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest -q

# Gate 0 at reduced size (a smoke check, never a pass claim)
.venv/bin/python scripts/gate0.py --quick --out .local/gate0

# Scripted baselines on the minimal matrix, then the report
.venv/bin/python -m mirage.evaluation.runner run --agent good_scientist --matrix minimal --out .local/runs
.venv/bin/python -m mirage.evaluation.runner run --agent passive_bayes --matrix minimal --out .local/runs
.venv/bin/python -m mirage.evaluation.report --out .local/report \
  --good-scientist .local/runs/<good_scientist run dir> \
  --passive-bayes .local/runs/<passive_bayes run dir>

# Offline replay of one saved episode
.venv/bin/python -m mirage.demo.replay .local/runs/<run dir>/episodes/<episode>.json --pace 0
```

## Documentation

Start with the [documentation index](docs/README.md).

| Document | Purpose |
|---|---|
| [docs/MIRAGE.md](docs/MIRAGE.md) | What MIRAGE is and is not |
| [docs/BENCHMARK_METHODOLOGY.md](docs/BENCHMARK_METHODOLOGY.md) | Paired worlds, controlled non-identifiability, diagnosticity |
| [docs/DIFFERENTIATION.md](docs/DIFFERENTIATION.md) | Contribution and novelty boundary |
| [docs/mirage-bio/TEAM_HANDOFF.md](docs/mirage-bio/TEAM_HANDOFF.md) | Team start here: roles and immediate priorities |
| [docs/mirage-bio/ANALYSIS.md](docs/mirage-bio/ANALYSIS.md) | MIRAGE-Bio requirements |
| [docs/mirage-bio/DESIGN.md](docs/mirage-bio/DESIGN.md) | MIRAGE-Bio implementation design |
| [docs/mirage-bio/GATE0_SPEC.md](docs/mirage-bio/GATE0_SPEC.md) | Scientific validation required before agent integration |
| [docs/mirage-bio/DEVELOPMENT_PLAN.md](docs/mirage-bio/DEVELOPMENT_PLAN.md) | Milestones, tasks, timeline, stop rules |
| [docs/mirage-bio/TEST_PLAN.md](docs/mirage-bio/TEST_PLAN.md) · [EXPERIMENT_PLAN](docs/mirage-bio/EXPERIMENT_PLAN.md) · [RISKS](docs/mirage-bio/RISKS.md) · [ADR/](docs/mirage-bio/ADR/) | Verification, measurement, risks, decisions |

## Repository structure

```text
docs/                    MIRAGE docs (current); docs/mirage-bio/ for the first environment
experiments/reference/   Design-time numerical reference (current; not Gate 0)
src/mirage/              Simulator, assay, virtual lab, agents, evaluation, replay
scripts/                 Gate 0 validation and plots
experiments/             Frozen configs, episode matrices, candidate Gate 0 results
tests/                   Automated tests (pytest)
```

## Scientific integrity

- **Synthetic environment.** MIRAGE-Bio's biology and instrument are controlled
  abstractions, with every assumption labelled. It is an adversarial identifiability
  benchmark, not a digital twin of any organism or plate reader.
- **No biological discovery.** Nothing produced here is a finding about real cells
  or instruments, and there is no universal OD threshold.
- **Hidden ground truth.** The simulator configuration is the truth. The agent never
  sees it. Parameters are frozen before any agent run and are never retuned in
  response to agent results.
- **No LLM judge.** Scoring is a deterministic function of saved records.
- **Limited claims.** Results apply only to this environment, configuration and
  sample size.

## Get the repository

```sh
git clone https://github.com/Pimentellll/originator-science.git
cd originator-science
python3 experiments/reference/design_validation.py --quick   # stdlib only; design-time reference
```

The application and test suite do not exist yet. Planned commands are listed in
[TEAM_HANDOFF](docs/mirage-bio/TEAM_HANDOFF.md#commands).

## Collaboration

- Use short-lived branches (one per DEV task, e.g. `feat/dev-007-lab-environment`)
  and focused pull requests into `main`.
- Coordinate ownership before editing the same component. Owners are listed in
  [DEVELOPMENT_PLAN §4](docs/mirage-bio/DEVELOPMENT_PLAN.md#4-work-breakdown-structure).
- Include the commands run and their actual outcomes in each pull request.
- Keep research claims separate from implementation status.

## Experiments and evidence

For each experiment, record the hypothesis, baseline, scenario version and hash,
configuration, random seeds, metrics and limitations. Keep development seeds
separate from held-out evaluation seeds.

Use `.local/` for scratch runs and private logs. Add selected reproducible,
non-sensitive evidence to `experiments/results/` deliberately rather than
committing every raw output.

## Secrets

Keep API keys in local environment variables or an ignored `.env` file. Never
commit credentials or put them in issue reports, pull requests or experiment logs.
Ignoring a file does not remove it if it was already tracked.
