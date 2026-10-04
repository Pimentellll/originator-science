# Demo guide

For someone showing MIRAGE to a judge or a teammate. Setup is [DEVELOPER_SETUP](DEVELOPER_SETUP.md); problems are in
[TROUBLESHOOTING](TROUBLESHOOTING.md).

```bash
./mirage demo
```

The browser opens on the **Start** page. Everything on screen comes from a real simulated campaign served by the public API;
nothing is scripted or hard-coded, including the outcome.

## The 30-second version

1. Click **START GUIDED DEMO**. It runs a fixed, deterministic campaign (seed 9, the *aggregation + kinetic defect* world,
   `SEMANTICS_V2`, the Rescue Planner) and narrates it.
2. Press **NEXT** at each step. Each press executes the policy's next real action and explains what happened, with the real
   numbers from that run:

   | Step | What you see |
   |---|---|
   | FAILURE | The binder failed downstream. Is the cause the molecule, the experiment, or the biological model? |
   | SEC (or whichever assay ran) | The assay, its reading, and what it cost |
   | CAUSAL UPDATE | Which failure mode the evidence moved, e.g. *Aggregation 0.61 → 1.00*, and the entropy change |
   | REDESIGN | The candidate is repaired instead of discarded; a child joins the lineage |
   | SPR | Binding kinetics measured on the repaired candidate, and what it did to SPR instrument health |
   | DECISION | Select, reject, declare the model invalid, or abstain, and the belief it rests on |
   | JUSTIFICATION | Correct? Justified? Evidence supporting it, missing evidence, resources used, assays not run, remaining uncertainty |

   The step sequence follows the actual trace; if the policy chose differently the narration would too.
3. The last step shows the verdict, one of **CORRECT + JUSTIFIED**, **CORRECT BUT UNJUSTIFIED**, **JUSTIFIED ABSTENTION**,
   **INCORRECT** or **NO VERDICT**. This is the point of MIRAGE: *correct* and *justified* are scored separately.

`./mirage demo --guided` opens straight into the guided walk-through.

## Take control: MANUAL SCIENTIST

On the **Start** page choose **MANUAL SCIENTIST**, pick a scenario and **START CAMPAIGN**. The Next-action panel becomes your
control surface: every action the public state allows (measure stability, SEC, SPR, epitope, developability, validate assay,
orthogonal function; redesign stability, solubility, interface; select, reject, model invalid, abstain). Next to it, **MIRAGE
RECOMMENDS** shows what the policy would do from the *same public state*, with its rationale.

Ask the judge: *"Would you run SPR now?"* After they choose, the **You vs MIRAGE** log shows their choice next to MIRAGE's at each
step, and the belief updates from their choice. Actions that are unaffordable are greyed out. **USE MIRAGE'S CHOICE** lets
MIRAGE take a step for you.

Hidden truth is never shown while a manual or guided run is in progress. The scenario name is masked ("hidden until
decision") unless you press *reveal*, and it appears automatically after the decision.

## Choosing a scenario, policy and seed

The **Start** page offers five worlds and the policies the backend really serves:

| Scenario | In one line |
|---|---|
| Folding instability | A folding failure with otherwise usable binding |
| Aggregation + kinetic defect | Aggregation plus a fast-dissociation kinetic defect (the guided demo) |
| Broken assay | A good molecule with an invalid downstream assay |
| Invalid biological model | A good molecule and assay in an invalid biological model |
| Misleading proxy trap | Attractive proxy readouts conceal functional and developability failure |

Policies: Rescue Planner, Greedy EIG, Fixed Pipeline, Random. **Lookahead** and **PPO** appear as **NOT AVAILABLE** with the
reason, because they are not wired into the live API; the page never presents them as working. Note that the Rescue Planner is
specialised for the compound-failure world and can be wrong elsewhere; that is a real result, not a bug.

The scenario is **orchestration metadata chosen by whoever runs the demo**. It is not policy input, and the public record and
replay contain only the semantics version, seed, policy and git SHA.

## What each part of the cockpit is for

Read it left to right along the strip at the top: **1 Candidate → 2 Evidence → 3 Belief → 4 Action → 5 Resources → 6 Timeline.**

- **Candidate and lineage:** which molecule is active, what has been measured on each version.
- **Evidence graph:** which result raised or lowered belief in which failure mode.
- **Causal belief:** the model posterior over molecule / experiment / biological-model failure modes. It is a *model posterior,
  not an empirical biological probability*, and the rows need not sum to 1. Entropy and effective sample size are shown; particle
  count and inference-validation status are not part of the public state, so they are not shown.
- **Is this conclusion justified?:** leading explanation, unresolved alternative, evidence still required, whether the assay
  and the model have been separated, and (after the decision) the evaluator's verdict and its checks.
- **Resources:** budget, sample, simulated campaign time (model units, **not** laboratory hours), experiment and redesign
  counts, SPR instrument health. When the same-seed fixed pipeline has really been run, its cost is shown beside yours.
- **Summary bar:** campaign, policy, scenario (orchestration metadata), seed, semantics version, status, budget, sample, SPR health.

## System check (before you present)

The **System check** tab calls only public/system routes and shows: API reachable, environment initialised, policies wired,
frontend and backend versions with the git SHA, scenario-semantics version, deterministic smoke, record/replay, and the public
leakage guard. Quote the SHA and semantics version with any screenshot so the run can be reproduced.

```bash
./mirage doctor          # same idea, from the terminal, with exact fixes
```

## Reproducibility of a demo run

Every episode records: git SHA (with `-dirty` if the tree had uncommitted changes), seed, policy, environment profile plus
scenario-semantics version, and contract version. The hidden world never enters the record or replay.

Same seed, same policy, same semantics gives the same campaign.

## Options

```bash
./mirage demo --scenario ASSAY_FAILURE --seed 4 --policy greedy_eig
./mirage demo --scenario-version BASELINE_V1     # the frozen historical baseline
./mirage demo --no-browser                       # print the URL only (SSH, CI, headless)
./mirage demo --port 8100 --frontend-port 5180
./mirage stop                                    # stop MIRAGE-owned processes only
```

## Docker fallback

`./mirage demo --docker` uses `compose.yaml` (API + cockpit, ports bound to loopback). **Verification status: written but
not run.** Docker was not available in the environment where this was developed, so the compose path is untested. Native
`./mirage demo` is the supported route and the one tested end to end.
