import pytest
from policy_helpers import ASSAYS, TERMINALS, make_actions, make_belief, make_state

from mirage.core.contracts import ActionType as A
from mirage.policies import (
    DEFAULT_PIPELINE, FixedPipelineConfig, FixedPipelinePolicy, PolicyError, RandomPolicy, ScientificPolicy,
)


def rollout(policy, steps=30):
    s, b, acts = make_state(), make_belief(), make_actions()
    out = []
    for _ in range(steps):
        out.append(policy.choose_action(s, b, acts))
    return out


def test_random_reproducible_and_seed_sensitive():
    assert rollout(RandomPolicy(seed=4)) == rollout(RandomPolicy(seed=4))
    assert rollout(RandomPolicy(seed=4)) != rollout(RandomPolicy(seed=5))


def test_random_reset_restarts_stream():
    p = RandomPolicy(seed=1)
    first = rollout(p, 10)
    p.reset()
    assert rollout(p, 10) == first
    p.reset(seed=2)
    assert rollout(p, 10) == rollout(RandomPolicy(seed=2), 10)


def test_random_only_returns_available_actions_and_ignores_enumeration_order():
    acts = make_actions(ASSAYS[:3])
    rev = tuple(reversed(acts))
    a, b = RandomPolicy(seed=3), RandomPolicy(seed=3)
    for _ in range(20):
        x = a.choose_action(make_state(), make_belief(), acts)
        assert x in acts
        assert x == b.choose_action(make_state(), make_belief(), rev)


def test_random_can_exclude_terminals():
    p = RandomPolicy(seed=0, allow_terminal=False)
    assert all(a.action_type not in TERMINALS for a in rollout(p, 100))
    only_terminal = make_actions(TERMINALS)
    assert p.choose_action(make_state(), make_belief(), only_terminal) in only_terminal


def test_random_covers_action_space():
    seen = {a.action_type for a in rollout(RandomPolicy(seed=0), 400)}
    assert len(seen) == 14


def test_fixed_pipeline_order_and_deterministic():
    p = FixedPipelinePolicy()
    done, seq = [], []
    for _ in range(len(DEFAULT_PIPELINE)):
        a = p.choose_action(make_state(done), make_belief(), make_actions())
        seq.append(a.action_type); done.append(a.action_type)
    assert tuple(seq) == DEFAULT_PIPELINE
    assert seq.index(A.MEASURE_SEC) < seq.index(A.MEASURE_SPR)  # QC before SPR
    assert rollout(p, 5) == rollout(FixedPipelinePolicy(), 5)


def test_fixed_pipeline_order_ignores_belief():
    p = FixedPipelinePolicy()
    for belief in (make_belief(), make_belief(p_aggregation_failure=0.99, p_assay_invalid=0.9)):
        assert p.choose_action(make_state([A.MEASURE_STABILITY]), belief, make_actions()).action_type == A.MEASURE_SEC


def test_fixed_pipeline_skips_unavailable_assays():
    acts = make_actions([t for t in ASSAYS if t != A.MEASURE_SPR] + TERMINALS)
    a = FixedPipelinePolicy().choose_action(make_state([A.MEASURE_STABILITY, A.MEASURE_SEC]), make_belief(), acts)
    assert a.action_type == A.MEASURE_EPITOPE


def test_fixed_pipeline_only_uses_active_candidate_history():
    s = make_state(done=list(DEFAULT_PIPELINE), cid="old")
    # active candidate is c1 with no observations of its own
    s = s.model_copy(update={"active_candidate": s.active_candidate.model_copy(update={"candidate_id": "c1"})})
    a = FixedPipelinePolicy().choose_action(s, make_belief(), make_actions(cid="c1"))
    assert a.action_type == A.MEASURE_STABILITY and a.candidate_id == "c1"


@pytest.mark.parametrize(
    "belief_kw,expected",
    [
        ({}, A.SELECT),
        ({"p_aggregation_failure": 0.9}, A.REJECT),
        ({"p_kinetic_failure": 0.5}, A.REJECT),
        ({"p_model_invalid": 0.8}, A.MODEL_INVALID),
        ({"p_assay_invalid": 0.8, "p_model_invalid": 0.8}, A.ABSTAIN),
        ({"p_aggregation_failure": 0.9, "p_model_invalid": 0.5}, A.REJECT),  # unmeasured model flag at its prior must not override a molecular failure
    ],
)
def test_fixed_pipeline_terminal_rule(belief_kw, expected):
    s = make_state(done=list(DEFAULT_PIPELINE))
    assert FixedPipelinePolicy().choose_action(s, make_belief(**belief_kw), make_actions()).action_type == expected


def test_fixed_pipeline_never_redesigns_and_falls_back_to_available_terminal():
    s = make_state(done=list(DEFAULT_PIPELINE))
    acts = make_actions([A.REDESIGN_SOLUBILITY, A.REJECT])
    assert FixedPipelinePolicy().choose_action(s, make_belief(), acts).action_type == A.REJECT
    with pytest.raises(PolicyError):
        FixedPipelinePolicy().choose_action(s, make_belief(), make_actions([A.REDESIGN_SOLUBILITY]))


def test_fixed_pipeline_custom_sequence():
    p = FixedPipelinePolicy(FixedPipelineConfig(sequence=(A.MEASURE_SEC,)))
    assert p.choose_action(make_state(), make_belief(), make_actions()).action_type == A.MEASURE_SEC
    assert p.choose_action(make_state([A.MEASURE_SEC]), make_belief(), make_actions()).action_type == A.SELECT


@pytest.mark.parametrize("policy", [RandomPolicy(seed=0), FixedPipelinePolicy()])
def test_terminal_state_or_no_actions_raises(policy):
    with pytest.raises(PolicyError):
        policy.choose_action(make_state(terminal=True), make_belief(), make_actions())
    with pytest.raises(PolicyError):
        policy.choose_action(make_state(), make_belief(), ())


def test_policies_share_one_contract():
    import inspect
    sigs = set()
    for cls in (RandomPolicy, FixedPipelinePolicy):
        assert issubclass(cls, ScientificPolicy)
        sig = inspect.signature(cls.choose_action)
        sigs.add(tuple(sig.parameters))
    assert sigs == {("self", "state", "belief", "available_actions")}
    assert inspect.signature(ScientificPolicy.choose_action) == inspect.signature(RandomPolicy.choose_action)


def test_belief_summary_cannot_carry_extra_fields():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        make_belief(particles=[1.0])
