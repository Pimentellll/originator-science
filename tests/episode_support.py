"""Test/script harness that plays the real BinderBioPOMDP against a policy.

The harness owns the environment (and therefore the hidden world); the policy and the
belief it consults only ever see public state, observations and the public predictive
model. Tests may compare outcomes with the environment's hidden world afterwards, via
the environment's own local score() and the world-mode label used to construct it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from binder_support import MODEL

from mirage.belief import DegenerateBeliefError, TERMINAL_ORDER, correct_terminal_masks, ParticleBelief, BINDER_SCHEMA_PROVISIONAL as SCHEMA
from mirage.belief.binder import ScenarioPrior
from mirage.core.contracts import ActionType, ScientificAction
from mirage.environments.binder import BinderBioPOMDP
from mirage.policies.base import REDESIGN_ACTIONS


@dataclass
class Episode:
    decision: ActionType | None
    actions: list[ScientificAction] = field(default_factory=list)
    steps: int = 0
    budget_used: float = 0.0
    score: float = 0.0
    final_health: float = 1.0
    skipped_updates: int = 0
    redesigns: int = 0
    correct_terminal: ActionType | None = None  # evaluator-side: right answer for the FINAL active candidate
    belief: ParticleBelief | None = None


def scenario_belief(n: int = 512, seed: int = 0, **kw) -> ParticleBelief:
    return ParticleBelief.from_prior(SCHEMA, ScenarioPrior(MODEL), n=n, seed=seed, **kw)


def run_episode(env: BinderBioPOMDP, make_policy, *, seed: int, belief: ParticleBelief | None = None, max_steps: int = 14) -> Episode:
    """``make_policy(belief)`` -> ScientificPolicy that reads that belief."""
    state = env.reset(seed)
    belief = belief or scenario_belief(seed=seed)
    policy = make_policy(belief)
    policy.reset(seed)
    ep = Episode(decision=None, belief=belief)
    for _ in range(max_steps):
        action = policy.choose_action(state, belief.summary(), env.available_actions())
        result = env.step(action)
        ep.actions.append(action)
        ep.steps += 1
        if result.observation is not None:
            try:
                belief.observe(MODEL, action, result.observation)
            except DegenerateBeliefError:
                ep.skipped_updates += 1  # the public likelihood cannot explain this observation
        elif action.action_type in REDESIGN_ACTIONS:
            belief.apply_redesign(MODEL, action)
        state = result.state
        if result.terminal:
            ep.decision = action.action_type
            break
    ep.budget_used = 12.0 - state.resources.budget_remaining
    ep.final_health = state.resources.spr_instrument_health
    ep.score = env.score()
    ep.redesigns = sum(a.action_type in REDESIGN_ACTIONS for a in ep.actions)
    # Evaluator-side only (never visible to a policy): the right terminal for the final active
    # candidate, from its hidden factors and the benchmark-default terminal semantics.
    hidden = env._hidden_by_candidate[state.active_candidate.candidate_id]
    row = MODEL.to_row(hidden)[None, :]
    ep.correct_terminal = TERMINAL_ORDER[int(correct_terminal_masks(SCHEMA.failure_indicators(row))[0].argmax())]
    return ep
