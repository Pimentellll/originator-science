import numpy as np

from mirage.core import ActionType, ScientificAction
from mirage.environments.binder import BinderHypothesis, BinderPredictiveModel


def particle() -> BinderHypothesis:
    return BinderHypothesis(0.7, 0.8, -8.0, -2.1, True, 0.2, True, True)


def test_spr_is_structured_and_likelihood_prefers_its_particle() -> None:
    model, action = BinderPredictiveModel(), ScientificAction(action_type=ActionType.MEASURE_SPR, candidate_id="c0")
    observation = model.sample_observation(particle(), action, np.random.default_rng(7))
    assert set(observation.measurements) == {"log_kd", "log_koff"}
    assert model.log_likelihood(observation, particle(), action) > model.log_likelihood(observation, BinderHypothesis(0.7, 0.8, -5.0, 0.5, True, 0.2, True, True), action)


def test_predictive_sampling_and_redesign_are_seeded() -> None:
    model, h = BinderPredictiveModel(), particle()
    action = ScientificAction(action_type=ActionType.REDESIGN_STABILITY, candidate_id="c0")
    assert model.redesign(h, action, np.random.default_rng(3)) == model.redesign(h, action, np.random.default_rng(3))
