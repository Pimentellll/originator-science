# Demo pair: live Claude run (DEV-017, DESIGN §20)

This is the live-demo backup. Claude ran **once** on the matched pair in `experiments/configs/demo_pair.json`,
after the prompt-v2 freeze. The command was:

```bash
python -m mirage.evaluation.runner run --agent claude --matrix demo --out experiments/results/demo
```

- **Run:** `20261004-0016_claude_demo/`, with `claude-opus-5-5`, effort `high`, `prompt-v2` and noise seeds `(0, 0)`.
  Both twins share one noise stream, so their passive readings are identical: `passive` is equal in
  `demo-BP.json` and `demo-MA.json`.
- **Not evaluation data.** These are dev-block demo episodes and never enter M1–M4 (EXPERIMENT_PLAN §6).
  The scored result is `../20261003-2323_claude_strong/`.
- **Outcome:** both episodes are `DIAGNOSED` and correct, each with a diagnostic dilution. There were no re-runs.
  See `replay/*.txt`.
- **Usage:** 8 API calls, 22,958 input and 1,936 output tokens (`usage.jsonl`), with no caching.

## Replay offline (no network)

```bash
python -m mirage.demo.replay experiments/results/demo/20261004-0016_claude_demo/episodes/demo-MA.json
```

`replay/demo-{BP,MA}.txt` and `.png` were generated with `--pace 0 --figure ...`.

Note: in `demo-BP` the true K (1.0306) is about 3% above the undiluted plateau. This is the
assay compression below S described in OPEN_RULINGS §H. Claude answered `BIOMASS_AS_READ`, which the
pre-registered scoring counts as correct.
