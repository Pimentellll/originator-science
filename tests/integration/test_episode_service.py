"""EpisodeService wiring for the executable Binder profile."""

from mirage.api import ActionRequest
from mirage.core import ActionType
from mirage.integration.controller import make_receptor_binder_service
from mirage.provenance import PublicRecordStore


def test_episode_service_wires_binder_belief_and_public_dtos(tmp_path) -> None:
    service = make_receptor_binder_service(PublicRecordStore(tmp_path))
    state = service.create(9, "fixed_pipeline")
    assert state.belief is not None and state.available_actions
    step = service.act(state.episode_id, ActionRequest(action_type=ActionType.MEASURE_SEC))
    assert step.event.observation is not None
    assert step.state.belief is not None
    assert "hidden" not in step.model_dump_json().lower()
