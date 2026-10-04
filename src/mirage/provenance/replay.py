"""Replay of stored public traces.

Consumes only an EpisodeRecord. It imports no environment, belief engine, PPO or LLM
module and draws no random numbers (G11).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict

from mirage.core import Candidate, ResourceState, ScientificAction, ScientificObservation
from mirage.provenance.events import EpisodeRecord, ScientificEvent
from mirage.provenance.validation import assert_valid_record


class ReplayFrame(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step: int
    action: ScientificAction
    observation: ScientificObservation | None
    belief: dict[str, Any] | None
    resources: ResourceState
    candidates: tuple[Candidate, ...]
    active_candidate_id: str
    terminal: bool
    policy_name: str
    rationale: str | None


class Replay:
    """Deterministic frame sequence derived from a stored record."""

    def __init__(self, record: EpisodeRecord, *, validate: bool = True) -> None:
        if validate:
            assert_valid_record(record)
        self.record = record
        self.frames: tuple[ReplayFrame, ...] = tuple(self._build(record))

    @staticmethod
    def _build(record: EpisodeRecord) -> Iterator[ReplayFrame]:
        candidates = list(record.initial_state.candidates)
        lineage = {c.candidate_id: c for c in candidates}
        active = record.initial_state.active_candidate.candidate_id
        for event in record.events:
            active = _apply(event, lineage, candidates, active)
            yield ReplayFrame(
                step=event.step,
                action=event.action,
                observation=event.observation,
                belief=event.belief_after,
                resources=event.resources_after,
                candidates=tuple(candidates),
                active_candidate_id=active,
                terminal=record.terminal_decision is not None
                and event.step == len(record.events) - 1,
                policy_name=event.policy_name,
                rationale=event.rationale,
            )

    def __len__(self) -> int:
        return len(self.frames)

    def __iter__(self) -> Iterator[ReplayFrame]:
        return iter(self.frames)

    def at(self, step: int) -> ReplayFrame:
        return self.frames[step]


def _apply(
    event: ScientificEvent,
    lineage: dict[str, Candidate],
    candidates: list[Candidate],
    active: str,
) -> str:
    if event.child_candidate_id is not None:
        parent = lineage[event.candidate_id]
        child = Candidate(
            candidate_id=event.child_candidate_id,
            generation=parent.generation + 1,
            parent_candidate_id=parent.candidate_id,
        )
        lineage[child.candidate_id] = child
        candidates.append(child)
        return child.candidate_id
    return event.candidate_id
