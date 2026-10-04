import json
import pytest

from mirage.core import ActionType
from mirage.environments.binder.environment import BinderBioPOMDP
from mirage.environments.binder.scenarios import (
    BinderScenarioVersion,
    SHOWCASE_SCENARIOS,
)

@pytest.mark.parametrize("scenario", SHOWCASE_SCENARIOS, ids=lambda item: item.name)
def test_v2_signature_matches_privileged_threshold_labels_over_seeds(scenario):
    for seed in range(32):
        env = BinderBioPOMDP(
            scenario.world_mode, scenario_version=BinderScenarioVersion.SEMANTICS_V2
        )
        state = env.reset(seed)
        truth = env.evaluator_truth(state.active_candidate.candidate_id)
        labels = truth.labels
        actual = {
            name for name in (
                "folding_failure", "aggregation_failure", "affinity_failure",
                "kinetic_failure", "epitope_failure", "developability_failure",
                "assay_invalid", "model_invalid",
            ) if getattr(labels, name)
        }
        assert set(labels.primary_failure_mechanisms) == set(scenario.signature.primary_failure_mechanisms)
        assert actual == set(scenario.signature.primary_failure_mechanisms)
        assert not actual.intersection(scenario.signature.forbidden_primary_mechanisms)
        spr = next(action for action in env.available_actions() if action.action_type == ActionType.MEASURE_SPR)
        result = env.step(spr)
        assert result.observation is not None
        expected_quality = "degraded" if "aggregation_failure" in actual else "nominal"
        assert result.observation.quality == expected_quality
        assert scenario.signature.expected_assay_signature
        assert labels.secondary_consequences == scenario.signature.secondary_consequences

def test_v2_truth_accessor_is_private_and_public_state_stays_scrubbed():
    env = BinderBioPOMDP.from_showcase(
        "aggregation_kinetic_defect",
        scenario_version=BinderScenarioVersion.SEMANTICS_V2,
    )
    state = env.reset(9)
    truth = env.evaluator_truth(state.active_candidate.candidate_id)
    assert truth.labels.primary_failure_mechanisms == (
        "aggregation_failure", "kinetic_failure"
    )
    assert truth.labels.secondary_consequences
    payload = json.dumps(state.model_dump(mode="json")).lower()
    for forbidden in ("truth", "hidden", "primary_failure", "secondary_consequence"):
        assert forbidden not in payload

def test_v1_compound_sampler_remains_available_without_v2_semantic_metadata():
    env = BinderBioPOMDP.from_showcase("aggregation_kinetic_defect")
    state = env.reset(9)
    labels = env.evaluator_truth(state.active_candidate.candidate_id).labels
    assert labels.primary_failure_mechanisms == ()
    assert labels.affinity_failure and labels.developability_failure
