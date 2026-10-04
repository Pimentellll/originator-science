"""Deterministic contrast for the H0 aggregation-plus-kinetics showcase."""

from mirage.core import ActionType
from mirage.environments.binder import BinderWorldMode
from mirage.integration import CampaignController
from mirage.provenance import PublicRecordStore


def test_greedy_eig_showcase_takes_degrading_spr_first(tmp_path) -> None:
    controller = CampaignController(PublicRecordStore(tmp_path))
    controller.reset(9, BinderWorldMode.COMPOUND_FAILURE, policy_name="greedy_eig")
    outcome = controller.step()
    assert outcome.dto.event.action.action_type == ActionType.MEASURE_SPR
    assert outcome.dto.event.observation is not None and outcome.dto.event.observation.quality == "degraded"
    assert outcome.dto.state.resources.spr_instrument_health < 1.0
