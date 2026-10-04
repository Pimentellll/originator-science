"""Structural interfaces for components owned by other workstreams.

They describe only what the controller/harness needs, so no belief, policy or training
module is imported (and none is duplicated)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from mirage.core import AgentState, ScientificAction, StepResult


class BeliefSession(Protocol):
    """Per-episode belief tracker; ``summary()`` returns a BeliefSummary-like object."""

    def summary(self) -> Any: ...

    def update(self, action: ScientificAction, result: StepResult) -> None: ...


BeliefFactory = Callable[[int, AgentState], BeliefSession]


class PolicyLike(Protocol):
    """The common public policy contract (BELIEF_AND_POLICY_CONTRACT)."""

    name: str

    def reset(self, seed: int | None = None) -> None: ...

    def choose_action(
        self, state: AgentState, belief: Any, available_actions: Sequence[ScientificAction]
    ) -> ScientificAction: ...
