"""Training-side specialisation of the REAL ``BinderBioPOMDP``.

``RandomizedBinderPOMDP`` is the real environment plus (a) per-episode lab conditions from a
``WorldConfig`` and (b) a privileged ``terminal_utility`` used only by the training reward.
Everything a policy sees still comes from ``agent_state()`` / ``available_actions()``.

With a nominal ``WorldConfig`` it is bit-identical to ``BinderBioPOMDP`` (pinned by tests).

Fragility, reported as a backend requirement: the cost, resource and noise hooks override
private members (``_can_pay``, ``_charge``, ``_resources``, ``_predictive``,
``_hidden_by_candidate``) of the core environment. A public ``BinderEpisodeConfig`` there
would remove that coupling.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from mirage.core import ActionType, AgentState, ResourceState, ScientificAction, ScientificObservation
from mirage.environments.binder import BinderBioPOMDP, BinderHypothesis, BinderPredictiveModel
from mirage.environments.binder.environment import _COSTS
from mirage.rl.randomization import WorldConfig

# The environment passes its module-level cost objects to _can_pay/_charge; map them back to actions.
_KIND_BY_COST = {id(cost): kind for kind, cost in _COSTS.items()}

DECISIVE = (ActionType.SELECT, ActionType.REJECT, ActionType.MODEL_INVALID)


class _ScaledPredictive(BinderPredictiveModel):
    """Environment-side assay noise / redesign effect scaling.

    Draws the same random numbers as the base model, so scale 1.0 is identical to it. The
    belief keeps using the nominal model, so scale != 1 is deliberate model misspecification.
    """

    def __init__(self, noise_scale: float, redesign_effect_scale: float) -> None:
        self._noise, self._effect = noise_scale, redesign_effect_scale

    def sample_observation(self, hypothesis: BinderHypothesis, action: ScientificAction, rng: np.random.Generator) -> ScientificObservation:
        observation = super().sample_observation(hypothesis, action, rng)
        if self._noise == 1.0:
            return observation
        means, _ = self.expected_measurements(hypothesis, action)
        scaled = {k: float(means[k] + self._noise * (v - means[k])) for k, v in observation.measurements.items()}
        return observation.model_copy(update={"measurements": scaled})

    def redesign(self, hypothesis: BinderHypothesis, action: ScientificAction, rng: np.random.Generator) -> BinderHypothesis:
        child = super().redesign(hypothesis, action, rng)
        if self._effect == 1.0:
            return child
        k, h = self._effect, hypothesis
        blend = lambda parent, new: parent + k * (new - parent)  # noqa: E731
        unit = lambda x: float(min(1.0, max(0.0, x)))  # noqa: E731
        return dataclasses.replace(
            child,
            stability=unit(blend(h.stability, child.stability)),
            monomer_fraction=unit(blend(h.monomer_fraction, child.monomer_fraction)),
            log_kd=blend(h.log_kd, child.log_kd),
            log_koff=blend(h.log_koff, child.log_koff),
        )


class RandomizedBinderPOMDP(BinderBioPOMDP):
    """BinderBioPOMDP with seeded lab-condition randomization and a training utility."""

    def __init__(self, config: WorldConfig) -> None:
        self.config = config
        super().__init__(config.world_mode)  # calls self.reset() once; overridden below
        self._predictive = _ScaledPredictive(config.assay_noise_scale, config.redesign_effect_scale)

    def reset(self, seed: int | None = None) -> AgentState:
        super().reset(seed)
        cfg = getattr(self, "config", None)
        if cfg is not None:
            self._resources = ResourceState(
                budget_remaining=cfg.budget, sample_remaining=cfg.sample, simulated_time=0.0,
                spr_instrument_health=cfg.initial_spr_health,
            )
        return self.agent_state()

    # -- cost scaling ------------------------------------------------------------------
    def _scaled(self, cost):
        kind = _KIND_BY_COST.get(id(cost))
        k = self.config.cost_scale * (self.config.spr_cost_scale if kind == ActionType.MEASURE_SPR else 1.0)
        return dataclasses.replace(cost, budget=cost.budget * k, sample=cost.sample * k, time=cost.time * k)

    def _can_pay(self, cost) -> bool:
        return super()._can_pay(self._scaled(cost))

    def _charge(self, cost) -> None:
        super()._charge(self._scaled(cost))

    # -- privileged training utility ---------------------------------------------------
    def terminal_utility(self, abstain_value: float = 0.3) -> float:
        """Training-only terminal utility in [-1, +1]; never visible to a policy.

        Correctness is the environment's own ``score()`` (re-evaluated counterfactually for
        each decisive action, so no scoring logic is duplicated here):

        * SELECT / REJECT / MODEL_INVALID: +1 if correct, -1 if wrong.
        * ABSTAIN: ``abstain_value`` if no decisive action would have been correct
          (abstention was the best available answer), otherwise 0 (a hedge).

        The raw environment score pays +1 for ABSTAIN in every world. Taken as reward that
        teaches "abstain at step 0", and it makes an abstention exactly as valuable as a
        successful rescue, so ``abstain_value`` < 1 keeps rescue/diagnosis worth pursuing.
        """
        if not self._terminal or self._decision is None:
            return 0.0
        decision = self._decision
        correct = {d: self._counterfactual_correct(d) for d in DECISIVE}
        if decision == ActionType.ABSTAIN:
            return 0.0 if any(correct.values()) else float(abstain_value)
        return 1.0 if correct[decision] else -1.0

    def _counterfactual_correct(self, decision: ActionType) -> bool:
        saved = self._decision
        try:
            self._decision = ActionType.ABSTAIN
            reference = super().score()  # ABSTAIN is always scored correct by the environment
            self._decision = decision
            return super().score() >= reference - 1e-9
        finally:
            self._decision = saved
