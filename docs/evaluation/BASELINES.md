# Policy taxonomy and baselines

Every policy implements one contract, `choose_action(state, belief, available_actions)`, and sees only public inputs
([contract](../architecture/BELIEF_AND_POLICY_CONTRACT.md)). They play identical seeded worlds. Status below is as of
`d182a2c`.

| Policy | Role | What it is | Implemented | Evaluated |
|---|---|---|---|---|
| **Random** | control | uniform over legal actions (terminal actions included in the benchmark; excluded in the live API) | yes | **Baseline V1** |
| **FixedPipeline** | scripted characterisation baseline | runs all seven assays once in a fixed QC-before-SPR order (stability, SEC, SPR, epitope, developability, assay control, orthogonal), then a fixed threshold rule; never redesigns | yes | **Baseline V1** |
| **GreedyEIG** | myopic information-gain policy | scores each assay by the one-step expected reduction of total marginal mechanism entropy on the current belief (Monte Carlo, tempered likelihood), measures while the best score ≥ 0.02 nats, then closes with the threshold rule; no multi-step search, no model of future instrument health, never redesigns | yes | **Baseline V1** |
| **ReceptorRescuePlanner** | hand-authored domain strategy | SEC first; if SEC shows monomer fraction < 0.45, `REDESIGN_SOLUBILITY`; then SPR once; then the threshold rule | yes (live demo, `h0_smoke.py`) | not run on the benchmark |
| **Lookahead** | explicit model-based long-horizon planner | closed-loop sparse-sampling expectimax (depth 2 default, 3 supported) over the same public model; at each node stop, measure or redesign; terminal utility, entropy shaping, budget/sample/time and an SPR-health path model; at most one redesign per plan | yes, unit-tested | **NOT RUN** |
| **PPO** | learned campaign-level planner | MaskablePPO over the 14 actions on a Gym wrapper of the same environment; `PPOPolicy` loads a checkpoint behind the common contract | stack and adapter yes | **NOT RUN**: no frozen, scientifically valid checkpoint |

**Shared threshold closing rule** (Random excepted): any molecular marginal ≥ 0.5 → `REJECT`; else `p_assay_invalid` ≥ 0.5 →
`ABSTAIN`; else `p_model_invalid` ≥ 0.5 → `MODEL_INVALID`; else `SELECT`.

**MIRAGE is not synonymous with PPO.** PPO is a swappable pragmatic planner (ADR 0005). The benchmark, trust boundary,
causal belief and evaluator are the system; any policy can be plugged in.

## What the baselines are for

- Random calibrates luck: how often is a decision correct with no evidence?
- FixedPipeline shows what exhaustive characterisation buys when the lab can afford it.
- GreedyEIG is the principled-but-myopic comparator; it should be competitive on genuinely myopic worlds and exposes
  the limit on path-dependent ones.
- Lookahead and PPO are the candidates that *should* beat the above under scarcity. That is a hypothesis
  (preregistered in V2), not a result. **MIRAGE does not claim RL or planning wins by default**, and nothing is
  reported that has not been run.
