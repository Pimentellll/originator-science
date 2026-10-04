# MIRAGE-Bio v0.1 (legacy growth / OD600 benchmark)

MIRAGE-Bio was the project's **first environment**: a controlled virtual microbiology lab in which an OD600-like growth
curve rises and flattens, and the agent must decide, using diluted remeasurements on a budget of six readings, whether
late biomass is at the level the undiluted readings indicate (`BIOMASS_AS_READ`) or higher (`BIOMASS_ABOVE_READING`).
The two hidden worlds (`BIOLOGICAL_PLATEAU`, `MEASUREMENT_ARTIFACT`) are built so passive curves are quantitatively
ambiguous.

## Status

| Item | State |
|---|---|
| Implementation (`src/mirage/{lab,assay,biology,agents,demo}`, `evaluation/runner.py`, `report.py`, `metrics.py`) | implemented and tested (`tests/test_*.py`) |
| Gate 0 validation | run and frozen under provisional rulings: `experiments/results/gate0/` |
| Claude C1 strong-matrix run (`claude-opus-5-5`, 30 episodes), C2 Sonnet, baselines | committed under `experiments/results/` |
| Relationship to the Binder system | separate, earlier environment; **not replaced or rewritten**; its results say nothing about binder rescue |

The documents in this directory (ANALYSIS, DESIGN, GATE0_SPEC, DEVELOPMENT_PLAN, TEST_PLAN, EXPERIMENT_PLAN, RISKS,
TEAM_HANDOFF, OPEN_RULINGS, ADR/) were written before implementation and carry a LEGACY banner; their "not started" status
lines are historical. The OD600, growth-plateau and "plate reader" vocabulary belongs to this environment and is
intentionally retained here.

## Quickstart (legacy)

```bash
.venv/bin/python -m pytest -q tests/test_growth.py tests/test_assay.py tests/test_runner.py
.venv/bin/python scripts/gate0.py --quick --out .local/gate0       # smoke only; never a pass claim
.venv/bin/python -m mirage.evaluation.runner run --agent good_scientist --matrix minimal --out .local/runs
.venv/bin/python -m mirage.demo.replay <episode.json> --pace 0
```

Scientific integrity limits apply to this environment as to the other: synthetic, no biological discovery, hidden truth
frozen before agent runs, no LLM judge, results scoped to this configuration.
