# Documentation index

To run the project, start with the [root README quick start](../README.md#quick-start), then
[DEVELOPER_SETUP.md](DEVELOPER_SETUP.md), [DEMO_GUIDE.md](DEMO_GUIDE.md) and [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
To understand it, start at [START_HERE.md](START_HERE.md). The Binder system is documented under `architecture/`, `scientific-spec/`,
`evaluation/`, `validation/`, `implementation/` and `adr/`. The earlier growth benchmark is documented under
`mirage-bio/` and is retained for history.

```text
docs/
├── DEVELOPER_SETUP.md     ./mirage commands, bootstrap, tests, launcher layout
├── DEMO_GUIDE.md          guided demo, manual scientist, what each cockpit panel means
├── TROUBLESHOOTING.md     exact fixes for every setup failure seen so far
├── START_HERE.md          status table and reading order
├── MIRAGE.md              framing: correct != justified, failure hierarchy, scope
├── DIFFERENTIATION.md     what is and is not claimed
├── BENCHMARK_METHODOLOGY.md   paired-world methodology (introduced for MIRAGE-Bio; see its banner)
├── architecture/          system, trust boundary, belief/policy contract, provenance, API
├── scientific-spec/       environment, causal state, actions, assays, resources, redesign, scenarios
├── evaluation/            policy taxonomy, metrics, protocol, Baseline V1 analysis, V2 preregistration + status
├── validation/            B4A posterior convergence gate and its measured results (+ raw audit JSON)
├── implementation/        acceptance gates, work packages, migration, historical execution plan
├── adr/                   decision records 0001-0011
├── research/              identifiability research note (not implemented)
├── pitch/                 legacy MIRAGE-Bio pitch
└── mirage-bio/            legacy growth/OD benchmark documentation
```

## Frozen records (never edited in place)

| Record | Where | Why frozen |
|---|---|---|
| Baseline V1 results | `../results/baseline_v1/` (tag `mirage-baseline-v1`) | historical; later policies are appended elsewhere |
| V2 preregistration | `evaluation/BINDER_RESCUE_V2.md`, `../experiments/preregistration/binder_rescue_v2/` (tag `mirage-v2-prereg`) | hash-locked; a change is a new version |
| Posterior convergence gate | `validation/POSTERIOR_CONVERGENCE_GATE.md` | declared before any remedy was evaluated |

Interpretation, corrections and status for these records live in separate documents:
[BASELINE_V1.md](evaluation/BASELINE_V1.md), [BINDER_RESCUE_V2_STATUS.md](evaluation/BINDER_RESCUE_V2_STATUS.md) and
[B4A_CONVERGENCE_RESULTS.md](validation/B4A_CONVERGENCE_RESULTS.md).

## Precedence when documents overlap

| Question | Document that wins |
|---|---|
| What the system is and claims | root README, MIRAGE.md, DIFFERENTIATION.md |
| Public interfaces and the trust boundary | architecture/ |
| Simulator behaviour and numbers | scientific-spec/ (numbers are checked against `src/mirage/environments/binder/`) |
| What a metric means; evidence rules | evaluation/METRICS.md |
| What was measured | evaluation/BASELINE_V1.md, validation/B4A_CONVERGENCE_RESULTS.md and the raw files they cite |
| Why a decision was made | adr/ |
| The legacy growth benchmark | mirage-bio/ |

Where prose and code disagree, the code at the freeze SHA wins and the document is a bug.
