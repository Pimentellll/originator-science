# Contributing to MIRAGE

Thanks for your interest. MIRAGE is a research benchmark: it measures whether an AI scientist
runs the control that resolves an ambiguous result, rather than only whether it reaches the right
answer. Contributions are welcome, but the same principle applies to them. **A change is judged
by its evidence.**

## Set up

```bash
./mirage setup     # Python 3.11+ virtualenv (.venv) and frontend dependencies
./mirage doctor    # checks the environment and prints READY or what is missing
./mirage demo      # API + cockpit in the browser
```

See the [README](README.md#quick-start) for the full quick start, and §7 there for every command it runs.

## Before you open a pull request

```bash
./mirage test --quick                                   # fast Python + smoke checks
.venv/bin/python -m pytest -q                           # full Python suite
cd frontend && npm run typecheck && npm run lint && npm test
```

Fill in every section of the [pull request template](.github/pull_request_template.md).
- **Change:** what changed, and why.
- **Verification:** the commands you ran and their *actual* outcomes, including failures. If a
  failure already happens on `main`, say so and show it.
- **Research impact:** which claim the change touches, the evidence, and its limitations.
- **Release impact:** `major`, `minor`, `patch` or `none`, with a reason.

Keep branches short-lived and PRs focused on one change.

## Rules that protect the science

- **Frozen results are read-only.** Never edit, re-score or regenerate anything under `results/`
  or `experiments/results/`, or a preregistration/lock file. Fresh runs go into a new directory
  (`.local/` for scratch work).
- **Register before you run.** A new experiment gets a written registration (question, configs,
  seeds, metrics, decision rule, spend cap) committed *before* any scored run. Exploratory work
  lives under `experiments/exploratory/<name>/` and is labelled exploratory. See the existing
  folders there for examples.
- **No hidden truth on the public side.** Prompts, public API responses and public records must
  never contain the simulator's hidden state (true condition, parameters, assay validity). The
  trust-boundary tests enforce this. Don't weaken them.
- **Changing a scorer means a new scorer version.** Propose it in its own PR, together with its
  effect on every existing result.
- **Report what was measured.** Use counts and intervals ("29/30, Wilson 95 % …"). Write "no
  detectable difference at n = 30", not "equal".

## Reporting bugs and proposing experiments

Use the [issue templates](https://github.com/Pimentellll/originator-science/issues/new/choose).
For a security issue, follow [SECURITY.md](SECURITY.md) and don't open a public issue.

## Secrets

Keep API keys in an ignored `.env` or your shell environment. Never commit credentials, and never
paste them into issues, PRs or logs.

## Conduct and licence

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md). By
contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
