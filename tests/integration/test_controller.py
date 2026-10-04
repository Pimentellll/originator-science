"""H0 end-to-end integration coverage."""

from types import SimpleNamespace

from mirage.belief.summary import BeliefSummary
from mirage.core import ActionType, ScientificAction
from mirage.environments.binder import BinderWorldMode
from mirage.integration import CampaignController, ScientificProfile
from mirage.integration.rescue_policy import ReceptorRescuePlannerPolicy
from mirage.provenance import PublicRecordStore, Replay


def test_receptor_rescue_controller_records_replays_and_evaluates(tmp_path) -> None:
    controller = CampaignController(PublicRecordStore(tmp_path))
    controller.reset(9, BinderWorldMode.COMPOUND_FAILURE, ScientificProfile.RECEPTOR_BINDER_RESCUE, "rescue_planner")
    actions = []
    for _ in range(6):
        outcome = controller.step()
        actions.append(outcome.dto.event.action.action_type)
        if outcome.terminal:
            break
    assert actions[:3] == [ActionType.MEASURE_SEC, ActionType.REDESIGN_SOLUBILITY, ActionType.MEASURE_SPR]
    record = controller.record()
    assert record.events[2].observation is not None and record.events[2].observation.quality == "nominal"
    assert record.events and (tmp_path / f"{record.episode_id}.jsonl").is_file()
    assert len(tuple(Replay(record))) == len(record.events)
    evaluation = controller.evaluate()
    assert evaluation.scenario_class == "COMPOUND_FAILURE"
    assert evaluation.regime == "path_dependent"


def test_controller_steps_only_with_public_dto_data(tmp_path) -> None:
    controller = CampaignController(PublicRecordStore(tmp_path))
    initial = controller.reset(2, policy_name="fixed_pipeline")
    outcome = controller.step()
    payload = outcome.dto.model_dump_json().lower()
    assert initial.active_candidate.candidate_id == "binder-000"
    assert "hidden" not in payload and "truth" not in payload and "world_mode" not in payload


def test_rescue_planner_does_not_repeat_validation_already_observed_on_any_candidate() -> None:
    state = SimpleNamespace(
        terminal=False,
        active_candidate=SimpleNamespace(candidate_id="binder-001", parent_candidate_id="binder-000"),
        observations=(
            SimpleNamespace(
                candidate_id="binder-000",
                action_type=ActionType.MEASURE_SEC,
                measurements={"monomer_fraction": 0.9},
            ),
            SimpleNamespace(candidate_id="binder-001", action_type=ActionType.MEASURE_SPR),
            SimpleNamespace(candidate_id="binder-000", action_type=ActionType.VALIDATE_ASSAY),
        ),
    )
    belief = BeliefSummary(
        p_folding_failure=0.0,
        p_aggregation_failure=0.0,
        p_affinity_failure=0.0,
        p_kinetic_failure=0.0,
        p_epitope_failure=0.0,
        p_developability_failure=0.0,
        p_assay_invalid=0.5,
        p_model_invalid=0.1,
        posterior_entropy=1.0,
        continuous_means={},
        continuous_variances={},
        effective_sample_size=256.0,
    )
    available = (
        ScientificAction(action_type=ActionType.VALIDATE_ASSAY, candidate_id="binder-001"),
        ScientificAction(action_type=ActionType.REJECT, candidate_id="binder-001"),
    )

    action = ReceptorRescuePlannerPolicy().choose_action(state, belief, available)

    assert action.action_type == ActionType.REJECT
