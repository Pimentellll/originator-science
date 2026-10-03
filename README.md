# Originator Science

Research project for the Originator track at the London AI x Science Hackathon.

## Status

Repository scaffold only. The research question, recursive-loop design and
implementation stack are pending team agreement. No experimental results or
working research-agent capabilities are claimed yet.

## Structure

```text
src/          Implementation code
tests/        Automated tests
experiments/  Reproducible experiment configurations and runners
```

## Get the repository

```sh
git clone https://github.com/Pimentellll/originator-science.git
cd originator-science
```

Dependency installation and run instructions will follow the agreed technical
plan. There is no application or test suite to run yet.

## Collaboration

- Use short-lived branches and focused pull requests into `main`.
- Coordinate ownership before editing the same component.
- Include the commands run and their actual outcomes in each pull request.
- Keep research claims separate from implementation status.

## Experiments and evidence

For each experiment, record the hypothesis, baseline, task or dataset version,
configuration, random seeds where applicable, metrics and limitations. Preserve
the distinction between development tasks and held-out evaluation tasks.

Use `.local/` for scratch runs and private logs. Add selected reproducible,
non-sensitive evidence deliberately rather than committing every raw output.

## Secrets

Keep API keys in local environment variables or an ignored `.env` file. Never
commit credentials or put them in issue reports, pull requests or experiment
logs. Ignoring a file does not remove it if it was already tracked.
