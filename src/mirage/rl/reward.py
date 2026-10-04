"""Transparent campaign reward (F1). Training signal only; never scientific evidence.

Per step t (action a_t taking state s_t -> s_{t+1}):

    r_t =   lambda_info * (H_t - H_{t+1})                          information shaping
          - c_budget  * (budget spent)                              experiment cost
          - c_sample  * (sample consumed)                           sample depletion
          - c_time    * (simulated time elapsed)                    time
          - c_spr     * (SPR instrument health lost)                instrument damage
          - c_redesign * [a_t is a redesign and #redesigns > free_redesigns]   excessive redesign
          + U_terminal                    on the decisive step only
          + P_illegal                     if an unavailable action is attempted (masking should make this 0)

H is the belief's total marginal mechanism entropy (``BeliefSummary.posterior_entropy``, nats).
The shaping telescopes: summed over an episode it equals lambda_info * (H_0 - H_T), bounded by
lambda_info * 8 ln 2, so repeated redesign/measure cycles cannot farm it.

U_terminal comes from ``RandomizedBinderPOMDP.terminal_utility`` (environment training utility):
+1 correct SELECT/REJECT/MODEL_INVALID (a correct SELECT is always a rescued candidate in this
environment), -1 wrong, ``abstain_value`` (0.3) for ABSTAIN when no decisive action was correct,
0 for ABSTAIN when one was. Abstention is kept below a correct decisive action so a blind
abstention cannot match a rescue or a diagnosis.

The privileged evaluator is never imported here; correct-vs-justified scoring stays external.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RewardConfig:
    lambda_info: float = 0.10
    c_budget: float = 0.02  # matches the environment's own -0.02 per budget unit
    c_sample: float = 0.01
    c_time: float = 0.01
    c_spr: float = 0.50
    c_redesign: float = 0.05
    free_redesigns: int = 3
    illegal_penalty: float = -1.0
    abstain_value: float = 0.3  # utility of an abstention when abstaining was the best available answer

    def as_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}


def step_reward(
    cfg: RewardConfig,
    *,
    entropy_before: float,
    entropy_after: float,
    budget_spent: float,
    sample_spent: float,
    time_elapsed: float,
    spr_health_lost: float,
    is_redesign: bool,
    redesign_count: int,
    terminal_utility: float | None,
) -> tuple[float, dict[str, float]]:
    """Return (reward, named terms). ``terminal_utility`` is None unless the episode just ended."""
    terms = {
        "info_gain": cfg.lambda_info * (entropy_before - entropy_after),
        "budget": -cfg.c_budget * budget_spent,
        "sample": -cfg.c_sample * sample_spent,
        "time": -cfg.c_time * time_elapsed,
        "instrument": -cfg.c_spr * max(spr_health_lost, 0.0),
        "redesign": -cfg.c_redesign if is_redesign and redesign_count > cfg.free_redesigns else 0.0,
        "terminal": 0.0 if terminal_utility is None else float(terminal_utility),
    }
    return sum(terms.values()), terms
