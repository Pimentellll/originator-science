"""Builds a public EpisodeRecord from live environment steps."""

from __future__ import annotations

from typing import Any

from mirage.core import AgentState, ScientificAction, StepResult
from mirage.provenance.compat import REDESIGN_ACTIONS
from mirage.provenance.events import (
    EpisodeRecord,
    PolicyMetadata,
    ScientificEvent,
    belief_to_payload,
)

CONTRACT_VERSION = "mirage.core/1"


class EpisodeRecorder:
    def __init__(
        self,
        *,
        episode_id: str,
        seed: int,
        initial_state: AgentState,
        policy: PolicyMetadata,
        environment_id: str,
        code_version: str,
        contract_version: str = CONTRACT_VERSION,
    ) -> None:
        self._header = {
            "episode_id": episode_id,
            "seed": seed,
            "initial_state": initial_state,
            "policy": policy,
            "environment_id": environment_id,
            "code_version": code_version,
            "contract_version": contract_version,
        }
        self._events: list[ScientificEvent] = []
        self._terminal: ScientificAction | None = None
        self._policy_name = policy.name

    @property
    def events(self) -> tuple[ScientificEvent, ...]:
        return tuple(self._events)

    @property
    def finished(self) -> bool:
        return self._terminal is not None

    def record_step(
        self,
        *,
        state_before: AgentState,
        action: ScientificAction,
        result: StepResult,
        belief_before: Any = None,
        belief_after: Any = None,
        rationale: str | None = None,
    ) -> ScientificEvent:
        if self._terminal is not None:
            raise ValueError("episode already terminated")
        candidate_id = action.candidate_id or state_before.active_candidate.candidate_id
        child = (
            result.state.active_candidate.candidate_id
            if action.action_type in REDESIGN_ACTIONS
            else None
        )
        event = ScientificEvent(
            episode_id=self._header["episode_id"],
            step=len(self._events),
            candidate_id=candidate_id,
            action=action,
            observation=result.observation,
            child_candidate_id=child,
            belief_before=belief_to_payload(belief_before),
            belief_after=belief_to_payload(belief_after),
            resources_before=state_before.resources,
            resources_after=result.state.resources,
            policy_name=self._policy_name,
            rationale=rationale,
        )
        self._events.append(event)
        if result.terminal:
            self._terminal = action
        return event

    def finish(self) -> EpisodeRecord:
        return EpisodeRecord(
            events=tuple(self._events), terminal_decision=self._terminal, **self._header
        )
