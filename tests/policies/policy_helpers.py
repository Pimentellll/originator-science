from mirage.belief import BeliefSummary
from mirage.core.contracts import (
    ActionType as A,
    AgentState,
    Candidate,
    ResourceState,
    ScientificAction,
    ScientificObservation,
)

ASSAYS = [A.MEASURE_STABILITY, A.MEASURE_SEC, A.MEASURE_SPR, A.MEASURE_EPITOPE,
          A.MEASURE_DEVELOPABILITY, A.VALIDATE_ASSAY, A.ORTHOGONAL_FUNCTION]
REDESIGNS = [A.REDESIGN_STABILITY, A.REDESIGN_SOLUBILITY, A.REDESIGN_INTERFACE]
TERMINALS = [A.SELECT, A.REJECT, A.MODEL_INVALID, A.ABSTAIN]


def make_belief(**kw) -> BeliefSummary:
    base = dict(
        p_folding_failure=0.1, p_aggregation_failure=0.1, p_affinity_failure=0.1,
        p_kinetic_failure=0.1, p_epitope_failure=0.1, p_developability_failure=0.1,
        p_assay_invalid=0.1, p_model_invalid=0.1, posterior_entropy=1.0,
        continuous_means={"log_kd": -8.0}, continuous_variances={"log_kd": 1.0},
        effective_sample_size=512.0,
    )
    base.update(kw)
    return BeliefSummary(**base)


def make_state(done=(), cid="c0", terminal=False) -> AgentState:
    cand = Candidate(candidate_id=cid, generation=0)
    obs = tuple(ScientificObservation(action_type=a, candidate_id=cid) for a in done)
    return AgentState(
        active_candidate=cand, candidates=(cand,),
        resources=ResourceState(budget_remaining=10, sample_remaining=10, simulated_time=0, spr_instrument_health=1.0),
        observations=obs, terminal=terminal,
    )


def make_actions(types=None, cid="c0"):
    types = types or ASSAYS + REDESIGNS + TERMINALS
    return tuple(ScientificAction(action_type=t, candidate_id=cid) for t in types)
